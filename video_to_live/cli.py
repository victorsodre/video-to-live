"""CLI in spoken Brazilian Portuguese."""

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
Transforma um vídeo curto em Live Photo pra lock screen do iPhone.

exemplos:
  video-to-live clipe.mp4
  video-to-live clipe.mp4 -o saida/
  video-to-live --make-demo demo/orbits.mp4
"""


class PortugueseHelp(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions, groups, prefix if prefix is not None else "uso: ")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-to-live",
        description="Transforma um vídeo curto em Live Photo pra lock screen do iPhone.",
        epilog="AirDrop a pasta .pvt e recebe no Fotos — não no Files, não zip, não JPG+MOV solto. O iOS que manda se anima. Receita que já passou no aparelho: HEVC hvc1, 1080x1920, container 1.05s.",
        formatter_class=PortugueseHelp,
        add_help=False,
    )
    parser._positionals.title = "entrada"
    parser._optionals.title = "opções"
    parser.add_argument("input", nargs="?", help="vídeo de entrada (mp4, mov, …)")
    parser.add_argument("-o", "--output", help="pasta de saída (padrão: ao lado do vídeo)")
    parser.add_argument("--sem-pvt", action="store_true", help="não monta a pasta .pvt")
    parser.add_argument("--uuid", help="força o content.identifier (senão gera um)")
    parser.add_argument("--make-demo", metavar="ARQUIVO", help="gera o clipe procedural de 1s (sem IP de terceiro)")
    parser.add_argument("--check", nargs="+", metavar="ARQUIVO", help="confere MOV HEIC PVT na receita")
    parser.add_argument("-h", "--help", action="help", help="mostra esta ajuda")
    parser.add_argument("--version", action="version", version=f"video-to-live {__version__}", help="mostra a versão")
    return parser


def main(argv: list[str] | None = None) -> int:
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
        )
        print("pronto. AirDrop a pasta .pvt pro Fotos (não pro Files).")
        if "pvt" in outputs:
            print(f"  PVT  {outputs['pvt']}")
        print(f"  MOV  {outputs['mov']}")
        print(f"  HEIC {outputs['heic']}  (JPEG/JFIF com MakerApple 17)")
        return 0
    except (ConvertError, FfmpegError, InspectError, MovError, StillError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
