"""Transcrição com diarização (separação de falantes) — modo nuvem.

Requer ``modelo='whisperx'``. O modo local não suporta diarização.

    python examples/03_transcricao_diarizacao.py audiencia.mp3 4
"""

import os
import sys

import labdados


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python 03_transcricao_diarizacao.py <audio> [num_falantes]")
    audio = sys.argv[1]
    num_falantes = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    saida = labdados.transcricao(
        arquivos=audio,
        api_key=os.environ["LABDADOS_API_KEY"],
        saida="transcricoes/",
        modelo="whisperx",
        diarizacao=True,
        num_falantes=num_falantes,
        idioma="pt",
        formato="srt",
    )
    print(f"Pronto. Resultado em {saida}/")


if __name__ == "__main__":
    main()
