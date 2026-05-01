"""
OCR de PDFs — extrai texto de PDFs nativos ou escaneados.

Modo nuvem (default)
--------------------
Faz upload dos PDFs, dispara o OCR no escritório (PyMuPDF+Tesseract ou
PaddleOCR), espera concluir e baixa o resultado (.zip) na pasta ``saida``.

Modo local (``local=True``)
---------------------------
Roda PyMuPDF + pytesseract direto na máquina. Precisa do Tesseract
instalado no OS e do extra ``pip install labdados[ocr]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

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
        Chave de API (apenas para modo nuvem). Peça uma em
        https://escritorio.labdados.fgv.br/consultoria/api-key.
    modelo
        ``"pymupdf-tesseract"`` (default — leve, CPU) ou ``"paddleocr"``
        (mais preciso em layouts complexos, GPU).
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

    Modo local com PaddleOCR (off — só nuvem para Paddle):

    >>> labdados.ocr(arquivos=["a.pdf", "b.pdf"], local=True)
    """
    pdfs = resolve_inputs(arquivos, extensoes=ACCEPTED_EXTENSIONS)
    saida_dir = ensure_output_dir(saida)

    if local:
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
    config: dict[str, Any] = {
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
# Local
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
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise LocalDependencyMissing(
            "OCR local requer extras opcionais. Instale com:\n"
            "    pip install labdados[ocr]\n"
            "Em seguida, instale o binário do Tesseract no seu sistema "
            "(https://tesseract-ocr.github.io)."
        ) from exc

    from io import BytesIO

    from labdados._progress import clear_status, render_status

    for i, pdf in enumerate(pdfs, start=1):
        if progress:
            render_status(f"OCR local {i}/{len(pdfs)}: {pdf.name}", frame=i)
        text_chunks: list[str] = []
        with fitz.open(pdf) as doc:
            for page in doc:
                # Tenta texto nativo primeiro — se a página é PDF de texto,
                # economiza o OCR.
                native = page.get_text("text")
                if native and native.strip():
                    text_chunks.append(native)
                    continue
                pix = page.get_pixmap(dpi=dpi)
                img = Image.open(BytesIO(pix.tobytes("png")))
                if deskew:
                    img = _deskew(img)
                ocr_text = pytesseract.image_to_string(img, lang=idiomas)
                text_chunks.append(ocr_text)
        ext = "md" if formato == "md" else "txt"
        out_path = saida_dir / f"{pdf.stem}.{ext}"
        out_path.write_text("\n\n".join(text_chunks), encoding="utf-8")
    if progress:
        clear_status()
    return saida_dir


def _deskew(img: Any) -> Any:
    """Deskew leve baseado em PIL — não tão sofisticado quanto opencv,
    mas evita uma dependência pesada. Se Pillow falhar, devolve a imagem
    original."""
    try:
        from PIL import ImageOps

        return ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001
        return img
