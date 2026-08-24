"""Testes do retorno em texto (``text=True``).

Cobrem o helper ``collect_text`` (arquivos soltos e ``.zip``, que é o
formato devolvido pela nuvem) e a presença do parâmetro nas funções
públicas. O caminho local do Whisper/Tesseract não é exercitado aqui
porque depende de binários e modelos.
"""

from __future__ import annotations

import inspect
import io
import re
import zipfile
from pathlib import Path

import httpx
import respx

import labdados
from labdados._io import collect_text


def test_collect_text_le_arquivos_soltos(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("primeiro áudio", encoding="utf-8")
    b.write_text("segundo áudio", encoding="utf-8")

    assert collect_text([a, b]) == "primeiro áudio\n\nsegundo áudio"


def test_collect_text_preserva_a_ordem_de_entrada(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("um", encoding="utf-8")
    b.write_text("dois", encoding="utf-8")

    assert collect_text([b, a]) == "dois\n\num"


def test_collect_text_le_de_dentro_do_zip(tmp_path):
    z = tmp_path / "resultado.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("2-segundo.txt", "segundo")
        zf.writestr("1-primeiro.txt", "primeiro")

    # Dentro do zip a ordem é alfabética, para ser determinística.
    assert collect_text([z]) == "primeiro\n\nsegundo"


def test_collect_text_ignora_membros_que_nao_sao_texto(tmp_path):
    z = tmp_path / "resultado.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("saida.txt", "texto útil")
        zf.writestr("metadados.json", '{"custo": 1}')
        zf.writestr("pasta/", "")

    assert collect_text([z]) == "texto útil"


def test_collect_text_descarta_vazios(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("   \n", encoding="utf-8")
    b.write_text("conteúdo", encoding="utf-8")

    assert collect_text([a, b]) == "conteúdo"


def test_collect_text_sem_arquivos():
    assert collect_text([]) == ""


def test_parametro_text_existe_nas_funcoes_publicas():
    for funcao in (labdados.ocr, labdados.transcricao):
        parametros = inspect.signature(funcao).parameters
        assert "text" in parametros, funcao.__name__
        assert parametros["text"].default is False
        assert parametros["text"].kind is inspect.Parameter.KEYWORD_ONLY


def _zip_com(nome: str, conteudo: str) -> bytes:
    """Monta em memória um zip como o que a nuvem devolve."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(nome, conteudo)
    return buf.getvalue()


@respx.mock
def test_nuvem_com_text_devolve_o_texto_de_dentro_do_zip(tmp_path: Path):
    """Fluxo nuvem completo: com text=True, sai a string, não o caminho."""
    pdf = tmp_path / "acordao.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy bytes")
    saida = tmp_path / "out"

    from labdados.client import PUBLIC_BASE_URL as base

    respx.post(f"{base}/api/v1/uploads/sas").mock(
        return_value=httpx.Response(
            200,
            json={
                "upload_url": "https://sas.example/u?sig=x",
                "blob_path": "ocr/abc/acordao.pdf",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )
    )
    respx.put(re.compile(r"^https://sas\.example/u")).mock(
        return_value=httpx.Response(201)
    )
    respx.post(f"{base}/api/v1/requests").mock(
        return_value=httpx.Response(201, json={"id": "req-9", "status": "APPROVED"})
    )
    respx.get(f"{base}/api/v1/requests/req-9").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "req-9",
                "status": "COMPLETED",
                "result_url": "https://sas.example/r?sig=y",
            },
        )
    )
    respx.get(re.compile(r"^https://sas\.example/r")).mock(
        return_value=httpx.Response(
            200, content=_zip_com("acordao.txt", "ACORDAO. Vistos, relatados.")
        )
    )

    texto = labdados.ocr(
        arquivos=pdf,
        api_key="sk_lab_test",
        saida=saida,
        modelo="pymupdf-tesseract",
        text=True,
        progress=False,
    )

    assert isinstance(texto, str)
    assert texto == "ACORDAO. Vistos, relatados."
    # O zip continua em disco: text=True não tira o arquivo de ninguém.
    assert len(list(saida.glob("ocr_*.zip"))) == 1
