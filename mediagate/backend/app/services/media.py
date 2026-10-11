"""Analyze orchestration: validation → platform checks → adapter → cache."""
from __future__ import annotations

from app.adapters.base import ResolvedMedia
from app.adapters.registry import get_adapter
from app.core.auth import CurrentUser
from app.core.config import get_settings
from app.net.safe_http import API_HOSTS, SafeHttpClient
from app.net.url_validation import ParsedMediaUrl, parse_media_url
from app.services import connections, runtime_config
from app.services.cache import resolve_cache


async def resolve_url(url: str, user: CurrentUser | None, *, use_cache: bool = True
                      ) -> tuple[ParsedMediaUrl, ResolvedMedia]:
    parsed = parse_media_url(url)
    runtime_config.ensure_enabled(parsed.platform)
    adapter = get_adapter(parsed.platform)

    token = None
    if user is not None and adapter.connectable and adapter.configured:
        token = await connections.get_token(user.id, parsed.platform)

    key = (parsed.platform.value, parsed.media_id, token.account_id if token else None, user is not None)
    if use_cache:
        cached = resolve_cache.get(key)
        if cached is not None:
            return parsed, cached

    async with SafeHttpClient(API_HOSTS, timeout=get_settings().http_timeout_seconds) as http:
        resolved = await adapter.resolve(parsed, http=http, connection=token, signed_in=user is not None)
    resolve_cache.set(key, resolved)
    return parsed, resolved
