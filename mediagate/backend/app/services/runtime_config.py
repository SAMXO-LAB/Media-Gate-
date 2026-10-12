"""Admin-editable runtime configuration (platform toggles and rate limits), refreshed periodically."""
from __future__ import annotations

import asyncio
import logging
import time

from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import AppError
from app.net.url_validation import DISPLAY_NAMES, Platform

log = logging.getLogger("mediagate")

_state: dict = {"platforms": {}, "limits": {}, "loaded_at": 0.0}


def platform_enabled(platform: Platform) -> bool:
    return _state["platforms"].get(platform.value, True)


def ensure_enabled(platform: Platform) -> None:
    if not platform_enabled(platform):
        raise AppError(f"{DISPLAY_NAMES[platform]} support is temporarily disabled.",
                       code="platform_disabled", status_code=503)


def max_active_jobs() -> int:
    return int(_state["limits"].get("max_active_jobs_per_user") or get_settings().max_active_jobs_per_user)


def current_limits() -> dict[str, int]:
    s = get_settings()
    lim = _state["limits"]
    return {"analyze_per_minute": int(lim.get("analyze_per_minute") or s.rate_limit_analyze_per_min),
            "jobs_per_minute": int(lim.get("jobs_per_minute") or s.rate_limit_jobs_per_min),
            "max_active_jobs_per_user": max_active_jobs()}


def apply(platforms: dict[str, bool], limits: dict[str, int]) -> None:
    _state["platforms"] = platforms
    _state["limits"] = limits
    _state["loaded_at"] = time.time()
    if limits.get("analyze_per_minute"):
        ratelimit.set_override("analyze", int(limits["analyze_per_minute"]))
    if limits.get("jobs_per_minute"):
        ratelimit.set_override("jobs", int(limits["jobs_per_minute"]))


async def load() -> None:
    from app.services.db import pool
    rows = await pool().fetch("select platform, enabled from public.platform_config")
    setting = await pool().fetchval("select value from public.app_settings where key = 'rate_limits'")
    apply({r["platform"]: r["enabled"] for r in rows}, setting or {})


async def maybe_refresh(max_age: float = 30.0) -> None:
    """Reload config if older than max_age seconds. Failures keep the last known values."""
    if time.time() - _state["loaded_at"] < max_age:
        return
    _state["loaded_at"] = time.time()  # avoid a thundering herd of reloads
    try:
        await load()
    except Exception:  # noqa: BLE001
        log.warning("runtime_config_refresh_failed")


async def refresh_loop(interval: float = 30.0) -> None:
    while True:
        try:
            await load()
        except Exception:  # noqa: BLE001
            log.warning("runtime_config_refresh_failed")
        await asyncio.sleep(interval)
