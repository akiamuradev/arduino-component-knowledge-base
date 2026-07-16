"""Durable source provenance and parser job models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("policy IN ('metadata_only','licensed_content')", name="ck_sources_policy"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    seed_url: Mapped[str] = mapped_column(String(500), nullable=False)
    allowed_host: Mapped[str] = mapped_column(String(253), nullable=False, unique=True)
    adapter: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy: Mapped[str] = mapped_column(String(32), nullable=False)
    rights_note: Mapped[str | None] = mapped_column(Text)
    attribution_template: Mapped[str | None] = mapped_column(String(1000))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentSource(Base):
    __tablename__ = "component_sources"
    __table_args__ = (
        CheckConstraint("length(content_sha256) = 64", name="ck_component_sources_sha256"),
        Index("ix_component_sources_component", "component_id"),
        Index(
            "uq_component_sources_item",
            "source_id",
            "source_item_id",
            unique=True,
            postgresql_where=text("source_item_id IS NOT NULL"),
        ),
        Index(
            "uq_component_sources_canonical",
            "source_id",
            "canonical_url",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False
    )
    submitted_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(String(160))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attribution: Mapped[str | None] = mapped_column(String(1000))


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','retrying','succeeded','failed')",
            name="ck_import_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_import_jobs_attempts"),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_import_jobs_max_attempts"),
        CheckConstraint("attempts <= max_attempts", name="ck_import_jobs_attempt_bound"),
        CheckConstraint(
            "status != 'succeeded' OR draft_component_id IS NOT NULL",
            name="ck_import_jobs_success_result",
        ),
        CheckConstraint(
            "status != 'failed' OR error_code IS NOT NULL", name="ck_import_jobs_failed_error"
        ),
        Index("ix_import_jobs_requested", "requested_by", "created_at"),
        Index("ix_import_jobs_status", "status", "updated_at"),
        Index("uq_import_jobs_idempotency", "requested_by", "idempotency_key", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False
    )
    submitted_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    parser_version: Mapped[str | None] = mapped_column(String(40))
    draft_component_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id")
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
