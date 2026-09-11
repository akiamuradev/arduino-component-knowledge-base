"""Separate synchronization tokens from semantic history; idempotent draft creation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260910_30"
down_revision: str | None = "20260910_29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "components", sa.Column("edit_token", sa.BigInteger(), nullable=False, server_default="1")
    )
    op.execute("UPDATE components SET edit_token=revision")
    op.execute("""
        CREATE FUNCTION ackb_advance_edit_token() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.edit_token := OLD.edit_token + 1;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER components_edit_token BEFORE UPDATE ON components
        FOR EACH ROW EXECUTE FUNCTION ackb_advance_edit_token()
    """)
    op.create_table(
        "editor_creations",
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "component_id", UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("editor_creations")
    op.execute("DROP TRIGGER components_edit_token ON components")
    op.execute("DROP FUNCTION ackb_advance_edit_token()")
    op.drop_column("components", "edit_token")
