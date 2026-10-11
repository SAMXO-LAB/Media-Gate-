from __future__ import annotations

import os
import time
import uuid

# Configure the environment before any app module reads settings.
os.environ.update({
    "APP_ENV": "test",
    "SUPABASE_JWT_SECRET": "test-jwt-secret-please-change-0123456789",
    "TOKEN_ENCRYPTION_KEY": "3q2Gp0d1m8pJ2bqY0h3wE6r9eQhQ0yXr2Y0v2k1n5Zs=",
    "STATE_SIGNING_KEY": "test-state-signing-key",
    "YOUTUBE_API_KEY": "test-yt-key",
    "INSTAGRAM_APP_ID": "123",
    "INSTAGRAM_APP_SECRET": "ig-secret",
    "X_BEARER_TOKEN": "x-bearer",
    "X_CLIENT_ID": "x-client",
    "TEMP_DIR": "/tmp/mediagate-tests",
    "STORAGE_BACKEND": "local",
})

import httpx  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.net.safe_http import HostPolicy, SafeHttpClient  # noqa: E402
from app.services.cache import resolve_cache  # noqa: E402


def make_token(user_id: uuid.UUID, *, exp_offset: int = 3600, aud: str = "authenticated") -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "aud": aud, "exp": now + exp_offset, "iat": now,
                       "email": "user@example.com", "role": "authenticated"},
                      os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")


def public_resolver(ip: str = "93.184.216.34"):
    async def resolve(host: str, port: int) -> list[str]:
        return [ip]
    return resolve


def mock_client(policy: HostPolicy, handler, ip: str = "93.184.216.34") -> SafeHttpClient:
    """SafeHttpClient whose network is an httpx.MockTransport; handler sees the original Host."""
    return SafeHttpClient(policy, resolver=public_resolver(ip), transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _reset_state():
    ratelimit._limiter = ratelimit.InMemoryLimiter()
    ratelimit._overrides.clear()
    resolve_cache.clear()
    yield


@pytest.fixture
def admin_ids():
    return set()


@pytest.fixture
def app(monkeypatch, admin_ids):
    from app.main import create_app
    from app.services import db

    async def fake_is_admin(uid):
        return uid in admin_ids

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(db, "fetch_is_admin", fake_is_admin)
    monkeypatch.setattr("app.routes.analyze.record_event", noop)
    monkeypatch.setattr("app.services.jobs.record_event", noop)
    return create_app(with_lifespan=False)


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
