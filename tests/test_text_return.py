"""Testes do retorno em texto (``text=True``).

Cobrem o helper ``collect_text`` (arquivos soltos e ``.zip``, que é o
formato devolvido pela nuvem) e a presença do parâmetro nas funções
públicas. O caminho local do Whisper/Tesseract não é exercitado aqui
porque depende de binários e modelos.
"""

from __future__ import annotations

import inspect
import zipfile

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
