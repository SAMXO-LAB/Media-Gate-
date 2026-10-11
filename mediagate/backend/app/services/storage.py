"""Temporary result storage with expiring links.

Backends
* supabase (default, production): private bucket; links are Supabase signed URLs.
* local: files kept under TEMP_DIR/results; links are HMAC-signed API URLs. Only valid when the
  API and worker share a volume (single host / docker-compose).

Object keys are always server-generated (`{user_id}/{download_id}.{ext}`); user input never
reaches a path.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import httpx

from app.core import crypto
from app.core.config import get_settings
from app.core.errors import AppError, NotFound

_ALLOWED_EXT = {"mp4", "m4a", "jpg", "png", "webp"}


def object_key(user_id: UUID, download_id: UUID, ext: str) -> str:
    if ext not in _ALLOWED_EXT:
        raise AppError("Unsupported output type.", code="bad_output_type", status_code=500)
    return f"{user_id}/{download_id}.{ext}"


def safe_local_path(root: Path, key: str) -> Path:
    """Resolve a key under root, refusing anything that escapes it."""
    root = root.resolve()
    p = (root / key).resolve()
    if not p.is_relative_to(root):
        raise NotFound("File not found.")
    return p


class SupabaseStorage:
    name = "supabase"

    def __init__(self) -> None:
        s = get_settings()
        self.base = s.supabase_url.rstrip("/") + "/storage/v1"
        self.bucket = s.storage_bucket
        key = s.supabase_service_role_key.get_secret_value()
        self.headers = {"Authorization": f"Bearer {key}", "apikey": key}

    async def upload(self, key: str, file_path: Path, content_type: str) -> None:
        async def body() -> AsyncIterator[bytes]:
            with open(file_path, "rb") as fh:
                while chunk := fh.read(1024 * 1024):
                    yield chunk

        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as c:
            r = await c.post(f"{self.base}/object/{self.bucket}/{key}", content=body(),
                             headers={**self.headers, "Content-Type": content_type, "x-upsert": "false",
                                      "Content-Length": str(os.path.getsize(file_path))})
        if r.status_code >= 300:
            raise AppError("Couldn't store the processed file.", code="storage_error", status_code=502)

    async def signed_url(self, key: str, ttl: int, filename: str) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{self.base}/object/sign/{self.bucket}/{key}", headers=self.headers,
                             json={"expiresIn": ttl})
        if r.status_code == 404 or (r.status_code == 400 and "not found" in r.text.lower()):
            raise NotFound("This file is no longer available.")
        if r.status_code >= 300:
            raise AppError("Couldn't create a download link.", code="storage_error", status_code=502)
        signed = r.json().get("signedURL") or r.json().get("signedUrl")
        return f"{self.base}{signed}&download={quote(filename)}"

    async def delete(self, keys: list[str]) -> None:
        if not keys:
            return
        async with httpx.AsyncClient(timeout=30) as c:
            await c.request("DELETE", f"{self.base}/object/{self.bucket}", headers=self.headers,
                            json={"prefixes": keys})


class LocalStorage:
    name = "local"

    def __init__(self) -> None:
        self.root = get_settings().temp_dir / "results"
        self.root.mkdir(parents=True, exist_ok=True)

    async def upload(self, key: str, file_path: Path, content_type: str) -> None:
        dest = safe_local_path(self.root, key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(file_path, dest)

    async def signed_url(self, key: str, ttl: int, filename: str) -> str:
        if not safe_local_path(self.root, key).exists():
            raise NotFound("This file is no longer available.")
        token = crypto.sign({"k": key, "f": filename}, ttl)
        return f"{get_settings().public_api_url.rstrip('/')}/api/files/{token}"

    def open_from_token(self, token: str) -> tuple[Path, str]:
        body = crypto.verify(token)
        path = safe_local_path(self.root, body["k"])
        if not path.exists():
            raise NotFound("This file is no longer available.")
        return path, body["f"]

    async def delete(self, keys: list[str]) -> None:
        for k in keys:
            try:
                safe_local_path(self.root, k).unlink(missing_ok=True)
            except NotFound:
                continue


_storage: SupabaseStorage | LocalStorage | None = None


def get_storage() -> SupabaseStorage | LocalStorage:
    global _storage
    if _storage is None:
        backend = get_settings().storage_backend.lower()
        _storage = LocalStorage() if backend == "local" else SupabaseStorage()
    return _storage
