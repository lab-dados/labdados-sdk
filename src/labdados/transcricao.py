"""
Transcrição de áudio com Whisper (e opcionalmente diarização com pyannote).

Modo nuvem
----------
Whisper Large V3 Turbo (rápido) ou WhisperX (timestamps a nível de palavra
+ diarização integrada).

Modo local
----------
Usa ``faster-whisper`` em CPU ou GPU. Diarização local não é suportada por
default — o extra ``[transcricao]`` traz só ``faster-whisper`` para manter
o footprint pequeno.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from labdados._io import PathLike, ensure_output_dir, resolve_inputs
from labdados.client import Client
from labdados.exceptions import LocalDependencyMissing

OUTPUT_FORMAT = Literal["txt", "srt", "vtt"]
MODELO_NUVEM = Literal["whisper-large-v3-turbo", "whisperx"]
ACCEPTED_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma")


def transcricao(
    arquivos: PathLike | list[PathLike],
    *,
    saida: PathLike | None = None,
    api_key: str | None = None,
    modelo: str = "whisper-large-v3-turbo",
    idioma: str = "pt",
    diarizacao: bool = False,
    num_falantes: int = 0,
    formato: OUTPUT_FORMAT = "srt",
    timestamps: bool = True,
    beam_size: int = 5,
    local: bool = False,
    modelo_local: str = "large-v3",
    client: Client | None = None,
    progress: bool = True,
) -> Path:
    """Transcreve áudio para texto/legenda.

    Parameters
    ----------
    arquivos
        Arquivo único, lista, ou pasta com áudios.
    saida
        Pasta de saída.
    api_key
        Chave de API (modo nuvem).
    modelo
        Modelo na nuvem: ``"whisper-large-v3-turbo"`` (rápido) ou
        ``"whisperx"`` (timestamps + diarização).
    idioma
        ISO 639-1 ou ``"auto"``. Default: português.
    diarizacao
        Se ``True``, separa falantes (``SPEAKER_00``, ``SPEAKER_01``...).
        Requer ``modelo="whisperx"`` na nuvem.
    num_falantes
        Estimativa de quantas pessoas falam (``0`` = detectar). Só vale
        com ``diarizacao=True``.
    formato
        ``"txt"``, ``"srt"`` (default), ou ``"vtt"``.
    timestamps
        Inclui ``[hh:mm:ss]`` no início de cada trecho (``txt`` apenas —
        ``srt``/``vtt`` sempre têm timestamps).
    beam_size
        Beam search do Whisper. Default 5; só mexa se houver erros sistemáticos.
    local
        Se ``True``, usa ``faster-whisper`` no próprio computador. Requer
        ``pip install labdados[transcricao]``. Diarização local não
        suportada (use modo nuvem ou pyannote separado).
    modelo_local
        Modelo do faster-whisper (``"tiny"``, ``"base"``, ``"small"``,
        ``"medium"``, ``"large-v3"``). Mais alto = mais preciso e mais
        lento; ``large-v3`` precisa de ~10GB de VRAM em GPU ou bastante RAM.
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
    Modo nuvem com diarização:

    >>> import labdados
    >>> labdados.transcricao(
    ...     arquivos="audios/",
    ...     api_key="sk_lab_...",
    ...     modelo="whisperx",
    ...     diarizacao=True,
    ...     formato="srt",
    ... )

    Modo local com modelo small em CPU:

    >>> labdados.transcricao(
    ...     arquivos="reuniao.mp3",
    ...     local=True,
    ...     modelo_local="small",
    ...     idioma="pt",
    ... )
    """
    # Valida configurações antes de tocar no filesystem ou na rede — assim
    # erros de assinatura aparecem instantaneamente.
    if not local and diarizacao and modelo == "whisper-large-v3-turbo":
        raise ValueError(
            "Diarização requer modelo='whisperx'. O whisper-large-v3-turbo "
            "não tem pipeline de diarização."
        )

    audios = resolve_inputs(arquivos, extensoes=ACCEPTED_EXTENSIONS)
    saida_dir = ensure_output_dir(saida)

    if local:
        return _trans_local(
            audios,
            saida_dir=saida_dir,
            modelo=modelo_local,
            idioma=idioma,
            formato=formato,
            timestamps=timestamps,
            beam_size=beam_size,
            progress=progress,
        )

    return _trans_remote(
        audios,
        saida_dir=saida_dir,
        api_key=api_key,
        client=client,
        modelo=modelo,
        idioma=idioma,
        diarizacao=diarizacao,
        num_falantes=num_falantes,
        formato=formato,
        timestamps=timestamps,
        beam_size=beam_size,
        progress=progress,
    )


def _trans_remote(
    audios: list[Path],
    *,
    saida_dir: Path,
    api_key: str | None,
    client: Client | None,
    modelo: str,
    idioma: str,
    diarizacao: bool,
    num_falantes: int,
    formato: str,
    timestamps: bool,
    beam_size: int,
    progress: bool,
) -> Path:
    cli = client or Client(api_key=api_key, progress=progress)
    files_meta = cli._upload_files("transcription", audios)
    config: dict[str, Any] = {
        "language": idioma,
        "diarization": diarizacao,
        "num_speakers": num_falantes,
        "include_timestamps": timestamps,
        "output_format": formato,
        "beam_size": beam_size,
    }
    req = cli._post(
        "/api/v1/requests",
        {
            "service_id": "transcription",
            "model_id": modelo,
            "config": config,
            "files_metadata": files_meta,
        },
    )
    final = cli._poll_request(req["id"], label="transcrição no escritório")
    cli._download(final["result_url"], saida_dir / f"transcricao_{req['id'][:8]}.zip")
    return saida_dir


def _trans_local(
    audios: list[Path],
    *,
    saida_dir: Path,
    modelo: str,
    idioma: str,
    formato: str,
    timestamps: bool,
    beam_size: int,
    progress: bool,
) -> Path:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise LocalDependencyMissing(
            "Transcrição local requer:\n    pip install labdados[transcricao]"
        ) from exc

    from labdados._progress import clear_status, render_status

    if progress:
        render_status(f"carregando faster-whisper:{modelo}...", frame=0)
    # CPU por default — simples; se o usuário tiver CUDA, faster-whisper
    # detecta automaticamente quando ``device="auto"``.
    model = WhisperModel(modelo, device="auto", compute_type="default")
    if progress:
        clear_status()

    for i, audio in enumerate(audios, start=1):
        if progress:
            render_status(f"transcrevendo {i}/{len(audios)}: {audio.name}", frame=i)
        segments, _info = model.transcribe(
            str(audio),
            language=None if idioma == "auto" else idioma,
            beam_size=beam_size,
        )
        out_path = saida_dir / f"{audio.stem}.{formato}"
        with out_path.open("w", encoding="utf-8") as f:
            if formato == "txt":
                for seg in segments:
                    if timestamps:
                        ts = _fmt_timestamp(seg.start)
                        f.write(f"[{ts}] {seg.text.strip()}\n")
                    else:
                        f.write(seg.text.strip() + "\n")
            elif formato in ("srt", "vtt"):
                if formato == "vtt":
                    f.write("WEBVTT\n\n")
                for n, seg in enumerate(segments, start=1):
                    f.write(f"{n}\n")
                    f.write(
                        f"{_fmt_srt(seg.start, vtt=formato == 'vtt')} --> "
                        f"{_fmt_srt(seg.end, vtt=formato == 'vtt')}\n"
                    )
                    f.write(seg.text.strip() + "\n\n")
    if progress:
        clear_status()
    return saida_dir


def _fmt_timestamp(secs: float) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_srt(secs: float, *, vtt: bool) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    sep = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{int(s):02d}{sep}{int((s - int(s)) * 1000):03d}"
