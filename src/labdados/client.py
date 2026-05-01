"""
Cliente HTTP do SDK — encapsula host, API key, retries e helpers de
upload/download. Usado tanto pelo modo nuvem das funções de alto nível
quanto diretamente quando o usuário prefere a API ``client.ocr(...)``.
"""

from __future__ import annotations

import mimetypes
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

from labdados._progress import clear_status, render_status
from labdados.exceptions import (
    ApiKeyError,
    LabdadosError,
    ProcessingFailed,
    UploadError,
)

DEFAULT_BASE_URL = "https://escritorio.labdados.fgv.br"
DEFAULT_TIMEOUT = 60.0
DEFAULT_POLL_INTERVAL = 5.0
# Timeout total esperando o worker terminar. 4h cobre transcrição de áudios
# longos em CPU; OCR/estruturação terminam muito antes.
DEFAULT_POLL_TIMEOUT = 4 * 3600


class Client:
    """Cliente HTTP do escritório de apoio do LabDados.

    Parameters
    ----------
    api_key
        Chave gerada pelo escritório. Solicite em
        ``https://escritorio.labdados.fgv.br/consultoria/api-key``.
    base_url
        URL do backend. Default: produção do escritório.
    timeout
        Timeout (em segundos) para cada request HTTP. Não confunda com o
        ``poll_timeout``, que é o tempo total esperando o resultado.
    poll_interval
        Intervalo entre polls quando aguardando processamento.
    poll_timeout
        Tempo máximo total esperando o processamento. Default: 4 horas.
    progress
        Se ``True`` (default), imprime spinner/status no stderr enquanto
        aguarda. Use ``False`` em scripts não interativos.

    Examples
    --------
    >>> import labdados
    >>> client = labdados.Client(api_key="sk_lab_xxx")
    >>> client.ocr(arquivos="pdfs/", saida="out/")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
        progress: bool = True,
    ) -> None:
        if api_key is not None and not api_key.strip():
            raise ApiKeyError("api_key não pode ser vazia")
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.progress = progress

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ApiKeyError(
                "Operação no modo nuvem exige uma API key. Peça uma em "
                "https://escritorio.labdados.fgv.br/consultoria/api-key — ou "
                "use o modo local com `local=True`."
            )
        return {
            "X-API-Key": self.api_key,
            "User-Agent": "labdados-sdk-python",
        }

    def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as h:
                r = h.post(url, json=json, headers=self._headers())
        except httpx.HTTPError as exc:  # noqa: PERF203
            raise LabdadosError(f"Falha de rede em POST {path}: {exc}") from exc
        return _json_or_raise(r)

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as h:
                r = h.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise LabdadosError(f"Falha de rede em GET {path}: {exc}") from exc
        return _json_or_raise(r)

    # ------------------------------------------------------------------
    # whoami / health
    # ------------------------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        """Confirma que a API key é válida. Retorna metadados da chave."""
        return self._get("/api/v1/whoami")

    # ------------------------------------------------------------------
    # Upload via SAS URL
    # ------------------------------------------------------------------

    def _upload_files(
        self,
        service_id: str,
        paths: Iterable[Path],
    ) -> list[dict[str, Any]]:
        """Faz upload de cada arquivo via SAS URL e devolve metadata.

        Cada item da lista resultante tem o formato esperado por
        ``POST /api/v1/requests``: ``name``, ``size_bytes``, ``blob_path``,
        ``content_type``.
        """
        out: list[dict[str, Any]] = []
        paths_list = list(paths)
        for i, path in enumerate(paths_list, start=1):
            if self.progress:
                render_status(f"upload {i}/{len(paths_list)}: {path.name}", frame=i)

            ctype, _ = mimetypes.guess_type(path.name)
            sas = self._post(
                "/api/v1/uploads/sas",
                {
                    "filename": path.name,
                    "content_type": ctype,
                    "service_id": service_id,
                },
            )
            try:
                with httpx.Client(timeout=self.timeout * 5) as h:  # uploads são maiores
                    with path.open("rb") as f:
                        headers = {"x-ms-blob-type": "BlockBlob"}
                        if ctype:
                            headers["x-ms-blob-content-type"] = ctype
                        resp = h.put(sas["upload_url"], content=f.read(), headers=headers)
                        if resp.status_code >= 400:
                            raise UploadError(
                                f"Upload de {path.name} falhou: "
                                f"{resp.status_code} {resp.text[:200]}"
                            )
            except httpx.HTTPError as exc:
                raise UploadError(f"Falha de rede no upload de {path.name}: {exc}") from exc

            out.append(
                {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "blob_path": sas["blob_path"],
                    "content_type": ctype,
                }
            )
        if self.progress:
            clear_status()
        return out

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _poll_request(self, request_id: str, *, label: str = "processando") -> dict[str, Any]:
        """Aguarda o pedido sair de PENDING/APPROVED/RUNNING e devolve a row final.

        Levanta :class:`ProcessingFailed` se acabar em FAILED ou REJECTED.
        """
        deadline = time.time() + self.poll_timeout
        frame = 0
        last_status = ""
        while time.time() < deadline:
            data = self._get(f"/api/v1/requests/{request_id}")
            status = data.get("status", "")
            if status != last_status:
                last_status = status
            if self.progress:
                render_status(f"{label} ({status.lower()})", frame=frame)
                frame += 1
            if status == "COMPLETED":
                if self.progress:
                    clear_status()
                return data
            if status == "FAILED":
                if self.progress:
                    clear_status()
                raise ProcessingFailed(
                    data.get("error_message") or "Processamento falhou",
                    request_id=request_id,
                )
            if status == "REJECTED":
                if self.progress:
                    clear_status()
                raise ProcessingFailed(
                    "Pedido rejeitado pelo escritório (não deveria acontecer via SDK).",
                    request_id=request_id,
                )
            time.sleep(self.poll_interval)
        if self.progress:
            clear_status()
        raise ProcessingFailed(
            f"Timeout ({self.poll_timeout}s) esperando o resultado.",
            request_id=request_id,
        )

    def _poll_viability(self, request_id: str) -> dict[str, Any]:
        """Aguarda ``analysis.status`` virar ``completed`` ou ``failed``."""
        deadline = time.time() + self.poll_timeout
        frame = 0
        while time.time() < deadline:
            data = self._get(f"/api/v1/viability/{request_id}")
            analysis = data.get("analysis") or {}
            ana_status = analysis.get("status", "")
            if self.progress:
                render_status(
                    f"análise de viabilidade ({ana_status or 'aguardando'})",
                    frame=frame,
                )
                frame += 1
            if ana_status == "completed":
                if self.progress:
                    clear_status()
                return data
            if ana_status == "failed":
                if self.progress:
                    clear_status()
                raise ProcessingFailed(
                    analysis.get("error") or "Análise falhou",
                    request_id=request_id,
                )
            time.sleep(self.poll_interval)
        if self.progress:
            clear_status()
        raise ProcessingFailed(
            f"Timeout ({self.poll_timeout}s) esperando a análise.",
            request_id=request_id,
        )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download(self, url: str, dest: Path) -> Path:
        """Baixa o arquivo da SAS URL para ``dest``. Retorna o path final."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(timeout=self.timeout * 5) as h:
                with h.stream("GET", url) as resp:
                    if resp.status_code >= 400:
                        raise LabdadosError(
                            f"Download falhou: {resp.status_code} — talvez SAS expirou."
                        )
                    with dest.open("wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                            f.write(chunk)
        except httpx.HTTPError as exc:
            raise LabdadosError(f"Falha de rede no download: {exc}") from exc
        return dest

    # ------------------------------------------------------------------
    # Service-level shortcuts (lazy delegation)
    # ------------------------------------------------------------------
    # Os métodos abaixo são wrappers convenientes pra usar
    # ``client.ocr(...)`` em vez de ``labdados.ocr(..., api_key=client.api_key)``.

    def ocr(self, **kwargs: Any) -> Any:
        from labdados.ocr import ocr as _f

        kwargs.setdefault("client", self)
        return _f(**kwargs)

    def transcricao(self, **kwargs: Any) -> Any:
        from labdados.transcricao import transcricao as _f

        kwargs.setdefault("client", self)
        return _f(**kwargs)

    def estruturacao(self, **kwargs: Any) -> Any:
        from labdados.estruturacao import estruturacao as _f

        kwargs.setdefault("client", self)
        return _f(**kwargs)

    def analise_viabilidade(self, **kwargs: Any) -> Any:
        from labdados.analise_viabilidade import analise_viabilidade as _f

        kwargs.setdefault("client", self)
        return _f(**kwargs)


def _json_or_raise(r: httpx.Response) -> dict[str, Any]:
    if r.status_code == 401:
        raise ApiKeyError("API key inválida ou ausente (HTTP 401).")
    if r.status_code == 403:
        raise ApiKeyError("API key revogada (HTTP 403).")
    if r.status_code >= 400:
        # Tenta extrair detalhe do FastAPI (``{"detail": "..."}``)
        detail: str
        try:
            detail = str(r.json().get("detail") or r.text)
        except Exception:  # noqa: BLE001
            detail = r.text
        raise LabdadosError(f"HTTP {r.status_code}: {detail[:500]}")
    return r.json()
