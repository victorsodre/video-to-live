"""ffmpeg encode: 1080x1920, 1s, 60fps, libx265 hvc1, QuickTime qt."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from video_to_live.constants import CRF, ENCODE_DURATION, FRAME_COUNT, FPS, HEIGHT, TIMESCALE, WIDTH

# Flags that actually matter for the lock-screen recipe. Everything else is padding.
FFMPEG_FLAGS_THAT_MATTER = (
    "-c:v libx265",
    "-tag:v hvc1",
    "-pix_fmt yuv420p",
    f"-r {FPS}",
    f"-t {ENCODE_DURATION:g}",
    f"-frames:v {FRAME_COUNT}",
    f"scale/pad {WIDTH}x{HEIGHT}",
    f"-movie_timescale {TIMESCALE}",
    f"-video_track_timescale {TIMESCALE}",
    "-brand qt",
    "-movflags +faststart",
    "-an",
)


class FfmpegError(RuntimeError):
    pass


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FfmpegError("não achei o ffmpeg no PATH")
    encoders = subprocess.run(
        [path, "-hide_banner", "-encoders"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if "libx265" not in encoders:
        raise FfmpegError("ffmpeg sem libx265 — precisa de HEVC pra iOS aceitar")
    return path


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = "\n".join(detail[-12:])
        raise FfmpegError(f"ffmpeg falhou ({result.returncode}):\n{tail}")


def encode_live_mov(ffmpeg: str, source: Path, destination: Path) -> None:
    vf = (
        f"fps={FPS},"
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1,"
        f"tpad=stop_mode=clone:stop_duration={ENCODE_DURATION:g},"
        f"trim=duration={ENCODE_DURATION:g},"
        "setpts=N/FRAME_RATE/TB"
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-an",
            "-vf",
            vf,
            "-r",
            str(FPS),
            "-t",
            str(ENCODE_DURATION),
            "-frames:v",
            str(FRAME_COUNT),
            "-c:v",
            "libx265",
            "-preset",
            "medium",
            "-crf",
            str(CRF),
            "-pix_fmt",
            "yuv420p",
            "-tag:v",
            "hvc1",
            "-x265-params",
            "log-level=error:repeat-headers=1",
            "-movie_timescale",
            str(TIMESCALE),
            "-video_track_timescale",
            str(TIMESCALE),
            "-brand",
            "qt",
            "-movflags",
            "+faststart",
            "-map_metadata",
            "-1",
            "-f",
            "mov",
            str(destination),
        ]
    )


def extract_still_jpeg(ffmpeg: str, source: Path, destination: Path, time_seconds: float) -> None:
    _run(
        [
            ffmpeg,
            "-y",
            "-ss",
            f"{time_seconds:.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(destination),
        ]
    )


def make_demo_clip(ffmpeg: str, destination: Path) -> None:
    """Original procedural motion. No third-party IP."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"hue=h='360*t':s=1.15,"
        f"drawbox=x='iw/2-90+320*sin(2*PI*t)':y='ih/2-90+220*cos(2*PI*t)':"
        f"w=180:h=180:color=white@0.88:t=fill,"
        f"drawbox=x='180+220*cos(2*PI*t*1.35)':y='420+480*sin(2*PI*t)':"
        f"w=140:h=140:color=0xff6b35@0.9:t=fill,"
        f"drawbox=x='640+140*sin(2*PI*t*0.7)':y='1180+260*cos(2*PI*t*1.1)':"
        f"w=220:h=90:color=0x4ecdc4@0.85:t=fill"
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x12263a:s={WIDTH}x{HEIGHT}:d={ENCODE_DURATION:g}:r={FPS}",
            "-vf",
            vf,
            "-r",
            str(FPS),
            "-t",
            str(ENCODE_DURATION),
            "-frames:v",
            str(FRAME_COUNT),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(destination),
        ]
    )
