from __future__ import annotations

import shutil

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness: the process is up")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness: database reachable, ffmpeg present")
async def readyz() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        from app.services.db import pool
        await pool().fetchval("select 1")
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        checks["database"] = "error"
    checks["ffmpeg"] = "ok" if shutil.which(get_settings().ffmpeg_path) else "missing"
    ok = checks["database"] == "ok"
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)
