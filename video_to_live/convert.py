"""Turn a short video into a paired Live Photo still + MOV."""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path

from video_to_live.constants import STILL_TIME_SECONDS
from video_to_live.ffmpeg import encode_live_mov, extract_still_jpeg, probe_duration, require_ffmpeg
from video_to_live.inspect import assert_recipe
from video_to_live.mux import inject_live_photo_metadata
from video_to_live.pvt import write_pvt
from video_to_live.still import stamp_jpeg


class ConvertError(RuntimeError):
    pass


def safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^\w\s-]+", "-", stem, flags=re.UNICODE).strip(" .-_")
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    return (cleaned[:80] or "live").strip("-") or "live"


def resolve_range(
    start: float | None,
    end: float | None,
    source_duration: float | None = None,
) -> tuple[float, float | None]:
    start = 0.0 if start is None else float(start)
    if start < 0:
        raise ConvertError("start cannot be negative")
    if source_duration is not None and start >= source_duration:
        raise ConvertError("start is after the end of the video")
    if end is None:
        return start, None
    end = float(end)
    if source_duration is not None:
        end = min(end, source_duration)
    if end <= start:
        raise ConvertError("end must be after start")
    return start, end


def convert(
    source: Path,
    output_dir: Path | None = None,
    *,
    make_pvt: bool = True,
    asset_id: str | None = None,
    start: float | None = None,
    end: float | None = None,
    stem: str | None = None,
) -> dict[str, Path]:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ConvertError(f"video was not found: {source}")

    output_dir = (output_dir or source.parent).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    name = safe_stem(stem or source.stem)
    movie_path = output_dir / f"{name}.MOV"
    still_path = output_dir / f"{name}.HEIC"
    pvt_path = output_dir / f"{name}.pvt"
    identifier = (asset_id or str(uuid.uuid4())).upper()

    ffmpeg = require_ffmpeg()
    start, end = resolve_range(start, end, probe_duration(ffmpeg, source))
    with tempfile.TemporaryDirectory(prefix="video-to-live-") as tmp:
        tmpdir = Path(tmp)
        raw_mov = tmpdir / "encoded.mov"
        raw_jpg = tmpdir / "still.jpg"
        encode_live_mov(ffmpeg, source, raw_mov, start=start, end=end)
        extract_still_jpeg(ffmpeg, raw_mov, raw_jpg, STILL_TIME_SECONDS)
        inject_live_photo_metadata(raw_mov, movie_path, identifier)
        still_path.write_bytes(stamp_jpeg(raw_jpg.read_bytes(), identifier))

    outputs = {"mov": movie_path, "heic": still_path}
    if make_pvt:
        write_pvt(pvt_path, still_path, movie_path)
        outputs["pvt"] = pvt_path

    assert_recipe(movie_path, still_path, outputs.get("pvt"))
    return outputs
