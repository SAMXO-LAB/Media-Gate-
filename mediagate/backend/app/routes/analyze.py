from __future__ import annotations

from fastapi import APIRouter, Depends

from app.adapters.registry import all_adapters
from app.core.auth import CurrentUser, optional_user
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.models.schemas import AnalyzeRequest, AnalyzeResponse, PlatformStatus
from app.services import runtime_config
from app.services.db import record_event
from app.services.media import resolve_url

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse,
             summary="Validate a link, fetch metadata and real formats, and report download eligibility")
async def analyze(body: AnalyzeRequest, user: CurrentUser | None = Depends(optional_user),
                  _: None = Depends(rate_limit("analyze", "rate_limit_analyze_per_min"))) -> AnalyzeResponse:
    try:
        parsed, resolved = await resolve_url(body.url, user)
    except AppError as exc:
        await record_event("analyze", user_id=user.id if user else None, status_code=exc.status_code,
                           platform=(exc.details or {}).get("platform") if isinstance(exc.details, dict) else None,
                           error_code=exc.code)
        raise
    await record_event("analyze", user_id=user.id if user else None, platform=parsed.platform.value, status_code=200)
    return AnalyzeResponse(media=resolved.info, formats=resolved.formats, download=resolved.eligibility,
                           notices=resolved.notices)


@router.get("/platforms", response_model=list[PlatformStatus], summary="What each platform supports on this server")
async def platforms() -> list[PlatformStatus]:
    return [PlatformStatus(platform=a.platform, enabled=runtime_config.platform_enabled(a.platform),
                           configured=a.configured, missing=a.missing_config(), capabilities=a.capabilities,
                           summary=a.summary) for a in all_adapters()]
