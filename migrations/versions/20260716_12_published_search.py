"""Add indexed published snapshot search documents.

Revision ID: 20260716_12
Revises: 20260716_11
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_12"
down_revision: str | None = "20260716_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "published_search_documents",
        sa.Column(
            "component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("category_id", uuid, sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("aliases_text", sa.Text(), nullable=False),
        sa.Column("manufacturer", sa.String(120), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("tags_text", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "difficulty IN ('beginner','intermediate','advanced')",
            name="ck_published_search_difficulty",
        ),
    )
    op.create_index(
        "ix_published_search_vector",
        "published_search_documents",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_published_search_trigram",
        "published_search_documents",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index("ix_published_search_category", "published_search_documents", ["category_id"])
    op.create_index("ix_published_search_difficulty", "published_search_documents", ["difficulty"])
    op.execute(
        """
        INSERT INTO published_search_documents (
            component_id, revision, category_id, difficulty, title, aliases_text,
            manufacturer, model, summary, tags_text, search_text, search_vector, published_at
        )
        SELECT
            revision.component_id,
            revision.revision,
            (revision.content_json ->> 'primary_category_id')::uuid,
            revision.content_json ->> 'difficulty',
            revision.content_json ->> 'title',
            COALESCE((
                SELECT string_agg(value, ' ')
                FROM jsonb_array_elements_text(revision.content_json -> 'aliases') AS value
            ), ''),
            COALESCE(revision.content_json ->> 'manufacturer', ''),
            COALESCE(revision.content_json ->> 'model', ''),
            revision.content_json ->> 'summary',
            COALESCE((
                SELECT string_agg(value, ' ')
                FROM jsonb_array_elements_text(revision.content_json -> 'tags') AS value
            ), ''),
            lower(concat_ws(
                ' ',
                revision.content_json ->> 'title',
                COALESCE((
                    SELECT string_agg(value, ' ')
                    FROM jsonb_array_elements_text(revision.content_json -> 'aliases') AS value
                ), ''),
                COALESCE(revision.content_json ->> 'manufacturer', ''),
                COALESCE(revision.content_json ->> 'model', ''),
                revision.content_json ->> 'summary',
                COALESCE((
                    SELECT string_agg(value, ' ')
                    FROM jsonb_array_elements_text(revision.content_json -> 'tags') AS value
                ), '')
            )),
            setweight(to_tsvector('simple', revision.content_json ->> 'title'), 'A') ||
            setweight(to_tsvector('simple', concat_ws(
                ' ',
                COALESCE((
                    SELECT string_agg(value, ' ')
                    FROM jsonb_array_elements_text(revision.content_json -> 'aliases') AS value
                ), ''),
                COALESCE(revision.content_json ->> 'manufacturer', ''),
                COALESCE(revision.content_json ->> 'model', '')
            )), 'B') ||
            setweight(to_tsvector('simple', concat_ws(
                ' ',
                revision.content_json ->> 'summary',
                COALESCE((
                    SELECT string_agg(value, ' ')
                    FROM jsonb_array_elements_text(revision.content_json -> 'tags') AS value
                ), '')
            )), 'C'),
            revision.created_at
        FROM component_revisions AS revision
        JOIN components ON components.id = revision.component_id
        JOIN (
            SELECT component_id, max(revision) AS revision
            FROM component_revisions
            WHERE status = 'published'
            GROUP BY component_id
        ) AS latest
          ON latest.component_id = revision.component_id
         AND latest.revision = revision.revision
        WHERE revision.status = 'published' AND components.status != 'archived'
        """
    )


def downgrade() -> None:
    op.drop_table("published_search_documents")
