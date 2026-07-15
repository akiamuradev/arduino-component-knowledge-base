"""Add durable retry, lease, and idempotency metadata to media jobs.

Revision ID: 20260715_05
Revises: 20260715_04
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_05"
down_revision: str | None = "20260715_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_jobs", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4")
    )
    op.add_column(
        "media_jobs",
        sa.Column("manual_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("media_jobs", sa.Column("idempotency_key", sa.String(length=160), nullable=True))
    op.add_column("media_jobs", sa.Column("queue_name", sa.String(length=32), nullable=True))
    op.add_column("media_jobs", sa.Column("task_name", sa.String(length=80), nullable=True))
    op.add_column(
        "media_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "media_jobs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "media_jobs", sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.execute("UPDATE media_jobs SET idempotency_key = 'media:' || asset_id::text")
    op.execute(
        "UPDATE media_jobs AS job SET queue_name = CASE asset.kind "
        "WHEN 'video' THEN 'videos' ELSE 'images' END, "
        "task_name = CASE asset.kind WHEN 'video' THEN 'process_media_video' "
        "ELSE 'process_media_image' END FROM media_assets AS asset "
        "WHERE asset.id = job.asset_id"
    )
    op.alter_column("media_jobs", "idempotency_key", nullable=False)
    op.alter_column("media_jobs", "queue_name", nullable=False)
    op.alter_column("media_jobs", "task_name", nullable=False)
    op.alter_column("media_jobs", "max_attempts", server_default=None)
    op.alter_column("media_jobs", "manual_retry_count", server_default=None)

    op.drop_constraint("ck_media_jobs_status", "media_jobs", type_="check")
    op.create_check_constraint(
        "ck_media_jobs_status",
        "media_jobs",
        "status IN ('queued', 'running', 'retrying', 'succeeded', 'failed')",
    )
    op.create_check_constraint(
        "ck_media_jobs_max_attempts", "media_jobs", "max_attempts BETWEEN 1 AND 10"
    )
    op.create_check_constraint(
        "ck_media_jobs_attempt_bound", "media_jobs", "attempts <= max_attempts"
    )
    op.create_check_constraint(
        "ck_media_jobs_manual_retries", "media_jobs", "manual_retry_count >= 0"
    )
    op.create_unique_constraint("uq_media_jobs_idempotency_key", "media_jobs", ["idempotency_key"])
    op.create_index("ix_media_jobs_monitor", "media_jobs", ["status", "updated_at"])
    op.create_index("ix_media_jobs_queue_status", "media_jobs", ["queue_name", "status"])


def downgrade() -> None:
    op.drop_index("ix_media_jobs_queue_status", table_name="media_jobs")
    op.drop_index("ix_media_jobs_monitor", table_name="media_jobs")
    op.drop_constraint("uq_media_jobs_idempotency_key", "media_jobs", type_="unique")
    op.drop_constraint("ck_media_jobs_manual_retries", "media_jobs", type_="check")
    op.drop_constraint("ck_media_jobs_attempt_bound", "media_jobs", type_="check")
    op.drop_constraint("ck_media_jobs_max_attempts", "media_jobs", type_="check")
    op.drop_constraint("ck_media_jobs_status", "media_jobs", type_="check")
    op.execute("UPDATE media_jobs SET status = 'failed' WHERE status = 'retrying'")
    op.create_check_constraint(
        "ck_media_jobs_status",
        "media_jobs",
        "status IN ('queued', 'running', 'succeeded', 'failed')",
    )
    for column in (
        "last_enqueued_at",
        "next_retry_at",
        "heartbeat_at",
        "task_name",
        "queue_name",
        "idempotency_key",
        "manual_retry_count",
        "max_attempts",
    ):
        op.drop_column("media_jobs", column)
