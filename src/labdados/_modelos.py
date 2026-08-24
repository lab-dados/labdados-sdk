"""
Resolução dos modelos usados na transcrição local.

O ``faster-whisper`` baixa os modelos do Hugging Face. Requisições anônimas
vindas de IPs de datacenter (Google Colab, runners de CI) são barradas por
rate limit, e quem chamou vê um pedido de ``HF_TOKEN`` que não tem. Isso
quebra justamente o cenário "só quero rodar sem instalar nada".

Por isso espelhamos os modelos pequenos nas releases deste repositório e
resolvemos o nome para um diretório local antes de entregar ao
``faster-whisper``, que aceita tanto um ``repo_id`` do Hugging Face quanto
um caminho de pasta.

Nomes fora de ``MODELOS_ESPELHADOS`` passam direto, e continuam sendo
resolvidos pelo Hugging Face como sempre foram.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

import httpx

from labdados.exceptions import LabdadosError

ESPELHO_BASE = "https://github.com/lab-dados/labdados-sdk/releases/download/modelos-v1"

#: Modelos servidos por nós. O valor é o nome do asset na release.
MODELOS_ESPELHADOS = {
    "tiny": "faster-whisper-tiny.zip",
}


def cache_dir() -> Path:
    """Pasta onde os modelos espelhados ficam guardados.

    Pode ser trocada com a variável de ambiente ``LABDADOS_CACHE``.
    """
    raiz = os.environ.get("LABDADOS_CACHE")
    if raiz:
        return Path(raiz).expanduser()
    return Path.home() / ".cache" / "labdados" / "modelos"


def resolver_modelo(nome: str, *, progress: bool = True) -> str:
    """Devolve algo que o ``faster-whisper`` saiba carregar.

    A ordem de resolução é:

    1. Se ``nome`` é uma pasta que existe, devolve como está.
    2. Se ``LABDADOS_MODELOS_HF`` está setada, devolve como está (força o
       caminho antigo, via Hugging Face).
    3. Se ``nome`` está entre os modelos espelhados, baixa da release
       (uma vez só, fica em cache) e devolve o caminho da pasta.
    4. Caso contrário, devolve como está, e o Hugging Face resolve.

    Parameters
    ----------
    nome
        Nome curto do modelo (``"tiny"``), ``repo_id`` do Hugging Face ou
        caminho de uma pasta.
    progress
        Imprime no stderr o andamento do download.

    Returns
    -------
    str
        Caminho de pasta ou o próprio ``nome``.
    """
    if Path(nome).is_dir():
        return nome
    if os.environ.get("LABDADOS_MODELOS_HF"):
        return nome
    asset = MODELOS_ESPELHADOS.get(nome)
    if asset is None:
        return nome

    destino = cache_dir() / f"faster-whisper-{nome}"
    if destino.is_dir():
        return str(destino)

    _baixar_e_extrair(f"{ESPELHO_BASE}/{asset}", destino, progress=progress)
    return str(destino)


def _baixar_e_extrair(url: str, destino: Path, *, progress: bool) -> None:
    """Baixa um ``.zip`` e extrai em ``destino``, de forma atômica.

    O download e a extração acontecem em caminhos temporários, e só no fim
    o diretório é movido para o lugar definitivo. Assim uma interrupção no
    meio não deixa um cache pela metade, que seria pior do que cache nenhum.
    """
    from labdados._progress import clear_status, render_status

    destino.parent.mkdir(parents=True, exist_ok=True)
    zip_tmp = destino.with_suffix(".zip.parcial")
    dir_tmp = destino.with_suffix(".parcial")

    try:
        if progress:
            render_status(f"baixando modelo {destino.name}...", frame=0)
        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            baixado = 0
            with open(zip_tmp, "wb") as f:
                for i, bloco in enumerate(r.iter_bytes(chunk_size=1024 * 256)):
                    f.write(bloco)
                    baixado += len(bloco)
                    if progress and total and i % 20 == 0:
                        pct = 100 * baixado // total
                        render_status(
                            f"baixando modelo {destino.name}: {pct}%", frame=i
                        )
        if progress:
            render_status(f"extraindo modelo {destino.name}...", frame=0)

        if dir_tmp.exists():
            shutil.rmtree(dir_tmp)
        with zipfile.ZipFile(zip_tmp) as z:
            z.extractall(dir_tmp)

        # O zip traz uma pasta raiz (faster-whisper-tiny/). Se for esse o
        # caso, sobe um nível para não criar pasta dentro de pasta.
        conteudo = list(dir_tmp.iterdir())
        raiz = conteudo[0] if len(conteudo) == 1 and conteudo[0].is_dir() else dir_tmp

        if destino.exists():
            shutil.rmtree(destino)
        shutil.move(str(raiz), str(destino))
    except httpx.HTTPError as exc:
        raise LabdadosError(
            f"Falha ao baixar o modelo de {url}: {exc}\n"
            "Se você tem acesso ao Hugging Face, force o caminho antigo com "
            "LABDADOS_MODELOS_HF=1."
        ) from exc
    finally:
        if progress:
            clear_status()
        zip_tmp.unlink(missing_ok=True)
        if dir_tmp.exists():
            shutil.rmtree(dir_tmp, ignore_errors=True)
