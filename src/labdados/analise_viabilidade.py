"""
Análise de viabilidade — estima volume de processos antes de uma raspagem.

Roda **sempre local** (no próprio computador do usuário): a análise
consulta APIs públicas (Datajud do CNJ + bancos de jurisprudência via
juscraper), constrói o JSON de resultados e renderiza o relatório
PDF/MD via Quarto. Sem dependência da infra nuvem do escritório, sem
API key, sem cota.

A lógica vive em ``labdados-core`` — mesmo núcleo que o admin do
escritório usa quando aprova um pedido de consultoria-levantamento via
UI. Garantia de paridade: o veredito e o template são byte-equivalentes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from labdados._io import PathLike, ensure_output_dir
from labdados.exceptions import LocalDependencyMissing

ListagemTipo = Literal["datajud", "jurisprudencia", "sentencas"]


def analise_viabilidade(
    *,
    descricao: str,
    listagem: ListagemTipo,
    tribunais: list[str],
    saida: PathLike | None = None,
    palavras_chave: str = "",
    classes_cnj: list[str] | None = None,
    assuntos_cnj: list[str] | None = None,
    grau: list[str] | None = None,
    inicio: str | None = None,
    fim: str | None = None,
    notas: str = "",
    progress: bool = True,
) -> dict[str, Any]:
    """Estima o volume de processos antes de uma coleta — sempre local.

    Esta função **não tem modo nuvem**: a análise é leve (consulta APIs
    públicas como Datajud e juscraper, sem GPU nem dados sigilosos), e
    rodar local elimina latência de fila do escritório, custo de
    infraestrutura e cota de API key. Requer apenas
    ``pip install labdados[viabilidade]`` e — opcionalmente — o
    [Quarto](https://quarto.org) + Typst para o relatório PDF.

    Parameters
    ----------
    descricao
        Descrição da pesquisa em uma frase. Vai pro relatório.
    listagem
        Fonte da listagem:

        - ``"datajud"``: API pública do CNJ (estudos prospectivos).
          Permite filtrar por classe, assunto, grau, datas.
        - ``"jurisprudencia"``: bancos de acórdãos (2º grau). Filtra por
          palavras-chave + datas.
        - ``"sentencas"``: bancos de sentenças (1º grau). Disponibilidade
          varia por tribunal.
    tribunais
        Códigos dos tribunais (``"tjsp"``, ``"tjrj"``, ``"trf3"``, ...).
    saida
        Pasta de saída (PDF + MD + JSON com os resultados).
    palavras_chave
        Para ``listagem="jurisprudencia"`` ou ``"sentencas"``. Sintaxe
        depende do tribunal.
    classes_cnj, assuntos_cnj, grau
        Filtros do Datajud. Códigos numéricos da TPU do CNJ — listas
        completas em [abjur/tpur](https://github.com/abjur/tpur).
    inicio, fim
        Recorte temporal em ``"YYYY-MM-DD"`` (inclusivo). ``None`` = sem
        filtro temporal nesse extremo.
    notas
        Texto livre para o relatório.
    progress
        Spinner no stderr.

    Returns
    -------
    dict
        ``{"results": ..., "report_pdf": Path | None, "report_md": Path | None}``.

    Examples
    --------
    Datajud — Tratamento Domiciliar (Home Care) e Fornecimento de
    Medicamentos no TJSP, 2020 a 2024:

    >>> import labdados
    >>> ana = labdados.analise_viabilidade(
    ...     descricao="Acoes contra planos de saude — TJSP, 2020-2024",
    ...     listagem="datajud",
    ...     tribunais=["tjsp"],
    ...     assuntos_cnj=["11884", "14759"],   # Medicamentos + Home Care
    ...     inicio="2020-01-01",
    ...     fim="2024-12-31",
    ...     saida="relatorios/",
    ... )
    >>> print(ana["results"]["verdict"])
    """
    saida_dir = ensure_output_dir(saida)
    form: dict[str, Any] = {
        "listagem": listagem,
        "descricao_pesquisa": descricao,
        "tribunais_selecionados": [t.lower() for t in tribunais],
        "filtro_palavras_chave": palavras_chave,
        "filtro_classes_cnj": "\n".join(classes_cnj or []),
        "filtro_assuntos_cnj": "\n".join(assuntos_cnj or []),
        "filtro_grau": grau or [],
        "recorte_inicio": inicio or "",
        "recorte_fim": fim or "",
    }
    return _viab_local(form, saida_dir=saida_dir, notas=notas, progress=progress)


def _viab_local(
    form: dict[str, Any],
    *,
    saida_dir: Path,
    notas: str,
    progress: bool,
) -> dict[str, Any]:
    """Roda a análise via ``labdados-core``. Mesmo template, mesmas regras
    de veredito que o escritório usa em produção."""
    try:
        from labdados_core.viabilidade import analyze_form, render_report
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Análise de viabilidade requer:\n    pip install labdados[viabilidade]"
        ) from exc

    from labdados._progress import clear_status, render_status

    if progress:
        render_status("consultando tribunais...", frame=0)
    results = analyze_form(form)
    if progress:
        clear_status()

    request_meta = {
        "researcher_name": "(modo local)",
        "institution": "(modo local)",
        "email": "",
        "created_at": None,
    }

    pdf_path: Path | None = None
    md_path: Path | None = None
    rendered = render_report(
        request_id="local",
        form=form,
        results=results,
        request_meta=request_meta,
    )
    if rendered is not None:
        pdf_bytes, md_bytes = rendered
        if md_bytes:
            md_path = saida_dir / "viabilidade_relatorio.md"
            md_path.write_bytes(md_bytes)
        if pdf_bytes:
            pdf_path = saida_dir / "viabilidade_relatorio.pdf"
            pdf_path.write_bytes(pdf_bytes)

    # Sempre escreve o JSON pra o usuário ter algo navegável mesmo sem PDF.
    (saida_dir / "viabilidade_resultados.json").write_text(
        json.dumps(
            {"form": form, "results": results, "notas": notas},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "results": results,
        "report_pdf": pdf_path,
        "report_md": md_path,
    }
