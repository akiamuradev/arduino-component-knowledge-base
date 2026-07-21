"""Track completed media storage cleanup.

Revision ID: 20260721_16
Revises: 20260716_15
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_16"
down_revision: str | None = "20260716_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("storage_cleaned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_media_assets_retention",
        "media_assets",
        ["storage_cleaned_at", "status", "upload_expires_at"],
    )
    op.create_check_constraint(
        "ck_media_storage_cleaned_rejected",
        "media_assets",
        "storage_cleaned_at IS NULL OR status = 'rejected'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_media_storage_cleaned_rejected", "media_assets", type_="check")
    op.drop_index("ix_media_assets_retention", table_name="media_assets")
    op.drop_column("media_assets", "storage_cleaned_at")
