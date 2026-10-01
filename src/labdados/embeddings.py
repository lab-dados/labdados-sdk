"""Embeddings de textos — transforma documentos em vetores numéricos.

Os vetores servem para busca semântica, agrupamento e classificação: textos
de sentido parecido ficam com vetores próximos.

Modo nuvem (default)
--------------------
Faz upload dos arquivos, calcula os vetores no escritório com um modelo do
Azure AI Foundry da FGV (``text-embedding-3-small`` por padrão) e extrai o
resultado na pasta ``saida``.

Modo local (``local=True``)
---------------------------
Roda ``sentence-transformers`` na própria máquina (``pip install
labdados[embeddings-local]``) ou, com ``base_url_local``, qualquer servidor
OpenAI-compatível (Ollama, OpenAI, um recurso Azure). Leitura, corte em
trechos e formato de saída vêm de ``labdados_core.embeddings`` — a mesma
rotina do serviço do escritório.

Saída (nos dois modos)
----------------------
- ``embeddings.parquet`` — um trecho por linha: ``arquivo``, ``doc_id``,
  ``chunk``, ``texto``, ``embedding`` (lista de floats);
- ``chunks.csv`` — os mesmos trechos sem os vetores;
- ``_reproducibilidade/parametros.json`` — modelo, tamanho do trecho etc.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from labdados._io import PathLike, ensure_output_dir, resolve_inputs
from labdados.client import Client
from labdados.exceptions import LocalDependencyMissing

if TYPE_CHECKING:
    import pandas as pd

MODELO_NUVEM = Literal[
    "text-embedding-3-small",
    "text-embedding-3-large",
    "embed-v-4-0",
    "Cohere-embed-v3-multilingual",
]
ACCEPTED_EXTENSIONS = (".txt", ".md", ".docx", ".csv", ".xlsx")
# Espelha labdados_core.embeddings (sem importar o core no modo nuvem).
MAX_CHARS_PADRAO = 2000
SOBREPOSICAO_PADRAO = 200


def embeddings(
    arquivos: PathLike | list[PathLike],
    *,
    saida: PathLike | None = None,
    api_key: str | None = None,
    modelo: str = "text-embedding-3-small",
    coluna_texto: str = "",
    max_chars: int = MAX_CHARS_PADRAO,
    sobreposicao: int = SOBREPOSICAO_PADRAO,
    local: bool = False,
    modelo_local: str | None = None,
    base_url_local: str | None = None,
    api_key_local: str | None = None,
    dataframe: bool = False,
    client: Client | None = None,
    progress: bool = True,
) -> Path | pd.DataFrame:
    """Calcula embeddings de textos.

    Parameters
    ----------
    arquivos
        ``.txt``, ``.md``, ``.docx``, ``.csv`` ou ``.xlsx`` (arquivo, lista
        ou pasta). Em CSV/XLSX, cada linha vira um documento.
    saida
        Pasta de saída. Default: ``./resultados_labdados/``.
    api_key
        Chave de API do escritório (modo nuvem).
    modelo
        Modo nuvem (Azure AI Foundry da FGV): ``"text-embedding-3-small"``
        (default, o mais barato), ``"text-embedding-3-large"``,
        ``"embed-v-4-0"`` ou ``"Cohere-embed-v3-multilingual"`` (Cohere são
        multilíngues). Use o mesmo modelo para todos os textos que serão
        comparados — vetores de modelos diferentes não são comparáveis.
    coluna_texto
        CSV/XLSX: coluna com o texto. Vazio = concatena todas as colunas.
    max_chars, sobreposicao
        Textos longos são cortados em trechos de até ``max_chars``
        caracteres (default 2000, ~500 tokens), com ``sobreposicao``
        caracteres repetidos entre trechos vizinhos. Cada trecho vira um vetor.
    local
        Se ``True``, calcula na própria máquina.
    modelo_local
        Modo local: modelo do sentence-transformers (default
        ``paraphrase-multilingual-MiniLM-L12-v2``) ou, com ``base_url_local``,
        o nome do modelo/deployment no servidor.
    base_url_local, api_key_local
        Servidor OpenAI-compatível para o modo local (ex.:
        ``"http://localhost:11434/v1"`` no Ollama, ou o endpoint ``/openai/v1/``
        de um recurso Azure). Sem ``base_url_local``, usa sentence-transformers.
    dataframe
        Se ``True``, devolve um ``pandas.DataFrame`` lido do
        ``embeddings.parquet`` em vez do caminho da pasta (requer pandas e
        pyarrow).
    client
        Cliente reaproveitado (modo nuvem).
    progress
        Spinner no stderr.

    Returns
    -------
    Path | pandas.DataFrame
        Pasta de saída, ou o DataFrame com os trechos e vetores.

    Examples
    --------
    >>> import labdados
    >>> df = labdados.embeddings("acordaos.csv", coluna_texto="ementa", dataframe=True)
    >>> df[["arquivo", "doc_id", "texto"]].head()

    Modo local com sentence-transformers:

    >>> labdados.embeddings("textos/", local=True)
    """
    docs = resolve_inputs(arquivos, extensoes=ACCEPTED_EXTENSIONS)
    saida_dir = ensure_output_dir(saida)

    if local:
        _emb_local(
            docs,
            saida_dir=saida_dir,
            coluna_texto=coluna_texto,
            max_chars=max_chars,
            sobreposicao=sobreposicao,
            modelo_local=modelo_local,
            base_url=base_url_local,
            api_key_local=api_key_local,
            progress=progress,
        )
    else:
        _emb_remote(
            docs,
            saida_dir=saida_dir,
            api_key=api_key,
            client=client,
            modelo=modelo,
            coluna_texto=coluna_texto,
            max_chars=max_chars,
            sobreposicao=sobreposicao,
            progress=progress,
        )

    if dataframe:
        try:
            import pandas as pd
        except ImportError as exc:
            raise LocalDependencyMissing(
                "dataframe=True requer pandas e pyarrow:\n    pip install labdados[embeddings]"
            ) from exc
        return pd.read_parquet(saida_dir / "embeddings.parquet")
    return saida_dir


def _extract_zip(blob: bytes, saida_dir: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        zf.extractall(saida_dir)


def _emb_remote(
    docs: list[Path],
    *,
    saida_dir: Path,
    api_key: str | None,
    client: Client | None,
    modelo: str,
    coluna_texto: str,
    max_chars: int,
    sobreposicao: int,
    progress: bool,
) -> None:
    cli = client or Client(api_key=api_key, progress=progress)
    files_meta = cli._upload_files("embeddings", docs)
    config: dict[str, Any] = {
        "csv_text_column": coluna_texto,
        "max_chars": max_chars,
        "overlap": sobreposicao,
    }
    req = cli._post(
        "/api/v1/requests",
        {"service_id": "embeddings", "model_id": modelo, "config": config, "files_metadata": files_meta},
    )
    final = cli._poll_request(req["id"], label="embeddings no escritório")
    destino = saida_dir / f"embeddings_{req['id'][:8]}.zip"
    cli._download(final["result_url"], destino)
    _extract_zip(destino.read_bytes(), saida_dir)


def _emb_local(
    docs: list[Path],
    *,
    saida_dir: Path,
    coluna_texto: str,
    max_chars: int,
    sobreposicao: int,
    modelo_local: str | None,
    base_url: str | None,
    api_key_local: str | None,
    progress: bool,
) -> None:
    try:
        from labdados_core.embeddings import (
            DEFAULT_LOCAL_MODEL,
            EmbeddingConfig,
            build_chunks,
            build_result_zip,
            embed,
        )
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Embeddings locais requerem:\n    pip install labdados[embeddings-local]"
        ) from exc

    from labdados._progress import clear_status, render_status

    if base_url:
        if not modelo_local:
            raise ValueError("Com base_url_local, informe modelo_local (nome do modelo/deployment no servidor).")
        config = EmbeddingConfig(model=modelo_local, provider="openai", base_url=base_url, api_key=api_key_local)
    else:
        config = EmbeddingConfig(model=modelo_local or DEFAULT_LOCAL_MODEL, provider="sentence_transformers")

    if progress:
        render_status(f"lendo {len(docs)} arquivo(s)...", frame=0)
    chunks = build_chunks(
        [(p.name, p.read_bytes()) for p in docs],
        csv_text_column=coluna_texto,
        max_chars=max_chars,
        overlap=sobreposicao,
    )
    if not chunks:
        raise ValueError("Nenhum texto encontrado nos arquivos.")
    if progress:
        render_status(f"calculando {len(chunks)} vetores com {config.model}...", frame=1)
    vectors = embed([c["texto"] for c in chunks], config)
    if progress:
        clear_status()
    _extract_zip(
        build_result_zip(
            chunks,
            vectors,
            {
                "model_id": config.model,
                "provider": config.provider,
                "max_chars": max_chars,
                "overlap": sobreposicao,
                "csv_text_column": coluna_texto,
                "arquivos": len(docs),
            },
        ),
        saida_dir,
    )
