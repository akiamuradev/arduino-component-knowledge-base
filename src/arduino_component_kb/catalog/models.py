"""SQLAlchemy models for catalog cards and controlled taxonomy."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    parent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id")
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Component(Base):
    __tablename__ = "components"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    title: Mapped[str] = mapped_column(String(160))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    usage_notes: Mapped[str | None] = mapped_column(Text)
    safety_notes: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(16))
    teacher_notes: Mapped[str | None] = mapped_column(Text)
    primary_category_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id")
    )
    manual_original: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    updated_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class ComponentRevision(Base):
    __tablename__ = "component_revisions"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE")
    )
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    content_json: Mapped[dict[str, object]] = mapped_column(JSONB)
    actor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ComponentAlias(Base):
    __tablename__ = "component_aliases"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE")
    )
    alias: Mapped[str] = mapped_column(String(100))
    normalized_alias: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True)


class ComponentTag(Base):
    __tablename__ = "component_tags"
    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class Board(Base):
    __tablename__ = "boards"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Unit(Base):
    __tablename__ = "units"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    symbol: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))


class PropertyDefinition(Base):
    __tablename__ = "property_definitions"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    label: Mapped[str] = mapped_column(String(160))
    value_type: Mapped[str] = mapped_column(String(16))
    unit_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("units.id"))
    is_multivalue: Mapped[bool] = mapped_column(Boolean, default=False)


class ComponentProperty(Base):
    __tablename__ = "component_properties"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE")
    )
    definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("property_definitions.id")
    )
    value_text: Mapped[str] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    position: Mapped[int] = mapped_column(Integer, default=0)
