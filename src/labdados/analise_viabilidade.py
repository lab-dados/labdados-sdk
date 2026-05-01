"""
Análise de viabilidade — estima volume de processos antes de uma raspagem.

Modo nuvem
----------
Cria pedido de ``consultoria-levantamento`` já aprovado, dispara a análise
no backend e baixa o relatório (PDF + MD) quando pronto.

Modo local
----------
Roda a **mesma** análise via ``labdados-core`` — núcleo compartilhado com
o backend, garantindo que a regra de veredito e o template do relatório
fiquem byte-equivalentes ao que o escritório gera. Sem o Quarto+Typst
no sistema, retorna apenas o markdown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from labdados._io import PathLike, ensure_output_dir
from labdados.client import Client
from labdados.exceptions import LocalDependencyMissing

ListagemTipo = Literal["datajud", "jurisprudencia", "sentencas"]


def analise_viabilidade(
    *,
    descricao: str,
    listagem: ListagemTipo,
    tribunais: list[str],
    saida: PathLike | None = None,
    api_key: str | None = None,
    palavras_chave: str = "",
    classes_cnj: list[str] | None = None,
    assuntos_cnj: list[str] | None = None,
    grau: list[str] | None = None,
    inicio: str | None = None,
    fim: str | None = None,
    notas: str = "",
    local: bool = False,
    client: Client | None = None,
    progress: bool = True,
) -> dict[str, Any]:
    """Estima o volume de processos antes de uma coleta.

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
        Pasta de saída (PDF + MD).
    api_key
        Chave de API (modo nuvem).
    palavras_chave
        Para ``listagem="jurisprudencia"`` ou ``"sentencas"``. Sintaxe
        depende do tribunal.
    classes_cnj, assuntos_cnj, grau
        Filtros do Datajud. Códigos numéricos do CNJ.
    inicio, fim
        Recorte temporal em ``"YYYY-MM-DD"`` (inclusivo). ``None`` = sem
        filtro temporal nesse extremo.
    notas
        Texto livre para o relatório.
    local
        Se ``True``, roda direto via ``labdados-core``
        (``pip install labdados[viabilidade]``).
    client
        Cliente reaproveitado (modo nuvem).
    progress
        Spinner no stderr.

    Returns
    -------
    dict
        ``{"results": ..., "report_pdf": Path | None, "report_md": Path | None,
        "request_id": str | None}``. ``request_id`` é populado no modo nuvem.

    Examples
    --------
    Modo nuvem para Datajud:

    >>> import labdados
    >>> ana = labdados.analise_viabilidade(
    ...     descricao="Ações de saúde suplementar contra planos de saúde — 2020 a 2025",
    ...     listagem="datajud",
    ...     tribunais=["tjsp", "tjrj", "tjmg"],
    ...     classes_cnj=["7"],
    ...     assuntos_cnj=["7780"],
    ...     inicio="2020-01-01",
    ...     fim="2025-12-31",
    ...     api_key="sk_lab_...",
    ...     saida="relatorios/",
    ... )
    >>> print(ana["results"]["verdict"])  # "viable" / "caveats" / "unviable"

    Modo local para jurisprudência:

    >>> ana = labdados.analise_viabilidade(
    ...     descricao="Decisões sobre nepotismo no STF",
    ...     listagem="jurisprudencia",
    ...     tribunais=["stf"],
    ...     palavras_chave="nepotismo",
    ...     local=True,
    ...     saida="relatorios/",
    ... )
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

    if local:
        return _viab_local(form, saida_dir=saida_dir, notas=notas, progress=progress)
    return _viab_remote(
        form,
        notas=notas,
        saida_dir=saida_dir,
        api_key=api_key,
        client=client,
        progress=progress,
    )


def _viab_remote(
    form: dict[str, Any],
    *,
    notas: str,
    saida_dir: Path,
    api_key: str | None,
    client: Client | None,
    progress: bool,
) -> dict[str, Any]:
    cli = client or Client(api_key=api_key, progress=progress)
    req = cli._post("/api/v1/viability", {"form": form, "notes": notas or None})
    final = cli._poll_viability(req["id"])
    analysis = final.get("analysis") or {}

    pdf_path: Path | None = None
    md_path: Path | None = None
    if analysis.get("report_pdf_path"):
        url = cli._get(f"/api/v1/viability/{req['id']}/report-url?format=pdf")["url"]
        pdf_path = cli._download(url, saida_dir / f"viabilidade_{req['id'][:8]}.pdf")
    if analysis.get("report_md_path"):
        url = cli._get(f"/api/v1/viability/{req['id']}/report-url?format=md")["url"]
        md_path = cli._download(url, saida_dir / f"viabilidade_{req['id'][:8]}.md")

    return {
        "request_id": req["id"],
        "results": analysis.get("results") or {},
        "report_pdf": pdf_path,
        "report_md": md_path,
    }


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
            "Análise local requer:\n    pip install labdados[viabilidade]"
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
        "request_id": None,
        "results": results,
        "report_pdf": pdf_path,
        "report_md": md_path,
    }
