"""Add video metadata, rendition constraints, and durable progress.

Revision ID: 20260715_04
Revises: 20260715_03
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_04"
down_revision: str | None = "20260715_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("media_assets", sa.Column("video_codec", sa.String(length=40), nullable=True))
    op.add_column("media_assets", sa.Column("audio_codec", sa.String(length=40), nullable=True))
    op.add_column("media_assets", sa.Column("frame_rate", sa.Float(), nullable=True))
    for name in (
        "ck_media_assets_kind",
        "ck_media_declared_size",
        "ck_media_declared_mime",
        "ck_media_size",
        "ck_media_ready_metadata",
    ):
        op.drop_constraint(name, "media_assets", type_="check")
    op.create_check_constraint("ck_media_assets_kind", "media_assets", "kind IN ('image', 'video')")
    op.create_check_constraint(
        "ck_media_declared_size",
        "media_assets",
        "(kind = 'image' AND declared_size_bytes BETWEEN 1 AND 8388608) OR "
        "(kind = 'video' AND declared_size_bytes BETWEEN 1 AND 268435456)",
    )
    op.create_check_constraint(
        "ck_media_declared_mime",
        "media_assets",
        "(kind = 'image' AND declared_mime IN ('image/jpeg', 'image/png', 'image/webp')) OR "
        "(kind = 'video' AND declared_mime IN ('video/mp4', 'video/quicktime', 'video/webm'))",
    )
    op.create_check_constraint(
        "ck_media_size",
        "media_assets",
        "size_bytes IS NULL OR (kind = 'image' AND size_bytes BETWEEN 1 AND 8388608) OR "
        "(kind = 'video' AND size_bytes BETWEEN 1 AND 268435456)",
    )
    op.create_check_constraint(
        "ck_media_ready_metadata",
        "media_assets",
        "status != 'ready' OR (detected_mime IS NOT NULL AND size_bytes IS NOT NULL "
        "AND length(sha256) = 64 AND width > 0 AND height > 0 AND "
        "((kind = 'image' AND length(phash) = 16) OR "
        "(kind = 'video' AND duration_ms > 0 AND video_codec IS NOT NULL "
        "AND frame_rate > 0 AND frame_rate <= 30)))",
    )

    op.add_column("media_variants", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("media_variants", sa.Column("video_codec", sa.String(length=40), nullable=True))
    op.add_column("media_variants", sa.Column("audio_codec", sa.String(length=40), nullable=True))
    op.add_column("media_variants", sa.Column("frame_rate", sa.Float(), nullable=True))
    op.drop_constraint("ck_media_variants_name", "media_variants", type_="check")
    op.drop_constraint("ck_media_variants_mime", "media_variants", type_="check")
    op.create_check_constraint(
        "ck_media_variants_name",
        "media_variants",
        "variant IN ('320w', '800w', '1600w', 'video_720p', 'poster')",
    )
    op.create_check_constraint(
        "ck_media_variants_mime",
        "media_variants",
        "(variant IN ('320w', '800w', '1600w', 'poster') AND mime = 'image/webp') OR "
        "(variant = 'video_720p' AND mime = 'video/mp4')",
    )
    op.create_check_constraint(
        "ck_media_video_rendition",
        "media_variants",
        "variant != 'video_720p' OR (duration_ms > 0 AND video_codec = 'h264' "
        "AND (audio_codec IS NULL OR audio_codec = 'aac') "
        "AND frame_rate > 0 AND frame_rate <= 30)",
    )

    op.add_column(
        "media_jobs",
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="queued"),
    )
    op.add_column(
        "media_jobs",
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_media_jobs_progress", "media_jobs", "progress_percent BETWEEN 0 AND 100"
    )
    op.create_check_constraint(
        "ck_media_jobs_phase",
        "media_jobs",
        "phase IN ('queued', 'starting', 'downloading', 'probing', 'transcoding', "
        "'poster', 'uploading', 'retrying', 'completed', 'failed')",
    )
    op.alter_column("media_jobs", "phase", server_default=None)
    op.alter_column("media_jobs", "progress_percent", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_media_jobs_phase", "media_jobs", type_="check")
    op.drop_constraint("ck_media_jobs_progress", "media_jobs", type_="check")
    op.drop_column("media_jobs", "progress_percent")
    op.drop_column("media_jobs", "phase")

    op.drop_constraint("ck_media_video_rendition", "media_variants", type_="check")
    op.drop_constraint("ck_media_variants_mime", "media_variants", type_="check")
    op.drop_constraint("ck_media_variants_name", "media_variants", type_="check")
    op.create_check_constraint(
        "ck_media_variants_name",
        "media_variants",
        "variant IN ('320w', '800w', '1600w')",
    )
    op.create_check_constraint("ck_media_variants_mime", "media_variants", "mime = 'image/webp'")
    for column in ("frame_rate", "audio_codec", "video_codec", "duration_ms"):
        op.drop_column("media_variants", column)

    for name in (
        "ck_media_ready_metadata",
        "ck_media_size",
        "ck_media_declared_mime",
        "ck_media_declared_size",
        "ck_media_assets_kind",
    ):
        op.drop_constraint(name, "media_assets", type_="check")
    op.create_check_constraint("ck_media_assets_kind", "media_assets", "kind = 'image'")
    op.create_check_constraint(
        "ck_media_declared_size",
        "media_assets",
        "declared_size_bytes BETWEEN 1 AND 8388608",
    )
    op.create_check_constraint(
        "ck_media_declared_mime",
        "media_assets",
        "declared_mime IN ('image/jpeg', 'image/png', 'image/webp')",
    )
    op.create_check_constraint(
        "ck_media_size",
        "media_assets",
        "size_bytes IS NULL OR size_bytes BETWEEN 1 AND 8388608",
    )
    op.create_check_constraint(
        "ck_media_ready_metadata",
        "media_assets",
        "status != 'ready' OR (detected_mime IS NOT NULL AND size_bytes IS NOT NULL "
        "AND length(sha256) = 64 AND length(phash) = 16 AND width > 0 AND height > 0)",
    )
    for column in ("frame_rate", "audio_codec", "video_codec", "duration_ms"):
        op.drop_column("media_assets", column)
