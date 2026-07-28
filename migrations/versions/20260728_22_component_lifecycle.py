"""Add the ACKB 1.0.0 component review and visibility lifecycle.

Revision ID: 20260728_22
Revises: 20260728_21
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_22"
down_revision: str | None = "20260728_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = (
    "draft",
    "in_review",
    "changes_requested",
    "approved",
    "published",
    "hidden",
    "archived",
)
_ARCHIVE_ORIGINS = tuple(status for status in _STATUSES if status != "archived")


def _quoted(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.drop_constraint("ck_components_published_at", "components", type_="check")
    op.drop_constraint("ck_components_status", "components", type_="check")
    op.alter_column(
        "components",
        "status",
        existing_type=sa.String(16),
        type_=sa.String(24),
        existing_nullable=False,
    )
    op.alter_column(
        "component_revisions",
        "status",
        existing_type=sa.String(16),
        type_=sa.String(24),
        existing_nullable=False,
    )
    op.add_column(
        "components",
        sa.Column("archived_from_status", sa.String(24), nullable=True),
    )
    op.execute(
        """
        UPDATE components AS component
        SET archived_from_status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM component_revisions AS revision
                WHERE revision.component_id = component.id
                  AND revision.status = 'published'
            ) THEN 'published'
            ELSE 'draft'
        END
        WHERE component.status = 'archived'
        """
    )
    op.create_check_constraint(
        "ck_components_status",
        "components",
        f"status IN ({_quoted(_STATUSES)})",
    )
    op.create_check_constraint(
        "ck_components_published_at",
        "components",
        "status NOT IN ('published','hidden') OR published_at IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_components_archive_origin",
        "components",
        "(status = 'archived') = (archived_from_status IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_components_archive_origin_status",
        "components",
        f"archived_from_status IS NULL OR archived_from_status IN ({_quoted(_ARCHIVE_ORIGINS)})",
    )
    op.create_check_constraint(
        "ck_component_revisions_status",
        "component_revisions",
        f"status IN ({_quoted(_STATUSES)})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_component_revisions_status",
        "component_revisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_components_archive_origin_status",
        "components",
        type_="check",
    )
    op.drop_constraint("ck_components_archive_origin", "components", type_="check")
    op.drop_constraint("ck_components_published_at", "components", type_="check")
    op.drop_constraint("ck_components_status", "components", type_="check")
    op.execute(
        """
        UPDATE component_revisions
        SET status = CASE
            WHEN status IN ('in_review','changes_requested','approved') THEN 'draft'
            WHEN status = 'hidden' THEN 'archived'
            ELSE status
        END
        """
    )
    op.execute(
        """
        UPDATE components
        SET
            status = CASE
                WHEN status IN ('in_review','changes_requested','approved') THEN 'draft'
                WHEN status = 'hidden' THEN 'archived'
                ELSE status
            END,
            published_at = CASE
                WHEN status = 'archived' AND published_at IS NULL THEN updated_at
                ELSE published_at
            END
        """
    )
    op.drop_column("components", "archived_from_status")
    op.alter_column(
        "component_revisions",
        "status",
        existing_type=sa.String(24),
        type_=sa.String(16),
        existing_nullable=False,
    )
    op.alter_column(
        "components",
        "status",
        existing_type=sa.String(24),
        type_=sa.String(16),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_components_status",
        "components",
        "status IN ('draft','published','archived')",
    )
    op.create_check_constraint(
        "ck_components_published_at",
        "components",
        "status = 'draft' OR published_at IS NOT NULL",
    )
