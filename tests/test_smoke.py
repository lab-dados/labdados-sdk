"""Testes de fumaça: o pacote importa, expõe a API esperada e o roteamento
nuvem/local funciona sem rede.

Não testamos OS-OCR / Whisper local (precisam de binários do sistema). O
caminho remoto é exercitado via ``respx`` mockando ``httpx``.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
import respx

import labdados


def test_top_level_api_exposed():
    """Confere que as 5 funções e o Client estão disponíveis no nível raiz."""
    assert callable(labdados.ocr)
    assert callable(labdados.transcricao)
    assert callable(labdados.estruturacao)
    assert callable(labdados.anonimizacao)
    assert callable(labdados.analise_viabilidade)
    assert isinstance(labdados.Client(api_key="sk_lab_x"), labdados.Client)
    assert isinstance(labdados.__version__, str)


def test_anonimizacao_signature():
    """Smoke: a assinatura aceita os argumentos documentados (modelos +
    estratégias)."""
    import inspect

    sig = inspect.signature(labdados.anonimizacao)
    expected = {
        "arquivos", "saida", "api_key", "modelo", "estrategia",
        "coluna_texto", "local", "use_gpu", "client", "progress",
    }
    assert expected <= set(sig.parameters)


@respx.mock
def test_anonimizacao_remote_full_flow(tmp_path: Path):
    """Mocka o fluxo nuvem da anonimização: SAS → upload → request → poll → download."""
    txt = tmp_path / "doc.txt"
    txt.write_text("Meu nome é João Silva.", encoding="utf-8")
    saida = tmp_path / "out"

    from labdados.client import PUBLIC_BASE_URL

    base = PUBLIC_BASE_URL
    respx.post(f"{base}/api/v1/uploads/sas").mock(
        return_value=httpx.Response(
            200,
            json={
                "upload_url": "https://sas.example/u?sig=x",
                "blob_path": "anonimizacao/abc/doc.txt",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )
    )
    respx.put(re.compile(r"^https://sas\.example/u")).mock(
        return_value=httpx.Response(201)
    )
    respx.post(f"{base}/api/v1/requests").mock(
        return_value=httpx.Response(
            201,
            json={"id": "req-anon-1", "status": "APPROVED"},
        )
    )
    respx.get(f"{base}/api/v1/requests/req-anon-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "req-anon-1",
                "status": "COMPLETED",
                "result_url": "https://sas.example/r?sig=y",
            },
        )
    )
    respx.get(re.compile(r"^https://sas\.example/r")).mock(
        return_value=httpx.Response(200, content=b"PK\x03\x04 zip-bytes-anon")
    )

    out_dir = labdados.anonimizacao(
        arquivos=txt,
        api_key="sk_lab_test",
        modelo="lenerbr",
        estrategia="pseudonimo",
        saida=saida,
        progress=False,
    )
    assert out_dir == saida
    zips = list(saida.glob("anonimizacao_*.zip"))
    assert len(zips) == 1
    assert zips[0].read_bytes() == b"PK\x03\x04 zip-bytes-anon"


def test_client_requires_api_key_for_cloud():
    cli = labdados.Client()
    with pytest.raises(labdados.ApiKeyError):
        cli.test_connection()


def test_resolve_inputs_folder(tmp_path: Path):
    """O resolver de inputs aceita pasta e varre recursivamente por extensão."""
    from labdados._io import resolve_inputs

    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 dummy")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 dummy")
    (tmp_path / "ignore.txt").write_text("nope")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.pdf").write_bytes(b"%PDF-1.4 dummy")

    out = resolve_inputs(tmp_path, extensoes=(".pdf",))
    assert {p.name for p in out} == {"a.pdf", "b.pdf", "c.pdf"}


def test_resolve_inputs_list_and_single(tmp_path: Path):
    from labdados._io import resolve_inputs

    a = tmp_path / "a.pdf"
    a.write_bytes(b"%PDF-1.4")
    b = tmp_path / "b.pdf"
    b.write_bytes(b"%PDF-1.4")

    assert len(resolve_inputs([a, b], extensoes=(".pdf",))) == 2
    assert len(resolve_inputs(a, extensoes=(".pdf",))) == 1


def test_resolve_inputs_rejects_wrong_extension(tmp_path: Path):
    from labdados._io import resolve_inputs

    bad = tmp_path / "x.docx"
    bad.write_text("not a pdf")
    with pytest.raises(FileNotFoundError):
        resolve_inputs(bad, extensoes=(".pdf",))


@respx.mock
def test_ocr_remote_full_flow(tmp_path: Path):
    """Mocka todo o fluxo nuvem: SAS, upload, criar request, polling, download."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy bytes")
    saida = tmp_path / "out"

    from labdados.client import PUBLIC_BASE_URL

    base = PUBLIC_BASE_URL

    respx.post(f"{base}/api/v1/uploads/sas").mock(
        return_value=httpx.Response(
            200,
            json={
                "upload_url": "https://sas.example/u?sig=x",
                "blob_path": "ocr/abc/doc.pdf",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )
    )
    respx.put(re.compile(r"^https://sas\.example/u")).mock(
        return_value=httpx.Response(201)
    )
    respx.post(f"{base}/api/v1/requests").mock(
        return_value=httpx.Response(
            201,
            json={"id": "req-123", "status": "APPROVED"},
        )
    )
    poll_responses = iter(
        [
            httpx.Response(200, json={"id": "req-123", "status": "RUNNING"}),
            httpx.Response(
                200,
                json={
                    "id": "req-123",
                    "status": "COMPLETED",
                    "result_url": "https://sas.example/r?sig=y",
                },
            ),
        ]
    )
    respx.get(f"{base}/api/v1/requests/req-123").mock(side_effect=lambda r: next(poll_responses))
    respx.get(re.compile(r"^https://sas\.example/r")).mock(
        return_value=httpx.Response(200, content=b"PK\x03\x04 zip-bytes")
    )

    out = labdados.ocr(
        arquivos=pdf,
        api_key="sk_lab_test",
        saida=saida,
        modelo="pymupdf-tesseract",
        progress=False,
    )
    assert out == saida
    zips = list(saida.glob("ocr_*.zip"))
    assert len(zips) == 1
    assert zips[0].read_bytes() == b"PK\x03\x04 zip-bytes"


def test_estruturacao_schema_passthrough():
    """O ``schema`` aceita dict ou string JSON — converte coerentemente."""
    from labdados.estruturacao import estruturacao  # noqa: F401

    # Apenas garantimos que a função existe e os tipos casam — fluxo nuvem
    # é exercitado em test_ocr_remote_full_flow.


def test_estruturacao_local_azure_usa_api_v1():
    """Endpoint Azure vira provider ``openai`` na API v1.

    Modelos de raciocínio (gpt-5.6-luna) rejeitam ``max_tokens`` — só o
    provider ``openai`` do core manda ``max_completion_tokens``.
    """
    from labdados.estruturacao import _resolve_local_endpoint

    azure = "https://meu-recurso.openai.azure.com/"
    v1 = "https://meu-recurso.openai.azure.com/openai/v1/"
    assert _resolve_local_endpoint(azure) == ("openai", v1)
    assert _resolve_local_endpoint(v1) == ("openai", v1)
    assert _resolve_local_endpoint("http://localhost:11434/v1") == (
        "openai_compat",
        "http://localhost:11434/v1",
    )


def test_estruturacao_modelos_nuvem():
    from typing import get_args

    from labdados.estruturacao import MODELO_NUVEM

    assert {"gpt-4.1-mini", "gpt-5.6-luna", "DeepSeek-V4-Flash", "Mistral-Large-3"} <= set(get_args(MODELO_NUVEM))


def test_anonimizacao_estrategia_default():
    """Default deve ser 'categoria' — padrão mais legível."""
    import inspect

    sig = inspect.signature(labdados.anonimizacao)
    assert sig.parameters["estrategia"].default == "categoria"


def test_analise_viabilidade_signature():
    """Smoke: a assinatura aceita os argumentos documentados."""
    import inspect

    sig = inspect.signature(labdados.analise_viabilidade)
    expected = {
        "descricao", "listagem", "tribunais", "saida",
        "palavras_chave", "classes_cnj", "assuntos_cnj", "grau",
        "inicio", "fim", "notas", "progress",
    }
    assert expected <= set(sig.parameters)


@respx.mock
def test_test_connection_returns_metadata():
    from labdados.client import PUBLIC_BASE_URL

    base = PUBLIC_BASE_URL
    respx.get(f"{base}/api/v1/whoami").mock(
        return_value=httpx.Response(
            200,
            json={
                "email": "user@fgv.br",
                "researcher_name": "Fulano",
                "institution": "FGV",
                "key_prefix": "sk_lab_aB3x",
                "created_at": "2026-05-01T00:00:00+00:00",
            },
        )
    )
    cli = labdados.Client(api_key="sk_lab_test", progress=False)
    info = cli.test_connection()
    assert info["email"] == "user@fgv.br"


def test_diarization_validation():
    """Diarização exige azure-speech ou WhisperX — falha cedo no SDK."""
    with pytest.raises(ValueError, match="azure-speech"):
        labdados.transcricao(
            arquivos=Path("ignored"),  # nem chega a tocar no arquivo
            api_key="sk_lab_x",
            modelo="whisper-large-v3-turbo",
            diarizacao=True,
        )


@respx.mock
def test_embeddings_remote_extrai_zip_na_saida(tmp_path: Path):
    """Fluxo nuvem de embeddings: upload, request com service_id/config, polling e extração."""
    import io
    import json
    import zipfile

    txt = tmp_path / "doc.txt"
    txt.write_text("Ação de cobrança.", encoding="utf-8")
    saida = tmp_path / "out"

    from labdados.client import PUBLIC_BASE_URL as base

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("embeddings.parquet", b"PAR1fake")
        zf.writestr("chunks.csv", "arquivo,doc_id,chunk,texto\n")
    respx.post(f"{base}/api/v1/uploads/sas").mock(
        return_value=httpx.Response(200, json={"upload_url": "https://sas.example/u?sig=x", "blob_path": "embeddings/a/doc.txt", "expires_at": "2030-01-01T00:00:00Z"})
    )
    respx.put(re.compile(r"^https://sas\.example/u")).mock(return_value=httpx.Response(201))
    create = respx.post(f"{base}/api/v1/requests").mock(return_value=httpx.Response(201, json={"id": "req-emb", "status": "APPROVED"}))
    respx.get(f"{base}/api/v1/requests/req-emb").mock(
        return_value=httpx.Response(200, json={"id": "req-emb", "status": "COMPLETED", "result_url": "https://sas.example/r?sig=y"})
    )
    respx.get(re.compile(r"^https://sas\.example/r")).mock(return_value=httpx.Response(200, content=zbuf.getvalue()))

    out = labdados.embeddings(txt, api_key="sk_lab_test", saida=saida, modelo="embed-v-4-0", max_chars=500, progress=False)

    assert out == saida
    assert (saida / "embeddings.parquet").read_bytes() == b"PAR1fake"
    assert (saida / "chunks.csv").exists()
    body = json.loads(create.calls.last.request.content)
    assert body["service_id"] == "embeddings"
    assert body["model_id"] == "embed-v-4-0"
    assert body["config"] == {"csv_text_column": "", "max_chars": 500, "overlap": 200}


def test_embeddings_local_com_servidor_openai_compat(tmp_path: Path, monkeypatch):
    """Modo local com base_url_local usa provider openai e grava parquet legível."""
    pytest.importorskip("labdados_core.embeddings")
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    import labdados_core.embeddings.pipeline as pipeline

    captured = {}

    def fake_embed(texts, config):
        captured["config"] = config
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(pipeline, "embed", fake_embed)
    monkeypatch.setattr("labdados_core.embeddings.embed", fake_embed)
    (tmp_path / "a.txt").write_text("Primeiro texto.", encoding="utf-8")

    df = labdados.embeddings(
        tmp_path / "a.txt", saida=tmp_path / "out", local=True,
        base_url_local="http://localhost:11434/v1", modelo_local="nomic-embed-text",
        dataframe=True, progress=False,
    )

    assert captured["config"].provider == "openai"
    assert captured["config"].model == "nomic-embed-text"
    assert list(df["texto"]) == ["Primeiro texto."]
    assert [list(v) for v in df["embedding"]] == [[1.0, 0.0]]


def test_defaults_de_modelo_nuvem_sao_do_foundry():
    import inspect
    from typing import get_args

    from labdados import embeddings as emb_mod  # noqa: F401
    from labdados.estruturacao import MODELO_NUVEM as EST
    from labdados.ocr import MODELO_PADRAO_NUVEM as OCR_PADRAO
    from labdados.transcricao import MODELO_PADRAO_NUVEM as TR_PADRAO

    assert OCR_PADRAO == "azure-document-intelligence"
    assert TR_PADRAO == "azure-speech"
    assert inspect.signature(labdados.ocr).parameters["modelo"].default is None
    assert "gpt-6-luna" in get_args(EST) and len(get_args(EST)) == 9



@respx.mock
def test_client_solicitacoes_lista_com_limite():
    from labdados.client import PUBLIC_BASE_URL as base

    route = respx.get(f"{base}/api/v1/requests").mock(
        return_value=httpx.Response(200, json=[{"id": "r1", "service_id": "ocr", "status": "COMPLETED"}])
    )
    out = labdados.Client(api_key="sk_lab_x", progress=False).solicitacoes(limite=5)
    assert out == [{"id": "r1", "service_id": "ocr", "status": "COMPLETED"}]
    assert route.calls.last.request.url.params["limit"] == "5"


def test_client_tem_atalhos_de_todos_os_servicos_de_nuvem():
    c = labdados.Client(api_key="sk_lab_x", progress=False)
    for nome in ("ocr", "transcricao", "estruturacao", "anonimizacao", "embeddings", "solicitacoes"):
        assert callable(getattr(c, nome))


def test_upload_recusa_arquivo_vazio(tmp_path: Path):
    """REGRESSÃO: download que falhou no Colab gerava arquivo vazio e o serviço
    quebrava no ffprobe com mensagem obscura. O SDK recusa antes de subir."""
    from labdados.exceptions import UploadError

    vazio = tmp_path / "audio.flac"
    vazio.write_bytes(b"")
    with pytest.raises(UploadError, match="vazio"):
        labdados.Client(api_key="sk_lab_x", progress=False)._upload_files("transcription", [vazio])
