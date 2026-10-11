from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.auth import CurrentUser, require_admin
from app.models.schemas import (AdminOverview, AdminUser, AdminUserUpdate, PlatformToggle, RateLimitConfig)
from app.net.url_validation import Platform
from app.services import admin, runtime_config

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/overview", response_model=AdminOverview)
async def get_overview(hours: int = Query(24, ge=1, le=24 * 30)) -> AdminOverview:
    return await admin.overview(hours)


@router.get("/usage/daily")
async def usage_daily(days: int = Query(14, ge=1, le=90)) -> list[dict]:
    return await admin.daily_series(days)


@router.get("/users", response_model=list[AdminUser])
async def users(q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=200),
                offset: int = Query(0, ge=0)) -> list[AdminUser]:
    return await admin.list_users(q, limit, offset)


@router.patch("/users/{user_id}", response_model=AdminUser)
async def patch_user(user_id: UUID, body: AdminUserUpdate, me: CurrentUser = Depends(require_admin)) -> AdminUser:
    return await admin.update_user(me, user_id, body)


@router.get("/rate-limits", response_model=RateLimitConfig)
async def get_limits() -> RateLimitConfig:
    return RateLimitConfig(**runtime_config.current_limits())


@router.put("/rate-limits", response_model=RateLimitConfig)
async def put_limits(body: RateLimitConfig, me: CurrentUser = Depends(require_admin)) -> RateLimitConfig:
    return await admin.set_rate_limits(me, body)


@router.put("/platforms/{platform}", status_code=204, response_class=Response)
async def toggle_platform(platform: Platform, body: PlatformToggle, me: CurrentUser = Depends(require_admin)) -> Response:
    await admin.set_platform_enabled(me, platform.value, body.enabled)
    return Response(status_code=204)
