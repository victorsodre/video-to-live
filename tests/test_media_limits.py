import subprocess
import unittest
from unittest.mock import patch

from video_to_live.ffmpeg import FfmpegError, run_media_process
from video_to_live.serve import ServeError, _float_field


class MediaLimitsTests(unittest.TestCase):
    def test_process_timeout_becomes_a_conversion_error(self):
        with patch("video_to_live.ffmpeg.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 120)) as run:
            with self.assertRaises(FfmpegError):
                run_media_process(["ffmpeg", "-version"])
        self.assertEqual(run.call_args.kwargs["timeout"], 120)

    def test_range_rejects_non_finite_numbers(self):
        for value in (b"nan", b"inf", b"-inf"):
            with self.subTest(value=value), self.assertRaises(ServeError):
                _float_field({"start": (None, value)}, "start")
