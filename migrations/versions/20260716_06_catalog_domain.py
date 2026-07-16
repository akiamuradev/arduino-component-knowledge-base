"""Add catalog cards, taxonomy, boards, and typed properties.

Revision ID: 20260716_06
Revises: 20260715_05
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_06"
down_revision: str | None = "20260715_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "categories",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("parent_id", uuid, sa.ForeignKey("categories.id")),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("key", name="uq_categories_key"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_categories_parent"),
    )
    op.create_table(
        "boards",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("manufacturer", sa.String(120)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "units",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
    )
    op.create_table(
        "property_definitions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("unit_id", uuid, sa.ForeignKey("units.id")),
        sa.Column("is_multivalue", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "value_type IN ('text','number','boolean')", name="ck_property_definitions_type"
        ),
    )
    op.create_table(
        "components",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("manufacturer", sa.String(120)),
        sa.Column("model", sa.String(120)),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text()),
        sa.Column("usage_notes", sa.Text()),
        sa.Column("safety_notes", sa.Text()),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("teacher_notes", sa.Text()),
        sa.Column("primary_category_id", uuid, sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("manual_original", sa.Boolean(), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_components_status"
        ),
        sa.CheckConstraint(
            "difficulty IN ('beginner','intermediate','advanced')", name="ck_components_difficulty"
        ),
        sa.CheckConstraint("revision > 0", name="ck_components_revision"),
        sa.CheckConstraint("char_length(title) BETWEEN 2 AND 160", name="ck_components_title"),
        sa.CheckConstraint("char_length(summary) BETWEEN 20 AND 500", name="ck_components_summary"),
        sa.CheckConstraint(
            "status = 'draft' OR published_at IS NOT NULL", name="ck_components_published_at"
        ),
    )
    op.create_index("ix_components_status_updated", "components", ["status", "updated_at"])
    op.create_table(
        "component_revisions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "component_id", uuid, sa.ForeignKey("components.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_json", postgresql.JSONB(), nullable=False),
        sa.Column("actor_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("component_id", "revision", name="uq_component_revisions_number"),
    )
    op.create_table(
        "component_aliases",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "component_id", uuid, sa.ForeignKey("components.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("alias", sa.String(100), nullable=False),
        sa.Column("normalized_alias", sa.String(100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "component_id", "normalized_alias", name="uq_component_aliases_normalized"
        ),
    )
    op.create_table(
        "tags",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("normalized_name", sa.String(100), nullable=False, unique=True),
    )
    op.create_table(
        "component_tags",
        sa.Column(
            "component_id",
            uuid,
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tag_id", uuid, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "component_properties",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "component_id", uuid, sa.ForeignKey("components.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("definition_id", uuid, sa.ForeignKey("property_definitions.id"), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("value_number", sa.Numeric(24, 8)),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    categories = (
        ("boards", "Платы"),
        ("sensors", "Датчики"),
        ("actuators", "Исполнительные устройства"),
        ("displays", "Дисплеи"),
        ("communication", "Связь"),
        ("power", "Питание"),
        ("input", "Устройства ввода"),
        ("prototyping", "Прототипирование"),
        ("passive", "Пассивные компоненты"),
        ("other", "Другое"),
    )
    for position, (key, name) in enumerate(categories):
        op.execute(
            sa.text(
                "INSERT INTO categories (id,key,name,is_active,position) "
                "VALUES (CAST(:id AS uuid),:key,:name,true,:position)"
            ).bindparams(
                id=f"00000000-0000-4000-8000-{position + 1:012d}",
                key=key,
                name=name,
                position=position,
            )
        )
    op.execute("UPDATE media_assets SET component_id = NULL WHERE component_id IS NOT NULL")
    op.create_foreign_key(
        "fk_media_assets_component",
        "media_assets",
        "components",
        ["component_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_media_assets_component", "media_assets", type_="foreignkey")
    for table in (
        "component_properties",
        "component_tags",
        "tags",
        "component_aliases",
        "component_revisions",
        "components",
        "property_definitions",
        "units",
        "boards",
        "categories",
    ):
        op.drop_table(table)
