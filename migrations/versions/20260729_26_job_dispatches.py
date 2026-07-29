"""Add bounded transactional background-job dispatch.

Revision ID: 20260729_26
Revises: 20260729_25
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_26"
down_revision: str | None = "20260729_25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "job_dispatches",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("job_type", sa.String(16), nullable=False),
        sa.Column("job_id", uuid, nullable=False),
        sa.Column("queue_name", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("job_type IN ('import','media')", name="ck_job_dispatches_type"),
        sa.CheckConstraint(
            "queue_name IN ('imports','images','videos')",
            name="ck_job_dispatches_queue",
        ),
        sa.CheckConstraint(
            "status IN ('pending','delivered','failed')",
            name="ck_job_dispatches_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_job_dispatches_attempts"),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_job_dispatches_max_attempts",
        ),
        sa.CheckConstraint(
            "attempts <= max_attempts",
            name="ck_job_dispatches_attempt_bound",
        ),
        sa.CheckConstraint(
            "(job_type = 'import' AND queue_name = 'imports') OR "
            "(job_type = 'media' AND queue_name IN ('images','videos'))",
            name="ck_job_dispatches_type_queue",
        ),
        sa.UniqueConstraint("job_type", "job_id", name="uq_job_dispatches_job"),
    )
    op.create_index(
        "ix_job_dispatches_due",
        "job_dispatches",
        ["status", "next_attempt_at"],
    )

    op.execute(
        """
        INSERT INTO job_dispatches (
            id, job_type, job_id, queue_name, status, attempts, max_attempts,
            next_attempt_at, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), 'import', id, 'imports', 'pending', 0, max_attempts,
            updated_at, created_at, updated_at
        FROM import_jobs
        WHERE status IN ('queued','running','retrying')
        """
    )
    op.execute(
        """
        INSERT INTO job_dispatches (
            id, job_type, job_id, queue_name, status, attempts, max_attempts,
            next_attempt_at, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), 'media', id, queue_name, 'pending', 0, max_attempts,
            updated_at, created_at, updated_at
        FROM media_jobs
        WHERE status IN ('queued','running','retrying')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_job_dispatches_due", table_name="job_dispatches")
    op.drop_table("job_dispatches")
