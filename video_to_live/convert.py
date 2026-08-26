"""Turn a short video into a paired Live Photo still + MOV."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from video_to_live.constants import STILL_TIME_SECONDS
from video_to_live.ffmpeg import encode_live_mov, extract_still_jpeg, require_ffmpeg
from video_to_live.inspect import assert_recipe
from video_to_live.mux import inject_live_photo_metadata
from video_to_live.pvt import write_pvt
from video_to_live.still import stamp_jpeg


class ConvertError(RuntimeError):
    pass


def convert(
    source: Path,
    output_dir: Path | None = None,
    *,
    make_pvt: bool = True,
    asset_id: str | None = None,
) -> dict[str, Path]:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ConvertError(f"não achei o vídeo: {source}")

    output_dir = (output_dir or source.parent).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    movie_path = output_dir / f"{stem}.MOV"
    still_path = output_dir / f"{stem}.HEIC"
    pvt_path = output_dir / f"{stem}.pvt"
    identifier = (asset_id or str(uuid.uuid4())).upper()

    ffmpeg = require_ffmpeg()
    with tempfile.TemporaryDirectory(prefix="video-to-live-") as tmp:
        tmpdir = Path(tmp)
        raw_mov = tmpdir / "encoded.mov"
        raw_jpg = tmpdir / "still.jpg"
        encode_live_mov(ffmpeg, source, raw_mov)
        extract_still_jpeg(ffmpeg, raw_mov, raw_jpg, STILL_TIME_SECONDS)
        inject_live_photo_metadata(raw_mov, movie_path, identifier)
        still_path.write_bytes(stamp_jpeg(raw_jpg.read_bytes(), identifier))

    outputs = {"mov": movie_path, "heic": still_path}
    if make_pvt:
        write_pvt(pvt_path, still_path, movie_path)
        outputs["pvt"] = pvt_path

    assert_recipe(movie_path, still_path)
    return outputs
