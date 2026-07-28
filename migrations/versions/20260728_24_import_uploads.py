"""Add explicit cancellation to component imports.

Revision ID: 20260728_24
Revises: 20260728_23
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_24"
down_revision: str | None = "20260728_23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_import_jobs_status", "import_jobs", type_="check")
    op.create_check_constraint(
        "ck_import_jobs_status",
        "import_jobs",
        "status IN ('queued','running','retrying','succeeded','failed','cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_import_jobs_status", "import_jobs", type_="check")
    op.execute(
        """
        UPDATE import_jobs
        SET
            status = 'failed',
            error_code = 'import_cancelled'
        WHERE status = 'cancelled'
        """
    )
    op.create_check_constraint(
        "ck_import_jobs_status",
        "import_jobs",
        "status IN ('queued','running','retrying','succeeded','failed')",
    )
