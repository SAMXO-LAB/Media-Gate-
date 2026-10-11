import httpx
import pytest

from app.adapters.base import ConnectionToken, parse_iso8601_duration
from app.adapters.instagram import InstagramAdapter
from app.adapters.x import XAdapter
from app.adapters.youtube import YouTubeAdapter
from app.core.errors import AppError, MediaUnavailable, PlatformNotConfigured, RateLimited
from app.models.schemas import DownloadReason
from app.net.safe_http import API_HOSTS
from app.net.url_validation import parse_media_url
from tests.conftest import mock_client

YT = parse_media_url("https://youtu.be/dQw4w9WgXcQ")
IG = parse_media_url("https://www.instagram.com/reel/C1a2B3c4D5e/")
XP = parse_media_url("https://x.com/me/status/1800000000000000000")


def test_iso_duration():
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("P1DT1M") == 86460
    assert parse_iso8601_duration("bogus") is None


# ---------------- YouTube

async def test_youtube_metadata_and_no_download():
    def handler(req):
        assert req.url.path == "/youtube/v3/videos"
        return httpx.Response(200, json={"items": [{
            "snippet": {"title": "Demo", "channelTitle": "Chan", "publishedAt": "2024-01-02T03:04:05Z",
                        "thumbnails": {"high": {"url": "https://i.ytimg.com/vi/x/hq.jpg"}}},
            "contentDetails": {"duration": "PT3M33S"}, "status": {"privacyStatus": "public"}}]})

    async with mock_client(API_HOSTS, handler) as http:
        r = await YouTubeAdapter().resolve(YT, http=http, connection=None, signed_in=True)
    assert r.info.title == "Demo" and r.info.duration_seconds == 213
    assert r.formats == [] and r.sources == {}
    assert not r.eligibility.allowed and r.eligibility.reason is DownloadReason.platform_prohibits


async def test_youtube_not_found():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json={"items": []})) as http:
        with pytest.raises(MediaUnavailable):
            await YouTubeAdapter().resolve(YT, http=http, connection=None, signed_in=False)


async def test_youtube_quota():
    body = {"error": {"errors": [{"reason": "quotaExceeded"}]}}
    async with mock_client(API_HOSTS, lambda req: httpx.Response(403, json=body)) as http:
        with pytest.raises(RateLimited):
            await YouTubeAdapter().resolve(YT, http=http, connection=None, signed_in=False)


async def test_youtube_bad_key():
    body = {"error": {"errors": [{"reason": "keyInvalid"}]}}
    async with mock_client(API_HOSTS, lambda req: httpx.Response(400, json=body)) as http:
        with pytest.raises(PlatformNotConfigured):
            await YouTubeAdapter().resolve(YT, http=http, connection=None, signed_in=False)


async def test_youtube_unconfigured(monkeypatch):
    from app.core.config import get_settings
    from pydantic import SecretStr
    monkeypatch.setattr(get_settings(), "youtube_api_key", SecretStr(""))
    async with mock_client(API_HOSTS, lambda req: httpx.Response(500)) as http:
        with pytest.raises(PlatformNotConfigured) as ei:
            await YouTubeAdapter().resolve(YT, http=http, connection=None, signed_in=False)
    assert ei.value.details["missing"] == ["YOUTUBE_API_KEY"]


# ---------------- X

def _tweet(author="111", duration=12_000):
    return {
        "data": {"id": XP.media_id, "text": "hello https://t.co/abc", "author_id": author,
                 "created_at": "2025-06-01T10:00:00.000Z"},
        "includes": {
            "users": [{"id": author, "username": "someone"}],
            "media": [{"type": "video", "duration_ms": duration, "preview_image_url": "https://pbs.twimg.com/p.jpg",
                       "variants": [
                           {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/pl.m3u8"},
                           {"bit_rate": 832000, "content_type": "video/mp4",
                            "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/avc1/640x360/a.mp4"},
                           {"bit_rate": 2176000, "content_type": "video/mp4",
                            "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/avc1/1280x720/b.mp4"},
                           {"bit_rate": 950000, "content_type": "video/mp4",
                            "url": "https://evil.example/c.mp4"},
                       ]}]},
    }


async def test_x_formats_owner_allowed():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=_tweet(author="111"))) as http:
        r = await XAdapter().resolve(XP, http=http, connection=ConnectionToken("tok", "111", "someone"), signed_in=True)
    assert r.eligibility.allowed
    labels = [f.label for f in r.formats]
    assert labels[0].startswith("720p")                  # sorted by bitrate, real resolution from URL
    assert any("360p" in lbl for lbl in labels)
    bad = next(f for f in r.formats if f.id == "v950000")
    assert not bad.available and "host" in bad.unavailable_reason
    assert "v950000" not in r.sources
    assert set(r.sources) == {"v2176000", "v832000", "audio"}
    assert r.info.title == "hello" and r.info.duration_seconds == 12


async def test_x_not_owner_disables_formats():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=_tweet(author="999"))) as http:
        r = await XAdapter().resolve(XP, http=http, connection=ConnectionToken("tok", "111"), signed_in=True)
    assert r.eligibility.reason is DownloadReason.not_owner
    assert r.sources == {}
    assert all(not f.available for f in r.formats)


async def test_x_anonymous_needs_sign_in():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=_tweet())) as http:
        r = await XAdapter().resolve(XP, http=http, connection=None, signed_in=False)
    assert r.eligibility.reason is DownloadReason.sign_in_required and r.eligibility.action == "sign_in"


async def test_x_too_long_is_unsupported(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "max_duration_seconds", 5)
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=_tweet(author="111"))) as http:
        r = await XAdapter().resolve(XP, http=http, connection=ConnectionToken("tok", "111"), signed_in=True)
    assert r.sources == {}
    assert not r.eligibility.allowed


async def test_x_deleted_post():
    body = {"errors": [{"title": "Not Found Error", "detail": "Could not find tweet"}]}
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=body)) as http:
        with pytest.raises(MediaUnavailable):
            await XAdapter().resolve(XP, http=http, connection=None, signed_in=False)


async def test_x_rate_limited_and_billing():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(429, headers={"x-rate-limit-reset": "1"})) as http:
        with pytest.raises(RateLimited):
            await XAdapter().resolve(XP, http=http, connection=None, signed_in=False)
    async with mock_client(API_HOSTS, lambda req: httpx.Response(402)) as http:
        with pytest.raises(PlatformNotConfigured):
            await XAdapter().resolve(XP, http=http, connection=None, signed_in=False)


async def test_x_expired_user_token():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(401)) as http:
        with pytest.raises(AppError) as ei:
            await XAdapter().resolve(XP, http=http, connection=ConnectionToken("old", "111"), signed_in=True)
    assert ei.value.code == "connection_expired"


def test_x_pkce_start():
    s = XAdapter().start_oauth(state="st", redirect_uri="https://api.example/cb")
    assert "code_challenge_method=S256" in s.authorize_url and s.code_verifier and len(s.code_verifier) >= 43


# ---------------- Instagram

def _ig_page(media_url="https://scontent-iad3-1.cdninstagram.com/v/t50/vid.mp4?oe=1", code="C1a2B3c4D5e"):
    item = {"id": "1789", "caption": "My reel\nmore", "media_type": "VIDEO", "media_product_type": "REELS",
            "thumbnail_url": "https://scontent.cdninstagram.com/t.jpg",
            "permalink": f"https://www.instagram.com/reel/{code}/", "timestamp": "2025-01-01T00:00:00+0000",
            "username": "mybrand"}
    if media_url:
        item["media_url"] = media_url
    return {"data": [item], "paging": {}}


async def test_instagram_requires_sign_in_and_connection():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(500)) as http:
        a = await InstagramAdapter().resolve(IG, http=http, connection=None, signed_in=False)
        b = await InstagramAdapter().resolve(IG, http=http, connection=None, signed_in=True)
    assert a.eligibility.reason is DownloadReason.sign_in_required
    assert b.eligibility.reason is DownloadReason.not_connected and b.eligibility.action == "connect"
    assert a.formats == [] and b.sources == {}


async def test_instagram_own_media():
    def handler(req):
        assert req.headers["authorization"] == "Bearer igtok"
        return httpx.Response(200, json=_ig_page())

    async with mock_client(API_HOSTS, handler) as http:
        r = await InstagramAdapter().resolve(IG, http=http, connection=ConnectionToken("igtok", "1", "mybrand"),
                                             signed_in=True)
    assert r.eligibility.allowed
    assert {f.id for f in r.formats} == {"orig", "orig-audio"}
    assert r.sources["orig"].operation == "remux_mp4"
    assert r.info.title == "My reel" and r.info.media_type == "reel"


async def test_instagram_not_owned():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=_ig_page(code="ZZZZZZZZ"))) as http:
        r = await InstagramAdapter().resolve(IG, http=http, connection=ConnectionToken("t", "1", "mybrand"),
                                             signed_in=True)
    assert r.eligibility.reason is DownloadReason.not_owner and "@mybrand" in r.eligibility.message


async def test_instagram_copyright_withheld():
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=_ig_page(media_url=None))) as http:
        r = await InstagramAdapter().resolve(IG, http=http, connection=ConnectionToken("t", "1"), signed_in=True)
    assert r.eligibility.reason is DownloadReason.copyright_withheld
    assert all(not f.available for f in r.formats) and r.sources == {}


async def test_instagram_unexpected_media_host_not_downloadable():
    page = _ig_page(media_url="https://attacker.example/x.mp4")
    async with mock_client(API_HOSTS, lambda req: httpx.Response(200, json=page)) as http:
        r = await InstagramAdapter().resolve(IG, http=http, connection=ConnectionToken("t", "1"), signed_in=True)
    assert r.sources == {} and not r.eligibility.allowed


async def test_instagram_expired_token():
    body = {"error": {"type": "OAuthException", "code": 190, "message": "expired"}}
    async with mock_client(API_HOSTS, lambda req: httpx.Response(400, json=body)) as http:
        with pytest.raises(AppError) as ei:
            await InstagramAdapter().resolve(IG, http=http, connection=ConnectionToken("t", "1"), signed_in=True)
    assert ei.value.code == "connection_expired"
