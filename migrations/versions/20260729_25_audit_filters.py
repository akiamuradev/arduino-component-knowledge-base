"""Add bounded audit-log filter indexes.

Revision ID: 20260729_25
Revises: 20260728_24
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260729_25"
down_revision: str | None = "20260728_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_events_actor_occurred",
        "audit_events",
        ["actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_action_occurred",
        "audit_events",
        ["action", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_action_occurred", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_occurred", table_name="audit_events")
