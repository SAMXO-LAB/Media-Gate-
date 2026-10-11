"""Sliding-window rate limiter.

Uses Redis when REDIS_URL is set (required when running more than one API replica);
otherwise falls back to an in-process limiter suitable for a single instance and tests.
Limits can be changed at runtime from the admin dashboard (platform_config / rate_limits).
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import RateLimited


class InMemoryLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window: float, now: float | None = None) -> tuple[bool, int]:
        now = now if now is not None else time.monotonic()
        async with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, int(q[0] + window - now) + 1)
                return False, retry
            q.append(now)
            return True, 0

    def reset(self) -> None:
        self._hits.clear()


class RedisLimiter:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # optional dependency
        self._r = redis.from_url(url)

    async def hit(self, key: str, limit: int, window: float, now: float | None = None) -> tuple[bool, int]:
        now = now if now is not None else time.time()
        k = f"rl:{key}"
        async with self._r.pipeline(transaction=True) as p:
            p.zremrangebyscore(k, 0, now - window)
            p.zcard(k)
            _, count = await p.execute()
        if count >= limit:
            oldest = await self._r.zrange(k, 0, 0, withscores=True)
            retry = max(1, int(oldest[0][1] + window - now) + 1) if oldest else int(window)
            return False, retry
        async with self._r.pipeline(transaction=True) as p:
            p.zadd(k, {f"{now}:{id(p)}": now})
            p.expire(k, int(window) + 1)
            await p.execute()
        return True, 0


_limiter: InMemoryLimiter | RedisLimiter | None = None
# Runtime overrides set by admin: {"analyze": 20, "jobs": 5}
_overrides: dict[str, int] = {}


def get_limiter() -> InMemoryLimiter | RedisLimiter:
    global _limiter
    if _limiter is None:
        url = get_settings().redis_url
        _limiter = RedisLimiter(url) if url else InMemoryLimiter()
    return _limiter


def set_override(bucket: str, per_minute: int) -> None:
    _overrides[bucket] = per_minute


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, default_per_minute_attr: str):
    """FastAPI dependency factory. Keys on user id when signed in, else on client IP."""
    async def dep(request: Request) -> None:
        settings = get_settings()
        limit = _overrides.get(bucket) or getattr(settings, default_per_minute_attr)
        who = getattr(request.state, "user_id", None) or client_ip(request)
        ok, retry = await get_limiter().hit(f"{bucket}:{who}", limit, 60.0)
        if not ok:
            raise RateLimited("Too many requests. Please wait a moment and try again.",
                              details={"retry_after": retry})
    return dep
