"""Add evidence-first import pipeline persistence.

Revision ID: 20260723_17
Revises: 20260721_16
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_17"
down_revision: str | None = "20260721_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "import_pipeline_artifacts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("component_id", UUID, nullable=True),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("source_key", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("source_file_path", sa.String(1000), nullable=True),
        sa.Column("source_revision", sa.String(160), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("facts_sha256", sa.String(64), nullable=False),
        sa.Column("facts_payload", JSONB, nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("normalization_version", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_import_artifacts_content_sha"),
        sa.CheckConstraint("length(facts_sha256) = 64", name="ck_import_artifacts_facts_sha"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "idempotency_key", name="uq_import_artifacts_idempotency"),
    )
    op.create_index(
        "ix_import_artifacts_component", "import_pipeline_artifacts", ["component_id", "created_at"]
    )
    op.create_index(
        "ix_import_artifacts_revision",
        "import_pipeline_artifacts",
        ["source_id", "source_revision"],
    )

    op.create_table(
        "component_identity_candidates",
        sa.Column("id", UUID, nullable=False),
        sa.Column("artifact_id", UUID, nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("canonical_name", sa.String(500), nullable=False),
        sa.Column("component_kind", sa.String(32), nullable=False),
        sa.Column("selected_category", sa.String(80), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("resolution_status", sa.String(24), nullable=False),
        sa.Column("resolver_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(payload_sha256) = 64", name="ck_identity_candidates_sha"),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["import_pipeline_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "payload_sha256", name="uq_identity_candidates_payload"),
    )
    op.create_index(
        "ix_identity_candidates_resolution",
        "component_identity_candidates",
        ["resolution_status", "created_at"],
    )

    op.create_table(
        "parser_evaluations",
        sa.Column("id", UUID, nullable=False),
        sa.Column("artifact_id", UUID, nullable=False),
        sa.Column("identity_candidate_id", UUID, nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("route", sa.String(24), nullable=False),
        sa.Column("score_basis_points", sa.Integer(), nullable=False),
        sa.Column("evaluator_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(input_sha256) = 64", name="ck_parser_evaluations_input_sha"),
        sa.CheckConstraint("length(report_sha256) = 64", name="ck_parser_evaluations_report_sha"),
        sa.CheckConstraint(
            "score_basis_points BETWEEN 0 AND 1000", name="ck_parser_evaluations_score"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["import_pipeline_artifacts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["identity_candidate_id"], ["component_identity_candidates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "report_sha256", name="uq_parser_evaluations_report"),
    )
    op.create_index("ix_parser_evaluations_route", "parser_evaluations", ["route", "created_at"])

    op.create_table(
        "import_review_drafts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("artifact_id", UUID, nullable=False),
        sa.Column("identity_candidate_id", UUID, nullable=False),
        sa.Column("parser_evaluation_id", UUID, nullable=False),
        sa.Column("component_id", UUID, nullable=True),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("composer_version", sa.String(40), nullable=False),
        sa.Column("quality_route", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(input_sha256) = 64", name="ck_import_review_drafts_input_sha"),
        sa.CheckConstraint(
            "length(payload_sha256) = 64", name="ck_import_review_drafts_payload_sha"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["import_pipeline_artifacts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["identity_candidate_id"], ["component_identity_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parser_evaluation_id"], ["parser_evaluations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id", "payload_sha256", name="uq_import_review_drafts_payload"
        ),
    )
    op.create_index(
        "ix_import_review_drafts_component", "import_review_drafts", ["component_id", "created_at"]
    )

    op.create_table(
        "component_enrichments",
        sa.Column("id", UUID, nullable=False),
        sa.Column("artifact_id", UUID, nullable=False),
        sa.Column("review_draft_id", UUID, nullable=False),
        sa.Column("component_id", UUID, nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("relation_type", sa.String(40), nullable=False),
        sa.Column("external_identity", sa.String(500), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("confidence_basis_points", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("source_revision", sa.String(160), nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("reviewed_by", UUID, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('kicad')", name="ck_component_enrichments_provider"),
        sa.CheckConstraint(
            "status IN ('suggested','accepted','rejected','stale','conflict')",
            name="ck_component_enrichments_status",
        ),
        sa.CheckConstraint(
            "confidence_basis_points BETWEEN 0 AND 1000", name="ck_component_enrichments_confidence"
        ),
        sa.CheckConstraint(
            "length(payload_sha256) = 64", name="ck_component_enrichments_payload_sha"
        ),
        sa.CheckConstraint(
            "(reviewed_by IS NULL) = (reviewed_at IS NULL)",
            name="ck_component_enrichments_review_pair",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["import_pipeline_artifacts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["review_draft_id"], ["import_review_drafts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_draft_id",
            "provider",
            "relation_type",
            "external_identity",
            "source_revision",
            name="uq_component_enrichments_identity",
        ),
    )
    op.create_index(
        "ix_component_enrichments_component", "component_enrichments", ["component_id", "status"]
    )
    op.create_index(
        "ix_component_enrichments_revision",
        "component_enrichments",
        ["provider", "source_revision", "status"],
    )

    op.create_table(
        "component_enrichment_reviews",
        sa.Column("id", UUID, nullable=False),
        sa.Column("enrichment_id", UUID, nullable=False),
        sa.Column("reviewer_id", UUID, nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("previous_status", sa.String(16), nullable=False),
        sa.Column("resulting_status", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accept','reject')", name="ck_enrichment_reviews_decision"
        ),
        sa.CheckConstraint(
            "resulting_status IN ('accepted','rejected')", name="ck_enrichment_reviews_result"
        ),
        sa.ForeignKeyConstraint(
            ["enrichment_id"], ["component_enrichments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_enrichment_reviews_history",
        "component_enrichment_reviews",
        ["enrichment_id", "reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_reviews_history", table_name="component_enrichment_reviews")
    op.drop_table("component_enrichment_reviews")
    op.drop_index("ix_component_enrichments_revision", table_name="component_enrichments")
    op.drop_index("ix_component_enrichments_component", table_name="component_enrichments")
    op.drop_table("component_enrichments")
    op.drop_index("ix_import_review_drafts_component", table_name="import_review_drafts")
    op.drop_table("import_review_drafts")
    op.drop_index("ix_parser_evaluations_route", table_name="parser_evaluations")
    op.drop_table("parser_evaluations")
    op.drop_index("ix_identity_candidates_resolution", table_name="component_identity_candidates")
    op.drop_table("component_identity_candidates")
    op.drop_index("ix_import_artifacts_revision", table_name="import_pipeline_artifacts")
    op.drop_index("ix_import_artifacts_component", table_name="import_pipeline_artifacts")
    op.drop_table("import_pipeline_artifacts")
