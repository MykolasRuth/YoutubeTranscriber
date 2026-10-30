import unittest

from url_utils import extract_supported_url, extract_youtube_id, is_tiktok_url, is_youtube_url


class UrlUtilsTests(unittest.TestCase):
    def test_extracts_tiktok_url_from_share_text(self):
        text = (
            "Check out this TikTok I found! This video is designed to make it easy. "
            "Watch the full video now! https://www.tiktok.com/t/ZTkwovhow/"
        )

        self.assertEqual(extract_supported_url(text), "https://www.tiktok.com/t/ZTkwovhow/")

    def test_strips_common_trailing_punctuation(self):
        text = "Watch this (https://vm.tiktok.com/ZTkwovhow/)."

        self.assertEqual(extract_supported_url(text), "https://vm.tiktok.com/ZTkwovhow/")

    def test_clean_url_is_unchanged(self):
        url = "https://youtu.be/dQw4w9WgXcQ"

        self.assertEqual(extract_supported_url(url), url)

    def test_unsupported_text_returns_original_text(self):
        text = "not a video url"

        self.assertEqual(extract_supported_url(text), text)

    def test_detects_supported_hosts(self):
        self.assertTrue(is_tiktok_url("https://www.tiktok.com/@user/video/123"))
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_extracts_youtube_id(self):
        self.assertEqual(extract_youtube_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")


if __name__ == "__main__":
    unittest.main()
