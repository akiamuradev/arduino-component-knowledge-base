"""Add component compatibility records.

Revision ID: 20260716_07
Revises: 20260716_06
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_07"
down_revision: str | None = "20260716_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "component_compatibility",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version_constraint", sa.String(120)),
        sa.Column("notes", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('board','library','platform')",
            name="ck_component_compatibility_target_type",
        ),
        sa.UniqueConstraint(
            "component_id",
            "target_type",
            "name",
            "version_constraint",
            name="uq_component_compatibility_target",
        ),
    )
    op.create_index(
        "ix_component_compatibility_component_position",
        "component_compatibility",
        ["component_id", "position"],
    )


def downgrade() -> None:
    op.drop_table("component_compatibility")
