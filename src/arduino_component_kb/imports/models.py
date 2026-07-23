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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("policy IN ('metadata_only','licensed_content')", name="ck_sources_policy"),
        CheckConstraint(
            "source_type IN ('website','git_repository','official_library')",
            name="ck_sources_type",
        ),
        CheckConstraint("status IN ('active','inactive','disabled')", name="ck_sources_status"),
        CheckConstraint(
            "permission_status IN ('unknown','denied','license_granted')",
            name="ck_sources_permission",
        ),
        CheckConstraint(
            "allow_text_import IN ('none','limited','full')", name="ck_sources_text_import"
        ),
        Index(
            "uq_sources_repository_url",
            "repository_url",
            unique=True,
            postgresql_where=text("repository_url IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    seed_url: Mapped[str] = mapped_column(String(500), nullable=False)
    allowed_host: Mapped[str | None] = mapped_column(String(253))
    adapter: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy: Mapped[str] = mapped_column(String(32), nullable=False)
    rights_note: Mapped[str | None] = mapped_column(Text)
    attribution_template: Mapped[str | None] = mapped_column(String(1000))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False, default="website")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inactive")
    repository_url: Mapped[str | None] = mapped_column(String(500))
    repository_owner: Mapped[str | None] = mapped_column(String(160))
    repository_name: Mapped[str | None] = mapped_column(String(160))
    default_revision_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="immutable_commit"
    )
    license_name: Mapped[str | None] = mapped_column(String(160))
    license_spdx: Mapped[str | None] = mapped_column(String(80))
    license_url: Mapped[str | None] = mapped_column(String(500))
    permission_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    content_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="metadata_only")
    disable_reason: Mapped[str | None] = mapped_column(String(160))
    allow_text_import: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    allow_facts_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_media_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_code_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_attachment_import: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentSource(Base):
    __tablename__ = "component_sources"
    __table_args__ = (
        CheckConstraint("length(content_sha256) = 64", name="ck_component_sources_sha256"),
        CheckConstraint(
            "source_revision IS NULL OR source_revision ~ '^[0-9a-f]{40}$'",
            name="ck_component_sources_revision_sha",
        ),
        Index("ix_component_sources_component", "component_id"),
        Index(
            "uq_component_sources_item",
            "source_id",
            "source_item_id",
            unique=True,
            postgresql_where=text("source_item_id IS NOT NULL AND source_revision IS NULL"),
        ),
        Index(
            "uq_component_sources_repository_entry",
            "source_id",
            "source_revision",
            "source_file_path",
            "source_entry_name",
            unique=True,
            postgresql_where=text("source_revision IS NOT NULL AND source_file_path IS NOT NULL"),
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
    source_revision: Mapped[str | None] = mapped_column(String(64))
    source_tag: Mapped[str | None] = mapped_column(String(100))
    source_file_path: Mapped[str | None] = mapped_column(String(1000))
    source_entry_name: Mapped[str | None] = mapped_column(String(300))
    original_url: Mapped[str | None] = mapped_column(String(1000))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    provenance_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    modifications_notice: Mapped[str | None] = mapped_column(String(1000))
    license_snapshot_name: Mapped[str | None] = mapped_column(String(160))
    license_snapshot_spdx: Mapped[str | None] = mapped_column(String(80))
    license_snapshot_url: Mapped[str | None] = mapped_column(String(500))
    attribution_snapshot: Mapped[str | None] = mapped_column(String(1000))
    parser_name: Mapped[str | None] = mapped_column(String(80))
    parser_version: Mapped[str | None] = mapped_column(String(40))


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
        CheckConstraint(
            "parse_status IS NULL OR parse_status IN "
            "('parsed','parsed_with_warnings','unsupported_document','source_drift',"
            "'invalid_metadata','license_missing','failed')",
            name="ck_import_jobs_parse_status",
        ),
        CheckConstraint(
            "source_revision IS NULL OR source_revision ~ '^[0-9a-f]{40}$'",
            name="ck_import_jobs_revision_sha",
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
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    repository_url: Mapped[str | None] = mapped_column(String(500))
    requested_revision: Mapped[str | None] = mapped_column(String(100))
    source_revision: Mapped[str | None] = mapped_column(String(64))
    source_file_path: Mapped[str | None] = mapped_column(String(1000))
    source_entry_name: Mapped[str | None] = mapped_column(String(300))
    parser_name: Mapped[str | None] = mapped_column(String(80))
    parse_status: Mapped[str | None] = mapped_column(String(32))
    warnings_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


# Imported here so Alembic's existing imports.models registration sees the
# parallel pipeline tables without changing runtime wiring.
from arduino_component_kb.imports.persistence_models import (  # noqa: E402, F401
    ComponentEnrichmentRecord,
    ComponentEnrichmentReviewRecord,
    ComponentIdentityCandidateRecord,
    ImportPipelineArtifact,
    ImportReviewDraftRecord,
    ParserEvaluationRecord,
)
