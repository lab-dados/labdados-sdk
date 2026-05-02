"""Estruturação de textos com LLMs — extrai campos JSON conforme um schema.

Modo nuvem
----------
Roda na infra do escritório (GPT-4.1-mini via Azure OpenAI). Os modelos
self-host em GPU A100 (gpt-oss-20b, gemma-4-26b-it) foram descontinuados
por custo proibitivo no padrão de uso atual.

Modo local
----------
Cliente OpenAI-compatível: aceita OpenAI, Azure OpenAI, Ollama (default
``http://localhost:11434/v1``) ou qualquer servidor ``/v1/chat/completions``.
O usuário traz a própria chave/URL. Desde a v0.5.0 a chamada ao LLM e a
montagem do prompt vivem em ``labdados_core.estruturacao`` — o mesmo
código rodado pelo backend (``services/structuring``), garantindo que
prompt e parsing não divirjam.

.. note::
   **Mudança de comportamento na v0.5.0**: o schema passa a ser injetado
   na mensagem ``user`` (junto do texto), não mais na ``system``. Isso
   alinha com o backend e funciona melhor com
   ``response_format=json_schema``. Se o seu prompt depender da
   formulação antiga, instrua o LLM via ``prompt_sistema`` ou abra uma
   issue.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from labdados._io import PathLike, ensure_output_dir, resolve_inputs
from labdados.client import Client
from labdados.exceptions import LocalDependencyMissing

MODELO_NUVEM = Literal["gpt-4.1-mini"]
ACCEPTED_EXTENSIONS = (".txt", ".md", ".docx", ".csv", ".xlsx")


def estruturacao(
    arquivos: PathLike | list[PathLike],
    *,
    schema: dict[str, Any] | str,
    prompt_sistema: str = "",
    saida: PathLike | None = None,
    api_key: str | None = None,
    modelo: str = "gpt-4.1-mini",
    coluna_texto: str = "",
    temperatura: float = 0.0,
    max_tokens: int = 4096,
    local: bool = False,
    base_url_local: str = "http://localhost:11434/v1",
    api_key_local: str = "ollama",
    modelo_local: str = "llama3.1",
    client: Client | None = None,
    progress: bool = True,
) -> Path:
    """Extrai campos estruturados (JSON) a partir de textos.

    Parameters
    ----------
    arquivos
        ``.txt``, ``.md``, ``.docx``, ``.csv`` ou ``.xlsx``. Para CSV/XLSX,
        cada linha vira um documento — use ``coluna_texto`` para indicar
        qual coluna contém o texto a estruturar.
    schema
        JSON Schema (dict) ou string JSON. Define os campos extraídos
        e seus tipos. Mantenha simples — campos com ``description`` ajudam
        muito a LLM.
    prompt_sistema
        Instruções de contexto (qual o tipo de documento, o que ignorar...).
    saida
        Pasta de saída. Cada documento gera um ``.json`` com a extração.
    api_key
        Chave de API do escritório (modo nuvem).
    modelo
        ``"gpt-4.1-mini"`` (default — único modelo nuvem disponível
        hoje). Os modelos self-host em GPU A100 (gpt-oss-20b,
        gemma-4-26b-it) foram descontinuados por custo.
    coluna_texto
        Para CSV/XLSX: nome da coluna que contém o texto a ser estruturado.
        Vazio = concatena todas as colunas da linha.
    temperatura
        ``0.0`` para resultado determinístico (recomendado em extração).
    max_tokens
        Tamanho máximo da resposta JSON. Aumente se o JSON estiver sendo
        cortado.
    local
        Se ``True``, chama um servidor OpenAI-compatível local. Default:
        Ollama em ``http://localhost:11434/v1``.
    base_url_local, api_key_local, modelo_local
        Configuração do servidor local. Para Azure OpenAI, ajuste
        ``base_url_local`` e ``api_key_local``. Para Ollama, mantenha
        os defaults e mude apenas ``modelo_local`` (ex.: ``"qwen2.5:7b"``).
    client
        Cliente reaproveitado (modo nuvem).
    progress
        Spinner no stderr.

    Returns
    -------
    Path
        Pasta de saída.

    Examples
    --------
    Modo nuvem com schema simples:

    >>> import labdados
    >>> labdados.estruturacao(
    ...     arquivos="acordaos.csv",
    ...     coluna_texto="ementa",
    ...     api_key="sk_lab_...",
    ...     prompt_sistema="Você está extraindo decisões judiciais sobre direito do consumidor.",
    ...     schema={
    ...         "type": "object",
    ...         "properties": {
    ...             "autor": {"type": "string"},
    ...             "reu": {"type": "string"},
    ...             "valor_causa": {"type": "number"},
    ...             "procedente": {"type": "boolean"},
    ...         },
    ...         "required": ["autor", "reu"],
    ...     },
    ... )

    Modo local com Ollama:

    >>> labdados.estruturacao(
    ...     arquivos="textos/",
    ...     schema={"type": "object", "properties": {"resumo": {"type": "string"}}},
    ...     local=True,
    ...     modelo_local="qwen2.5:7b",
    ... )
    """
    docs = resolve_inputs(arquivos, extensoes=ACCEPTED_EXTENSIONS)
    saida_dir = ensure_output_dir(saida)
    schema_dict = json.loads(schema) if isinstance(schema, str) else schema

    if local:
        return _estr_local(
            docs,
            saida_dir=saida_dir,
            schema=schema_dict,
            prompt_sistema=prompt_sistema,
            coluna_texto=coluna_texto,
            temperatura=temperatura,
            max_tokens=max_tokens,
            base_url=base_url_local,
            api_key_local=api_key_local,
            modelo_local=modelo_local,
            progress=progress,
        )
    return _estr_remote(
        docs,
        saida_dir=saida_dir,
        api_key=api_key,
        client=client,
        modelo=modelo,
        schema=schema_dict,
        prompt_sistema=prompt_sistema,
        coluna_texto=coluna_texto,
        temperatura=temperatura,
        max_tokens=max_tokens,
        progress=progress,
    )


def _estr_remote(
    docs: list[Path],
    *,
    saida_dir: Path,
    api_key: str | None,
    client: Client | None,
    modelo: str,
    schema: dict[str, Any],
    prompt_sistema: str,
    coluna_texto: str,
    temperatura: float,
    max_tokens: int,
    progress: bool,
) -> Path:
    cli = client or Client(api_key=api_key, progress=progress)
    files_meta = cli._upload_files("structuring", docs)
    config: dict[str, Any] = {
        "system_prompt": prompt_sistema,
        "schema": json.dumps(schema, ensure_ascii=False),
        "csv_text_column": coluna_texto,
        "temperature": temperatura,
        "max_output_tokens": max_tokens,
    }
    req = cli._post(
        "/api/v1/requests",
        {
            "service_id": "structuring",
            "model_id": modelo,
            "config": config,
            "files_metadata": files_meta,
        },
    )
    final = cli._poll_request(req["id"], label="estruturação no escritório")
    cli._download(final["result_url"], saida_dir / f"estruturacao_{req['id'][:8]}.zip")
    return saida_dir


def _estr_local(
    docs: list[Path],
    *,
    saida_dir: Path,
    schema: dict[str, Any],
    prompt_sistema: str,
    coluna_texto: str,
    temperatura: float,
    max_tokens: int,
    base_url: str,
    api_key_local: str,
    modelo_local: str,
    progress: bool,
) -> Path:
    """Roda extração local via labdados_core.estruturacao.

    O cliente OpenAI, a montagem de prompt e a leitura de
    ``.txt/.md/.docx/.csv/.xlsx`` vivem no core — mesma rotina que o
    backend roda. Esta função só faz: ler bytes do disco, dividir em
    documentos, chamar o pipeline e gravar o ``.json`` por arquivo.
    """
    try:
        from labdados_core.estruturacao import (
            LlmConfig,
            estruturar,
            read_document,
        )
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Estruturação local requer:\n    pip install labdados[estruturacao]"
        ) from exc

    from labdados._progress import clear_status, render_status

    llm_config = LlmConfig(
        provider="openai_compat",
        model=modelo_local,
        api_key=api_key_local,
        base_url=base_url,
        temperature=temperatura,
        max_tokens=max_tokens,
    )

    for i, path in enumerate(docs, start=1):
        if progress:
            render_status(f"estruturando {i}/{len(docs)}: {path.name}", frame=i)
        documents = read_document(
            path.read_bytes(), path.name, csv_text_column=coluna_texto
        )
        results = estruturar(
            documents,
            schema=schema,
            system_prompt=prompt_sistema,
            llm_config=llm_config,
        )
        out_path = saida_dir / f"{path.stem}.json"
        payload = results if len(results) > 1 else results[0]
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if progress:
        clear_status()
    return saida_dir
