import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main


class TiktokHelperTests(unittest.TestCase):
    def test_has_audio_stream_returns_true_when_ffprobe_finds_audio(self):
        result = SimpleNamespace(returncode=0, stdout="audio\n")

        with patch("main.subprocess.run", return_value=result):
            self.assertTrue(main._has_audio_stream("/tmp/video.mp4"))

    def test_has_audio_stream_returns_false_without_audio(self):
        result = SimpleNamespace(returncode=0, stdout="")

        with patch("main.subprocess.run", return_value=result):
            self.assertFalse(main._has_audio_stream("/tmp/video.mp4"))


if __name__ == "__main__":
    unittest.main()
