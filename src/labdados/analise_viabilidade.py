"""
Análise de viabilidade — estima volume de processos e gera relatório PDF/MD
antes de uma raspagem em tribunais brasileiros.

Modo nuvem
----------
Cria pedido de ``consultoria-levantamento`` já aprovado, dispara a análise
no backend e baixa o relatório (PDF + MD) quando pronto.

Modo local
----------
Roda a mesma análise (via ``juscraper`` para tribunais e Datajud do CNJ),
gera o JSON com contagens e — se Quarto + Typst estão instalados no
sistema — renderiza o relatório local. Caso contrário, retorna apenas o
JSON com os resultados.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

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
        Recorte temporal (``"YYYY-MM-DD"``). Vazio = sem filtro de datas.
    notas
        Texto livre para o relatório.
    local
        Se ``True``, roda direto via ``juscraper`` (extra
        ``pip install labdados[viabilidade]``).
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
    ...     classes_cnj=["7"],  # Procedimento Comum Cível
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
    """Reproduz o pipeline do backend localmente (Datajud direto + juscraper).

    Por design, segue o mesmo formato de saída para que o relatório local
    seja indistinguível do gerado pelo escritório.
    """
    try:
        # juscraper só é necessário para listagem != datajud, mas validamos
        # o extra cedo pra dar mensagem coerente.
        import juscraper as _juscraper  # noqa: F401
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Análise local requer:\n    pip install labdados[viabilidade]"
        ) from exc

    from labdados._progress import clear_status, render_status

    if progress:
        render_status("consultando tribunais...", frame=0)
    results = _analyze_form(form)
    if progress:
        clear_status()

    pdf_path, md_path = _try_render_local_report(form, results, saida_dir, notas)
    # Sempre escreve o JSON pra que o usuário tenha algo navegável
    # mesmo quando o Quarto não está disponível.
    (saida_dir / "viabilidade_resultados.json").write_text(
        json.dumps({"form": form, "results": results, "notas": notas}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "request_id": None,
        "results": results,
        "report_pdf": pdf_path,
        "report_md": md_path,
    }


# ---------------------------------------------------------------------------
# Análise — port direto do backend (mesmas regras de viabilidade)
# ---------------------------------------------------------------------------

_DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"
_DATAJUD_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="


def _datajud_alias(tribunal_code: str) -> str:
    return f"api_publica_{tribunal_code.lower()}"


def _extract_digits(s: str) -> str:
    return "".join(c for c in str(s) if c.isdigit())


def _datajud_count(
    code: str,
    inicio: str | None,
    fim: str | None,
    classes: list[str] | None,
    assuntos: list[str] | None,
) -> dict[str, Any]:
    must: list[dict[str, Any]] = []
    if inicio or fim:
        rng: dict[str, str] = {}
        if inicio:
            rng["gte"] = f"{inicio}T00:00:00.000Z"
        if fim:
            rng["lte"] = f"{fim}T23:59:59.999Z"
        must.append({"range": {"dataAjuizamento": rng}})
    if classes:
        codes = [_extract_digits(c) for c in classes if _extract_digits(c)]
        if codes:
            must.append({"terms": {"classe.codigo": codes}})
    if assuntos:
        codes = [_extract_digits(a) for a in assuntos if _extract_digits(a)]
        if codes:
            must.append({"terms": {"assuntos.codigo": codes}})
    payload = {
        "size": 0,
        "track_total_hits": True,
        "query": {"bool": {"must": must}} if must else {"match_all": {}},
    }
    url = f"{_DATAJUD_BASE}/{_datajud_alias(code)}/_search"
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"APIKey {_DATAJUD_KEY}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("hits", {}).get("total", {})
        return {
            "code": code,
            "count": int(total.get("value") or 0),
            "relation": total.get("relation", "eq"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"code": code, "error": str(exc)[:200]}


def _juscraper_count(method: str, code: str, pesquisa: str) -> dict[str, Any]:
    try:
        import juscraper

        scraper = juscraper.scraper(code.lower())
        scraper.set_verbose(0)
        df = getattr(scraper, method)(pesquisa=pesquisa, paginas=1)
        return {"code": code, "count": int(len(df)), "relation": "first_page"}
    except Exception as exc:  # noqa: BLE001
        return {"code": code, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _split_lines(raw: Any) -> list[str]:
    if not raw:
        return []
    return [line.strip() for line in str(raw).replace(",", "\n").splitlines() if line.strip()]


def _analyze_form(form: dict[str, Any]) -> dict[str, Any]:
    listagem = str(form.get("listagem") or "")
    tribunais = [str(t).lower() for t in (form.get("tribunais_selecionados") or [])]
    inicio = (form.get("recorte_inicio") or None) or None
    fim = (form.get("recorte_fim") or None) or None

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    if listagem == "datajud":
        classes = _split_lines(form.get("filtro_classes_cnj"))
        assuntos = _split_lines(form.get("filtro_assuntos_cnj"))
        for code in tribunais:
            r = _datajud_count(code, inicio, fim, classes, assuntos)
            if "error" in r:
                errors.append({"tribunal": code, "error": r["error"]})
            results.append(r)
    elif listagem in ("jurisprudencia", "sentencas"):
        method = "cjsg" if listagem == "jurisprudencia" else "cjpg"
        pesquisa = str(form.get("filtro_palavras_chave") or "").strip()
        if not pesquisa:
            errors.append(
                {"tribunal": "(geral)", "error": "Filtro de palavras-chave vazio."}
            )
        else:
            for code in tribunais:
                r = _juscraper_count(method, code, pesquisa)
                if "error" in r:
                    errors.append({"tribunal": code, "error": r["error"]})
                results.append(r)
    else:
        errors.append({"tribunal": "(geral)", "error": f"listagem desconhecida: {listagem}"})

    total_known = sum(r.get("count", 0) for r in results if isinstance(r.get("count"), int))
    has_unbounded = any(r.get("relation") in ("gte", "first_page") for r in results)

    highlights: list[str] = []
    if errors:
        highlights.append(f"{len(errors)} erro(s) durante a coleta — ver lista no relatório.")
    if listagem == "datajud":
        if total_known > 50_000:
            highlights.append(
                f"Volume estimado em {total_known:,} processos — recomenda-se fatiar a coleta."
            )
        elif total_known > 0:
            highlights.append(f"Volume estimado em {total_known:,} processos — gerenciável.")
    elif results:
        highlights.append(
            "Cada tribunal listou ao menos a 1ª página — contagem total não disponível na busca pública."
        )

    if not results:
        verdict = "unviable"
    elif errors and len(errors) >= len(results):
        verdict = "unviable"
    elif (listagem == "datajud" and total_known > 50_000) or errors:
        verdict = "caveats"
    else:
        verdict = "viable"

    return {
        "listagem": listagem,
        "tribunais": results,
        "total_aproximado": total_known,
        "has_unbounded": has_unbounded,
        "errors": errors,
        "verdict": verdict,
        "highlights": highlights,
    }


# ---------------------------------------------------------------------------
# Relatório local (Quarto opcional)
# ---------------------------------------------------------------------------

_LOCAL_TEMPLATE = """---
title: "Análise de viabilidade — {{descricao}}"
format:
  typst:
    papersize: a4
    margin:
      x: 2cm
      y: 2cm
---

**Gerado em:** {{generated_at}}

## Resumo

- **Listagem:** {{listagem}}
- **Tribunais consultados:** {{tribunais_str}}
- **Total aproximado:** {{total}}
- **Veredito:** {{verdict}}

{% if highlights %}
### Pontos de atenção

{% for h in highlights %}
- {{h}}
{% endfor %}
{% endif %}

## Resultados por tribunal

| Tribunal | Contagem | Observação |
|----------|---------:|------------|
{% for r in results %}
| {{r.code}} | {{r.get('count', '?')}} | {{r.get('relation', '')}}{% if r.get('error') %} — erro: {{r.error}}{% endif %} |
{% endfor %}

{% if errors %}
## Erros

{% for e in errors %}
- **{{e.tribunal}}:** {{e.error}}
{% endfor %}
{% endif %}

{% if notas %}
## Notas do solicitante

{{notas}}
{% endif %}
"""


def _try_render_local_report(
    form: dict[str, Any],
    results: dict[str, Any],
    saida_dir: Path,
    notas: str,
) -> tuple[Path | None, Path | None]:
    """Tenta renderizar o relatório local com Quarto. Se Quarto não está
    instalado, escreve só o ``.md`` (Jinja já gera markdown válido)."""
    try:
        from jinja2 import Template
    except ImportError:
        return None, None

    rendered = Template(_LOCAL_TEMPLATE).render(
        descricao=form.get("descricao_pesquisa", ""),
        generated_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
        listagem=results.get("listagem", ""),
        tribunais_str=", ".join(r.get("code", "?") for r in results.get("tribunais") or []),
        total=results.get("total_aproximado", 0),
        verdict=results.get("verdict", "?"),
        highlights=results.get("highlights") or [],
        results=results.get("tribunais") or [],
        errors=results.get("errors") or [],
        notas=notas or "",
    )

    md_path = saida_dir / "viabilidade_relatorio.md"
    md_path.write_text(rendered, encoding="utf-8")

    if not shutil.which("quarto"):
        return None, md_path

    pdf_path: Path | None = None
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        report_qmd = tmp_dir / "report.qmd"
        report_qmd.write_text(rendered, encoding="utf-8")
        try:
            subprocess.run(
                ["quarto", "render", str(report_qmd), "--to", "typst"],
                check=True,
                cwd=str(tmp_dir),
                capture_output=True,
                timeout=120,
            )
            generated_pdf = tmp_dir / "report.pdf"
            if generated_pdf.exists():
                pdf_path = saida_dir / "viabilidade_relatorio.pdf"
                pdf_path.write_bytes(generated_pdf.read_bytes())
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pdf_path = None

    return pdf_path, md_path
