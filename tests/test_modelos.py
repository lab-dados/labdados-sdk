"""Testes da resolução de modelos espelhados.

O download real não é exercitado aqui (67 MB); o que interessa é a lógica
de decisão: o que passa direto para o Hugging Face, o que vai para o
espelho, e o que já está em cache.
"""

from __future__ import annotations

import pytest

from labdados import _modelos


@pytest.fixture(autouse=True)
def _cache_isolado(tmp_path, monkeypatch):
    """Nenhum teste pode enxergar (nem sujar) o cache real do usuário."""
    monkeypatch.setenv("LABDADOS_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("LABDADOS_MODELOS_HF", raising=False)


def test_cache_dir_respeita_a_variavel_de_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("LABDADOS_CACHE", str(tmp_path / "outro"))
    assert _modelos.cache_dir() == tmp_path / "outro"


def test_caminho_de_pasta_passa_direto(tmp_path):
    pasta = tmp_path / "modelo-baixado-na-mao"
    pasta.mkdir()
    assert _modelos.resolver_modelo(str(pasta)) == str(pasta)


def test_modelo_nao_espelhado_passa_direto():
    # 'large-v3' não está no espelho: o faster-whisper resolve no HF.
    assert _modelos.resolver_modelo("large-v3") == "large-v3"


def test_repo_id_do_hugging_face_passa_direto():
    assert _modelos.resolver_modelo("Systran/faster-whisper-medium") == (
        "Systran/faster-whisper-medium"
    )


def test_variavel_de_ambiente_forca_o_hugging_face(monkeypatch):
    monkeypatch.setenv("LABDADOS_MODELOS_HF", "1")
    assert _modelos.resolver_modelo("tiny") == "tiny"


def test_cache_existente_evita_o_download(monkeypatch):
    destino = _modelos.cache_dir() / "faster-whisper-tiny"
    destino.mkdir(parents=True)

    def _nao_deveria_baixar(*args, **kwargs):
        raise AssertionError("baixou mesmo com o modelo em cache")

    monkeypatch.setattr(_modelos, "_baixar_e_extrair", _nao_deveria_baixar)
    assert _modelos.resolver_modelo("tiny") == str(destino)


def test_modelo_espelhado_baixa_uma_vez(monkeypatch):
    chamadas = []

    def _fake(url, destino, *, progress):
        chamadas.append(url)
        destino.mkdir(parents=True)
        (destino / "model.bin").write_bytes(b"fake")

    monkeypatch.setattr(_modelos, "_baixar_e_extrair", _fake)

    primeiro = _modelos.resolver_modelo("tiny", progress=False)
    segundo = _modelos.resolver_modelo("tiny", progress=False)

    assert primeiro == segundo
    assert len(chamadas) == 1
    assert chamadas[0].endswith("faster-whisper-tiny.zip")
    assert _modelos.ESPELHO_BASE in chamadas[0]
