"""Command-line interface for video-to-live."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from video_to_live import __version__
from video_to_live.convert import ConvertError, convert
from video_to_live.ffmpeg import FfmpegError, make_demo_clip, require_ffmpeg
from video_to_live.inspect import InspectError, assert_recipe
from video_to_live.mux import MovError
from video_to_live.still import StillError

HELP = """\
Turn a short video into an iPhone Lock Screen Live Photo.

examples:
  video-to-live serve
  video-to-live clip.mp4
  video-to-live clip.mp4 --start 2.4 --end 8.1
  video-to-live --make-demo demo/orbits.mp4
"""


class EnglishHelp(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions, groups, prefix if prefix is not None else "usage: ")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-to-live",
        description="Turn a short video into an iPhone Lock Screen Live Photo.",
        epilog="Open the local page with `serve` to choose a clip. AirDrop the .pvt folder to Photos, not Files, a standalone zip, or separate JPG+MOV files.",
        formatter_class=EnglishHelp,
        add_help=False,
    )
    parser._positionals.title = "input"
    parser._optionals.title = "options"
    parser.add_argument("input", nargs="?", help="input video (mp4, mov, …)")
    parser.add_argument("-o", "--output", help="output directory (default: beside the input video)")
    parser.add_argument("--start", type=float, default=None, metavar="S", help="clip start in seconds")
    parser.add_argument("--end", type=float, default=None, metavar="S", help="clip end in seconds")
    parser.add_argument("--sem-pvt", action="store_true", help="do not create the .pvt folder")
    parser.add_argument("--uuid", help="set content.identifier instead of generating one")
    parser.add_argument("--make-demo", metavar="FILE", help="create a one-second procedural demo clip without third-party IP")
    parser.add_argument("--check", nargs="+", metavar="FILE", help="verify MOV, HEIC, and PVT against the recipe")
    parser.add_argument("-h", "--help", action="help", help="show this help message")
    parser.add_argument("--version", action="version", version=f"video-to-live {__version__}", help="show the version")
    return parser


def _serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-to-live serve",
        description="Open the local page to choose a clip and create a Live Photo.",
        formatter_class=EnglishHelp,
        add_help=False,
    )
    parser._optionals.title = "options"
    parser.add_argument("--host", default="127.0.0.1", help="local only; default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="port (default: 8765)")
    parser.add_argument("--sem-browser", action="store_true", help="do not open a browser")
    parser.add_argument("-h", "--help", action="help", help="show this help message")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "serve":
        return _serve(argv[1:])
    args = _parser().parse_args(argv)
    try:
        if args.make_demo:
            ffmpeg = require_ffmpeg()
            path = Path(args.make_demo)
            make_demo_clip(ffmpeg, path)
            print(f"demo: {path}")
            return 0
        if args.check:
            movie = Path(args.check[0])
            still = Path(args.check[1]) if len(args.check) > 1 else None
            pvt = Path(args.check[2]) if len(args.check) > 2 else None
            print(assert_recipe(movie, still, pvt))
            return 0
        if not args.input:
            _parser().print_help()
            return 2
        outputs = convert(
            Path(args.input),
            Path(args.output) if args.output else None,
            make_pvt=not args.sem_pvt,
            asset_id=args.uuid,
            start=args.start,
            end=args.end,
        )
        print("Ready. AirDrop the .pvt folder to Photos, not Files.")
        if "pvt" in outputs:
            print(f"  PVT  {outputs['pvt']}")
        print(f"  MOV  {outputs['mov']}")
        print(f"  HEIC {outputs['heic']}  (JPEG/JFIF com MakerApple 17)")
        return 0
    except (ConvertError, FfmpegError, InspectError, MovError, StillError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _serve(argv: list[str]) -> int:
    from video_to_live.serve import ServeError, serve

    args = _serve_parser().parse_args(argv)
    try:
        serve(host=args.host, port=args.port, open_browser=not args.sem_browser)
        return 0
    except (OSError, ServeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
