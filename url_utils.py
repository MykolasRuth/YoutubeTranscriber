import re


def is_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))


def is_tiktok_url(url: str) -> bool:
    return bool(re.search(r"(tiktok\.com|vm\.tiktok\.com)", url or ""))


def extract_supported_url(text: str) -> str:
    """Return the first supported video URL from a pasted URL or share text."""
    text = (text or "").strip()
    match = re.search(r"https?://[^\s<>\"]+", text)
    if not match:
        return text

    url = match.group(0).rstrip(".,;:)]}")
    if is_tiktok_url(url) or is_youtube_url(url):
        return url

    return text


def extract_youtube_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract YouTube video ID from: {url}")
