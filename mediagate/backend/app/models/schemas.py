"""Typed request/response models (the public API contract)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.net.url_validation import Platform


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- analyze ----------------------------------------------------------------

class AnalyzeRequest(_Model):
    url: str = Field(..., min_length=1, max_length=2048)


class MediaFormat(BaseModel):
    id: str                          # opaque, adapter-scoped id (e.g. "orig", "v-2176000", "audio-m4a")
    label: str                       # human label, e.g. "720p · MP4"
    kind: Literal["video", "audio", "image"]
    container: str | None = None     # mp4, m4a, jpg ...
    width: int | None = None
    height: int | None = None
    bitrate: int | None = None       # bits/s, when reported
    filesize: int | None = None      # bytes, when reported
    derived: bool = False            # produced by FFmpeg from an original
    available: bool = True
    unavailable_reason: str | None = None


class DownloadReason(str, Enum):
    allowed = "allowed"
    platform_prohibits = "platform_prohibits"            # e.g. YouTube ToS
    not_connected = "not_connected"                       # user must connect the owning account
    not_owner = "not_owner"                               # connected, but not the author/owner
    copyright_withheld = "copyright_withheld"             # platform withheld the file
    sign_in_required = "sign_in_required"
    platform_not_configured = "platform_not_configured"
    no_media = "no_media"


class DownloadEligibility(BaseModel):
    allowed: bool
    reason: DownloadReason
    message: str
    action: Literal["connect", "sign_in", "open_external", None] = None
    action_url: str | None = None


class MediaInfo(BaseModel):
    platform: Platform
    media_id: str
    canonical_url: str
    title: str | None = None
    author: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    published_at: datetime | None = None
    media_type: str | None = None    # video, reel, carousel, image ...


class AnalyzeResponse(BaseModel):
    media: MediaInfo
    formats: list[MediaFormat]
    download: DownloadEligibility
    notices: list[str] = []


# ---- jobs -------------------------------------------------------------------

class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    processing = "processing"
    uploading = "uploading"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class CreateJobRequest(_Model):
    url: str = Field(..., min_length=1, max_length=2048)
    format_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")


class JobResponse(BaseModel):
    id: UUID
    platform: Platform
    media_id: str
    format_id: str
    status: JobStatus
    progress: float | None = None     # 0..1 when measurable
    error_code: str | None = None
    error_message: str | None = None
    download_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DownloadLinkResponse(BaseModel):
    download_id: UUID
    url: str
    filename: str
    content_type: str
    size_bytes: int | None
    expires_in: int                   # seconds the *link* stays valid
    file_expires_at: datetime         # when the stored file is deleted


# ---- connections ------------------------------------------------------------

class ConnectionInfo(BaseModel):
    platform: Platform
    configured: bool                  # server has credentials for this platform
    connectable: bool                 # platform supports account connection at all
    connected: bool
    account_name: str | None = None
    connected_at: datetime | None = None
    note: str | None = None


class ConnectStartResponse(BaseModel):
    authorize_url: str


# ---- platform status ---------------------------------------------------------

class PlatformStatus(BaseModel):
    platform: Platform
    enabled: bool
    configured: bool
    missing: list[str]
    capabilities: dict[str, bool]
    summary: str


# ---- admin -------------------------------------------------------------------

class AdminOverview(BaseModel):
    window_hours: int
    requests_total: int
    analyze_total: int
    jobs_completed: int
    jobs_failed: int
    jobs_active: int
    queue_depth: int
    oldest_queued_seconds: float | None
    by_platform: dict[str, dict[str, int]]
    recent_errors: list[dict]


class AdminUser(BaseModel):
    id: UUID
    email: str | None
    role: str
    is_blocked: bool
    created_at: datetime
    jobs_7d: int


class AdminUserUpdate(_Model):
    role: Literal["user", "admin"] | None = None
    is_blocked: bool | None = None


class RateLimitConfig(_Model):
    analyze_per_minute: int = Field(..., ge=1, le=1000)
    jobs_per_minute: int = Field(..., ge=1, le=200)
    max_active_jobs_per_user: int = Field(..., ge=1, le=50)


class PlatformToggle(_Model):
    enabled: bool
