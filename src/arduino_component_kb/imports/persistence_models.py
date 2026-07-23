"""SQLAlchemy records for the evidence-first import pipeline."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class ImportPipelineArtifact(Base):
    __tablename__ = "import_pipeline_artifacts"
    __table_args__ = (
        CheckConstraint("length(content_sha256) = 64", name="ck_import_artifacts_content_sha"),
        CheckConstraint("length(facts_sha256) = 64", name="ck_import_artifacts_facts_sha"),
        UniqueConstraint("source_id", "idempotency_key", name="uq_import_artifacts_idempotency"),
        Index("ix_import_artifacts_component", "component_id", "created_at"),
        Index("ix_import_artifacts_revision", "source_id", "source_revision"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False
    )
    component_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL")
    )
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_file_path: Mapped[str | None] = mapped_column(String(1000))
    source_revision: Mapped[str | None] = mapped_column(String(160))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    facts_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    facts_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentIdentityCandidateRecord(Base):
    __tablename__ = "component_identity_candidates"
    __table_args__ = (
        CheckConstraint("length(payload_sha256) = 64", name="ck_identity_candidates_sha"),
        UniqueConstraint("artifact_id", "payload_sha256", name="uq_identity_candidates_payload"),
        Index("ix_identity_candidates_resolution", "resolution_status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    artifact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_pipeline_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    component_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_category: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(24), nullable=False)
    resolver_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ParserEvaluationRecord(Base):
    __tablename__ = "parser_evaluations"
    __table_args__ = (
        CheckConstraint("length(input_sha256) = 64", name="ck_parser_evaluations_input_sha"),
        CheckConstraint("length(report_sha256) = 64", name="ck_parser_evaluations_report_sha"),
        CheckConstraint(
            "score_basis_points BETWEEN 0 AND 1000", name="ck_parser_evaluations_score"
        ),
        UniqueConstraint("artifact_id", "report_sha256", name="uq_parser_evaluations_report"),
        Index("ix_parser_evaluations_route", "route", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    artifact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_pipeline_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("component_identity_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    route: Mapped[str] = mapped_column(String(24), nullable=False)
    score_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportReviewDraftRecord(Base):
    __tablename__ = "import_review_drafts"
    __table_args__ = (
        CheckConstraint("length(input_sha256) = 64", name="ck_import_review_drafts_input_sha"),
        CheckConstraint("length(payload_sha256) = 64", name="ck_import_review_drafts_payload_sha"),
        UniqueConstraint("artifact_id", "payload_sha256", name="uq_import_review_drafts_payload"),
        Index("ix_import_review_drafts_component", "component_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    artifact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_pipeline_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("component_identity_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    parser_evaluation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("parser_evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL")
    )
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    composer_version: Mapped[str] = mapped_column(String(40), nullable=False)
    quality_route: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentEnrichmentRecord(Base):
    __tablename__ = "component_enrichments"
    __table_args__ = (
        CheckConstraint("provider IN ('kicad')", name="ck_component_enrichments_provider"),
        CheckConstraint(
            "status IN ('suggested','accepted','rejected','stale','conflict')",
            name="ck_component_enrichments_status",
        ),
        CheckConstraint(
            "confidence_basis_points BETWEEN 0 AND 1000", name="ck_component_enrichments_confidence"
        ),
        CheckConstraint("length(payload_sha256) = 64", name="ck_component_enrichments_payload_sha"),
        CheckConstraint(
            "(reviewed_by IS NULL) = (reviewed_at IS NULL)",
            name="ck_component_enrichments_review_pair",
        ),
        UniqueConstraint(
            "review_draft_id",
            "provider",
            "relation_type",
            "external_identity",
            "source_revision",
            name="uq_component_enrichments_identity",
        ),
        Index("ix_component_enrichments_component", "component_id", "status"),
        Index("ix_component_enrichments_revision", "provider", "source_revision", "status"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    artifact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_pipeline_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_draft_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_review_drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    external_identity: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentEnrichmentReviewRecord(Base):
    __tablename__ = "component_enrichment_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('accept','reject')", name="ck_enrichment_reviews_decision"),
        CheckConstraint(
            "resulting_status IN ('accepted','rejected')", name="ck_enrichment_reviews_result"
        ),
        Index("ix_enrichment_reviews_history", "enrichment_id", "reviewed_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    enrichment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("component_enrichments.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(16), nullable=False)
    resulting_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportReviewStateRecord(Base):
    """Mutable reviewer choices for an otherwise immutable pipeline draft."""

    __tablename__ = "import_review_states"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_import_review_states_revision"),
        CheckConstraint("status IN ('pending','confirmed')", name="ck_import_review_states_status"),
        CheckConstraint(
            "(confirmed_by IS NULL) = (confirmed_at IS NULL)",
            name="ck_import_review_states_confirmation_pair",
        ),
        Index("ix_import_review_states_status", "status", "updated_at"),
    )

    review_draft_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_review_drafts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    selected_identity_candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("component_identity_candidates.id"),
        nullable=False,
    )
    specification_mappings: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    parser_issues: Mapped[dict[str, dict[str, object]]] = mapped_column(JSONB, nullable=False)
    confirmed_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportReviewActionRecord(Base):
    """Append-only, workspace-specific decision history."""

    __tablename__ = "import_review_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ("
            "'enrichment_accepted','enrichment_rejected','enrichment_relation_changed',"
            "'identity_selected','specification_mapped','parser_issue_marked','draft_confirmed'"
            ")",
            name="ck_import_review_actions_action",
        ),
        CheckConstraint("review_revision >= 2", name="ck_import_review_actions_revision"),
        Index("ix_import_review_actions_history", "review_draft_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    review_draft_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_review_drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_key: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resulting_value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
