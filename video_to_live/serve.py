"""Local page: pick a range, call the same ffmpeg+mux converter."""

from __future__ import annotations

import json
import math
import os
import socket
import sys
import tempfile
import threading
import webbrowser
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
MAX_UPLOAD = 128 * 1024 * 1024
UPLOAD_TIMEOUT = 15


class ServeError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, *args, **kwargs):
        self._connection_slots = threading.BoundedSemaphore(4)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


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
    value = float(raw)
    if not math.isfinite(value):
        raise ServeError("nonFiniteRange")
    return value


class LiveHandler(BaseHTTPRequestHandler):
    server_version = "video-to-live"
    _conversion_slots = threading.BoundedSemaphore(1)

    def setup(self):
        super().setup()
        self.connection.settimeout(UPLOAD_TIMEOUT)

    def _local_request(self) -> bool:
        port = self.server.server_address[1]
        allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        try:
            host = urlsplit("http://" + self.headers.get("Host", ""))
            host_origin = f"{host.scheme}://{host.netloc}"
            return host_origin in allowed and self.headers.get("Origin", host_origin) == host_origin
        except ValueError:
            return False

    def log_message(self, format, *args):  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if not self._local_request():
            self._json(403, {"error": "originNotAllowed"})
            return
        name = PAGES.get(self.path.split("?", 1)[0])
        if name is None:
            self._send(404, "Not found".encode("utf-8"), "text/plain; charset=utf-8")
            return
        path = WEB_DIR / name
        if not path.is_file():
            self._send(404, "Not found".encode("utf-8"), "text/plain; charset=utf-8")
            return
        self._send(200, path.read_bytes(), TYPES.get(path.suffix, "application/octet-stream"))

    def do_POST(self) -> None:  # noqa: N802
        if not self._local_request():
            self._json(403, {"error": "originNotAllowed"})
            return
        if self.path.split("?", 1)[0] not in {"/generate", "/gerar"}:
            self._json(404, {"error": "notFound"})
            return
        if not self._conversion_slots.acquire(blocking=False):
            self._json(429, {"error": "alreadyProcessing"})
            return
        try:
            self._gerar()
        except ServeError as error:
            self._json(error.status, {"error": str(error)})
        except (socket.timeout, TimeoutError):
            self._json(408, {"error": "uploadTimedOut"})
        except (ConvertError, FfmpegError, InspectError, MovError, StillError, ValueError):
            self._json(400, {"error": "conversionFailed"})
        except Exception:  # noqa: BLE001
            self._json(500, {"error": "conversionIncomplete"})
        finally:
            self._conversion_slots.release()

    def _gerar(self) -> None:
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            raise ServeError("invalidLength")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ServeError("missingVideo")
        if length > MAX_UPLOAD:
            raise ServeError("uploadLimit", 413)
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ServeError("formRequired")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ServeError("incompleteUpload")
        fields = _parse_multipart(content_type, body)
        upload = fields.get("video") or fields.get("file")
        if upload is None or not upload[1]:
            raise ServeError("missingVideo")
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
    if host not in {"127.0.0.1", "localhost"}:
        raise ServeError("The conversion page is available only on localhost.")
    if not WEB_DIR.is_dir():
        raise ServeError(f"Web directory is missing: {WEB_DIR}")
    httpd = BoundedHTTPServer(("127.0.0.1", port), LiveHandler)
    url = f"http://{host}:{httpd.server_port}/"
    print(f"Open {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
