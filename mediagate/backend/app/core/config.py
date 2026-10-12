"""Application settings, loaded from environment variables only."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = Field("development", alias="APP_ENV")
    public_api_url: str = Field("http://localhost:8000", alias="PUBLIC_API_URL")
    frontend_url: str = Field("http://localhost:3000", alias="FRONTEND_URL")
    # Comma-separated in env (NoDecode stops pydantic-settings from expecting JSON).
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"], alias="CORS_ORIGINS")

    # Supabase
    supabase_url: str = Field("", alias="SUPABASE_URL")
    supabase_service_role_key: SecretStr = Field(SecretStr(""), alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: SecretStr = Field(SecretStr(""), alias="SUPABASE_JWT_SECRET")
    supabase_jwt_audience: str = Field("authenticated", alias="SUPABASE_JWT_AUDIENCE")
    database_url: SecretStr = Field(SecretStr(""), alias="DATABASE_URL")
    storage_bucket: str = Field("media-temp", alias="STORAGE_BUCKET")
    storage_backend: str = Field("supabase", alias="STORAGE_BACKEND")  # supabase | local

    # Secrets owned by this service
    token_encryption_key: SecretStr = Field(SecretStr(""), alias="TOKEN_ENCRYPTION_KEY")  # Fernet key
    state_signing_key: SecretStr = Field(SecretStr(""), alias="STATE_SIGNING_KEY")

    # Platforms
    youtube_api_key: SecretStr = Field(SecretStr(""), alias="YOUTUBE_API_KEY")
    instagram_app_id: str = Field("", alias="INSTAGRAM_APP_ID")
    instagram_app_secret: SecretStr = Field(SecretStr(""), alias="INSTAGRAM_APP_SECRET")
    instagram_graph_version: str = Field("v23.0", alias="INSTAGRAM_GRAPH_VERSION")
    x_bearer_token: SecretStr = Field(SecretStr(""), alias="X_BEARER_TOKEN")
    x_client_id: str = Field("", alias="X_CLIENT_ID")
    x_client_secret: SecretStr = Field(SecretStr(""), alias="X_CLIENT_SECRET")

    # Limits
    max_file_bytes: int = Field(500 * 1024 * 1024, alias="MAX_FILE_BYTES")
    max_duration_seconds: int = Field(60 * 60, alias="MAX_DURATION_SECONDS")
    http_timeout_seconds: float = Field(20.0, alias="HTTP_TIMEOUT_SECONDS")
    download_timeout_seconds: float = Field(600.0, alias="DOWNLOAD_TIMEOUT_SECONDS")
    ffmpeg_timeout_seconds: float = Field(900.0, alias="FFMPEG_TIMEOUT_SECONDS")
    worker_concurrency: int = Field(2, alias="WORKER_CONCURRENCY")
    max_active_jobs_per_user: int = Field(3, alias="MAX_ACTIVE_JOBS_PER_USER")
    result_ttl_seconds: int = Field(3600, alias="RESULT_TTL_SECONDS")
    signed_url_ttl_seconds: int = Field(120, alias="SIGNED_URL_TTL_SECONDS")
    stale_job_seconds: int = Field(1800, alias="STALE_JOB_SECONDS")
    temp_dir: Path = Field(Path("/tmp/mediagate"), alias="TEMP_DIR")
    ffmpeg_path: str = Field("ffmpeg", alias="FFMPEG_PATH")
    ffprobe_path: str = Field("ffprobe", alias="FFPROBE_PATH")

    # Default rate limits (admin can override per platform_config row)
    rate_limit_analyze_per_min: int = Field(20, alias="RATE_LIMIT_ANALYZE_PER_MIN")
    rate_limit_jobs_per_min: int = Field(5, alias="RATE_LIMIT_JOBS_PER_MIN")
    redis_url: str = Field("", alias="REDIS_URL")  # optional; in-memory limiter otherwise
    trust_proxy_headers: bool = Field(False, alias="TRUST_PROXY_HEADERS")

    @field_validator("*", mode="before")
    @classmethod
    def _strip_inline_comment(cls, v: object) -> object:
        # Tolerate values pasted from .env files with trailing "  # comment" text.
        if isinstance(v, str):
            import re
            v = re.sub(r"\s+#.*$", "", v).strip()
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
