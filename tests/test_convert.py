#!/usr/bin/env python3
import tempfile
import unittest
import uuid
from pathlib import Path

from video_to_live.convert import convert
from video_to_live.ffmpeg import FfmpegError, make_demo_clip, require_ffmpeg
from video_to_live.inspect import assert_recipe
from video_to_live.mux import mebx_keys, read_quicktime_keys


class ConvertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ffmpeg = require_ffmpeg()
        except FfmpegError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_demo_becomes_live_photo_recipe(self):
        asset_id = str(uuid.uuid4()).upper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            demo = root / "orbits.mp4"
            make_demo_clip(self.ffmpeg, demo)
            outputs = convert(demo, root / "out", asset_id=asset_id)
            report = assert_recipe(outputs["mov"], outputs["heic"])
            self.assertIn("ok", report)
            keys = read_quicktime_keys(outputs["mov"])
            self.assertEqual(keys["com.apple.quicktime.content.identifier"].decode("ascii"), asset_id)
            mebx = mebx_keys(outputs["mov"])
            self.assertIn("com.apple.quicktime.still-image-time", mebx)
            self.assertIn("com.apple.quicktime.video-orientation", mebx)
            self.assertTrue((outputs["pvt"] / "metadata.plist").is_file())
            self.assertIn(b"PFVideoComplementMetadataVersionKey", (outputs["pvt"] / "metadata.plist").read_bytes())


if __name__ == "__main__":
    unittest.main()
