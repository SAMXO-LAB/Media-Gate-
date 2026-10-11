"""Platform adapter contract.

Each adapter declares what its platform actually allows. Nothing here assumes the platforms
are equivalent: an adapter may expose metadata only, may require an account connection,
and may restrict downloads to the owner's own content.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Literal

import httpx

from app.core.errors import AppError, MediaUnavailable, PlatformError, PlatformNotConfigured, RateLimited
from app.models.schemas import DownloadEligibility, MediaFormat, MediaInfo
from app.net.safe_http import SafeHttpClient
from app.net.url_validation import ParsedMediaUrl, Platform

Operation = Literal["passthrough", "remux_mp4", "extract_m4a"]


@dataclass
class ConnectionToken:
    access_token: str
    account_id: str
    account_name: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scopes: str | None = None


@dataclass
class SourcePlan:
    """Server-only instructions for the worker. Never serialized to clients."""
    source_url: str
    operation: Operation
    content_type: str
    extension: str
    expected_duration: float | None = None


@dataclass
class ResolvedMedia:
    info: MediaInfo
    formats: list[MediaFormat]
    eligibility: DownloadEligibility
    sources: dict[str, SourcePlan] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)


@dataclass
class OAuthStart:
    authorize_url: str
    code_verifier: str | None = None


class PlatformAdapter(ABC):
    platform: ClassVar[Platform]
    display_name: ClassVar[str]
    connectable: ClassVar[bool] = False
    #: Static description of what the platform permits, shown on the status page.
    capabilities: ClassVar[dict[str, bool]] = {}
    summary: ClassVar[str] = ""
    #: URL patterns this adapter accepts (documentation; enforced in url_validation).
    url_patterns: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def missing_config(self) -> list[str]:
        """Names of required env vars that are not set."""

    @property
    def configured(self) -> bool:
        return not self.missing_config()

    def ensure_configured(self) -> None:
        missing = self.missing_config()
        if missing:
            raise PlatformNotConfigured(
                f"{self.display_name} isn't configured on this server yet.",
                details={"platform": self.platform.value, "missing": missing})

    @abstractmethod
    async def resolve(self, parsed: ParsedMediaUrl, *, http: SafeHttpClient,
                      connection: ConnectionToken | None, signed_in: bool) -> ResolvedMedia:
        """Fetch metadata, real formats and decide download eligibility."""

    # OAuth (only for connectable adapters) -----------------------------------
    def start_oauth(self, *, state: str, redirect_uri: str) -> OAuthStart:
        raise AppError(f"{self.display_name} doesn't support account connection.", code="not_connectable")

    async def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str | None,
                            http: SafeHttpClient) -> ConnectionToken:
        raise AppError(f"{self.display_name} doesn't support account connection.", code="not_connectable")

    async def refresh(self, token: ConnectionToken, *, http: SafeHttpClient) -> ConnectionToken:
        return token

    # Helpers -------------------------------------------------------------------
    def raise_for_upstream(self, resp: httpx.Response, *, not_found_message: str) -> None:
        """Map an upstream HTTP error to a safe, user-facing error."""
        s = resp.status_code
        if s < 400:
            return
        name = self.display_name
        if s == 404:
            raise MediaUnavailable(not_found_message)
        if s == 429:
            reset = resp.headers.get("retry-after") or resp.headers.get("x-rate-limit-reset")
            raise RateLimited(f"{name} is rate-limiting requests right now. Try again shortly.",
                              code="platform_rate_limited", details={"platform": self.platform.value,
                                                                     "reset": reset})
        if s in (401, 403):
            raise PlatformError(f"{name} refused the request (permission or credential problem).",
                                code="platform_permission_denied", status_code=502,
                                details={"platform": self.platform.value, "upstream_status": s})
        if s == 402:
            raise PlatformNotConfigured(f"The server's {name} API credits are exhausted.",
                                        code="platform_billing", details={"platform": self.platform.value})
        raise PlatformError(f"{name} returned an error. Please try again later.",
                            details={"platform": self.platform.value, "upstream_status": s})


_ISO_DURATION = re.compile(r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$")


def parse_iso8601_duration(value: str | None) -> float | None:
    if not value:
        return None
    m = _ISO_DURATION.match(value)
    if not m:
        return None
    d, h, mi, s = (float(m.group(k) or 0) for k in ("d", "h", "m", "s"))
    return d * 86400 + h * 3600 + mi * 60 + s


def human_size(n: int | None) -> str:
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"
