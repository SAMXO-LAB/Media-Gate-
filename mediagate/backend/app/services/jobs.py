"""Job lifecycle: creation (with server-side permission re-check), status, cancel, worker queue ops."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from app.core.auth import CurrentUser
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, Gone, NotFound
from app.models.schemas import DownloadLinkResponse, JobResponse, JobStatus
from app.services import runtime_config
from app.services.db import pool, record_event
from app.services.media import resolve_url
from app.services.storage import get_storage

ACTIVE = ("queued", "downloading", "processing", "uploading")


def _job(row: asyncpg.Record) -> JobResponse:
    return JobResponse(
        id=row["id"], platform=row["platform"], media_id=row["media_id"], format_id=row["format_id"],
        status=row["status"], progress=row["progress"], error_code=row["error_code"],
        error_message=row["error_message"], download_id=row["download_id"],
        created_at=row["created_at"], updated_at=row["updated_at"])


_JOB_SELECT = """
select j.*, d.id as download_id
from public.jobs j left join public.downloads d on d.job_id = j.id and d.deleted_at is null
"""


async def create_job(user: CurrentUser, url: str, format_id: str) -> JobResponse:
    # Always re-resolve server-side: the client's view of permissions is never trusted.
    parsed, resolved = await resolve_url(url, user)
    if not resolved.eligibility.allowed:
        raise Forbidden(resolved.eligibility.message, code=f"download_{resolved.eligibility.reason.value}")
    fmt = next((f for f in resolved.formats if f.id == format_id), None)
    if fmt is None:
        raise AppError("That format isn't offered for this media.", code="unsupported_format")
    if not fmt.available or format_id not in resolved.sources:
        raise AppError(fmt.unavailable_reason or "That format isn't available.", code="format_unavailable")
    plan = resolved.sources[format_id]
    s = get_settings()
    if plan.expected_duration and plan.expected_duration > s.max_duration_seconds:
        raise AppError("This media is longer than this server allows.", code="limit_exceeded", status_code=413)

    async with pool().acquire() as conn, conn.transaction():
        # Serialise per user so the active-job cap can't be raced.
        await conn.execute("select pg_advisory_xact_lock(hashtextextended($1::text, 0))", str(user.id))
        active = await conn.fetchval(
            "select count(*) from public.jobs where user_id = $1 and status = any($2::text[])", user.id, list(ACTIVE))
        if active >= runtime_config.max_active_jobs():
            raise Conflict("You have too many downloads in progress. Wait for one to finish.",
                           code="too_many_active_jobs")
        row = await conn.fetchrow(
            """insert into public.jobs (user_id, platform, media_id, format_id, operation, title, status)
               values ($1, $2, $3, $4, $5, $6, 'queued') returning id""",
            user.id, parsed.platform.value, parsed.media_id, format_id, plan.operation,
            (resolved.info.title or "")[:200] or None)
        await conn.execute(
            """insert into public.job_sources (job_id, source_url, content_type, extension, expected_duration)
               values ($1, $2, $3, $4, $5)""",
            row["id"], plan.source_url, plan.content_type, plan.extension, plan.expected_duration)
        await conn.execute("select pg_notify('mediagate_jobs', $1)", str(row["id"]))
    await record_event("job_created", user_id=user.id, platform=parsed.platform.value)
    return await get_job(user, row["id"])


async def get_job(user: CurrentUser, job_id: UUID) -> JobResponse:
    row = await pool().fetchrow(_JOB_SELECT + " where j.id = $1 and j.user_id = $2", job_id, user.id)
    if row is None:
        raise NotFound("Job not found.")  # same response for "not yours" and "doesn't exist"
    return _job(row)


async def list_jobs(user: CurrentUser, limit: int = 20) -> list[JobResponse]:
    rows = await pool().fetch(_JOB_SELECT + " where j.user_id = $1 order by j.created_at desc limit $2",
                              user.id, limit)
    return [_job(r) for r in rows]


async def cancel_or_delete(user: CurrentUser, job_id: UUID) -> None:
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("select status from public.jobs where id = $1 and user_id = $2 for update",
                                  job_id, user.id)
        if row is None:
            raise NotFound("Job not found.")
        if row["status"] in ACTIVE:
            await conn.execute("update public.jobs set status = 'cancelled', updated_at = now(), "
                               "finished_at = now() where id = $1", job_id)
        keys = await conn.fetch("update public.downloads set deleted_at = now() where job_id = $1 "
                                "and deleted_at is null returning storage_key", job_id)
        await conn.execute("delete from public.job_sources where job_id = $1", job_id)
    if keys:
        await get_storage().delete([k["storage_key"] for k in keys])


async def download_link(user: CurrentUser, download_id: UUID) -> DownloadLinkResponse:
    row = await pool().fetchrow(
        "select id, storage_key, filename, content_type, size_bytes, expires_at, deleted_at "
        "from public.downloads where id = $1 and user_id = $2", download_id, user.id)
    if row is None:
        raise NotFound("Download not found.")
    if row["deleted_at"] is not None or row["expires_at"] <= datetime.now(timezone.utc):
        raise Gone("This download has expired. Analyze the link again to create a new one.")
    ttl = get_settings().signed_url_ttl_seconds
    url = await get_storage().signed_url(row["storage_key"], ttl, row["filename"])
    await pool().execute("update public.downloads set download_count = download_count + 1, "
                         "last_link_at = now() where id = $1", download_id)
    await record_event("download_link", user_id=user.id)
    return DownloadLinkResponse(download_id=row["id"], url=url, filename=row["filename"],
                                content_type=row["content_type"], size_bytes=row["size_bytes"],
                                expires_in=ttl, file_expires_at=row["expires_at"])


# ---- worker-side queue operations -------------------------------------------------

async def claim_next(worker_id: str) -> asyncpg.Record | None:
    return await pool().fetchrow(
        """update public.jobs j set status = 'downloading', locked_by = $1, locked_at = now(),
                  heartbeat_at = now(), started_at = coalesce(started_at, now()), attempts = attempts + 1,
                  updated_at = now()
           where j.id = (select id from public.jobs where status = 'queued'
                         order by created_at for update skip locked limit 1)
           returning j.id, j.user_id, j.platform, j.media_id, j.format_id, j.operation, j.title, j.attempts""",
        worker_id)


async def job_source(job_id: UUID) -> asyncpg.Record | None:
    return await pool().fetchrow("select * from public.job_sources where job_id = $1", job_id)


async def set_status(job_id: UUID, status: JobStatus, progress: float | None = None) -> bool:
    """Returns False if the job was cancelled meanwhile (worker should stop)."""
    row = await pool().fetchrow(
        "update public.jobs set status = $2, progress = $3, heartbeat_at = now(), updated_at = now() "
        "where id = $1 and status <> 'cancelled' returning id", job_id, status.value, progress)
    return row is not None


async def heartbeat(job_id: UUID, progress: float | None) -> bool:
    row = await pool().fetchrow(
        "update public.jobs set progress = coalesce($2, progress), heartbeat_at = now(), updated_at = now() "
        "where id = $1 and status <> 'cancelled' returning id", job_id, progress)
    return row is not None


async def complete(job_id: UUID, user_id: UUID, download_id: UUID, key: str, filename: str,
                   content_type: str, size: int, platform: str) -> None:
    expires = datetime.now(timezone.utc) + timedelta(seconds=get_settings().result_ttl_seconds)
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute(
            """insert into public.downloads (id, job_id, user_id, storage_key, filename, content_type, size_bytes, expires_at)
               values ($1, $2, $3, $4, $5, $6, $7, $8)""",
            download_id, job_id, user_id, key, filename, content_type, size, expires)
        await conn.execute("update public.jobs set status = 'completed', progress = 1, finished_at = now(), "
                           "updated_at = now() where id = $1", job_id)
        await conn.execute("delete from public.job_sources where job_id = $1", job_id)
    await record_event("job_completed", user_id=user_id, platform=platform)


async def fail(job_id: UUID, user_id: UUID, code: str, message: str, platform: str) -> None:
    await pool().execute(
        "update public.jobs set status = 'failed', error_code = $2, error_message = $3, finished_at = now(), "
        "updated_at = now() where id = $1 and status <> 'cancelled'", job_id, code, message[:300])
    await pool().execute("delete from public.job_sources where job_id = $1", job_id)
    await record_event("job_failed", user_id=user_id, platform=platform, error_code=code)
