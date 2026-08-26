#!/usr/bin/env python3
import io
import os
import tempfile
import threading
import unittest
import uuid
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from video_to_live.convert import convert
from video_to_live.ffmpeg import FfmpegError, make_demo_clip, require_ffmpeg
from video_to_live.inspect import assert_recipe
from video_to_live.mux import describe_mebx
from video_to_live.serve import LiveHandler


class RangeAndServeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ffmpeg = require_ffmpeg()
        except FfmpegError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_squeezed_range_keeps_lock_screen_recipe(self):
        asset_id = str(uuid.uuid4()).upper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            demo = root / "long.mp4"
            make_demo_clip(self.ffmpeg, demo, duration=3.0)
            outputs = convert(demo, root / "out", asset_id=asset_id, start=0.4, end=2.8)
            assert_recipe(outputs["mov"], outputs["heic"], outputs["pvt"])
            mebx = describe_mebx(outputs["mov"])
            info = next(track for track in mebx if "com.apple.quicktime.live-photo-info" in track["keys"])
            self.assertEqual(info["samples"], 60)

    def test_serve_gerar_returns_pvt_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            demo = root / "orbits.mp4"
            make_demo_clip(self.ffmpeg, demo)
            os.environ["VIDEO_TO_LIVE_OUT"] = str(root / "saved")
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), LiveHandler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address[:2]
                page = HTTPConnection(host, port, timeout=60)
                page.request("GET", "/")
                home = page.getresponse()
                html = home.read().decode("utf-8")
                self.assertEqual(home.status, 200)
                self.assertIn("Gerar", html)
                self.assertIn("Tela de bloqueio usa ~1s", html)
                page.close()

                boundary = "----videotoliveboundary"
                payload = demo.read_bytes()
                body = (
                    (
                        f"--{boundary}\r\n"
                        'Content-Disposition: form-data; name="start"\r\n\r\n'
                        "0\r\n"
                        f"--{boundary}\r\n"
                        'Content-Disposition: form-data; name="end"\r\n\r\n'
                        "1\r\n"
                        f"--{boundary}\r\n"
                        'Content-Disposition: form-data; name="video"; filename="orbits.mp4"\r\n'
                        "Content-Type: video/mp4\r\n\r\n"
                    ).encode("utf-8")
                    + payload
                    + f"\r\n--{boundary}--\r\n".encode("utf-8")
                )
                conn = HTTPConnection(host, port, timeout=120)
                conn.request(
                    "POST",
                    "/gerar",
                    body=body,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Content-Length": str(len(body)),
                    },
                )
                response = conn.getresponse()
                data = response.read()
                self.assertEqual(response.status, 200, data[:500])
                self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    names = archive.namelist()
                self.assertTrue(any(name.endswith(".pvt/orbits.MOV") or name.endswith("orbits.MOV") for name in names))
                self.assertTrue(any(name.endswith("metadata.plist") for name in names))
                saved = Path(response.getheader("X-Saved-To"))
                self.assertTrue(saved.is_dir())
                conn.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                os.environ.pop("VIDEO_TO_LIVE_OUT", None)


if __name__ == "__main__":
    unittest.main()
