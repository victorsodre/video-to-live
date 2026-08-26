#!/usr/bin/env python3
import tempfile
import unittest
import uuid
from pathlib import Path

from video_to_live.constants import LIVE_PHOTO_INFO_SAMPLE, STILL_IMAGE_SAMPLE
from video_to_live.convert import convert
from video_to_live.ffmpeg import FfmpegError, make_demo_clip, require_ffmpeg
from video_to_live.inspect import assert_recipe
from video_to_live.mux import describe_mebx, describe_video_track, read_mvhd, read_quicktime_keys


class ConvertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ffmpeg = require_ffmpeg()
        except FfmpegError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_demo_becomes_lock_screen_recipe(self):
        asset_id = str(uuid.uuid4()).upper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            demo = root / "orbits.mp4"
            make_demo_clip(self.ffmpeg, demo)
            outputs = convert(demo, root / "out", asset_id=asset_id)
            report = assert_recipe(outputs["mov"], outputs["heic"], outputs["pvt"])
            self.assertIn("ok", report)
            keys = read_quicktime_keys(outputs["mov"])
            self.assertEqual(keys["com.apple.quicktime.content.identifier"].decode("ascii"), asset_id)
            self.assertEqual(set(keys), {
                "com.apple.quicktime.content.identifier",
                "com.apple.quicktime.live-photo.auto",
            })
            timescale, duration = read_mvhd(outputs["mov"])
            self.assertEqual(timescale, 600)
            self.assertEqual(duration, 630)
            mebx = describe_mebx(outputs["mov"])
            info = next(track for track in mebx if "com.apple.quicktime.live-photo-info" in track["keys"])
            still = next(track for track in mebx if "com.apple.quicktime.still-image-time" in track["keys"])
            self.assertEqual(info["samples"], 60)
            self.assertEqual(info["sample_size"], 144)
            self.assertEqual(info["empty_edit"], 30)
            self.assertEqual(info["stsc"], [(1, 30, 1), (2, 30, 1)])
            self.assertEqual(info["first_sample"], LIVE_PHOTO_INFO_SAMPLE)
            self.assertEqual(still["samples"], 1)
            self.assertEqual(still["sample_size"], 89)
            self.assertEqual(still["empty_edit"], 300)
            self.assertEqual(still["first_sample"], STILL_IMAGE_SAMPLE)
            video = describe_video_track(outputs["mov"])
            self.assertEqual(video["name"], "Core Media Video")
            self.assertEqual(video["hdlr_type"], b"mhlr")
            self.assertEqual(video["manufacturer"], b"appl")
            self.assertEqual(video["stts"], [(59, 10), (1, 30)])
            self.assertEqual(video["mdhd_duration"], 620)
            self.assertEqual(video["language"], 0x55C4)
            self.assertTrue(outputs["pvt"].is_dir())
            plist = (outputs["pvt"] / "metadata.plist").read_text(encoding="utf-8")
            self.assertIn("<string>1</string>", plist)
            self.assertNotIn("<integer>1</integer>", plist)


if __name__ == "__main__":
    unittest.main()
