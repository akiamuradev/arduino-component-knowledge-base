"""Add educational code examples and ordered hints.

Revision ID: 20260716_11
Revises: 20260716_10
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_11"
down_revision: str | None = "20260716_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "code_examples",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("practical_task", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("libraries_json", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.Text()),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_by", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "visibility IN ('student','teacher')", name="ck_code_examples_visibility"
        ),
        sa.CheckConstraint("octet_length(body) <= 65536", name="ck_code_examples_body_size"),
    )
    op.create_index(
        "ix_code_examples_component_position", "code_examples", ["component_id", "position"]
    )
    op.create_table(
        "code_example_hints",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "example_id",
            uuid,
            sa.ForeignKey("code_examples.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("example_id", "position", name="uq_code_example_hints_position"),
    )


def downgrade() -> None:
    op.drop_table("code_example_hints")
    op.drop_table("code_examples")
