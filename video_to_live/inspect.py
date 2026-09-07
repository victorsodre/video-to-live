"""Assert the lock-screen recipe that already passed on device."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from video_to_live.constants import (
    CONTAINER_DURATION,
    CONTENT_IDENTIFIER_KEY,
    FRAME_COUNT,
    HEIGHT,
    INFO_EMPTY_EDIT,
    INFO_SAMPLE_COUNT,
    INFO_SAMPLE_DELTA,
    INFO_SAMPLES_PER_CHUNK,
    INFO_TIMESCALE,
    LIVE_PHOTO_AUTO_KEY,
    LIVE_PHOTO_INFO_KEY,
    LIVE_PHOTO_INFO_SAMPLE,
    MVHD_DURATION,
    STILL_EMPTY_EDIT,
    STILL_IMAGE_SAMPLE,
    STILL_IMAGE_TIME_KEY,
    TIMESCALE,
    VIDEO_MDHD_DURATION,
    VIDEO_STTS,
    VITALITY_SCORE_KEY,
    VITALITY_VERSION_KEY,
    WIDTH,
)
from video_to_live.ffmpeg import run_media_process
from video_to_live.mux import describe_mebx, describe_video_track, read_mvhd, read_quicktime_keys
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
        raise InspectError("ffprobe was not found")
    result = run_media_process(
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
        timeout=30,
    )
    if result.returncode != 0:
        raise InspectError(result.stderr.strip() or "ffprobe failed")
    return json.loads(result.stdout)


def inspect_pair(movie: Path, still: Path | None = None, pvt: Path | None = None) -> list[Check]:
    info = _ffprobe(movie)
    video = next((stream for stream in info.get("streams", []) if stream.get("codec_type") == "video"), None)
    if video is None:
        return [Check(False, "video track", "ffprobe did not detect video")]

    codec = video.get("codec_name")
    tag = video.get("codec_tag_string")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    nb_frames = video.get("nb_read_packets") or video.get("nb_frames")
    try:
        frames = int(nb_frames) if nb_frames not in (None, "N/A") else None
    except ValueError:
        frames = None
    header = movie.read_bytes()[:32]
    brand = header[8:12].decode("latin1") if header[4:8] == b"ftyp" else ""
    pix_fmt = video.get("pix_fmt")
    handler = video.get("tags", {}).get("handler_name", "")
    timescale, mvhd_duration = read_mvhd(movie)
    container = mvhd_duration / timescale if timescale else 0.0

    keys = read_quicktime_keys(movie)
    identifier = keys.get(CONTENT_IDENTIFIER_KEY, b"").decode("ascii", "replace")
    mebx = describe_mebx(movie)
    info_track = next((track for track in mebx if LIVE_PHOTO_INFO_KEY in track["keys"]), None)
    still_track = next((track for track in mebx if STILL_IMAGE_TIME_KEY in track["keys"]), None)
    video_track = describe_video_track(movie)
    info_stsc = (
        ((1, INFO_SAMPLES_PER_CHUNK, 1), (2, INFO_SAMPLES_PER_CHUNK, 1))
        if info_track
        else ()
    )

    checks = [
        Check(codec == "hevc" and tag == "hvc1", "HEVC hvc1", f"{codec}/{tag}"),
        Check(width == WIDTH and height == HEIGHT, f"{WIDTH}x{HEIGHT}", f"{width}x{height}"),
        Check(
            timescale == TIMESCALE and mvhd_duration == MVHD_DURATION,
            f"container {CONTAINER_DURATION}s (mvhd {MVHD_DURATION}/{TIMESCALE})",
            f"{container:.3f}s ({mvhd_duration}/{timescale})",
        ),
        Check(frames is None or frames == FRAME_COUNT, f"{FRAME_COUNT} quadros", str(frames)),
        Check(pix_fmt == "yuv420p", "yuv420p", str(pix_fmt)),
        Check(brand.strip() == "qt", "marca qt", brand or "(vazia)"),
        Check("Core Media Video" in handler, "hdlr Core Media Video", handler or "(vazio)"),
        Check(
            video_track["hdlr_type"] == b"mhlr"
            and video_track["subtype"] == b"vide"
            and video_track["manufacturer"] == b"appl"
            and video_track["name"] == "Core Media Video",
            "hdlr mhlr+vide+appl",
            f"{video_track['hdlr_type']!r}+{video_track['subtype']!r}+{video_track['manufacturer']!r}",
        ),
        Check(video_track["tkhd_flags"] == 0x0F, "tkhd flags 0x0F", hex(int(video_track["tkhd_flags"]))),
        Check(
            video_track["mdhd_duration"] == VIDEO_MDHD_DURATION and video_track["language"] == 0x55C4,
            f"video mdhd {VIDEO_MDHD_DURATION} lang 0x55C4",
            f"{video_track['mdhd_duration']} lang {int(video_track['language']):#x}",
        ),
        Check(tuple(video_track["stts"]) == VIDEO_STTS, "video stts 59×10 + 1×30", str(video_track["stts"])),
        Check(bool(identifier), CONTENT_IDENTIFIER_KEY, identifier or "ausente"),
        Check(
            LIVE_PHOTO_AUTO_KEY in keys and keys[LIVE_PHOTO_AUTO_KEY] == b"\x01",
            LIVE_PHOTO_AUTO_KEY,
            "1" if LIVE_PHOTO_AUTO_KEY in keys else "ausente",
        ),
        Check(
            VITALITY_SCORE_KEY not in keys and VITALITY_VERSION_KEY not in keys,
            "sem vitality-score",
            "ok" if VITALITY_SCORE_KEY not in keys else "presente",
        ),
        Check(
            info_track is not None
            and info_track["samples"] == INFO_SAMPLE_COUNT
            and info_track["sample_size"] == len(LIVE_PHOTO_INFO_SAMPLE)
            and info_track["timescale"] == INFO_TIMESCALE
            and info_track["stts"] == [(INFO_SAMPLE_COUNT, INFO_SAMPLE_DELTA)]
            and tuple(info_track["stsc"]) == info_stsc
            and info_track["empty_edit"] == INFO_EMPTY_EDIT
            and info_track["first_sample"] == LIVE_PHOTO_INFO_SAMPLE,
            f"mebx live-photo-info ({INFO_SAMPLE_COUNT} samples)",
            str(info_track["samples"]) if info_track else "ausente",
        ),
        Check(
            still_track is not None
            and still_track["samples"] == 1
            and still_track["sample_size"] == len(STILL_IMAGE_SAMPLE)
            and still_track["empty_edit"] == STILL_EMPTY_EDIT
            and still_track["first_sample"] == STILL_IMAGE_SAMPLE,
            "mebx still-image-time",
            "ok" if still_track else "ausente",
        ),
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

    if pvt is not None:
        names = sorted(child.name for child in pvt.iterdir()) if pvt.is_dir() else []
        plist = pvt / "metadata.plist"
        body = plist.read_text(encoding="utf-8") if plist.is_file() else ""
        checks.append(Check(pvt.is_dir(), "pasta .pvt", str(pvt)))
        checks.append(
            Check(
                "<string>1</string>" in body and "PFVideoComplementMetadataVersionKey" in body,
                "plist PFVideoComplementMetadataVersionKey string 1",
                "ok" if "<string>1</string>" in body else body[:80] or "faltou plist",
            )
        )
        checks.append(
            Check(
                any(name.upper().endswith(".HEIC") for name in names)
                and any(name.upper().endswith(".MOV") for name in names),
                ".pvt com HEIC+MOV",
                ", ".join(names) or "vazia",
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


def assert_recipe(movie: Path, still: Path | None = None, pvt: Path | None = None) -> str:
    checks = inspect_pair(movie, still, pvt)
    report = format_report(checks)
    if not all(check.ok for check in checks):
        raise InspectError("output does not match the recipe:\n" + report)
    return report
