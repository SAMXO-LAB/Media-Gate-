import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.base import ResolvedMedia, SourcePlan
from app.core.errors import Gone
from app.models.schemas import DownloadEligibility, DownloadReason, MediaFormat, MediaInfo
from app.net.url_validation import parse_media_url
from tests.conftest import make_token

USER = uuid.uuid4()
ADMIN = uuid.uuid4()


def auth(uid=USER, **kw):
    return {"Authorization": f"Bearer {make_token(uid, **kw)}"}


def _resolved(allowed=True):
    p = parse_media_url("https://x.com/me/status/1")
    return p, ResolvedMedia(
        info=MediaInfo(platform=p.platform, media_id=p.media_id, canonical_url=p.canonical_url, title="t"),
        formats=[MediaFormat(id="v1", label="720p", kind="video"),
                 MediaFormat(id="v2", label="1080p", kind="video", available=False, unavailable_reason="nope")],
        eligibility=DownloadEligibility(allowed=allowed, reason=DownloadReason.allowed if allowed else DownloadReason.not_owner,
                                        message="m"),
        sources={"v1": SourcePlan("https://video.twimg.com/a.mp4", "remux_mp4", "video/mp4", "mp4")} if allowed else {})


async def test_error_shape_invalid_url(client, monkeypatch):
    r = await client.post("/api/analyze", json={"url": "https://evil.com/x"})
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == "unsupported_platform" and body["request_id"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


async def test_validation_error_hides_values(client):
    r = await client.post("/api/analyze", json={"url": "", "extra": "<script>"})
    assert r.status_code == 422
    assert "<script>" not in r.text


async def test_body_size_limit(client):
    r = await client.post("/api/analyze", content=b"x" * 20000, headers={"content-type": "application/json"})
    assert r.status_code == 413


async def test_analyze_success(client, monkeypatch):
    async def fake_resolve(url, user, **kw):
        return _resolved()
    monkeypatch.setattr("app.routes.analyze.resolve_url", fake_resolve)
    r = await client.post("/api/analyze", json={"url": "https://x.com/me/status/1"})
    assert r.status_code == 200
    body = r.json()
    assert body["download"]["allowed"] is True
    assert "sources" not in body and "video.twimg.com" not in r.text   # server-only URLs never leak


async def test_rate_limit(client, monkeypatch):
    from app.core import ratelimit
    ratelimit.set_override("analyze", 3)
    codes = [(await client.post("/api/analyze", json={"url": "https://evil.com/"})).status_code for _ in range(4)]
    assert codes[:3] == [400, 400, 400]
    assert codes[3] == 429
    r = await client.post("/api/analyze", json={"url": "https://evil.com/"})
    assert r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1


async def test_rate_limiter_window():
    from app.core.ratelimit import InMemoryLimiter
    lim = InMemoryLimiter()
    assert (await lim.hit("k", 2, 60, now=0))[0]
    assert (await lim.hit("k", 2, 60, now=1))[0]
    ok, retry = await lim.hit("k", 2, 60, now=2)
    assert not ok and retry > 0
    assert (await lim.hit("k", 2, 60, now=61))[0]


@pytest.mark.parametrize("method,path", [
    ("post", "/api/jobs"), ("get", f"/api/jobs/{uuid.uuid4()}"), ("delete", f"/api/jobs/{uuid.uuid4()}"),
    ("get", f"/api/downloads/{uuid.uuid4()}"), ("get", "/api/connections"), ("get", "/api/admin/overview"),
])
async def test_auth_required(client, method, path):
    kw = {"json": {"url": "https://x.com/a/status/1", "format_id": "v1"}} if method == "post" else {}
    r = await getattr(client, method)(path, **kw)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


async def test_expired_and_bad_tokens(client):
    r = await client.get("/api/jobs", headers=auth(exp_offset=-120))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    r = await client.get("/api/jobs", headers=auth(aud="wrong"))
    assert r.status_code == 401
    r = await client.get("/api/jobs", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


async def test_admin_forbidden_for_users(client, admin_ids, monkeypatch):
    r = await client.get("/api/admin/overview", headers=auth(USER))
    assert r.status_code == 403
    admin_ids.add(ADMIN)

    async def fake_limits():
        return None
    r = await client.get("/api/admin/rate-limits", headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["analyze_per_minute"] >= 1


async def test_job_rejects_unsupported_and_unavailable_formats(client, monkeypatch):
    async def fake_resolve(url, user, **kw):
        return _resolved()
    monkeypatch.setattr("app.services.jobs.resolve_url", fake_resolve)
    r = await client.post("/api/jobs", headers=auth(), json={"url": "https://x.com/me/status/1", "format_id": "nope"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_format"
    r = await client.post("/api/jobs", headers=auth(), json={"url": "https://x.com/me/status/1", "format_id": "v2"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "format_unavailable"


async def test_job_rejects_unauthorized_download(client, monkeypatch):
    async def fake_resolve(url, user, **kw):
        return _resolved(allowed=False)
    monkeypatch.setattr("app.services.jobs.resolve_url", fake_resolve)
    r = await client.post("/api/jobs", headers=auth(), json={"url": "https://x.com/me/status/1", "format_id": "v1"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "download_not_owner"


async def test_job_format_id_validation(client):
    r = await client.post("/api/jobs", headers=auth(), json={"url": "https://x.com/me/status/1", "format_id": "../../etc"})
    assert r.status_code == 422


async def test_expired_download_returns_410(client, monkeypatch):
    async def gone(user, did):
        raise Gone("This download has expired.")
    monkeypatch.setattr("app.services.jobs.download_link", gone)
    r = await client.get(f"/api/downloads/{uuid.uuid4()}", headers=auth())
    assert r.status_code == 410 and r.json()["error"]["code"] == "expired"


async def test_download_link_service_checks_expiry(monkeypatch):
    """Service-level: expired or deleted records never produce a link."""
    from app.core.auth import CurrentUser
    from app.services import jobs

    class FakePool:
        def __init__(self, row):
            self.row = row

        async def fetchrow(self, q, *a):
            assert "user_id = $2" in q          # ownership is part of the query
            return self.row

        async def execute(self, *a):
            raise AssertionError("must not record a link for expired downloads")

    row = {"id": uuid.uuid4(), "storage_key": "k", "filename": "f.mp4", "content_type": "video/mp4",
           "size_bytes": 1, "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1), "deleted_at": None}
    monkeypatch.setattr(jobs, "pool", lambda: FakePool(row))
    with pytest.raises(Gone):
        await jobs.download_link(CurrentUser(USER, None), row["id"])
    row2 = dict(row, expires_at=datetime.now(timezone.utc) + timedelta(hours=1), deleted_at=datetime.now(timezone.utc))
    monkeypatch.setattr(jobs, "pool", lambda: FakePool(row2))
    with pytest.raises(Gone):
        await jobs.download_link(CurrentUser(USER, None), row2["id"])


async def test_platforms_status(client):
    r = await client.get("/api/platforms")
    assert r.status_code == 200
    by = {p["platform"]: p for p in r.json()}
    assert by["youtube"]["capabilities"]["download"] is False
    assert by["instagram"]["capabilities"]["own_content_only"] is True


async def test_healthz(client):
    assert (await client.get("/healthz")).json() == {"status": "ok"}


async def test_local_file_token(client, tmp_path, monkeypatch):
    from app.core import crypto
    from app.services import storage
    st = storage.LocalStorage()
    key = f"{USER}/{uuid.uuid4()}.mp4"
    p = storage.safe_local_path(st.root, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"data")
    monkeypatch.setattr(storage, "_storage", st)
    url = await st.signed_url(key, 60, "clip.mp4")
    token = url.rsplit("/", 1)[1]
    r = await client.get(f"/api/files/{token}")
    assert r.status_code == 200 and r.content == b"data"
    assert "attachment" in r.headers["content-disposition"]
    expired = crypto.sign({"k": key, "f": "clip.mp4"}, -10)
    assert (await client.get(f"/api/files/{expired}")).status_code == 410
    tampered = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]
    assert (await client.get(f"/api/files/{tampered}")).status_code == 400
    escape = crypto.sign({"k": "../../../etc/passwd", "f": "x"}, 60)
    assert (await client.get(f"/api/files/{escape}")).status_code == 404


async def test_health_reachable_under_api_prefix(client):
    # Vercel routes only /api/* to the backend, so health must exist there too.
    assert (await client.get("/api/healthz")).json() == {"status": "ok"}


async def test_lazy_startup_returns_503_when_db_unreachable(monkeypatch):
    """With lifespan-less runtimes, the first request initialises the pool; failures become a clean 503."""
    import httpx

    from app import main
    from app.services import db

    async def boom(**kw):
        raise OSError("db down")

    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "init_pool", boom)
    app = main.create_app(with_lifespan=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/healthz")
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable"
