"""
Utilidades de IO: resolver inputs (pasta/lista/arquivo único) e gerir
diretórios de saída.

Mantenho aqui para que cada serviço (ocr, transcricao, ...) tenha exatamente
a mesma semântica de input — tanto faz `arquivos="pasta/"`,
`arquivos=["a.pdf", "b.pdf"]` ou `arquivos="unico.pdf"`.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

PathLike = str | os.PathLike[str]


def resolve_inputs(
    arquivos: PathLike | Iterable[PathLike],
    *,
    extensoes: tuple[str, ...],
    recursivo: bool = True,
) -> list[Path]:
    """Normaliza ``arquivos`` numa lista de ``Path`` existentes.

    Parameters
    ----------
    arquivos
        Pode ser:

        - ``str``/``Path`` apontando pra um **arquivo único**;
        - ``str``/``Path`` apontando pra uma **pasta** — varre todos os
          arquivos com extensão em ``extensoes``;
        - ``Iterable`` de paths (lista, tupla, generator).
    extensoes
        Tupla de extensões aceitas (com ponto, lowercase). Ex: ``(".pdf",)``.
    recursivo
        Se ``True`` (default), varre subpastas recursivamente quando
        ``arquivos`` é uma pasta.

    Returns
    -------
    list[Path]
        Lista ordenada e deduplicada.

    Raises
    ------
    FileNotFoundError
        Se um caminho informado não existe ou se a pasta não tem nenhum
        arquivo com extensão aceita.
    """
    if isinstance(arquivos, (str, os.PathLike)):
        path = Path(arquivos).expanduser()
        if path.is_dir():
            paths = _walk_dir(path, extensoes, recursivo)
            if not paths:
                raise FileNotFoundError(
                    f"Nenhum arquivo {extensoes} encontrado em '{path}'"
                )
            return paths
        if not path.exists():
            raise FileNotFoundError(f"'{path}' não existe")
        if path.suffix.lower() not in extensoes:
            raise FileNotFoundError(
                f"'{path}' tem extensão não aceita ({path.suffix}). Aceitas: {extensoes}"
            )
        return [path]

    out: list[Path] = []
    for item in arquivos:
        p = Path(item).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"'{p}' não existe")
        if p.is_dir():
            out.extend(_walk_dir(p, extensoes, recursivo))
        else:
            if p.suffix.lower() not in extensoes:
                raise FileNotFoundError(
                    f"'{p}' tem extensão não aceita ({p.suffix}). Aceitas: {extensoes}"
                )
            out.append(p)
    if not out:
        raise FileNotFoundError(f"Nenhum arquivo {extensoes} encontrado")
    # Preserva ordem mas remove duplicatas
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in out:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def _walk_dir(path: Path, extensoes: tuple[str, ...], recursivo: bool) -> list[Path]:
    pattern_iter = path.rglob("*") if recursivo else path.glob("*")
    return sorted(
        p for p in pattern_iter if p.is_file() and p.suffix.lower() in extensoes
    )


def ensure_output_dir(saida: PathLike | None) -> Path:
    """Cria (se preciso) e devolve o diretório de saída como ``Path``.

    Se ``saida`` for ``None``, usa ``./resultados_labdados/``.
    """
    out = Path(saida) if saida else Path("resultados_labdados")
    out = out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    return out
