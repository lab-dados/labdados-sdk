"""OCR de uma pasta inteira de PDFs no modo nuvem.

Pré-requisito: ``LABDADOS_API_KEY`` no ambiente.

    python examples/01_ocr_pasta_nuvem.py ./acordaos
"""

import os
import sys

import labdados


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python 01_ocr_pasta_nuvem.py <pasta_com_pdfs>")
    pasta = sys.argv[1]
    api_key = os.environ.get("LABDADOS_API_KEY")
    if not api_key:
        sys.exit("Defina LABDADOS_API_KEY no ambiente (peça em https://labdados-frontend.livelydesert-3e3e3dd8.brazilsouth.azurecontainerapps.io/consultoria/api-key)")

    saida = labdados.ocr(
        arquivos=pasta,
        api_key=api_key,
        saida="resultados_ocr/",
        formato="md",
        idiomas="por",
    )
    print(f"Pronto. Resultado em {saida}/")


if __name__ == "__main__":
    main()
