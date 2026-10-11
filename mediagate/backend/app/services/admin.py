"""Admin read models and mutations. All callers are already verified admins."""
from __future__ import annotations

from uuid import UUID

from app.core.auth import CurrentUser
from app.core.errors import AppError, NotFound
from app.models.schemas import AdminOverview, AdminUser, AdminUserUpdate, RateLimitConfig
from app.services import runtime_config
from app.services.db import pool


async def overview(hours: int = 24) -> AdminOverview:
    p = pool()
    ev = await p.fetch(
        """select event, coalesce(platform, 'none') as platform, count(*)::int as n
           from public.usage_events where created_at > now() - make_interval(hours => $1)
           group by 1, 2""", hours)
    by_platform: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for r in ev:
        totals[r["event"]] = totals.get(r["event"], 0) + r["n"]
        if r["platform"] != "none":
            by_platform.setdefault(r["platform"], {})[r["event"]] = r["n"]
    q = await p.fetchrow(
        """select count(*) filter (where status = 'queued')::int as depth,
                  count(*) filter (where status in ('downloading','processing','uploading'))::int as active,
                  extract(epoch from now() - min(created_at) filter (where status = 'queued')) as oldest
           from public.jobs""")
    errors = await p.fetch(
        """select j.id, j.platform, j.error_code, j.error_message, j.finished_at
           from public.jobs j where j.status = 'failed' and j.finished_at > now() - make_interval(hours => $1)
           order by j.finished_at desc limit 25""", hours)
    return AdminOverview(
        window_hours=hours, requests_total=sum(totals.values()), analyze_total=totals.get("analyze", 0),
        jobs_completed=totals.get("job_completed", 0), jobs_failed=totals.get("job_failed", 0),
        jobs_active=q["active"], queue_depth=q["depth"],
        oldest_queued_seconds=float(q["oldest"]) if q["oldest"] is not None else None,
        by_platform=by_platform,
        recent_errors=[{**dict(e), "id": str(e["id"])} for e in errors])


async def daily_series(days: int = 14) -> list[dict]:
    rows = await pool().fetch(
        """select date_trunc('day', created_at)::date as day, event, count(*)::int as n
           from public.usage_events where created_at > now() - make_interval(days => $1)
           group by 1, 2 order by 1""", days)
    return [{"day": r["day"].isoformat(), "event": r["event"], "n": r["n"]} for r in rows]


async def list_users(search: str | None, limit: int = 50, offset: int = 0) -> list[AdminUser]:
    pattern = f"%{search.strip()[:100]}%" if search else None
    rows = await pool().fetch(
        """select p.id, p.email, p.role, p.is_blocked, p.created_at,
                  (select count(*) from public.jobs j where j.user_id = p.id
                     and j.created_at > now() - interval '7 days')::int as jobs_7d
           from public.profiles p
           where ($1::text is null or p.email ilike $1)
           order by p.created_at desc limit $2 offset $3""", pattern, limit, offset)
    return [AdminUser(**dict(r)) for r in rows]


async def update_user(admin: CurrentUser, user_id: UUID, patch: AdminUserUpdate) -> AdminUser:
    if user_id == admin.id and (patch.role == "user" or patch.is_blocked):
        raise AppError("You can't demote or block your own account.", code="self_modification")
    row = await pool().fetchrow(
        """update public.profiles set role = coalesce($2, role), is_blocked = coalesce($3, is_blocked),
                  updated_at = now() where id = $1
           returning id, email, role, is_blocked, created_at, 0 as jobs_7d""",
        user_id, patch.role, patch.is_blocked)
    if row is None:
        raise NotFound("User not found.")
    await pool().execute("insert into public.admin_audit (admin_id, action, target, detail) values ($1, $2, $3, $4)",
                         admin.id, "update_user", str(user_id), patch.model_dump(exclude_none=True))
    return AdminUser(**dict(row))


async def set_rate_limits(admin: CurrentUser, cfg: RateLimitConfig) -> RateLimitConfig:
    await pool().execute(
        """insert into public.app_settings (key, value, updated_by) values ('rate_limits', $1, $2)
           on conflict (key) do update set value = excluded.value, updated_by = excluded.updated_by, updated_at = now()""",
        cfg.model_dump(), admin.id)
    await pool().execute("insert into public.admin_audit (admin_id, action, target, detail) values ($1, $2, $3, $4)",
                         admin.id, "set_rate_limits", "rate_limits", cfg.model_dump())
    await runtime_config.load()
    return cfg


async def set_platform_enabled(admin: CurrentUser, platform: str, enabled: bool) -> None:
    await pool().execute("update public.platform_config set enabled = $2, updated_by = $3, updated_at = now() "
                         "where platform = $1", platform, enabled, admin.id)
    await pool().execute("insert into public.admin_audit (admin_id, action, target, detail) values ($1, $2, $3, $4)",
                         admin.id, "set_platform_enabled", platform, {"enabled": enabled})
    await runtime_config.load()
