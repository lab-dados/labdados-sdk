"""Estruturação de uma planilha de ementas em colunas JSON — modo nuvem.

    python examples/04_estruturacao_csv.py ementas.csv ementa
"""

import os
import sys

import labdados

SCHEMA = {
    "type": "object",
    "properties": {
        "tribunal": {"type": "string", "description": "Sigla do tribunal (TJSP, STJ, ...)"},
        "ano": {"type": "integer"},
        "tema": {"type": "string", "description": "Direito do consumidor, família, ..."},
        "procedente": {
            "type": "boolean",
            "description": "Se o pedido principal foi julgado procedente",
        },
    },
    "required": ["tribunal", "ano", "tema"],
}


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("uso: python 04_estruturacao_csv.py <csv> <coluna_texto>")
    csv_path = sys.argv[1]
    coluna = sys.argv[2]

    labdados.estruturacao(
        arquivos=csv_path,
        coluna_texto=coluna,
        schema=SCHEMA,
        prompt_sistema=(
            "Você está extraindo metadados de ementas de acórdãos brasileiros. "
            "Se o tema não for claro, use 'desconhecido'. Retorne JSON puro."
        ),
        api_key=os.environ["LABDADOS_API_KEY"],
        saida="extraido/",
        modelo="gpt-4.1-mini",
    )


if __name__ == "__main__":
    main()
