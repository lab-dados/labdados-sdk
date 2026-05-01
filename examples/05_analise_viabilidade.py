"""Análise de viabilidade — Datajud, sempre local (sem API key).

A função ``labdados.analise_viabilidade`` consulta APIs públicas
diretamente do seu computador. Requer ``pip install labdados[viabilidade]``;
para gerar o PDF, instale também o Quarto + Typst do sistema.

Códigos de classes/assuntos vêm da TPU do CNJ — ver listas completas
no [abjur/tpur](https://github.com/abjur/tpur).

    python examples/05_analise_viabilidade.py
"""

import labdados


def main() -> None:
    ana = labdados.analise_viabilidade(
        descricao="Ações contra planos de saúde — TJSP, 2020-2024",
        listagem="datajud",
        tribunais=["tjsp", "tjrj", "tjmg"],
        # Códigos da TPU CNJ (assuntos):
        #   11884 = Fornecimento de Medicamentos
        #   14759 = Tratamento Domiciliar (Home Care)
        assuntos_cnj=["11884", "14759"],
        inicio="2020-01-01",
        fim="2024-12-31",
        saida="relatorios/",
        notas="Pesquisa para tese de doutorado em direito civil (FGV/SP).",
    )
    print("Veredito:", ana["results"].get("verdict"))
    print("Total aproximado:", ana["results"].get("total_aproximado"))
    print("Relatório PDF:", ana["report_pdf"])


if __name__ == "__main__":
    main()
