"""Strict URL parsing, hostname allowlisting and platform detection.

Only URLs that match an explicit (host, path) pattern for a supported platform are accepted.
Anything else — other domains, look-alike domains, IP literals, credentials in the URL,
non-default ports, control characters — is rejected before any network activity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import parse_qs, urlsplit

from app.core.errors import InvalidUrl, UnsupportedPlatform

MAX_URL_LENGTH = 2048


class Platform(str, Enum):
    youtube = "youtube"
    instagram = "instagram"
    x = "x"


DISPLAY_NAMES = {Platform.youtube: "YouTube", Platform.instagram: "Instagram", Platform.x: "X"}

PLATFORM_HOSTS: dict[Platform, frozenset[str]] = {
    Platform.youtube: frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}),
    Platform.instagram: frozenset({"instagram.com", "www.instagram.com"}),
    Platform.x: frozenset({"x.com", "www.x.com", "mobile.x.com",
                           "twitter.com", "www.twitter.com", "mobile.twitter.com"}),
}

_YT_ID = r"[A-Za-z0-9_-]{11}"
_IG_CODE = r"[A-Za-z0-9_-]{5,64}"
_X_USER = r"[A-Za-z0-9_]{1,15}"
_X_ID = r"[0-9]{1,20}"

_YT_PATH = re.compile(rf"^/(?:shorts|live|embed)/(?P<id>{_YT_ID})/?$")
_YTB_PATH = re.compile(rf"^/(?P<id>{_YT_ID})/?$")
_IG_PATH = re.compile(rf"^/(?:[A-Za-z0-9_.]{{1,30}}/)?(?:p|reel|reels|tv)/(?P<id>{_IG_CODE})/?$")
_X_PATH = re.compile(rf"^/(?:{_X_USER}|i/web|i)/status(?:es)?/(?P<id>{_X_ID})(?:/(?:video|photo)/[1-4])?/?$")

_CONTROL = re.compile(r"[\x00-\x20\x7f\\]")


@dataclass(frozen=True)
class ParsedMediaUrl:
    platform: Platform
    media_id: str
    canonical_url: str


def _canonical(platform: Platform, media_id: str) -> str:
    if platform is Platform.youtube:
        return f"https://www.youtube.com/watch?v={media_id}"
    if platform is Platform.instagram:
        return f"https://www.instagram.com/p/{media_id}/"
    return f"https://x.com/i/web/status/{media_id}"


def parse_media_url(raw: str) -> ParsedMediaUrl:
    """Validate a user-supplied URL and return the detected platform + media id."""
    if not isinstance(raw, str):
        raise InvalidUrl("URL must be a string.")
    url = raw.strip()
    if not url:
        raise InvalidUrl("Please paste a link.")
    if len(url) > MAX_URL_LENGTH:
        raise InvalidUrl("That link is too long.")
    if _CONTROL.search(url):
        raise InvalidUrl("That link contains characters that aren't allowed.")
    if not re.match(r"^https?://", url, re.I):
        # Allow users to paste "youtube.com/..." without a scheme.
        if re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}/", url):
            url = "https://" + url
        else:
            raise InvalidUrl("Links must start with https://")

    try:
        parts = urlsplit(url)
        port = parts.port  # raises ValueError for junk ports
    except ValueError as exc:
        raise InvalidUrl("That link is malformed.") from exc

    if parts.scheme.lower() not in ("http", "https"):
        raise InvalidUrl("Only web links are supported.")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise InvalidUrl("Links with embedded credentials are not allowed.")
    if port is not None and port not in (80, 443):
        raise InvalidUrl("Links with custom ports are not allowed.")

    host = (parts.hostname or "").lower().rstrip(".")
    if not host or not host.isascii():
        raise InvalidUrl("That link has an invalid hostname.")

    platform = next((p for p, hosts in PLATFORM_HOSTS.items() if host in hosts), None)
    if platform is None:
        raise UnsupportedPlatform("Only YouTube, Instagram and X links are supported.",
                                  details={"host": host[:255]})

    path = parts.path or "/"
    media_id: str | None = None

    if platform is Platform.youtube:
        if host == "youtu.be":
            m = _YTB_PATH.match(path)
            media_id = m.group("id") if m else None
        elif path in ("/watch", "/watch/"):
            vals = parse_qs(parts.query, strict_parsing=False).get("v", [])
            if len(vals) == 1 and re.fullmatch(_YT_ID, vals[0]):
                media_id = vals[0]
        else:
            m = _YT_PATH.match(path)
            media_id = m.group("id") if m else None
    elif platform is Platform.instagram:
        m = _IG_PATH.match(path)
        media_id = m.group("id") if m else None
    else:
        m = _X_PATH.match(path)
        media_id = m.group("id") if m else None

    if not media_id:
        raise InvalidUrl(f"This {DISPLAY_NAMES[platform]} link doesn't point to a single video or post.",
                         details={"platform": platform.value})

    return ParsedMediaUrl(platform=platform, media_id=media_id, canonical_url=_canonical(platform, media_id))
