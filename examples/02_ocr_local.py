"""OCR local — sem API key. Requer ``pip install labdados[ocr]`` + Tesseract.

    python examples/02_ocr_local.py arquivo.pdf [outro.pdf ...]
"""

import sys

import labdados


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python 02_ocr_local.py <pdf> [<pdf>...]")
    saida = labdados.ocr(
        arquivos=sys.argv[1:],
        local=True,
        idiomas="por+eng",
        formato="md",
        saida="resultados_ocr_local/",
        deskew=True,
    )
    print(f"Pronto. Resultado em {saida}/")


if __name__ == "__main__":
    main()
