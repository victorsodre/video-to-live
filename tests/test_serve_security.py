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
            response.read()
            return response.status
        finally:
            connection.close()

    def test_rejects_foreign_host(self):
        self.assertEqual(self.request("GET", "/", headers={"Host": "untrusted.example"}), 403)

    def test_rejects_cross_origin_form(self):
        self.assertEqual(self.request("POST", "/gerar", b"x", {"Origin": "https://untrusted.example"}), 403)

    def test_rejects_oversized_upload_without_reading_it(self):
        self.assertEqual(self.request("POST", "/gerar", headers={"Content-Length": str(MAX_UPLOAD + 1)}), 413)

    def test_rejects_busy_conversion_without_reading_upload(self):
        slot = threading.BoundedSemaphore(1)
        slot.acquire()
        with patch.object(LiveHandler, "_conversion_slots", slot, create=True):
            self.assertEqual(self.request("POST", "/gerar", b"x"), 429)

    def test_local_page_still_works(self):
        self.assertEqual(self.request("GET", "/"), 200)
