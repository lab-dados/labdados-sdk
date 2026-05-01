"""
Estruturação de textos com LLMs — extrai campos JSON conforme um schema.

.. note::
   **Em desenvolvimento.** Esta ferramenta está em fase inicial. Em
   breve será integrada ao pacote
   `bdcdo/dataframeit <https://github.com/bdcdo/dataframeit>`_, que
   trará uma API mais madura para extração estruturada em escala. A
   superfície atual pode mudar.

Modo nuvem
----------
Roda na infra do escritório (GPT-4.1-mini via Azure OpenAI). Os modelos
self-host em GPU A100 (gpt-oss-20b, gemma-4-26b-it) foram descontinuados
por custo proibitivo no padrão de uso atual.

Modo local
----------
Cliente OpenAI-compatível: aceita OpenAI, Azure OpenAI, Ollama (default
``http://localhost:11434/v1``) ou qualquer servidor ``/v1/chat/completions``.
O usuário traz a própria chave/URL.
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
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Estruturação local requer:\n    pip install labdados[estruturacao]"
        ) from exc

    from labdados._progress import clear_status, render_status

    client = OpenAI(base_url=base_url, api_key=api_key_local)

    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
    base_system = (
        prompt_sistema or "Você extrai informações estruturadas de documentos jurídicos."
    )
    system = (
        f"{base_system}\n\n"
        f"Responda EXCLUSIVAMENTE com JSON válido seguindo este schema:\n{schema_str}"
    )

    for i, path in enumerate(docs, start=1):
        if progress:
            render_status(f"estruturando {i}/{len(docs)}: {path.name}", frame=i)
        rows = _read_doc(path, coluna_texto)
        results: list[dict[str, Any]] = []
        for row_text in rows:
            response = client.chat.completions.create(
                model=modelo_local,
                temperature=temperatura,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": row_text},
                ],
            )
            content = response.choices[0].message.content or "{}"
            try:
                results.append(json.loads(content))
            except json.JSONDecodeError:
                results.append({"_raw": content, "_error": "invalid_json"})
        out_path = saida_dir / f"{path.stem}.json"
        out_path.write_text(
            json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if progress:
        clear_status()
    return saida_dir


def _read_doc(path: Path, coluna_texto: str) -> list[str]:
    """Devolve uma lista de strings (uma por 'documento'). Para CSV/XLSX
    cada linha é um documento; para .txt/.md/.docx, é uma única string."""
    suf = path.suffix.lower()
    if suf in (".txt", ".md"):
        return [path.read_text(encoding="utf-8")]
    if suf == ".docx":
        try:
            import docx  # python-docx
        except ImportError as exc:
            raise LocalDependencyMissing(
                "Para ler .docx no modo local, instale: pip install python-docx"
            ) from exc
        d = docx.Document(str(path))
        return ["\n".join(p.text for p in d.paragraphs)]
    if suf == ".csv":
        try:
            import pandas as pd
        except ImportError as exc:
            raise LocalDependencyMissing(
                "Para ler .csv/.xlsx no modo local, instale: pip install pandas"
            ) from exc
        df = pd.read_csv(path)
        return _df_rows_as_text(df, coluna_texto)
    if suf == ".xlsx":
        try:
            import pandas as pd
        except ImportError as exc:
            raise LocalDependencyMissing(
                "Para ler .xlsx no modo local, instale: pip install pandas openpyxl"
            ) from exc
        df = pd.read_excel(path)
        return _df_rows_as_text(df, coluna_texto)
    raise ValueError(f"Extensão não suportada localmente: {suf}")


def _df_rows_as_text(df: Any, coluna_texto: str) -> list[str]:
    if coluna_texto and coluna_texto in df.columns:
        return [str(v) for v in df[coluna_texto].fillna("").tolist()]
    return [
        " · ".join(f"{c}: {v}" for c, v in row.items() if str(v).strip())
        for row in df.fillna("").to_dict(orient="records")
    ]
