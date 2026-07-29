"""Add teacher correction proposals for published components.

Revision ID: 20260729_27
Revises: 20260729_26
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_27"
down_revision: str | None = "20260729_26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "component_correction_proposals",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            uuid,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "resolved_by",
            uuid,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('open','applied','dismissed')",
            name="ck_component_correction_proposals_status",
        ),
        sa.CheckConstraint(
            "char_length(message) BETWEEN 10 AND 4000",
            name="ck_component_correction_proposals_message",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND resolved_by IS NULL AND resolved_at IS NULL) OR "
            "(status IN ('applied','dismissed') AND resolved_by IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_component_correction_proposals_resolution",
        ),
    )
    op.create_index(
        "ix_component_correction_proposals_component_status_created",
        "component_correction_proposals",
        ["component_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_component_correction_proposals_component_status_created",
        table_name="component_correction_proposals",
    )
    op.drop_table("component_correction_proposals")
