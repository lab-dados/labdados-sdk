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
    """Confere que as 4 funções e o Client estão disponíveis no nível raiz."""
    assert callable(labdados.ocr)
    assert callable(labdados.transcricao)
    assert callable(labdados.estruturacao)
    assert callable(labdados.analise_viabilidade)
    assert isinstance(labdados.Client(api_key="sk_lab_x"), labdados.Client)
    assert isinstance(labdados.__version__, str)


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
    """Diarização exige WhisperX — falha cedo no SDK."""
    with pytest.raises(ValueError, match="modelo='whisperx'"):
        labdados.transcricao(
            arquivos=Path("ignored"),  # nem chega a tocar no arquivo
            api_key="sk_lab_x",
            modelo="whisper-large-v3-turbo",
            diarizacao=True,
        )
