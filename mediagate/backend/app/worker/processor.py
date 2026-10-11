"""Processes one job: fetch authorized media → validate → FFmpeg → store → record download."""
from __future__ import annotations

import logging
import re
import shutil
import time
import unicodedata
import uuid
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.errors import BlockedDestination, LimitExceeded
from app.models.schemas import JobStatus
from app.net.safe_http import MEDIA_HOSTS, SafeHttpClient
from app.services import jobs
from app.services.storage import get_storage, object_key
from app.worker.ffmpeg import FFmpegError, convert, probe

log = logging.getLogger("mediagate.worker")

_IMAGE_MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}
_ACCEPTED_TYPES = ("video/", "audio/", "image/", "application/octet-stream", "binary/octet-stream")


class Cancelled(Exception):
    pass


class JobFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def safe_filename(title: str | None, platform: str, media_id: str, ext: str) -> str:
    base = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9 _-]+", "", base).strip()
    base = re.sub(r"\s+", "-", base)[:60].strip("-_") or "media"
    mid = re.sub(r"[^A-Za-z0-9_-]", "", media_id)[:32]
    return f"{base}_{platform}-{mid}.{ext}"


def work_root() -> Path:
    root = get_settings().temp_dir / "work"
    root.mkdir(parents=True, exist_ok=True)
    return root


async def process(job) -> None:
    job_id, user_id, platform = job["id"], job["user_id"], job["platform"]
    workdir = work_root() / str(job_id)
    workdir.mkdir(parents=True, exist_ok=False)
    s = get_settings()
    try:
        src = await jobs.job_source(job_id)
        if src is None:
            raise JobFailure("source_missing", "The media source is no longer available. Analyze the link again.")

        inp = workdir / "input.bin"
        await _download(job_id, src["source_url"], inp)

        ext = src["extension"]
        operation = job["operation"]
        if operation == "passthrough":
            out = inp
            if src["content_type"].startswith("image/"):
                detected = _detect_image(inp)
                if detected is None:
                    raise JobFailure("invalid_media", "The file received wasn't a valid image.")
                ext = detected
            else:
                info = await probe(inp, workdir)
                _check_duration(info.duration)
        else:
            if not await jobs.set_status(job_id, JobStatus.processing, 0.7):
                raise Cancelled()
            info = await probe(inp, workdir)
            _check_duration(info.duration)
            out = workdir / f"output.{ext}"

            async def on_progress(frac: float) -> bool:
                return await jobs.heartbeat(job_id, 0.7 + 0.25 * frac)

            await convert(operation, inp, out, workdir, duration=info.duration,
                          audio_codec=info.audio_codec, on_progress=on_progress)

        if not await jobs.set_status(job_id, JobStatus.uploading, 0.96):
            raise Cancelled()
        download_id = uuid.uuid4()
        key = object_key(user_id, download_id, ext)
        size = out.stat().st_size
        if size > s.max_file_bytes:
            raise JobFailure("too_large", "The processed file is larger than this server allows.")
        content_type = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, src["content_type"])
        await get_storage().upload(key, out, content_type)
        filename = safe_filename(job["title"], platform, job["media_id"], ext)
        await jobs.complete(job_id, user_id, download_id, key, filename, content_type, size, platform)
        log.info("job_completed", extra={"job_id": str(job_id), "platform": platform})
    except Cancelled:
        log.info("job_cancelled", extra={"job_id": str(job_id)})
    except JobFailure as exc:
        await jobs.fail(job_id, user_id, exc.code, exc.message, platform)
    except LimitExceeded:
        await jobs.fail(job_id, user_id, "too_large", "This file is larger than this server allows.", platform)
    except BlockedDestination:
        await jobs.fail(job_id, user_id, "blocked_source", "The media source failed a security check.", platform)
    except FFmpegError as exc:
        await jobs.fail(job_id, user_id, "processing_failed", f"Processing failed: {exc}.", platform)
    except (httpx.TimeoutException, TimeoutError):
        await jobs.fail(job_id, user_id, "timeout", "The download timed out. Please try again.", platform)
    except httpx.HTTPError:
        await jobs.fail(job_id, user_id, "network_error", "Couldn't reach the media source. Please try again.", platform)
    except Exception:  # noqa: BLE001
        log.exception("job_crashed", extra={"job_id": str(job_id)})
        await jobs.fail(job_id, user_id, "internal_error", "Something went wrong while processing.", platform)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _check_duration(duration: float | None) -> None:
    if duration and duration > get_settings().max_duration_seconds:
        raise JobFailure("too_long", "This media is longer than this server allows.")


def _detect_image(path: Path) -> str | None:
    head = path.read_bytes()[:12]
    for magic, ext in _IMAGE_MAGIC.items():
        if head.startswith(magic) and (ext != "webp" or head[8:12] == b"WEBP"):
            return ext
    return None


async def _download(job_id, url: str, dest: Path) -> None:
    s = get_settings()
    deadline = time.monotonic() + s.download_timeout_seconds
    async with SafeHttpClient(MEDIA_HOSTS, timeout=s.http_timeout_seconds) as http:
        async with http.stream(url, max_bytes=s.max_file_bytes) as (resp, body):
            if resp.status_code in (403, 404, 410):
                raise JobFailure("source_expired", "The platform's media link expired. Analyze the link again.")
            if resp.status_code >= 400:
                raise JobFailure("source_error", "The platform didn't return the media file.")
            ctype = resp.headers.get("content-type", "").lower()
            if not ctype.startswith(_ACCEPTED_TYPES):
                raise JobFailure("invalid_media", "The platform returned something that isn't media.")
            total = int(resp.headers["content-length"]) if resp.headers.get("content-length", "").isdigit() else None
            done, last = 0, 0.0
            with open(dest, "wb") as fh:
                async for chunk in body:
                    fh.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if now > deadline:
                        raise TimeoutError()
                    if now - last > 1.0:
                        last = now
                        if not await jobs.heartbeat(job_id, 0.7 * done / total if total else None):
                            raise Cancelled()
