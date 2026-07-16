"""Add durable imports and exact duplicate constraints.

Revision ID: 20260716_08
Revises: 20260716_07
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_08"
down_revision: str | None = "20260716_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column("components", sa.Column("normalized_manufacturer", sa.String(160)))
    op.add_column("components", sa.Column("normalized_model", sa.String(160)))
    op.execute(
        """
        WITH normalized AS (
            SELECT id,
                   NULLIF(lower(regexp_replace(trim(manufacturer), '[^[:alnum:]]+', '', 'g')), '')
                       AS manufacturer_key,
                   NULLIF(lower(regexp_replace(trim(model), '[^[:alnum:]]+', '', 'g')), '')
                       AS model_key
            FROM components
            WHERE manufacturer IS NOT NULL AND model IS NOT NULL
        ), unique_pairs AS (
            SELECT manufacturer_key, model_key
            FROM normalized
            WHERE manufacturer_key IS NOT NULL AND model_key IS NOT NULL
            GROUP BY manufacturer_key, model_key
            HAVING count(*) = 1
        )
        UPDATE components AS component
        SET normalized_manufacturer = normalized.manufacturer_key,
            normalized_model = normalized.model_key
        FROM normalized
        JOIN unique_pairs USING (manufacturer_key, model_key)
        WHERE component.id = normalized.id
        """
    )
    op.create_index(
        "uq_components_manufacturer_model_exact",
        "components",
        ["normalized_manufacturer", "normalized_model"],
        unique=True,
        postgresql_where=sa.text(
            "normalized_manufacturer IS NOT NULL AND normalized_model IS NOT NULL"
        ),
    )
    op.create_table(
        "sources",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("seed_url", sa.String(500), nullable=False),
        sa.Column("allowed_host", sa.String(253), nullable=False, unique=True),
        sa.Column("adapter", sa.String(80), nullable=False),
        sa.Column("adapter_version", sa.String(40), nullable=False),
        sa.Column("policy", sa.String(32), nullable=False),
        sa.Column("rights_note", sa.Text()),
        sa.Column("attribution_template", sa.String(1000)),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "policy IN ('metadata_only','licensed_content')", name="ck_sources_policy"
        ),
    )
    op.create_table(
        "component_sources",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", uuid, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("submitted_url", sa.String(1000), nullable=False),
        sa.Column("canonical_url", sa.String(1000), nullable=False),
        sa.Column("source_item_id", sa.String(160)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adapter_version", sa.String(40), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("attribution", sa.String(1000)),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_component_sources_sha256"),
    )
    op.create_index("ix_component_sources_component", "component_sources", ["component_id"])
    op.create_index(
        "uq_component_sources_canonical",
        "component_sources",
        ["source_id", "canonical_url"],
        unique=True,
    )
    op.create_index(
        "uq_component_sources_item",
        "component_sources",
        ["source_id", "source_item_id"],
        unique=True,
        postgresql_where=sa.text("source_item_id IS NOT NULL"),
    )
    op.create_table(
        "import_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("source_id", uuid, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("submitted_url", sa.String(1000), nullable=False),
        sa.Column("canonical_url", sa.String(1000)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(40)),
        sa.Column("draft_component_id", uuid, sa.ForeignKey("components.id")),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','retrying','succeeded','failed')",
            name="ck_import_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_import_jobs_attempts"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_import_jobs_max_attempts"),
        sa.CheckConstraint("attempts <= max_attempts", name="ck_import_jobs_attempt_bound"),
        sa.CheckConstraint(
            "status != 'succeeded' OR draft_component_id IS NOT NULL",
            name="ck_import_jobs_success_result",
        ),
        sa.CheckConstraint(
            "status != 'failed' OR error_code IS NOT NULL", name="ck_import_jobs_failed_error"
        ),
    )
    op.create_index(
        "uq_import_jobs_idempotency",
        "import_jobs",
        ["requested_by", "idempotency_key"],
        unique=True,
    )
    op.create_index("ix_import_jobs_requested", "import_jobs", ["requested_by", "created_at"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status", "updated_at"])
    sources = (
        (
            "00000000-0000-4000-9000-000000000001",
            "arduino_tex",
            "https://arduino-tex.ru/",
            "arduino-tex.ru",
            "arduino_tex_component",
        ),
        (
            "00000000-0000-4000-9000-000000000002",
            "portal_pk",
            "https://portal-pk.ru/",
            "portal-pk.ru",
            "portal_pk_component",
        ),
        (
            "00000000-0000-4000-9000-000000000003",
            "alexgyver",
            "https://alexgyver.ru/ardu-proj/",
            "alexgyver.ru",
            "alexgyver_project",
        ),
    )
    for source_id, key, seed_url, host, adapter in sources:
        op.execute(
            sa.text(
                "INSERT INTO sources "
                "(id,key,seed_url,allowed_host,adapter,adapter_version,policy,is_enabled,"
                "updated_at) VALUES (CAST(:id AS uuid),:key,:seed_url,:host,:adapter,"
                "'1.0.0','metadata_only',true,now())"
            ).bindparams(id=source_id, key=key, seed_url=seed_url, host=host, adapter=adapter)
        )


def downgrade() -> None:
    op.drop_table("import_jobs")
    op.drop_table("component_sources")
    op.drop_table("sources")
    op.drop_index("uq_components_manufacturer_model_exact", table_name="components")
    op.drop_column("components", "normalized_model")
    op.drop_column("components", "normalized_manufacturer")
