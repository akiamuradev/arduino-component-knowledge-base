"""Add ordered component image metadata and one-primary invariant.

Revision ID: 20260723_19
Revises: 20260723_18
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_19"
down_revision: str | None = "20260723_18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("caption", sa.String(1000), nullable=True))
    op.add_column("media_assets", sa.Column("display_order", sa.Integer(), nullable=True))
    op.add_column("media_assets", sa.Column("is_primary", sa.Boolean(), nullable=True))
    op.execute(
        """
        WITH ordered AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY component_id, kind
                       ORDER BY created_at, id
                   ) - 1 AS position
            FROM media_assets
            WHERE component_id IS NOT NULL
        )
        UPDATE media_assets AS asset
        SET display_order = ordered.position
        FROM ordered
        WHERE asset.id = ordered.id
        """
    )
    op.execute("UPDATE media_assets SET display_order = 0 WHERE display_order IS NULL")
    op.execute("UPDATE media_assets SET is_primary = false")
    op.execute(
        """
        WITH first_images AS (
            SELECT DISTINCT ON (component_id) id
            FROM media_assets
            WHERE component_id IS NOT NULL
              AND kind = 'image'
              AND status != 'rejected'
            ORDER BY component_id, display_order, created_at, id
        )
        UPDATE media_assets AS asset
        SET is_primary = true
        FROM first_images
        WHERE asset.id = first_images.id
        """
    )
    op.alter_column("media_assets", "display_order", nullable=False)
    op.alter_column("media_assets", "is_primary", nullable=False)
    op.create_check_constraint(
        "ck_media_assets_display_order",
        "media_assets",
        "display_order >= 0",
    )
    op.create_check_constraint(
        "ck_media_assets_primary_image",
        "media_assets",
        "NOT is_primary OR (kind = 'image' AND component_id IS NOT NULL)",
    )
    op.create_index(
        "ix_media_assets_component_order",
        "media_assets",
        ["component_id", "kind", "display_order", "id"],
    )
    op.create_index(
        "uq_media_assets_component_primary_image",
        "media_assets",
        ["component_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'image' AND is_primary AND component_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_media_assets_component_primary_image",
        table_name="media_assets",
    )
    op.drop_index("ix_media_assets_component_order", table_name="media_assets")
    op.drop_constraint("ck_media_assets_primary_image", "media_assets", type_="check")
    op.drop_constraint("ck_media_assets_display_order", "media_assets", type_="check")
    op.drop_column("media_assets", "is_primary")
    op.drop_column("media_assets", "display_order")
    op.drop_column("media_assets", "caption")
