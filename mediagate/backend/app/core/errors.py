"""Consistent error model. Every error response has the shape
{"error": {"code": str, "message": str, "details": dict | None, "request_id": str}}"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class InvalidUrl(AppError):
    code = "invalid_url"


class UnsupportedPlatform(AppError):
    code = "unsupported_platform"


class BlockedDestination(AppError):
    code = "blocked_destination"
    status_code = 400


class NotAuthenticated(AppError):
    code = "not_authenticated"
    status_code = 401


class Forbidden(AppError):
    code = "forbidden"
    status_code = 403


class NotFound(AppError):
    code = "not_found"
    status_code = 404


class Gone(AppError):
    code = "expired"
    status_code = 410


class Conflict(AppError):
    code = "conflict"
    status_code = 409


class RateLimited(AppError):
    code = "rate_limited"
    status_code = 429


class PlatformError(AppError):
    """Errors returned by an upstream platform, already mapped to a safe message."""
    code = "platform_error"
    status_code = 502


class PlatformNotConfigured(AppError):
    code = "platform_not_configured"
    status_code = 503


class MediaUnavailable(AppError):
    code = "media_unavailable"
    status_code = 404


class LimitExceeded(AppError):
    code = "limit_exceeded"
    status_code = 413


def _body(request: Request, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details,
                      "request_id": getattr(request.state, "request_id", None)}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimited) and exc.details and "retry_after" in exc.details:
            headers["Retry-After"] = str(exc.details["retry_after"])
        return JSONResponse(_body(request, exc.code, exc.message, exc.details),
                            status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Only expose field locations and messages, never the submitted values.
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse(_body(request, "validation_error", "Request validation failed.", details),
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(_body(request, "http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        import logging
        logging.getLogger("mediagate").exception("unhandled_error")
        return JSONResponse(_body(request, "internal_error", "Something went wrong. Please try again."),
                            status_code=500)
