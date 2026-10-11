from __future__ import annotations

from app.adapters.base import PlatformAdapter
from app.adapters.instagram import InstagramAdapter
from app.adapters.x import XAdapter
from app.adapters.youtube import YouTubeAdapter
from app.net.url_validation import Platform

_ADAPTERS: dict[Platform, PlatformAdapter] = {
    Platform.youtube: YouTubeAdapter(),
    Platform.instagram: InstagramAdapter(),
    Platform.x: XAdapter(),
}


def get_adapter(platform: Platform) -> PlatformAdapter:
    return _ADAPTERS[platform]


def all_adapters() -> list[PlatformAdapter]:
    return list(_ADAPTERS.values())
