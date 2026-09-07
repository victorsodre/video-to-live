import json
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from video_to_live.serve import LiveHandler, MAX_UPLOAD
from http.server import ThreadingHTTPServer


class LocalServerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), LiveHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_rejects_foreign_host(self):
        status, _ = self.request("GET", "/", headers={"Host": "untrusted.example"})
        self.assertEqual(status, 403)

    def test_post_error_schema_preserves_legacy_alias(self):
        for path, legacy in (("/generate", False), ("/gerar", True)):
            with self.subTest(path=path, phase="preflight"):
                status, body = self.request("POST", path, b"x", {"Origin": "https://untrusted.example"})
                self.assertEqual(status, 403)
                payload = json.loads(body)
                self.assertEqual(payload["error"], "originNotAllowed")
                self.assertEqual("erro" in payload, legacy)
                if legacy:
                    self.assertEqual(payload["erro"], payload["error"])

            with self.subTest(path=path, phase="handler"):
                status, body = self.request("POST", path, b"x")
                self.assertEqual(status, 400)
                payload = json.loads(body)
                self.assertEqual(payload["error"], "formRequired")
                self.assertEqual("erro" in payload, legacy)
                if legacy:
                    self.assertEqual(payload["erro"], payload["error"])

    def test_rejects_oversized_upload_without_reading_it(self):
        status, _ = self.request("POST", "/gerar", headers={"Content-Length": str(MAX_UPLOAD + 1)})
        self.assertEqual(status, 413)

    def test_rejects_busy_conversion_without_reading_upload(self):
        slot = threading.BoundedSemaphore(1)
        slot.acquire()
        with patch.object(LiveHandler, "_conversion_slots", slot, create=True):
            status, _ = self.request("POST", "/gerar", b"x")
            self.assertEqual(status, 429)

    def test_local_page_still_works(self):
        status, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
