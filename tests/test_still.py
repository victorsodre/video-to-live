#!/usr/bin/env python3
import unittest
import uuid

from video_to_live.still import read_asset_identifier, stamp_jpeg


class StillTests(unittest.TestCase):
    def test_makerapple_roundtrip(self):
        asset_id = str(uuid.uuid4()).upper()
        # SOI + tiny SOS + EOI is enough for the APP1 injector.
        jpeg = b"\xff\xd8\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\xff\xd9"
        stamped = stamp_jpeg(jpeg, asset_id)
        self.assertTrue(stamped.startswith(b"\xff\xd8"))
        self.assertEqual(read_asset_identifier(stamped), asset_id)
        self.assertIn(b"Apple iOS\x00", stamped)
        self.assertIn(asset_id.encode("ascii"), stamped)


if __name__ == "__main__":
    unittest.main()
