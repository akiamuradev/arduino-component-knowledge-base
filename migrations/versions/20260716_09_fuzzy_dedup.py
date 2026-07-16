"""Add explainable fuzzy duplicate candidates.

Revision ID: 20260716_09
Revises: 20260716_08
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_09"
down_revision: str | None = "20260716_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_components_title_trgm",
        "components",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_components_model_trgm",
        "components",
        ["model"],
        postgresql_using="gin",
        postgresql_ops={"model": "gin_trgm_ops"},
    )
    op.create_table(
        "duplicate_candidates",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "left_component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "right_component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", uuid, sa.ForeignKey("users.id")),
        sa.CheckConstraint(
            "left_component_id < right_component_id", name="ck_duplicate_pair_order"
        ),
        sa.CheckConstraint("kind IN ('exact','fuzzy')", name="ck_duplicate_candidates_kind"),
        sa.CheckConstraint(
            "status IN ('open','merged','rejected','superseded')",
            name="ck_duplicate_candidates_status",
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_duplicate_candidates_score"),
    )
    op.create_index(
        "uq_duplicate_candidates_open_version",
        "duplicate_candidates",
        ["left_component_id", "right_component_id", "algorithm_version"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_duplicate_candidates_open_score",
        "duplicate_candidates",
        ["status", "score"],
    )


def downgrade() -> None:
    op.drop_table("duplicate_candidates")
    op.drop_index("ix_components_model_trgm", table_name="components")
    op.drop_index("ix_components_title_trgm", table_name="components")
