"""Local page: pick a range, call the same ffmpeg+mux converter."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import webbrowser
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from video_to_live.convert import ConvertError, convert, safe_stem
from video_to_live.ffmpeg import FfmpegError
from video_to_live.inspect import InspectError
from video_to_live.mux import MovError
from video_to_live.pvt import zip_pvt
from video_to_live.still import StillError

WEB_DIR = Path(__file__).resolve().parent / "web"
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}
PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.css": "app.css",
    "/app.js": "app.js",
}
MAX_UPLOAD = 2 * 1024 * 1024 * 1024


class ServeError(RuntimeError):
    pass


def default_output_dir() -> Path:
    env = os.environ.get("VIDEO_TO_LIVE_OUT")
    if env:
        return Path(env).expanduser()
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads / "video-to-live"
    return Path.cwd() / "video-to-live-out"


def _parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:
    header = f"MIME-Version: 1.0\r\nContent-Type: {content_type}\r\n\r\n".encode("utf-8")
    message = message_from_bytes(header + body)
    fields: dict[str, tuple[str | None, bytes]] = {}
    if not message.is_multipart():
        return fields
    for part in message.walk():
        disposition = part.get("Content-Disposition", "")
        if "form-data" not in disposition:
            continue
        name = part.get_param("name", header="Content-Disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = part.get_payload()
            payload = payload.encode("utf-8") if isinstance(payload, str) else (payload or b"")
        fields[str(name)] = (unquote(filename) if filename else None, payload)
    return fields


def _float_field(fields: dict[str, tuple[str | None, bytes]], name: str) -> float | None:
    if name not in fields:
        return None
    raw = fields[name][1].decode("utf-8").strip().replace(",", ".")
    if not raw:
        return None
    return float(raw)


class LiveHandler(BaseHTTPRequestHandler):
    server_version = "video-to-live"

    def log_message(self, format, *args):  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        name = PAGES.get(self.path.split("?", 1)[0])
        if name is None:
            self._send(404, "não achei".encode("utf-8"), "text/plain; charset=utf-8")
            return
        path = WEB_DIR / name
        if not path.is_file():
            self._send(404, "não achei".encode("utf-8"), "text/plain; charset=utf-8")
            return
        self._send(200, path.read_bytes(), TYPES.get(path.suffix, "application/octet-stream"))

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/gerar":
            self._json(404, {"erro": "não achei"})
            return
        try:
            self._gerar()
        except (ConvertError, FfmpegError, InspectError, MovError, StillError, ServeError, ValueError) as error:
            self._json(400, {"erro": str(error)})
        except Exception as error:  # noqa: BLE001
            self._json(500, {"erro": f"falhou aqui: {error}"})

    def _gerar(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ServeError("não veio vídeo")
        if length > MAX_UPLOAD:
            raise ServeError("arquivo grande demais")
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ServeError("manda o vídeo no formulário")
        body = self.rfile.read(length)
        fields = _parse_multipart(content_type, body)
        upload = fields.get("video") or fields.get("file")
        if upload is None or not upload[1]:
            raise ServeError("solta um vídeo primeiro")
        filename, data = upload
        start = _float_field(fields, "start") or 0.0
        end = _float_field(fields, "end")
        stem = safe_stem(filename or "live")
        suffix = Path(filename or "clip.mp4").suffix or ".mp4"
        output_dir = default_output_dir()
        with tempfile.TemporaryDirectory(prefix="video-to-live-up-") as tmp:
            source = Path(tmp) / f"source{suffix}"
            source.write_bytes(data)
            outputs = convert(source, output_dir, start=start, end=end, stem=stem)
            zip_path = Path(tmp) / f"{stem}.pvt.zip"
            zip_pvt(outputs["pvt"], zip_path)
            payload = zip_path.read_bytes()
        saved = str(outputs["pvt"])
        self._send(
            200,
            payload,
            "application/zip",
            {
                "Content-Disposition": f'attachment; filename="{stem}.pvt.zip"',
                "X-Saved-To": saved,
            },
        )


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    if not WEB_DIR.is_dir():
        raise ServeError(f"faltou a pasta da página: {WEB_DIR}")
    httpd = ThreadingHTTPServer((host, port), LiveHandler)
    url = f"http://{host}:{httpd.server_port}/"
    print(f"abre {url}")
    print("Ctrl+C pra fechar.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nfechou.")
    finally:
        httpd.server_close()
