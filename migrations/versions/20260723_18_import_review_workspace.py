"""Add evidence-first import review workspace state and audit.

Revision ID: 20260723_18
Revises: 20260723_17
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_18"
down_revision: str | None = "20260723_17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "import_review_states",
        sa.Column("review_draft_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("selected_identity_candidate_id", UUID, nullable=False),
        sa.Column("specification_mappings", JSONB, nullable=False),
        sa.Column("parser_issues", JSONB, nullable=False),
        sa.Column("confirmed_by", UUID, nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_import_review_states_revision"),
        sa.CheckConstraint(
            "status IN ('pending','confirmed')", name="ck_import_review_states_status"
        ),
        sa.CheckConstraint(
            "(confirmed_by IS NULL) = (confirmed_at IS NULL)",
            name="ck_import_review_states_confirmation_pair",
        ),
        sa.ForeignKeyConstraint(
            ["review_draft_id"], ["import_review_drafts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["selected_identity_candidate_id"], ["component_identity_candidates.id"]
        ),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("review_draft_id"),
    )
    op.create_index(
        "ix_import_review_states_status", "import_review_states", ["status", "updated_at"]
    )

    op.create_table(
        "import_review_actions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("review_draft_id", UUID, nullable=False),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("target_key", sa.String(500), nullable=False),
        sa.Column("previous_value", JSONB, nullable=False),
        sa.Column("resulting_value", JSONB, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("review_revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ("
            "'enrichment_accepted','enrichment_rejected','enrichment_relation_changed',"
            "'identity_selected','specification_mapped','parser_issue_marked','draft_confirmed'"
            ")",
            name="ck_import_review_actions_action",
        ),
        sa.CheckConstraint("review_revision >= 2", name="ck_import_review_actions_revision"),
        sa.ForeignKeyConstraint(
            ["review_draft_id"], ["import_review_drafts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_review_actions_history",
        "import_review_actions",
        ["review_draft_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_review_actions_history", table_name="import_review_actions")
    op.drop_table("import_review_actions")
    op.drop_index("ix_import_review_states_status", table_name="import_review_states")
    op.drop_table("import_review_states")
