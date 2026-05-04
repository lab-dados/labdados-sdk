"""Anonimização de PII em texto — detecção e mascaramento de dados pessoais.

Modo nuvem (default)
--------------------
Faz upload dos textos e dispara a anonimização no escritório. Dois
modelos disponíveis:

- ``"privacy-filter"`` — `openai/privacy-filter
  <https://huggingface.co/openai/privacy-filter>`_, multilíngue, 8
  categorias (nome, e-mail, telefone, endereço, URL, conta, data,
  segredos). Estado-da-arte no benchmark PII-Masking-300k.
- ``"lenerbr"`` — `pierreguillou/ner-bert-base-cased-pt-lenerbr
  <https://huggingface.co/pierreguillou/ner-bert-base-cased-pt-lenerbr>`_,
  BERT base PT-BR fine-tuned em LeNER-Br (decisões judiciais
  brasileiras). 6 categorias (PESSOA, ORGANIZACAO, LOCAL, TEMPO,
  LEGISLACAO, JURISPRUDENCIA). Mais leve e mais rápido — escolha
  quando estiver lidando especificamente com texto jurídico em PT-BR.

Modo local (``local=True``)
---------------------------
Roda o mesmo pipeline (``labdados_core.anonimizacao``) na sua máquina
via HF Transformers. Precisa do extra ``pip install
labdados[anonimizacao]`` (puxa torch + transformers de CPU). O primeiro
uso baixa os pesos do HuggingFace (~3 GB do privacy-filter ou ~440 MB
do lenerbr).

Aviso
-----
Detectores de PII são **uma camada** num approach de privacy-by-design,
não uma garantia absoluta de anonimização nem de conformidade com
LGPD/GDPR. Sempre revise manualmente o resultado antes de publicar.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Literal

from labdados._io import PathLike, ensure_output_dir, resolve_inputs
from labdados.client import Client
from labdados.exceptions import LocalDependencyMissing

MODELO_NUVEM = Literal["privacy-filter", "lenerbr"]
ESTRATEGIA = Literal["categoria", "asteriscos", "pseudonimo"]
ACCEPTED_EXTENSIONS = (".txt", ".md", ".docx", ".csv", ".xlsx")


def anonimizacao(
    arquivos: PathLike | list[PathLike],
    *,
    saida: PathLike | None = None,
    api_key: str | None = None,
    modelo: str = "privacy-filter",
    estrategia: ESTRATEGIA = "categoria",
    coluna_texto: str = "",
    local: bool = False,
    use_gpu: bool = False,
    client: Client | None = None,
    progress: bool = True,
) -> Path:
    """Detecta e mascara PII (nomes, e-mails, telefones, etc.) em textos.

    Parameters
    ----------
    arquivos
        ``.txt``, ``.md``, ``.docx``, ``.csv`` ou ``.xlsx``. Para CSV/XLSX,
        cada linha vira um documento — use ``coluna_texto`` para indicar
        qual coluna contém o texto a anonimizar.
    saida
        Pasta de saída. Modo nuvem baixa o ``.zip`` retornado; modo local
        escreve um ``.txt`` (texto anonimizado) e um ``.json`` (entidades
        detectadas) por documento, e um ``consolidated.csv`` com tudo.
    api_key
        Chave de API do escritório (modo nuvem).
    modelo
        ``"privacy-filter"`` (default — multilíngue, 8 categorias PII) ou
        ``"lenerbr"`` (PT-BR jurídico, 6 categorias incluindo
        legislação/jurisprudência citadas). Só vale no modo nuvem; no
        local, o modelo é o mesmo HF identifier passado direto pra
        ``labdados_core``.
    estrategia
        Como mascarar: ``"categoria"`` (default — substitui por
        ``[PESSOA]``, ``[EMAIL]``, etc.), ``"asteriscos"`` (preserva
        tamanho, útil em CSVs largura-fixa) ou ``"pseudonimo"``
        (substitui por ``PESSOA_1``, ``PESSOA_2``... mantendo
        consistência por texto).
    coluna_texto
        Para CSV/XLSX: nome da coluna que contém o texto. Vazio =
        concatena todas as colunas da linha.
    local
        Se ``True``, roda HF Transformers no próprio computador (precisa
        ``pip install labdados[anonimizacao]``).
    use_gpu
        No modo local: tenta CUDA quando disponível. CPU funciona, mas é
        ~10× mais lento no privacy-filter (1.5B params); o lenerbr (110M)
        roda confortável em CPU.
    client
        Reaproveita um :class:`labdados.Client` existente.
    progress
        Spinner no stderr.

    Returns
    -------
    Path
        Caminho do diretório de saída (criado se preciso).

    Examples
    --------
    Modo nuvem com lenerbr (jurídico PT-BR):

    >>> import labdados
    >>> labdados.anonimizacao(
    ...     arquivos="acordaos/",
    ...     modelo="lenerbr",
    ...     estrategia="pseudonimo",
    ...     api_key="sk_lab_...",
    ...     saida="anon/",
    ... )

    Modo local (privacy-filter, multilíngue):

    >>> labdados.anonimizacao(
    ...     arquivos="textos.csv",
    ...     coluna_texto="depoimento",
    ...     local=True,
    ...     modelo="privacy-filter",
    ... )
    """
    docs = resolve_inputs(arquivos, extensoes=ACCEPTED_EXTENSIONS)
    saida_dir = ensure_output_dir(saida)

    if local:
        return _anon_local(
            docs,
            saida_dir=saida_dir,
            modelo=modelo,
            estrategia=estrategia,
            coluna_texto=coluna_texto,
            use_gpu=use_gpu,
            progress=progress,
        )
    return _anon_remote(
        docs,
        saida_dir=saida_dir,
        api_key=api_key,
        client=client,
        modelo=modelo,
        estrategia=estrategia,
        coluna_texto=coluna_texto,
        progress=progress,
    )


def _anon_remote(
    docs: list[Path],
    *,
    saida_dir: Path,
    api_key: str | None,
    client: Client | None,
    modelo: str,
    estrategia: str,
    coluna_texto: str,
    progress: bool,
) -> Path:
    cli = client or Client(api_key=api_key, progress=progress)
    files_meta = cli._upload_files("anonimizacao", docs)
    config: dict[str, Any] = {
        "estrategia": estrategia,
        "csv_text_column": coluna_texto,
    }
    req = cli._post(
        "/api/v1/requests",
        {
            "service_id": "anonimizacao",
            "model_id": modelo,
            "config": config,
            "files_metadata": files_meta,
        },
    )
    final = cli._poll_request(req["id"], label="anonimização no escritório")
    cli._download(final["result_url"], saida_dir / f"anonimizacao_{req['id'][:8]}.zip")
    return saida_dir


# Mapeamento dos model_ids "amigáveis" do SDK pros HF identifiers reais
# usados pelo core no modo local. Mantém o SDK consistente com o serviço
# (que aceita os mesmos ids "privacy-filter" / "lenerbr").
_HF_MAP_LOCAL: dict[str, str] = {
    "privacy-filter": "openai/privacy-filter",
    "lenerbr": "pierreguillou/ner-bert-base-cased-pt-lenerbr",
}


def _anon_local(
    docs: list[Path],
    *,
    saida_dir: Path,
    modelo: str,
    estrategia: str,
    coluna_texto: str,
    use_gpu: bool,
    progress: bool,
) -> Path:
    """Roda anonimização local via labdados_core.anonimizacao."""
    try:
        from labdados_core.anonimizacao import anonimizar
        from labdados_core.estruturacao.readers import read_document
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Anonimização local requer:\n    pip install labdados[anonimizacao]"
        ) from exc

    from labdados._progress import clear_status, render_status

    modelo_hf = _HF_MAP_LOCAL.get(modelo, modelo)

    all_rows: list[dict[str, str]] = []
    for i, path in enumerate(docs, start=1):
        if progress:
            render_status(f"anonimizando {i}/{len(docs)}: {path.name}", frame=i)
        documents = read_document(
            path.read_bytes(), path.name, csv_text_column=coluna_texto
        )
        results = anonimizar(
            documents,
            estrategia=estrategia,
            modelo=modelo_hf,
            use_gpu=use_gpu,
        )
        for r in results:
            stem = f"{path.stem}__{r.doc_id}" if len(documents) > 1 else path.stem
            (saida_dir / f"{stem}.txt").write_text(
                r.texto_anonimizado, encoding="utf-8"
            )
            (saida_dir / f"{stem}.json").write_text(
                json.dumps(
                    {
                        "doc_id": r.doc_id,
                        "source_file": path.name,
                        "estrategia": estrategia,
                        "modelo": modelo_hf,
                        "n_entidades": len(r.entidades),
                        "entidades": [e.to_dict() for e in r.entidades],
                        "erro": r.erro,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            for e in r.entidades:
                all_rows.append(
                    {
                        "source_file": path.name,
                        "doc_id": r.doc_id,
                        "label": e.label,
                        "start": str(e.start),
                        "end": str(e.end),
                        "texto": e.texto,
                    }
                )

    if all_rows:
        with (saida_dir / "consolidated.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["source_file", "doc_id", "label", "start", "end", "texto"]
            )
            writer.writeheader()
            writer.writerows(all_rows)

    if progress:
        clear_status()
    return saida_dir
