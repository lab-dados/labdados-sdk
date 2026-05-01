"""Análise de viabilidade rodando localmente — sem API key.

Requer ``pip install labdados[viabilidade]``. Para o PDF, instale também
o Quarto (https://quarto.org).

    python examples/06_analise_viabilidade_local.py
"""

import labdados


def main() -> None:
    ana = labdados.analise_viabilidade(
        descricao="Decisões do TJSP sobre direito de família (2020–2024)",
        listagem="datajud",
        tribunais=["tjsp"],
        classes_cnj=["7"],
        inicio="2020-01-01",
        fim="2024-12-31",
        local=True,
        saida="relatorios_local/",
    )
    print("Veredito:", ana["results"].get("verdict"))
    print("PDF:", ana["report_pdf"])
    print("MD:", ana["report_md"])


if __name__ == "__main__":
    main()
