"""Deactivate all repository sources for new imports.

Revision ID: 20260910_29
Revises: 20260729_28
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_29"
down_revision: str | None = "20260729_28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE sources
            SET status = 'inactive',
                is_enabled = false,
                allow_text_import = 'none',
                allow_facts_import = false,
                allow_media_import = false,
                allow_code_import = false,
                allow_attachment_import = false,
                updated_at = now()
            WHERE key IN ('seeed_wiki', 'kicad_symbols')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE sources
            SET status = 'active',
                is_enabled = true,
                allow_text_import = 'limited',
                allow_facts_import = true,
                allow_media_import = false,
                allow_code_import = false,
                allow_attachment_import = false,
                updated_at = now()
            WHERE key IN ('seeed_wiki', 'kicad_symbols')
            """
        )
    )
