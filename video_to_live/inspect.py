"""Assert the working recipe: HEVC hvc1 1080x1920 ~1s + Live Photo pairing."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from video_to_live.constants import (
    CONTENT_IDENTIFIER_KEY,
    DURATION,
    FRAME_COUNT,
    HEIGHT,
    LIVE_PHOTO_AUTO_KEY,
    STILL_IMAGE_TIME_KEY,
    VIDEO_ORIENTATION_KEY,
    WIDTH,
)
from video_to_live.mux import mebx_keys, read_quicktime_keys
from video_to_live.still import read_asset_identifier


@dataclass
class Check:
    ok: bool
    title: str
    detail: str = ""


class InspectError(RuntimeError):
    pass


def _ffprobe(path: Path) -> dict:
    probe = shutil.which("ffprobe")
    if not probe:
        raise InspectError("não achei o ffprobe")
    result = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-count_packets",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise InspectError(result.stderr.strip() or "ffprobe falhou")
    return json.loads(result.stdout)


def inspect_pair(movie: Path, still: Path | None = None) -> list[Check]:
    info = _ffprobe(movie)
    video = next((stream for stream in info.get("streams", []) if stream.get("codec_type") == "video"), None)
    if video is None:
        return [Check(False, "trilha de vídeo", "ffprobe não viu vídeo")]

    codec = video.get("codec_name")
    tag = video.get("codec_tag_string")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    nb_frames = video.get("nb_read_packets") or video.get("nb_frames")
    try:
        frames = int(nb_frames) if nb_frames not in (None, "N/A") else None
    except ValueError:
        frames = None
    duration = float(video.get("duration") or info.get("format", {}).get("duration") or 0)
    header = movie.read_bytes()[:32]
    brand = header[8:12].decode("latin1") if header[4:8] == b"ftyp" else ""
    pix_fmt = video.get("pix_fmt")

    keys = read_quicktime_keys(movie)
    identifier = keys.get(CONTENT_IDENTIFIER_KEY, b"").decode("ascii", "replace")
    mebx = mebx_keys(movie)

    checks = [
        Check(codec == "hevc" and tag == "hvc1", "HEVC hvc1", f"{codec}/{tag}"),
        Check(width == WIDTH and height == HEIGHT, f"{WIDTH}x{HEIGHT}", f"{width}x{height}"),
        Check(abs(duration - DURATION) <= 0.15, f"~{DURATION:g}s", f"{duration:.3f}s"),
        Check(frames is None or abs(frames - FRAME_COUNT) <= 4, f"~{FRAME_COUNT} quadros", str(frames)),
        Check(pix_fmt == "yuv420p", "yuv420p", str(pix_fmt)),
        Check(brand.strip() == "qt", "marca qt", brand or "(vazia)"),
        Check(bool(identifier), CONTENT_IDENTIFIER_KEY, identifier or "ausente"),
        Check(LIVE_PHOTO_AUTO_KEY in keys and keys[LIVE_PHOTO_AUTO_KEY] == b"\x01", LIVE_PHOTO_AUTO_KEY, "1" if LIVE_PHOTO_AUTO_KEY in keys else "ausente"),
        Check(STILL_IMAGE_TIME_KEY in mebx, "mebx still-image-time", ", ".join(mebx) or "nenhuma"),
        Check(VIDEO_ORIENTATION_KEY in mebx, "mebx video-orientation (trilha inteira)", ", ".join(mebx) or "nenhuma"),
    ]

    if still is not None:
        if not still.exists():
            checks.append(Check(False, "still pareado", f"faltou {still}"))
        else:
            data = still.read_bytes()
            jpeg = data[:2] == b"\xff\xd8"
            still_id = read_asset_identifier(data) if jpeg else None
            checks.append(Check(jpeg, "still JPEG/JFIF (nome .HEIC)", "JPEG" if jpeg else f"assinatura {data[:12]!r}"))
            checks.append(
                Check(
                    bool(still_id) and still_id == identifier,
                    "MakerApple[17] = uuid do MOV",
                    still_id or "ausente",
                )
            )
    return checks


def format_report(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        mark = "ok" if check.ok else "falhou"
        extra = f"  ({check.detail})" if check.detail else ""
        lines.append(f"[{mark:>6}] {check.title}{extra}")
    return "\n".join(lines)


def assert_recipe(movie: Path, still: Path | None = None) -> str:
    checks = inspect_pair(movie, still)
    report = format_report(checks)
    if not all(check.ok for check in checks):
        raise InspectError("saída fora da receita:\n" + report)
    return report
