"""Anonimização de PII em texto — detecção e mascaramento.

Modo nuvem
----------
Roda na infra do escritório usando o modelo
`openai/privacy-filter <https://huggingface.co/openai/privacy-filter>`_
em GPU T4 (Container Apps consumption, KEDA min=0).

Modo local
----------
Carrega o mesmo modelo via HuggingFace Transformers no próprio
computador. CPU funciona mas é ~10x mais lento que GPU; útil para
volumes pequenos ou quando os dados não podem sair da máquina.

⚠️ **Privacy disclaimer**

> Use Privacy Filter as part of a holistic privacy-by-design approach,
> not as a blanket anonymization claim. — OpenAI

O modelo é um **detector de PII**, não uma garantia de anonimização.
Sempre revise manualmente o resultado antes de publicar dados sensíveis.
Não substitui análise de conformidade com LGPD/GDPR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from labdados._io import PathLike, ensure_output_dir, resolve_inputs
from labdados.client import Client
from labdados.exceptions import LocalDependencyMissing

ModeloAnonimizacao = Literal["privacy-filter"]
EstrategiaMascaramento = Literal["categoria", "asteriscos", "pseudonimo"]
ACCEPTED_EXTENSIONS = (".txt", ".md", ".docx", ".csv", ".xlsx")


def anonimizacao(
    arquivos: PathLike | list[PathLike],
    *,
    estrategia: EstrategiaMascaramento = "categoria",
    saida: PathLike | None = None,
    api_key: str | None = None,
    modelo: ModeloAnonimizacao = "privacy-filter",
    coluna_texto: str = "",
    local: bool = False,
    use_gpu_local: bool = False,
    client: Client | None = None,
    progress: bool = True,
) -> Path:
    """Detecta e mascara dados pessoais (PII) em textos.

    .. warning::
       Privacy Filter é um detector como UMA camada num approach de
       privacy-by-design — não é garantia de anonimização nem de
       conformidade com LGPD/GDPR. **Sempre revise manualmente o
       resultado** antes de publicar dados sensíveis.

    Parameters
    ----------
    arquivos
        ``.txt``, ``.md``, ``.docx``, ``.csv`` ou ``.xlsx``. Para CSV/XLSX,
        cada linha vira um documento — use ``coluna_texto`` para indicar
        qual coluna contém o texto a anonimizar.
    estrategia
        Como mascarar os spans detectados:

        - ``"categoria"`` (default): substitui pelo rótulo da categoria
          entre colchetes. Ex.: ``"João Silva"`` → ``"[PESSOA]"``.
        - ``"asteriscos"``: preserva o tamanho exato. Ex.:
          ``"João Silva"`` → ``"**********"``.
        - ``"pseudonimo"``: substitui por ``PESSOA_1``, ``PESSOA_2``...
          consistente por (categoria, valor) dentro do mesmo texto.
          Útil quando precisa preservar referências (ex.: análise de
          coocorrência) sem expor a identidade.
    saida
        Pasta de saída. Cada documento gera ``<doc>.txt`` (texto
        anonimizado) e ``<doc>.json`` (entidades detectadas).
    api_key
        Chave de API do escritório (modo nuvem).
    modelo
        ``"privacy-filter"`` (default e único hoje).
    coluna_texto
        Para CSV/XLSX: nome da coluna com o texto a anonimizar.
        Vazio = concatena todas as colunas da linha.
    local
        Se ``True``, roda na própria máquina via HF Transformers.
        Requer ``pip install labdados[anonimizacao]`` e ~3GB de
        download na primeira execução (modelo cacheado em
        ``~/.cache/huggingface``).
    use_gpu_local
        Se ``True`` no modo local e CUDA estiver disponível, roda em
        GPU. ~10x mais rápido. Padrão CPU.
    client
        Cliente reaproveitado (modo nuvem).
    progress
        Spinner no stderr.

    Returns
    -------
    Path
        Pasta de saída com os textos anonimizados.

    Examples
    --------
    Modo nuvem:

    >>> import labdados
    >>> labdados.anonimizacao(
    ...     arquivos="depoimentos.csv",
    ...     coluna_texto="texto",
    ...     api_key="sk_lab_...",
    ...     estrategia="categoria",
    ... )

    Modo local (sem GPU):

    >>> labdados.anonimizacao(
    ...     arquivos="textos/",
    ...     local=True,
    ...     estrategia="pseudonimo",
    ... )

    Categorias detectadas (rótulos do modelo):

    - ``private_person``  → nomes de pessoas
    - ``private_email``   → endereços de email
    - ``private_phone``   → telefones
    - ``private_address`` → endereços
    - ``private_url``     → URLs (potencialmente identificadoras)
    - ``account_number``  → contas, CPFs, CNPJs, etc.
    - ``private_date``    → datas potencialmente identificadoras (nascimento, etc.)
    - ``secret``          → segredos (chaves, tokens, senhas)
    """
    docs = resolve_inputs(arquivos, extensoes=ACCEPTED_EXTENSIONS)
    saida_dir = ensure_output_dir(saida)

    if local:
        return _anon_local(
            docs,
            saida_dir=saida_dir,
            estrategia=estrategia,
            coluna_texto=coluna_texto,
            use_gpu=use_gpu_local,
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
    config: dict = {
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


def _anon_local(
    docs: list[Path],
    *,
    saida_dir: Path,
    estrategia: str,
    coluna_texto: str,
    use_gpu: bool,
    progress: bool,
) -> Path:
    """Roda anonimização local via labdados_core.anonimizacao.

    O pipeline (carregamento do modelo, detecção de spans, mascaramento)
    vive no core — mesma rotina que o backend roda. Esta função só faz:
    ler bytes do disco, dividir em documentos via reader compartilhado,
    chamar o pipeline e gravar os arquivos por documento.
    """
    try:
        from labdados_core.anonimizacao import anonimizar
        from labdados_core.estruturacao.readers import read_document
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Anonimização local requer:\n    pip install labdados[anonimizacao]"
        ) from exc

    from labdados._progress import clear_status, render_status

    for i, path in enumerate(docs, start=1):
        if progress:
            render_status(f"anonimizando {i}/{len(docs)}: {path.name}", frame=i)
        documents = read_document(
            path.read_bytes(), path.name, csv_text_column=coluna_texto
        )
        results = anonimizar(
            documents,
            estrategia=estrategia,
            use_gpu=use_gpu,
        )
        # Para CSV/XLSX (vários docs por arquivo), grava 1 .txt e 1 .json
        # por linha (com sufixo __rowNNNN). Para arquivos únicos, grava
        # com o stem do arquivo.
        for r in results:
            label = r.doc_id if len(documents) > 1 else path.stem
            (saida_dir / f"{label}.txt").write_text(
                r.texto_anonimizado, encoding="utf-8"
            )
            (saida_dir / f"{label}.json").write_text(
                json.dumps(
                    {
                        "doc_id": r.doc_id,
                        "source_file": path.name,
                        "estrategia": estrategia,
                        "n_entidades": len(r.entidades),
                        "entidades": [e.to_dict() for e in r.entidades],
                        "erro": r.erro,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    if progress:
        clear_status()
    return saida_dir
