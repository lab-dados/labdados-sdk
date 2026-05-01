"""
Indicador de progresso minimalista, sem dependências externas.

Não usamos rich/tqdm para manter o pacote leve — o usuário típico instala
o SDK em notebook do Jupyter ou Colab, onde uma linha textual atualizada
via ``\\r`` é suficiente. Pra mensagens longas (vários minutos esperando
worker subir), exibimos um spinner Unicode que rotaciona.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


@contextmanager
def spinner(message: str, *, enabled: bool = True) -> Iterator[None]:
    """Spinner de uma linha enquanto o bloco interno roda.

    Não usa thread — o caller deve chamar ``tick()`` periodicamente. Como o
    nosso uso é polling síncrono, gerimos o spinner manualmente entre os
    polls (ver ``_polling.poll_until``).
    """
    if not enabled:
        yield
        return
    start = time.time()
    try:
        yield
    finally:
        if enabled:
            print(
                f"\r✓ {message} ({time.time() - start:.1f}s){' ' * 20}",
                file=sys.stderr,
                flush=True,
            )


def render_status(message: str, *, frame: int) -> None:
    """Pinta uma linha de status com spinner. Sobrescreve a linha anterior."""
    glyph = _SPINNER[frame % len(_SPINNER)]
    print(f"\r{glyph} {message}", end="", file=sys.stderr, flush=True)


def clear_status() -> None:
    print("\r" + " " * 80 + "\r", end="", file=sys.stderr, flush=True)
