"""Allow incomplete component content while a card remains a draft.

Revision ID: 20260729_28
Revises: 20260729_27
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_28"
down_revision: str | None = "20260729_27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_components_title", "components", type_="check")
    op.drop_constraint("ck_components_summary", "components", type_="check")
    op.create_check_constraint(
        "ck_components_title",
        "components",
        "char_length(title) <= 160",
    )
    op.create_check_constraint(
        "ck_components_summary",
        "components",
        "char_length(summary) <= 500",
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE components SET title = 'Без названия' WHERE char_length(title) < 2"))
    op.execute(
        sa.text(
            "UPDATE components SET summary = "
            "'Информация будет добавлена редактором.' "
            "WHERE char_length(summary) < 20"
        )
    )
    op.drop_constraint("ck_components_summary", "components", type_="check")
    op.drop_constraint("ck_components_title", "components", type_="check")
    op.create_check_constraint(
        "ck_components_title",
        "components",
        "char_length(title) BETWEEN 2 AND 160",
    )
    op.create_check_constraint(
        "ck_components_summary",
        "components",
        "char_length(summary) BETWEEN 20 AND 500",
    )
