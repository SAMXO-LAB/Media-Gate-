"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.routes import admin, analyze, connections, files, health, jobs

log = logging.getLogger("mediagate")
MAX_BODY_BYTES = 16 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services import db, runtime_config
    await db.init_pool()
    task = asyncio.create_task(runtime_config.refresh_loop())
    try:
        yield
    finally:
        task.cancel()
        await db.close_pool()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title="MediaGate API", version="1.0.0",
        description="Authorized media analysis and download for YouTube, Instagram and X.",
        lifespan=lifespan if with_lifespan else None,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"], max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return JSONResponse({"error": {"code": "payload_too_large", "message": "Request body too large.",
                                           "details": None, "request_id": request.state.request_id}}, 413)
        start = time.perf_counter()
        response = await call_next(request)
        h = response.headers
        h["X-Request-ID"] = request.state.request_id
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if not request.url.path.startswith(("/docs", "/redoc")):
            h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.is_production:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        log.info("request", extra={"request_id": request.state.request_id, "method": request.method,
                                   "path": request.url.path, "status": response.status_code,
                                   "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

    for r in (health.router, analyze.router, jobs.router, connections.router, admin.router, files.router):
        app.include_router(r)
    return app


app = create_app()
