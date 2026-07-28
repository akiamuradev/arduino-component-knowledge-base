"""Add centralized role-grant lifetime support for ACKB 1.0.0.

Revision ID: 20260728_20
Revises: 20260723_19
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_20"
down_revision: str | None = "20260723_19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "user_roles",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_roles",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE user_roles
        SET id = md5(user_id::text || ':' || role)::uuid
        WHERE id IS NULL
        """
    )
    op.alter_column("user_roles", "id", nullable=False)
    op.drop_constraint("pk_user_roles", "user_roles", type_="primary")
    op.create_primary_key("pk_user_roles", "user_roles", ["id"])
    op.drop_constraint("ck_user_roles_role", "user_roles", type_="check")
    op.create_check_constraint(
        "ck_user_roles_role",
        "user_roles",
        "role IN ('student', 'teacher', 'editor', 'administrator')",
    )
    op.create_check_constraint(
        "ck_user_roles_editor_expiry",
        "user_roles",
        "(role = 'editor' AND expires_at IS NOT NULL) OR (role != 'editor' AND expires_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_user_roles_expiry_after_grant",
        "user_roles",
        "expires_at IS NULL OR expires_at > granted_at",
    )
    op.create_check_constraint(
        "ck_user_roles_revocation_after_grant",
        "user_roles",
        "revoked_at IS NULL OR revoked_at >= granted_at",
    )
    op.create_index(
        "ix_user_roles_active_lookup",
        "user_roles",
        ["user_id", "role", "revoked_at", "expires_at"],
    )
    op.create_index(
        "uq_user_roles_current_grant",
        "user_roles",
        ["user_id", "role"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_roles_current_grant", table_name="user_roles")
    op.drop_index("ix_user_roles_active_lookup", table_name="user_roles")
    op.drop_constraint(
        "ck_user_roles_revocation_after_grant",
        "user_roles",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_roles_expiry_after_grant",
        "user_roles",
        type_="check",
    )
    op.drop_constraint("ck_user_roles_editor_expiry", "user_roles", type_="check")
    op.drop_constraint("ck_user_roles_role", "user_roles", type_="check")
    op.execute("DELETE FROM user_roles WHERE role = 'editor' OR revoked_at IS NOT NULL")
    op.drop_constraint("pk_user_roles", "user_roles", type_="primary")
    op.create_primary_key("pk_user_roles", "user_roles", ["user_id", "role"])
    op.create_check_constraint(
        "ck_user_roles_role",
        "user_roles",
        "role IN ('student', 'teacher', 'administrator')",
    )
    op.drop_column("user_roles", "revoked_at")
    op.drop_column("user_roles", "expires_at")
    op.drop_column("user_roles", "id")
