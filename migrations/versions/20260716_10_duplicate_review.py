"""Add immutable administrator decisions for duplicate review.

Revision ID: 20260716_10
Revises: 20260716_09
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_10"
down_revision: str | None = "20260716_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "merge_decisions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "candidate_id",
            uuid,
            sa.ForeignKey("duplicate_candidates.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column(
            "survivor_component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="RESTRICT"),
        ),
        sa.Column("field_resolution_json", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column(
            "decided_by", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("after_snapshot", postgresql.JSONB()),
        sa.CheckConstraint(
            "decision IN ('merge','attach','create','reject')",
            name="ck_merge_decisions_decision",
        ),
        sa.CheckConstraint(
            "(decision IN ('merge','attach') AND survivor_component_id IS NOT NULL) OR "
            "(decision IN ('create','reject') AND survivor_component_id IS NULL)",
            name="ck_merge_decisions_survivor",
        ),
    )


def downgrade() -> None:
    op.drop_table("merge_decisions")
