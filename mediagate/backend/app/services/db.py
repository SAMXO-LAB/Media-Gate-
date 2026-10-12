"""Postgres access (Supabase) via asyncpg.

The API and worker connect with a privileged role, which bypasses RLS. Every query that touches
user data therefore filters on user_id explicitly — RLS remains the guard for any direct
client access through Supabase's REST interface.
"""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

import asyncpg

from app.core.config import get_settings

_pool: asyncpg.Pool | None = None
_lock = asyncio.Lock()


async def _init(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_pool(min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    async with _lock:
        if _pool is not None:
            return _pool
        dsn = get_settings().database_url.get_secret_value()
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set")
        # statement_cache_size=0 keeps us compatible with Supabase's transaction pooler (port 6543).
        _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size,
                                          statement_cache_size=0, init=_init, command_timeout=30)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised")
    return _pool


async def fetch_is_admin(user_id: UUID) -> bool:
    row = await pool().fetchrow("select role, is_blocked from public.profiles where id = $1", user_id)
    if row is None:
        return False
    if row["is_blocked"]:
        from app.core.errors import Forbidden
        raise Forbidden("This account has been suspended.", code="account_blocked")
    return row["role"] == "admin"


async def record_event(event: str, *, user_id: UUID | None = None, platform: str | None = None,
                       status_code: int | None = None, error_code: str | None = None) -> None:
    """Best-effort usage logging; never raises into the request path."""
    try:
        await pool().execute(
            "insert into public.usage_events (event, user_id, platform, status_code, error_code) "
            "values ($1, $2, $3, $4, $5)", event, user_id, platform, status_code, error_code)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("mediagate").warning("usage_event_failed", extra={"status": event})
