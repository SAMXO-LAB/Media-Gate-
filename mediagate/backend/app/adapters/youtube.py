"""YouTube adapter — metadata only.

YouTube's Terms of Service prohibit downloading content unless YouTube itself shows a
download button or link for it, and the YouTube Data API offers no media-download endpoint
(not even for a video's owner). This adapter therefore never offers a download. It returns
real metadata from the Data API and explains the limitation.
"""
from __future__ import annotations

from datetime import datetime

from app.adapters.base import ConnectionToken, PlatformAdapter, ResolvedMedia, parse_iso8601_duration
from app.core.config import get_settings
from app.core.errors import MediaUnavailable, PlatformError, PlatformNotConfigured, RateLimited
from app.models.schemas import DownloadEligibility, DownloadReason, MediaInfo
from app.net.safe_http import SafeHttpClient
from app.net.url_validation import ParsedMediaUrl, Platform

API = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeAdapter(PlatformAdapter):
    platform = Platform.youtube
    display_name = "YouTube"
    connectable = False
    capabilities = {"metadata": True, "formats": False, "download": False, "requires_connection": False}
    summary = ("Metadata via the YouTube Data API. Downloads are not offered: YouTube's terms only "
               "permit downloads through YouTube's own download features.")
    url_patterns = ("youtube.com/watch?v={id}", "youtube.com/shorts/{id}", "youtube.com/live/{id}",
                    "youtube.com/embed/{id}", "youtu.be/{id}")

    def missing_config(self) -> list[str]:
        return [] if get_settings().youtube_api_key.get_secret_value() else ["YOUTUBE_API_KEY"]

    async def resolve(self, parsed: ParsedMediaUrl, *, http: SafeHttpClient,
                      connection: ConnectionToken | None, signed_in: bool) -> ResolvedMedia:
        self.ensure_configured()
        key = get_settings().youtube_api_key.get_secret_value()
        resp = await http.get(API, params={"part": "snippet,contentDetails,status", "id": parsed.media_id,
                                           "key": key, "maxResults": 1})
        if resp.status_code in (400, 403):
            reason = _error_reason(resp)
            if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
                raise RateLimited("YouTube's API quota for this server is used up for now. Try again later.",
                                  code="platform_quota", details={"platform": "youtube"})
            if reason in ("keyInvalid", "keyExpired", "accessNotConfigured", "ipRefererBlocked", "forbidden"):
                raise PlatformNotConfigured("The server's YouTube API key is invalid or not enabled.",
                                            details={"platform": "youtube", "reason": reason})
        self.raise_for_upstream(resp, not_found_message="That YouTube video wasn't found.")
        try:
            items = resp.json().get("items", [])
        except ValueError as exc:
            raise PlatformError("YouTube returned an unreadable response.") from exc
        if not items:
            raise MediaUnavailable("That YouTube video is private, removed, or doesn't exist.")

        item = items[0]
        sn = item.get("snippet", {})
        cd = item.get("contentDetails", {})
        thumbs = sn.get("thumbnails", {})
        thumb = next((thumbs[k]["url"] for k in ("maxres", "standard", "high", "medium", "default")
                      if k in thumbs and "url" in thumbs[k]), None)
        published = None
        if sn.get("publishedAt"):
            try:
                published = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            except ValueError:
                published = None

        info = MediaInfo(
            platform=self.platform, media_id=parsed.media_id, canonical_url=parsed.canonical_url,
            title=sn.get("title"), author=sn.get("channelTitle"), thumbnail_url=thumb,
            duration_seconds=parse_iso8601_duration(cd.get("duration")), published_at=published,
            media_type="live" if sn.get("liveBroadcastContent") in ("live", "upcoming") else "video",
        )
        eligibility = DownloadEligibility(
            allowed=False, reason=DownloadReason.platform_prohibits,
            message=("YouTube doesn't allow downloads through its API or third-party sites. "
                     "If this is your video, you can download it from YouTube Studio."),
            action="open_external", action_url="https://studio.youtube.com/",
        )
        notices = ["YouTube Premium members can save videos for offline viewing inside the YouTube app."]
        return ResolvedMedia(info=info, formats=[], eligibility=eligibility, notices=notices)


def _error_reason(resp) -> str | None:
    try:
        errs = resp.json().get("error", {}).get("errors", [])
        return errs[0].get("reason") if errs else None
    except (ValueError, AttributeError):
        return None
