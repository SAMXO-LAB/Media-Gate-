"""Integration tests against a real Postgres with the Supabase migrations applied.

Run with TEST_DATABASE_URL pointing at a disposable database (see docs/DEPLOYMENT.md#testing).
Skipped otherwise.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from app.adapters.base import ResolvedMedia, SourcePlan
from app.core.auth import CurrentUser
from app.core.errors import Conflict, Gone, NotFound
from app.models.schemas import DownloadEligibility, DownloadReason, MediaFormat, MediaInfo
from app.net.url_validation import parse_media_url

DSN = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def db(monkeypatch):
    from app.core.config import get_settings
    from app.services import db as dbmod
    monkeypatch.setattr(get_settings(), "database_url", SecretStr(DSN))
    pool = await dbmod.init_pool()
    await pool.execute("truncate auth.users cascade")
    yield pool
    await dbmod.close_pool()


async def _user(pool, email):
    uid = await pool.fetchval("insert into auth.users (email) values ($1) returning id", email)
    return uid


def _fake_resolve(allowed=True):
    async def fake(url, user, **kw):
        p = parse_media_url("https://x.com/me/status/42")
        return p, ResolvedMedia(
            info=MediaInfo(platform=p.platform, media_id=p.media_id, canonical_url=p.canonical_url, title="clip"),
            formats=[MediaFormat(id="v1", label="720p", kind="video")],
            eligibility=DownloadEligibility(allowed=allowed, reason=DownloadReason.allowed, message="ok"),
            sources={"v1": SourcePlan("https://video.twimg.com/a.mp4", "remux_mp4", "video/mp4", "mp4")})
    return fake


async def test_profile_trigger_and_rls(db):
    a = await _user(db, "a@example.com")
    b = await _user(db, "b@example.com")
    assert await db.fetchval("select count(*) from public.profiles") == 2
    await db.execute("insert into public.platform_connections (user_id, platform, account_id, access_token_enc) "
                     "values ($1, 'x', '1', 'enc')", a)
    job_a = await db.fetchval("insert into public.jobs (user_id, platform, media_id, format_id, operation) "
                              "values ($1, 'x', '1', 'v1', 'remux_mp4') returning id", a)
    async with db.acquire() as conn, conn.transaction():
        await conn.execute("set local role authenticated")
        await conn.execute(f"set local request.jwt.claim.sub = '{b}'")
        assert await conn.fetchval("select count(*) from public.jobs") == 0
        assert await conn.fetchval("select count(*) from public.platform_connections") == 0
        assert await conn.fetchval("select count(*) from public.profiles") == 1
    async with db.acquire() as conn, conn.transaction():
        await conn.execute("set local role authenticated")
        await conn.execute(f"set local request.jwt.claim.sub = '{a}'")
        assert await conn.fetchval("select id from public.jobs") == job_a
        assert await conn.fetchval("select platform from public.platform_connections") == "x"
    # Token columns are never readable by clients, even the owner.
    async with db.acquire() as conn:
        with pytest.raises(Exception):
            async with conn.transaction():
                await conn.execute("set local role authenticated")
                await conn.execute(f"set local request.jwt.claim.sub = '{a}'")
                await conn.fetch("select access_token_enc from public.platform_connections")
    # Users cannot escalate their own role.
    async with db.acquire() as conn:
        with pytest.raises(Exception):
            async with conn.transaction():
                await conn.execute("set local role authenticated")
                await conn.execute(f"set local request.jwt.claim.sub = '{a}'")
                await conn.execute("update public.profiles set role = 'admin' where id = $1", a)
    # Server-only tables are invisible.
    async with db.acquire() as conn:
        with pytest.raises(Exception):
            async with conn.transaction():
                await conn.execute("set local role authenticated")
                await conn.fetch("select * from public.job_sources")


async def test_job_lifecycle_cap_claim_and_cleanup(db, monkeypatch):
    from app.services import jobs, runtime_config
    from app.worker import cleanup

    monkeypatch.setattr(jobs, "resolve_url", _fake_resolve())
    runtime_config.apply({}, {"max_active_jobs_per_user": 2})
    uid = await _user(db, "c@example.com")
    other = CurrentUser(await _user(db, "d@example.com"), None)
    user = CurrentUser(uid, None)

    j1 = await jobs.create_job(user, "https://x.com/me/status/42", "v1")
    await jobs.create_job(user, "https://x.com/me/status/42", "v1")
    with pytest.raises(Conflict):
        await jobs.create_job(user, "https://x.com/me/status/42", "v1")
    with pytest.raises(NotFound):
        await jobs.get_job(other, j1.id)  # ownership enforced

    c1 = await jobs.claim_next("w1")
    c2 = await jobs.claim_next("w2")
    assert c1["id"] != c2["id"] and await jobs.claim_next("w3") is None

    did = uuid.uuid4()
    await jobs.complete(c1["id"], uid, did, f"{uid}/{did}.mp4", "clip.mp4", "video/mp4", 10, "x")
    assert await db.fetchval("select count(*) from public.job_sources where job_id = $1", c1["id"]) == 0

    class NullStorage:
        deleted: list = []

        async def delete(self, keys):
            self.deleted.extend(keys)

        async def signed_url(self, key, ttl, filename):
            return "https://signed.example/" + key

    ns = NullStorage()
    monkeypatch.setattr(jobs, "get_storage", lambda: ns)
    monkeypatch.setattr(cleanup, "get_storage", lambda: ns)
    link = await jobs.download_link(user, did)
    assert link.url.startswith("https://signed.example/")
    with pytest.raises(NotFound):
        await jobs.download_link(other, did)

    await db.execute("update public.downloads set expires_at = now() - interval '1 second' where id = $1", did)
    assert await cleanup.expire_downloads() == 1
    assert ns.deleted == [f"{uid}/{did}.mp4"]
    with pytest.raises(Gone):
        await jobs.download_link(user, did)
    assert (await jobs.get_job(user, c1["id"])).status == "expired"

    # Stale job (no heartbeat) is requeued, then failed after repeated abandonment.
    await db.execute("update public.jobs set heartbeat_at = now() - interval '2 hours' where id = $1", c2["id"])
    requeued, failed = await cleanup.recover_stale_jobs()
    assert requeued == 1
    await db.execute("update public.jobs set status='downloading', attempts = 5, "
                     "heartbeat_at = now() - interval '5 hours' where id = $1", c2["id"])
    requeued, failed = await cleanup.recover_stale_jobs()
    assert failed == 1 and (await jobs.get_job(user, c2["id"])).error_code == "abandoned"

    # Cancel deletes stored files and sources.
    j3 = await jobs.create_job(user, "https://x.com/me/status/42", "v1")
    await jobs.cancel_or_delete(user, j3.id)
    assert (await jobs.get_job(user, j3.id)).status == "cancelled"


async def test_unauthorized_job_is_not_created(db, monkeypatch):
    from app.core.errors import Forbidden
    from app.services import jobs
    monkeypatch.setattr(jobs, "resolve_url", _fake_resolve(allowed=False))
    uid = await _user(db, "e@example.com")
    with pytest.raises(Forbidden):
        await jobs.create_job(CurrentUser(uid, None), "https://x.com/me/status/42", "v1")
    assert await db.fetchval("select count(*) from public.jobs where user_id = $1", uid) == 0


async def test_oauth_state_single_use(db, monkeypatch):
    from app.core.errors import AppError
    from app.services import connections
    from app.net.url_validation import Platform
    uid = await _user(db, "f@example.com")
    url = await connections.start(uid, Platform.x)
    assert "code_challenge=" in url
    with pytest.raises(AppError):
        await connections.finish(Platform.x, state="forged", code="c")
    await db.execute("update public.oauth_states set expires_at = $1", datetime.now(timezone.utc) - timedelta(1))
    from urllib.parse import parse_qs, urlsplit
    state = parse_qs(urlsplit(url).query)["state"][0]
    with pytest.raises(Gone):
        await connections.finish(Platform.x, state=state, code="c")


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg not installed")
async def test_worker_end_to_end(db, monkeypatch, tmp_path):
    """Queue → worker download (SSRF client, mocked network) → ffmpeg → local storage → signed link."""
    import subprocess

    import httpx

    from app.net.safe_http import SafeHttpClient
    from app.services import jobs, runtime_config, storage
    from app.worker import processor

    sample = tmp_path / "s.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
                    "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(sample)], check=True)
    payload = sample.read_bytes()

    def handler(req):
        assert req.headers["host"] == "video.twimg.com"
        return httpx.Response(200, headers={"content-type": "video/mp4", "content-length": str(len(payload))},
                              content=payload)

    class MockSafe(SafeHttpClient):
        def __init__(self, policy, **kw):
            async def resolver(h, p):
                return ["93.184.216.34"]
            super().__init__(policy, resolver=resolver, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(processor, "SafeHttpClient", MockSafe)
    st = storage.LocalStorage()
    monkeypatch.setattr(storage, "_storage", st)
    monkeypatch.setattr(jobs, "resolve_url", _fake_resolve())
    runtime_config.apply({}, {"max_active_jobs_per_user": 5})

    uid = await _user(db, "g@example.com")
    user = CurrentUser(uid, None)
    job = await jobs.create_job(user, "https://x.com/me/status/42", "v1")
    claimed = await jobs.claim_next("w")
    await processor.process(claimed)
    done = await jobs.get_job(user, job.id)
    assert done.status == "completed" and done.download_id and done.progress == 1
    link = await jobs.download_link(user, done.download_id)
    assert link.filename == "clip_x-42.mp4" and link.size_bytes > 0
    assert "/api/files/" in link.url
