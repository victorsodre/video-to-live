"""ffmpeg encode: 1080x1920, 1s, 60fps, libx265 hvc1, QuickTime qt."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from video_to_live.constants import (
    CONTAINER_DURATION,
    CRF,
    ENCODE_DURATION,
    FRAME_COUNT,
    FPS,
    HEIGHT,
    TIMESCALE,
    WIDTH,
)

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


def run_media_process(cmd: list[str], *, check: bool = False, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise FfmpegError("o processamento de mídia excedeu o limite de tempo") from error


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FfmpegError("não achei o ffmpeg no PATH")
    encoders = run_media_process(
        [path, "-hide_banner", "-encoders"],
        check=True,
        timeout=30,
    ).stdout
    if "libx265" not in encoders:
        raise FfmpegError("ffmpeg sem libx265 — precisa de HEVC pra iOS aceitar")
    return path


def _run(cmd: list[str]) -> None:
    result = run_media_process(cmd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = "\n".join(detail[-12:])
        raise FfmpegError(f"ffmpeg falhou ({result.returncode}):\n{tail}")


def probe_duration(ffmpeg: str, source: Path) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        sibling = Path(ffmpeg).with_name("ffprobe")
        probe = str(sibling) if sibling.is_file() else None
    if not probe:
        return None
    result = run_media_process(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _fit() -> str:
    return (
        f"fps={FPS},"
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )


def _finish(pad: bool) -> str:
    parts = []
    if pad:
        parts.append(f"tpad=stop_mode=clone:stop_duration={ENCODE_DURATION:g}")
    parts.append(f"trim=duration={ENCODE_DURATION:g}")
    parts.append("setpts=N/FRAME_RATE/TB")
    return ",".join(parts)


def build_video_filter(start: float = 0.0, end: float | None = None) -> str:
    """Map a source range onto the 1s / 60-frame encode the muxer expects.

    Longer than ~1.05s is time-squeezed. Shorter keeps speed and pads.
    """
    start = max(0.0, float(start))
    fit = _fit()
    finish_pad = _finish(pad=True)

    if end is None:
        if start <= 0:
            return f"{fit},{finish_pad}"
        return f"trim=start={start:.6f},setpts=PTS-STARTPTS,{fit},{finish_pad}"

    end = float(end)
    selected = end - start
    if selected <= 0:
        raise FfmpegError("o fim tem que ser depois do início")

    trimmed = f"trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS"
    if selected > CONTAINER_DURATION:
        factor = ENCODE_DURATION / selected
        return f"{trimmed},setpts=PTS*{factor:.10f},{fit},{_finish(pad=False)}"
    return f"{trimmed},{fit},{finish_pad}"


def encode_live_mov(
    ffmpeg: str,
    source: Path,
    destination: Path,
    *,
    start: float = 0.0,
    end: float | None = None,
) -> None:
    vf = build_video_filter(start, end)
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


def make_demo_clip(ffmpeg: str, destination: Path, duration: float | None = None) -> None:
    """Original procedural motion. No third-party IP."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    seconds = ENCODE_DURATION if duration is None else float(duration)
    vf = (
        f"hue=h='360*t':s=1.15,"
        f"drawbox=x='iw/2-90+320*sin(2*PI*t)':y='ih/2-90+220*cos(2*PI*t)':"
        f"w=180:h=180:color=white@0.88:t=fill,"
        f"drawbox=x='180+220*cos(2*PI*t*1.35)':y='420+480*sin(2*PI*t)':"
        f"w=140:h=140:color=0xff6b35@0.9:t=fill,"
        f"drawbox=x='640+140*sin(2*PI*t*0.7)':y='1180+260*cos(2*PI*t*1.1)':"
        f"w=220:h=90:color=0x4ecdc4@0.85:t=fill"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x12263a:s={WIDTH}x{HEIGHT}:d={seconds:g}:r={FPS}",
        "-vf",
        vf,
        "-r",
        str(FPS),
        "-t",
        str(seconds),
    ]
    if duration is None:
        cmd.extend(["-frames:v", str(FRAME_COUNT)])
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(destination),
        ]
    )
    _run(cmd)
