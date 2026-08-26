#!/usr/bin/env python3
import unittest

from video_to_live.constants import CONTAINER_DURATION
from video_to_live.convert import ConvertError, resolve_range, safe_stem
from video_to_live.ffmpeg import build_video_filter


class FilterTests(unittest.TestCase):
    def test_default_matches_pad_recipe(self):
        vf = build_video_filter(0, None)
        self.assertIn("tpad=stop_mode=clone", vf)
        self.assertIn("pad=1080:1920", vf)
        self.assertNotIn("trim=start=", vf)
        self.assertNotIn("setpts=PTS*", vf)

    def test_short_range_keeps_speed_and_pads(self):
        vf = build_video_filter(0.2, 0.9)
        self.assertIn("trim=start=0.200000:end=0.900000", vf)
        self.assertIn("tpad=stop_mode=clone", vf)
        self.assertNotIn("setpts=PTS*", vf)

    def test_long_range_squeezes(self):
        vf = build_video_filter(1.0, 7.0)
        self.assertGreater(6.0, CONTAINER_DURATION)
        self.assertIn("trim=start=1.000000:end=7.000000", vf)
        self.assertIn("setpts=PTS*", vf)
        self.assertNotIn("tpad=", vf)

    def test_boundary_at_container_does_not_squeeze(self):
        vf = build_video_filter(0.0, CONTAINER_DURATION)
        self.assertIn("tpad=", vf)

    def test_bad_range(self):
        with self.assertRaises(Exception):
            build_video_filter(2.0, 1.0)
        with self.assertRaises(ConvertError):
            resolve_range(3.0, 1.0, 10.0)
        with self.assertRaises(ConvertError):
            resolve_range(-1, 1)

    def test_safe_stem(self):
        self.assertEqual(safe_stem("beija-flor.MOV"), "beija-flor")
        self.assertEqual(safe_stem("../../x.mp4"), "x")


if __name__ == "__main__":
    unittest.main()
