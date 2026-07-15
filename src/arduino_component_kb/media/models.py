"""SQLAlchemy metadata for durable media state."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("kind IN ('image', 'video')", name="ck_media_assets_kind"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'rejected')",
            name="ck_media_assets_status",
        ),
        CheckConstraint(
            "(kind = 'image' AND declared_size_bytes BETWEEN 1 AND 8388608) OR "
            "(kind = 'video' AND declared_size_bytes BETWEEN 1 AND 268435456)",
            name="ck_media_declared_size",
        ),
        CheckConstraint(
            "(kind = 'image' AND declared_mime IN ('image/jpeg', 'image/png', 'image/webp')) "
            "OR (kind = 'video' AND declared_mime IN "
            "('video/mp4', 'video/quicktime', 'video/webm'))",
            name="ck_media_declared_mime",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR (kind = 'image' AND size_bytes BETWEEN 1 AND 8388608) "
            "OR (kind = 'video' AND size_bytes BETWEEN 1 AND 268435456)",
            name="ck_media_size",
        ),
        CheckConstraint(
            "status != 'ready' OR (detected_mime IS NOT NULL AND size_bytes IS NOT NULL "
            "AND length(sha256) = 64 AND width > 0 AND height > 0 AND "
            "((kind = 'image' AND length(phash) = 16) OR "
            "(kind = 'video' AND duration_ms > 0 AND video_codec IS NOT NULL "
            "AND frame_rate > 0 AND frame_rate <= 30)))",
            name="ck_media_ready_metadata",
        ),
        CheckConstraint(
            "status != 'rejected' OR failure_code IS NOT NULL",
            name="ck_media_rejected_failure",
        ),
        Index("ix_media_assets_owner_status", "owner_user_id", "status"),
        UniqueConstraint("bucket", "object_key", name="uq_media_assets_object"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    component_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="image")
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    alt_text: Mapped[str] = mapped_column(String(500), nullable=False)
    attribution: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    declared_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_mime: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    phash: Mapped[str | None] = mapped_column(String(16))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    video_codec: Mapped[str | None] = mapped_column(String(40))
    audio_codec: Mapped[str | None] = mapped_column(String(40))
    frame_rate: Mapped[float | None] = mapped_column(Float)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    upload_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MediaVariant(Base):
    __tablename__ = "media_variants"
    __table_args__ = (
        CheckConstraint(
            "variant IN ('320w', '800w', '1600w', 'video_720p', 'poster')",
            name="ck_media_variants_name",
        ),
        CheckConstraint(
            "(variant IN ('320w', '800w', '1600w', 'poster') AND mime = 'image/webp') "
            "OR (variant = 'video_720p' AND mime = 'video/mp4')",
            name="ck_media_variants_mime",
        ),
        CheckConstraint("size_bytes > 0", name="ck_media_variants_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_media_variants_dimensions"),
        CheckConstraint("length(sha256) = 64", name="ck_media_variants_sha256"),
        CheckConstraint(
            "variant != 'video_720p' OR (duration_ms > 0 AND video_codec = 'h264' "
            "AND (audio_codec IS NULL OR audio_codec = 'aac') "
            "AND frame_rate > 0 AND frame_rate <= 30)",
            name="ck_media_video_rendition",
        ),
        Index("ix_media_variants_asset", "asset_id"),
        UniqueConstraint("asset_id", "variant", name="uq_media_variants_asset_variant"),
        UniqueConstraint("bucket", "object_key", name="uq_media_variants_object"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    variant: Mapped[str] = mapped_column(String(16), nullable=False)
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    video_codec: Mapped[str | None] = mapped_column(String(40))
    audio_codec: Mapped[str | None] = mapped_column(String(40))
    frame_rate: Mapped[float | None] = mapped_column(Float)


class MediaJob(Base):
    __tablename__ = "media_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'retrying', 'succeeded', 'failed')",
            name="ck_media_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_media_jobs_attempts"),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_media_jobs_max_attempts"),
        CheckConstraint("attempts <= max_attempts", name="ck_media_jobs_attempt_bound"),
        CheckConstraint("manual_retry_count >= 0", name="ck_media_jobs_manual_retries"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_media_jobs_progress"),
        CheckConstraint(
            "phase IN ('queued', 'starting', 'downloading', 'probing', 'transcoding', "
            "'poster', 'uploading', 'retrying', 'completed', 'failed')",
            name="ck_media_jobs_phase",
        ),
        UniqueConstraint("asset_id", name="uq_media_jobs_asset"),
        UniqueConstraint("idempotency_key", name="uq_media_jobs_idempotency_key"),
        Index("ix_media_jobs_monitor", "status", "updated_at"),
        Index("ix_media_jobs_queue_status", "queue_name", "status"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    manual_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    queue_name: Mapped[str] = mapped_column(String(32), nullable=False)
    task_name: Mapped[str] = mapped_column(String(80), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
