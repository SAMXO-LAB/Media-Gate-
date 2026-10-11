"""Serves files for the `local` storage backend via HMAC-signed, expiring tokens."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.errors import NotFound
from app.services.storage import LocalStorage, get_storage

router = APIRouter(prefix="/api", tags=["files"], include_in_schema=False)

_TYPES = {"mp4": "video/mp4", "m4a": "audio/mp4", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


@router.get("/files/{token}")
async def serve(token: str) -> FileResponse:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise NotFound("Not found.")
    path, filename = storage.open_from_token(token)
    return FileResponse(path, media_type=_TYPES.get(path.suffix.lstrip("."), "application/octet-stream"),
                        filename=filename, headers={"Cache-Control": "private, no-store",
                                                    "X-Content-Type-Options": "nosniff"})
