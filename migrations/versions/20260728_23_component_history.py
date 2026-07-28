"""Add authorship and safe change metadata to component revisions.

Revision ID: 20260728_23
Revises: 20260728_22
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_23"
down_revision: str | None = "20260728_22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIONS = (
    "component.created",
    "component.updated",
    "component.media_attached",
    "component.images_updated",
    "component.submitted_for_review",
    "component.changes_requested",
    "component.approved",
    "component.published",
    "component.hidden",
    "component.shown",
    "component.archived",
    "component.restored",
    "component.merged",
    "component.archived_by_merge",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.add_column(
        "component_revisions",
        sa.Column("previous_status", sa.String(24), nullable=True),
    )
    op.add_column(
        "component_revisions",
        sa.Column("action", sa.String(80), nullable=True),
    )
    op.add_column(
        "component_revisions",
        sa.Column("change_summary", sa.String(240), nullable=True),
    )
    op.execute(
        """
        UPDATE component_revisions AS target
        SET previous_status = history.previous_status
        FROM (
            SELECT
                id,
                lag(status) OVER (
                    PARTITION BY component_id
                    ORDER BY revision
                ) AS previous_status
            FROM component_revisions
        ) AS history
        WHERE history.id = target.id
        """
    )
    op.execute(
        """
        UPDATE component_revisions
        SET action = CASE
            WHEN revision = 1 THEN 'component.created'
            WHEN previous_status = 'hidden' AND status = 'published' THEN 'component.shown'
            WHEN status = 'in_review' THEN 'component.submitted_for_review'
            WHEN status = 'changes_requested' THEN 'component.changes_requested'
            WHEN status = 'approved' THEN 'component.approved'
            WHEN status = 'published' THEN 'component.published'
            WHEN status = 'hidden' THEN 'component.hidden'
            WHEN status = 'archived' THEN 'component.archived'
            ELSE 'component.updated'
        END
        """
    )
    op.execute(
        """
        UPDATE component_revisions
        SET change_summary = CASE action
            WHEN 'component.created' THEN 'Карточка создана'
            WHEN 'component.submitted_for_review' THEN 'Карточка отправлена на проверку'
            WHEN 'component.changes_requested' THEN 'Карточка возвращена на исправление'
            WHEN 'component.approved' THEN 'Карточка одобрена'
            WHEN 'component.published' THEN 'Карточка опубликована'
            WHEN 'component.hidden' THEN 'Карточка скрыта из каталога'
            WHEN 'component.shown' THEN 'Карточка возвращена в каталог'
            WHEN 'component.archived' THEN 'Карточка архивирована'
            ELSE 'Содержимое карточки изменено'
        END
        """
    )
    op.alter_column("component_revisions", "action", nullable=False)
    op.alter_column("component_revisions", "change_summary", nullable=False)
    op.create_check_constraint(
        "ck_component_revisions_action",
        "component_revisions",
        f"action IN ({_quoted(_ACTIONS)})",
    )
    op.create_check_constraint(
        "ck_component_revisions_previous_status",
        "component_revisions",
        "previous_status IS NULL OR "
        "previous_status IN "
        "('draft','in_review','changes_requested','approved','published','hidden','archived')",
    )
    op.create_check_constraint(
        "ck_component_revisions_summary",
        "component_revisions",
        "char_length(change_summary) BETWEEN 1 AND 240",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_component_revisions_summary",
        "component_revisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_component_revisions_previous_status",
        "component_revisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_component_revisions_action",
        "component_revisions",
        type_="check",
    )
    op.drop_column("component_revisions", "change_summary")
    op.drop_column("component_revisions", "action")
    op.drop_column("component_revisions", "previous_status")
