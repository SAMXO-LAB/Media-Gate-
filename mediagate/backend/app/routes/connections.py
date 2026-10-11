from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import RedirectResponse

from app.adapters.registry import all_adapters, get_adapter
from app.core.auth import CurrentUser, require_user
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.schemas import ConnectionInfo, ConnectStartResponse
from app.net.url_validation import Platform
from app.services import connections
from app.services.cache import resolve_cache

router = APIRouter(prefix="/api/connections", tags=["connections"])
log = logging.getLogger("mediagate")


@router.get("", response_model=list[ConnectionInfo])
async def list_connections(user: CurrentUser = Depends(require_user)) -> list[ConnectionInfo]:
    existing = await connections.list_for_user(user.id)
    out = []
    for a in all_adapters():
        row = existing.get(a.platform.value)
        out.append(ConnectionInfo(
            platform=a.platform, configured=a.configured, connectable=a.connectable, connected=row is not None,
            account_name=row["account_name"] if row else None, connected_at=row["created_at"] if row else None,
            note=None if a.connectable else "YouTube has no authorized download access, so there's nothing to connect."))
    return out


@router.post("/{platform}/start", response_model=ConnectStartResponse)
async def start(platform: Platform, user: CurrentUser = Depends(require_user)) -> ConnectStartResponse:
    if not get_adapter(platform).connectable:
        raise AppError("This platform doesn't support account connection.", code="not_connectable")
    return ConnectStartResponse(authorize_url=await connections.start(user.id, platform))


@router.get("/{platform}/callback", include_in_schema=False)
async def callback(platform: Platform, state: str = Query("", max_length=200), code: str = Query("", max_length=2000),
                   error: str | None = Query(None, max_length=200)) -> RedirectResponse:
    """Browser lands here from the platform. Always redirects back to the frontend."""
    target = get_settings().frontend_url.rstrip("/") + "/connections"
    if error or not code or not state:
        return RedirectResponse(f"{target}?{urlencode({'platform': platform.value, 'status': 'denied'})}", 303)
    try:
        await connections.finish(platform, state=state, code=code)
        resolve_cache.clear()
        status = "connected"
    except AppError as exc:
        log.info("oauth_callback_failed", extra={"platform": platform.value, "status": exc.code})
        status = "failed"
    return RedirectResponse(f"{target}?{urlencode({'platform': platform.value, 'status': status})}", 303)


@router.delete("/{platform}", status_code=204, response_class=Response)
async def disconnect(platform: Platform, user: CurrentUser = Depends(require_user)) -> Response:
    await connections.delete(user.id, platform)
    resolve_cache.clear()
    return Response(status_code=204)
