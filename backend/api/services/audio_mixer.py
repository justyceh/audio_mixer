"""Multi-track audio mixing with FFmpeg.

Used by both the ad-hoc `/api/audio/mix` endpoint and project exports. Each input is
trimmed, normalized to 44.1 kHz stereo float, gain-adjusted, faded and delayed onto a
shared timeline, then summed with `amix` (no automatic level normalization) and passed
through a limiter to avoid clipping where clips overlap.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from api.core.exceptions import BadRequestError, InvalidTimestampsError
from api.models import MediaAsset, MediaSource
from api.services import media_service
from api.utils import ffmpeg
from api.utils.paths import new_storage_file

SAMPLE_RATE = 44100
MAX_INPUTS = 64


@dataclass(frozen=True)
class MixInput:
    path: Path
    timeline_start: float
    source_start: float
    source_end: float
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0

    @property
    def length(self) -> float:
        return self.source_end - self.source_start


def _num(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def build_filter_graph(inputs: list[MixInput]) -> str:
    chains: list[str] = []
    labels: list[str] = []
    for i, item in enumerate(inputs):
        length = item.length
        fade_in = min(item.fade_in, length)
        fade_out = min(item.fade_out, length)
        filters = [
            f"atrim=start={_num(item.source_start)}:end={_num(item.source_end)}",
            "asetpts=PTS-STARTPTS",
            f"aresample={SAMPLE_RATE}",
            f"aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:channel_layouts=stereo",
            f"volume={_num(item.volume)}",
        ]
        if fade_in > 0:
            filters.append(f"afade=t=in:st=0:d={_num(fade_in)}")
        if fade_out > 0:
            filters.append(f"afade=t=out:st={_num(max(length - fade_out, 0))}:d={_num(fade_out)}")
        delay_ms = round(item.timeline_start * 1000)
        if delay_ms > 0:
            filters.append(f"adelay=delays={delay_ms}:all=1")
        label = f"a{i}"
        chains.append(f"[{i}:a:0]{','.join(filters)}[{label}]")
        labels.append(f"[{label}]")

    limiter = "alimiter=limit=0.97:level=0:latency=1"
    if len(inputs) == 1:
        chains.append(f"{labels[0]}{limiter}[out]")
    else:
        chains.append(f"{''.join(labels)}amix=inputs={len(inputs)}:duration=longest:normalize=0,{limiter}[out]")
    return ";".join(chains)


def build_mix_command(inputs: list[MixInput], output: Path, fmt: str) -> list[str]:
    if not inputs:
        raise BadRequestError("Nothing to mix")
    if len(inputs) > MAX_INPUTS:
        raise BadRequestError(f"At most {MAX_INPUTS} clips can be mixed at once")
    args: list[str] = []
    for item in inputs:
        args += ["-i", str(item.path)]
    args += [
        "-filter_complex", build_filter_graph(inputs),
        "-map", "[out]",
        "-ac", "2",
        "-ar", str(SAMPLE_RATE),
        *ffmpeg.AUDIO_CODEC_ARGS[fmt],
        str(output),
    ]
    return args


def expected_duration(inputs: list[MixInput]) -> float:
    return max(item.timeline_start + item.length for item in inputs)


def render_mix(inputs: list[MixInput], output: Path, fmt: str) -> None:
    ffmpeg.run_ffmpeg(build_mix_command(inputs, output, fmt))


def make_mix_input(
    asset: MediaAsset,
    *,
    timeline_start: float,
    source_start: float,
    source_end: float | None,
    volume: float,
    fade_in: float,
    fade_out: float,
    label: str,
) -> MixInput:
    media_service.require_audio(asset)
    try:
        start, end = media_service.validate_time_range(source_start, source_end, asset.duration)
    except InvalidTimestampsError as exc:
        raise InvalidTimestampsError(f"{label}: {exc.message}", details=exc.details) from exc
    return MixInput(
        path=media_service.media_file_path(asset),
        timeline_start=timeline_start,
        source_start=start,
        source_end=end,
        volume=volume,
        fade_in=fade_in,
        fade_out=fade_out,
    )


def resolve_mix_tracks(db: Session, tracks: list[dict]) -> list[MixInput]:
    """Turn request track dicts (MixTrack fields) into validated MixInputs."""
    inputs = []
    for index, track in enumerate(tracks):
        asset = media_service.get_media(db, uuid.UUID(str(track["media_id"])))
        inputs.append(
            make_mix_input(
                asset,
                timeline_start=float(track.get("start_time") or 0),
                source_start=float(track.get("source_start") or 0),
                source_end=track.get("source_end"),
                volume=float(track.get("volume", 1.0)),
                fade_in=float(track.get("fade_in") or 0),
                fade_out=float(track.get("fade_out") or 0),
                label=f"tracks[{index}]",
            )
        )
    return inputs


def mix_to_asset(
    db: Session,
    inputs: list[MixInput],
    *,
    fmt: str,
    area: str,
    original_filename: str,
    source: MediaSource,
) -> MediaAsset:
    """Render a mix into a new storage file and record it (commits)."""
    stored, relative, absolute = new_storage_file(area, fmt)
    with media_service.delete_files_on_error([absolute]):
        render_mix(inputs, absolute, fmt)
        asset = media_service.register_output(
            db,
            stored_filename=stored,
            relative_path=relative,
            absolute_path=absolute,
            original_filename=original_filename,
            source=source,
        )
        db.commit()
    return asset
