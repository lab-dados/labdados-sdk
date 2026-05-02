"""OCR de PDFs — extrai texto de PDFs nativos ou escaneados.

Modo nuvem (default)
--------------------
Faz upload dos PDFs, dispara o OCR no escritório (PyMuPDF+Tesseract ou
PaddleOCR), espera concluir e baixa o resultado (.zip) na pasta ``saida``.

Modo local (``local=True``)
---------------------------
Roda PyMuPDF + pytesseract direto na máquina via
``labdados_core.ocr`` — mesmo pipeline que o serviço no escritório
usa, sem chance de divergir em deskew, fallback BW ou descoberta do
binário do Tesseract.

Precisa do extra ``pip install labdados[ocr]`` e do binário do
Tesseract instalado no OS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from labdados._io import PathLike, ensure_output_dir, resolve_inputs
from labdados.client import Client
from labdados.exceptions import LocalDependencyMissing

OUTPUT_FORMAT = Literal["txt", "md"]
MODELO_NUVEM = Literal["pymupdf-tesseract", "paddleocr"]
ACCEPTED_EXTENSIONS = (".pdf",)


def ocr(
    arquivos: PathLike | list[PathLike],
    *,
    saida: PathLike | None = None,
    api_key: str | None = None,
    modelo: str = "pymupdf-tesseract",
    formato: OUTPUT_FORMAT = "txt",
    idiomas: str = "por+eng",
    dpi: int = 200,
    deskew: bool = False,
    local: bool = False,
    client: Client | None = None,
    progress: bool = True,
) -> Path:
    """Extrai texto de PDFs.

    Parameters
    ----------
    arquivos
        Pode ser um arquivo único, uma lista de arquivos ou uma pasta. No
        caso da pasta, varre recursivamente todos os ``.pdf``.
    saida
        Diretório onde o resultado é salvo. Default: ``./resultados_labdados/``.
        No modo nuvem, baixa o ``.zip`` retornado pelo serviço; no modo
        local, escreve um arquivo de texto por PDF processado.
    api_key
        Chave de API (apenas para modo nuvem). Peça uma no portal,
        em ``/consultoria/api-key``.
    modelo
        ``"pymupdf-tesseract"`` (default — leve, CPU) ou ``"paddleocr"``
        (mais preciso em layouts complexos, GPU). PaddleOCR só está
        disponível no modo nuvem.
    formato
        Formato do texto extraído: ``"txt"`` (default) ou ``"md"``.
    idiomas
        Códigos ISO 639-2 separados por ``+`` (padrão Tesseract). Ex.:
        ``"por+eng"``, ``"por+spa"``, ``"chi_sim+eng"``.
    dpi
        Resolução de renderização das páginas. 150/200/300.
    deskew
        Endireita páginas tortas antes do OCR. Útil em scans tortos.
    local
        Se ``True``, processa no próprio computador (exige
        ``pip install labdados[ocr]`` e Tesseract instalado no OS).
    client
        Reaproveita um :class:`labdados.Client` existente. Quando passado,
        o ``api_key`` daqui é ignorado.
    progress
        Mostra spinner no stderr enquanto processa.

    Returns
    -------
    Path
        Caminho do diretório de saída (criado se preciso).

    Examples
    --------
    Modo nuvem, pasta inteira:

    >>> import labdados
    >>> labdados.ocr(arquivos="meus_pdfs/", api_key="sk_lab_...", saida="resultados/")

    Modo local:

    >>> labdados.ocr(arquivos=["a.pdf", "b.pdf"], local=True)
    """
    pdfs = resolve_inputs(arquivos, extensoes=ACCEPTED_EXTENSIONS)
    saida_dir = ensure_output_dir(saida)

    if local:
        if modelo != "pymupdf-tesseract":
            raise ValueError(
                "No modo local, OCR suporta apenas modelo='pymupdf-tesseract'. "
                "Use local=False para modelo='paddleocr'."
            )
        return _ocr_local(
            pdfs,
            saida_dir=saida_dir,
            formato=formato,
            idiomas=idiomas,
            dpi=dpi,
            deskew=deskew,
            progress=progress,
        )
    return _ocr_remote(
        pdfs,
        saida_dir=saida_dir,
        api_key=api_key,
        client=client,
        modelo=modelo,
        formato=formato,
        idiomas=idiomas,
        dpi=dpi,
        deskew=deskew,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Nuvem
# ---------------------------------------------------------------------------


def _ocr_remote(
    pdfs: list[Path],
    *,
    saida_dir: Path,
    api_key: str | None,
    client: Client | None,
    modelo: str,
    formato: str,
    idiomas: str,
    dpi: int,
    deskew: bool,
    progress: bool,
) -> Path:
    cli = client or Client(api_key=api_key, progress=progress)
    files_meta = cli._upload_files("ocr", pdfs)
    config: dict = {
        "output_format": formato,
        "languages": idiomas,
        "dpi": dpi,
        "deskew": deskew,
    }
    req = cli._post(
        "/api/v1/requests",
        {
            "service_id": "ocr",
            "model_id": modelo,
            "config": config,
            "files_metadata": files_meta,
        },
    )
    final = cli._poll_request(req["id"], label="OCR no escritório")
    cli._download(final["result_url"], saida_dir / f"ocr_{req['id'][:8]}.zip")
    return saida_dir


# ---------------------------------------------------------------------------
# Local — delega a labdados_core.ocr
# ---------------------------------------------------------------------------


def _ocr_local(
    pdfs: list[Path],
    *,
    saida_dir: Path,
    formato: str,
    idiomas: str,
    dpi: int,
    deskew: bool,
    progress: bool,
) -> Path:
    try:
        from labdados_core.ocr import (
            EngineUnavailable,
            TesseractNotFound,
            extract,
            join_pages,
        )
    except ImportError as exc:
        raise LocalDependencyMissing(
            "OCR local requer extras opcionais. Instale com:\n"
            "    pip install labdados[ocr]"
        ) from exc

    from labdados._progress import clear_status, render_status

    for i, pdf in enumerate(pdfs, start=1):
        if progress:
            render_status(f"OCR local {i}/{len(pdfs)}: {pdf.name}", frame=i)
        try:
            pages = extract(
                pdf,
                modelo="pymupdf-tesseract",
                languages=idiomas,
                dpi=dpi,
                deskew=deskew,
            )
        except EngineUnavailable as exc:
            raise LocalDependencyMissing(str(exc)) from exc
        except TesseractNotFound as exc:
            raise LocalDependencyMissing(str(exc)) from exc

        text = join_pages(pages, output_format="md" if formato == "md" else "txt")
        ext = "md" if formato == "md" else "txt"
        out_path = saida_dir / f"{pdf.stem}.{ext}"
        out_path.write_text(text, encoding="utf-8")

    if progress:
        clear_status()
    return saida_dir
