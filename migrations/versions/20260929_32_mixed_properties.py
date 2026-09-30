"""Allow mixed technical specification definitions without rewriting stored data.

Revision ID: 20260929_32
Revises: 20260911_31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260929_32"
down_revision: str | None = "20260911_31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_property_definitions_type", "property_definitions", type_="check")
    op.create_check_constraint(
        "ck_property_definitions_type",
        "property_definitions",
        "value_type IN ('text','number','boolean','mixed')",
    )


def downgrade() -> None:
    # PostgreSQL validates the restored constraint. If mixed definitions exist,
    # the transactional downgrade fails rather than rewriting or losing data.
    op.drop_constraint("ck_property_definitions_type", "property_definitions", type_="check")
    op.create_check_constraint(
        "ck_property_definitions_type",
        "property_definitions",
        "value_type IN ('text','number','boolean')",
    )
