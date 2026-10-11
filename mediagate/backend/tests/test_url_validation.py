import pytest

from app.core.errors import InvalidUrl, UnsupportedPlatform
from app.net.url_validation import Platform, parse_media_url


@pytest.mark.parametrize("url,platform,media_id", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", Platform.youtube, "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s", Platform.youtube, "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", Platform.youtube, "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", Platform.youtube, "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/aBcDeFgHiJk", Platform.youtube, "aBcDeFgHiJk"),
    ("youtube.com/live/aBcDeFgHiJk", Platform.youtube, "aBcDeFgHiJk"),
    ("https://www.instagram.com/p/C1a2B3c4D5e/", Platform.instagram, "C1a2B3c4D5e"),
    ("https://instagram.com/reel/C1a2B3c4D5e/?igsh=xyz", Platform.instagram, "C1a2B3c4D5e"),
    ("https://www.instagram.com/someone/p/C1a2B3c4D5e/", Platform.instagram, "C1a2B3c4D5e"),
    ("https://x.com/jack/status/20", Platform.x, "20"),
    ("https://twitter.com/jack/status/1234567890123456789/video/1", Platform.x, "1234567890123456789"),
    ("https://mobile.twitter.com/i/web/status/1234567890", Platform.x, "1234567890"),
    ("HTTPS://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ", Platform.youtube, "dQw4w9WgXcQ"),
])
def test_valid_urls(url, platform, media_id):
    parsed = parse_media_url(url)
    assert parsed.platform is platform
    assert parsed.media_id == media_id
    assert parsed.canonical_url.startswith("https://")


@pytest.mark.parametrize("url", [
    "https://evil.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
    "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
    "https://instagram.com.attacker.net/p/abcdef/",
    "https://x.co/jack/status/20",
    "https://127.0.0.1/watch?v=dQw4w9WgXcQ",
    "https://169.254.169.254/latest/meta-data/",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
])
def test_unsupported_hosts(url):
    with pytest.raises(UnsupportedPlatform):
        parse_media_url(url)


@pytest.mark.parametrize("url", [
    "",
    "   ",
    "javascript:alert(1)",
    "file:///etc/passwd",
    "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
    "https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com@evil.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com:8080/watch?v=dQw4w9WgXcQ",
    "https://youtube.com:abc/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&v=aBcDeFgHiJk",
    "https://www.youtube.com/channel/UC123",
    "https://www.instagram.com/someone/",
    "https://x.com/jack",
    "https://x.com/jack/status/abc",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ\r\nHost: evil",
    "https://www.youtube.com/watch?v=dQw4w9WgX\x00cQ",
    "https://www.yоutube.com/watch?v=dQw4w9WgXcQ",  # Cyrillic 'о'
    "https://" + "a" * 3000 + ".com/",
])
def test_rejected_input(url):
    with pytest.raises((InvalidUrl, UnsupportedPlatform)):
        parse_media_url(url)
