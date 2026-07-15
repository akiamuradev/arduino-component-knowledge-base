"""Environment-backed application settings."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

Environment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class DatabaseSettings(BaseSettings):
    """Database-only settings shared by the application and Alembic."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ACKB_",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(repr=False)

    @field_validator("database_url")
    @classmethod
    def require_async_postgresql(cls, value: str) -> str:
        """Reject non-PostgreSQL and synchronous database drivers."""
        try:
            url = make_url(value)
        except ArgumentError as error:
            raise ValueError("database_url must be a valid SQLAlchemy URL") from error
        if url.drivername != "postgresql+asyncpg":
            raise ValueError("database_url must use postgresql+asyncpg")
        if not url.database:
            raise ValueError("database_url must include a database name")
        return value


class Settings(DatabaseSettings):
    """Validated runtime configuration loaded from ACKB_* variables."""

    app_name: str = "Arduino Component Knowledge Base"
    app_version: str = "0.8.0"
    environment: Environment = "production"
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    database_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    log_level: LogLevel = "INFO"
    docs_enabled: bool = False
    auth_throttle_pepper: SecretStr = Field(repr=False, min_length=32)
    session_ttl_minutes: int = Field(default=480, ge=15, le=1440)
    session_cookie_secure: bool = True
    auth_failure_limit: int = Field(default=5, ge=3, le=20)
    auth_failure_window_seconds: int = Field(default=900, ge=60, le=3600)
    auth_block_seconds: int = Field(default=900, ge=60, le=86400)
    redis_url: str = Field(repr=False)
    minio_endpoint: str
    minio_access_key: SecretStr = Field(repr=False, min_length=3)
    minio_secret_key: SecretStr = Field(repr=False, min_length=8)
    minio_secure: bool = True
    minio_quarantine_bucket: str = "ackb-media-quarantine"
    minio_variants_bucket: str = "ackb-media-variants"
    media_presign_ttl_seconds: int = Field(default=600, ge=60, le=900)
    media_pending_upload_limit: int = Field(default=5, ge=1, le=20)
    media_job_max_attempts: int = Field(default=4, ge=2, le=10)
    media_job_lease_seconds: int = Field(default=1800, ge=60, le=7200)
    ffprobe_path: str = "ffprobe"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_timeout_seconds: float = Field(default=15.0, ge=1, le=60)
    ffmpeg_timeout_seconds: float = Field(default=900.0, ge=30, le=1800)
    ffmpeg_threads: int = Field(default=2, ge=1, le=8)

    @field_validator("redis_url")
    @classmethod
    def require_redis_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"redis", "rediss"} or parsed.hostname is None:
            raise ValueError("redis_url must use redis or rediss and include a host")
        return value

    @field_validator("minio_endpoint")
    @classmethod
    def require_minio_endpoint(cls, value: str) -> str:
        if "://" in value or not value.strip() or "/" in value:
            raise ValueError("minio_endpoint must be host[:port] without scheme or path")
        return value

    @field_validator("minio_quarantine_bucket", "minio_variants_bucket")
    @classmethod
    def require_bucket_name(cls, value: str) -> str:
        if not 3 <= len(value) <= 63 or not all(
            character.islower() or character.isdigit() or character in {"-", "."}
            for character in value
        ):
            raise ValueError("MinIO bucket name must be a lowercase DNS-style name")
        return value

    @model_validator(mode="after")
    def require_secure_production_cookie(self) -> Settings:
        """Never permit plaintext transport for production session cookies."""
        if self.environment == "production" and not self.session_cookie_secure:
            raise ValueError("session_cookie_secure must be true in production")
        if self.environment == "production" and not self.minio_secure:
            raise ValueError("minio_secure must be true in production")
        if self.minio_quarantine_bucket == self.minio_variants_bucket:
            raise ValueError("quarantine and variants buckets must be different")
        return self
