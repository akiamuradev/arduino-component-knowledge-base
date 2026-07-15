"""Add durable image assets, variants, and processing jobs.

Revision ID: 20260715_03
Revises: 20260715_02
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_03"
down_revision: str | None = "20260715_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("alt_text", sa.String(length=500), nullable=False),
        sa.Column("attribution", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("object_key", sa.String(length=255), nullable=False),
        sa.Column("declared_mime", sa.String(length=100), nullable=False),
        sa.Column("declared_size_bytes", sa.Integer(), nullable=False),
        sa.Column("detected_mime", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("phash", sa.String(length=16), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind = 'image'", name="ck_media_assets_kind"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'rejected')",
            name="ck_media_assets_status",
        ),
        sa.CheckConstraint(
            "declared_size_bytes BETWEEN 1 AND 8388608", name="ck_media_declared_size"
        ),
        sa.CheckConstraint(
            "declared_mime IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_media_declared_mime",
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes BETWEEN 1 AND 8388608", name="ck_media_size"
        ),
        sa.CheckConstraint(
            "status != 'ready' OR (detected_mime IS NOT NULL AND size_bytes IS NOT NULL "
            "AND length(sha256) = 64 AND length(phash) = 16 AND width > 0 AND height > 0)",
            name="ck_media_ready_metadata",
        ),
        sa.CheckConstraint(
            "status != 'rejected' OR failure_code IS NOT NULL",
            name="ck_media_rejected_failure",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name="fk_media_assets_owner", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
        sa.UniqueConstraint("bucket", "object_key", name="uq_media_assets_object"),
    )
    op.create_index("ix_media_assets_owner_status", "media_assets", ["owner_user_id", "status"])
    op.create_table(
        "media_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant", sa.String(length=16), nullable=False),
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("object_key", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.CheckConstraint("variant IN ('320w', '800w', '1600w')", name="ck_media_variants_name"),
        sa.CheckConstraint("mime = 'image/webp'", name="ck_media_variants_mime"),
        sa.CheckConstraint("size_bytes > 0", name="ck_media_variants_size"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_media_variants_dimensions"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_media_variants_sha256"),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["media_assets.id"], name="fk_media_variants_asset", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_variants"),
        sa.UniqueConstraint("asset_id", "variant", name="uq_media_variants_asset_variant"),
        sa.UniqueConstraint("bucket", "object_key", name="uq_media_variants_object"),
    )
    op.create_index("ix_media_variants_asset", "media_variants", ["asset_id"])
    op.create_table(
        "media_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_media_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_media_jobs_attempts"),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["media_assets.id"], name="fk_media_jobs_asset", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_jobs"),
        sa.UniqueConstraint("asset_id", name="uq_media_jobs_asset"),
    )


def downgrade() -> None:
    op.drop_table("media_jobs")
    op.drop_index("ix_media_variants_asset", table_name="media_variants")
    op.drop_table("media_variants")
    op.drop_index("ix_media_assets_owner_status", table_name="media_assets")
    op.drop_table("media_assets")
