"""Análise de viabilidade — Datajud, modo nuvem.

    python examples/05_analise_viabilidade.py
"""

import os

import labdados


def main() -> None:
    ana = labdados.analise_viabilidade(
        descricao="Ações sobre planos de saúde — TJSP / TJRJ / TJMG (2020–2024)",
        listagem="datajud",
        tribunais=["tjsp", "tjrj", "tjmg"],
        classes_cnj=["7"],            # Procedimento Comum Cível
        assuntos_cnj=["7780"],        # Saúde Suplementar
        inicio="2020-01-01",
        fim="2024-12-31",
        api_key=os.environ["LABDADOS_API_KEY"],
        saida="relatorios/",
        notas="Pesquisa para a tese de doutorado em direito civil (FGV/SP).",
    )
    print("Veredito:", ana["results"].get("verdict"))
    print("Total aproximado:", ana["results"].get("total_aproximado"))
    print("Relatório PDF:", ana["report_pdf"])


if __name__ == "__main__":
    main()
