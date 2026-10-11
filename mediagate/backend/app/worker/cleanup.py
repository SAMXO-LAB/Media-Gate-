"""Periodic cleanup: expired results, abandoned jobs, stale temp dirs, old OAuth states and events."""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.core.config import get_settings
from app.services.db import pool
from app.services.storage import get_storage

log = logging.getLogger("mediagate.cleanup")
MAX_ATTEMPTS = 3


def sweep_temp_dirs(root: Path, max_age_seconds: float, now: float | None = None) -> int:
    """Remove job work dirs older than max_age. Only touches direct children of root."""
    if not root.exists():
        return 0
    now = now or time.time()
    removed = 0
    for child in root.iterdir():
        try:
            if child.is_symlink():
                child.unlink(missing_ok=True)
                removed += 1
                continue
            if now - child.stat().st_mtime > max_age_seconds:
                shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
                removed += 1
        except FileNotFoundError:
            continue
    return removed


async def expire_downloads() -> int:
    rows = await pool().fetch(
        "update public.downloads set deleted_at = now() where expires_at < now() and deleted_at is null "
        "returning storage_key, job_id")
    if rows:
        await get_storage().delete([r["storage_key"] for r in rows])
        await pool().execute("update public.jobs set status = 'expired', updated_at = now() "
                             "where id = any($1::uuid[]) and status = 'completed'", [r["job_id"] for r in rows])
    return len(rows)


async def recover_stale_jobs() -> tuple[int, int]:
    stale = get_settings().stale_job_seconds
    requeued = await pool().fetch(
        """update public.jobs set status = 'queued', locked_by = null, progress = null, updated_at = now()
           where status in ('downloading','processing','uploading')
             and heartbeat_at < now() - make_interval(secs => $1) and attempts < $2
             and exists (select 1 from public.job_sources s where s.job_id = jobs.id)
           returning id""", stale, MAX_ATTEMPTS)
    failed = await pool().fetch(
        """update public.jobs set status = 'failed', error_code = 'abandoned',
                  error_message = 'Processing stopped unexpectedly. Please try again.', finished_at = now(), updated_at = now()
           where status in ('queued','downloading','processing','uploading')
             and coalesce(heartbeat_at, created_at) < now() - make_interval(secs => $1 * 2)
           returning id""", stale)
    if failed:
        await pool().execute("delete from public.job_sources where job_id = any($1::uuid[])", [r["id"] for r in failed])
    return len(requeued), len(failed)


async def run_once() -> dict:
    s = get_settings()
    removed = sweep_temp_dirs(s.temp_dir / "work", s.stale_job_seconds)
    expired = await expire_downloads()
    requeued, failed = await recover_stale_jobs()
    await pool().execute("delete from public.oauth_states where expires_at < now()")
    await pool().execute("delete from public.usage_events where created_at < now() - interval '90 days'")
    stats = {"temp_removed": removed, "downloads_expired": expired, "jobs_requeued": requeued, "jobs_failed": failed}
    if any(stats.values()):
        log.info("cleanup", extra={"status": stats})
    return stats
