"""Durable bundle, immutable per-item plan and cross-bundle provenance."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class LegacyBundle(Base):
    __tablename__ = "legacy_bundles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploading','uploaded','analyzing','ready','applying',"
            "'completed','failed','cancelled')",
            name="ck_legacy_bundle_status",
        ),
        Index("ix_legacy_bundles_status", "status", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="analysis")
    zip_size: Mapped[int] = mapped_column(Integer, nullable=False)
    xlsx_size: Mapped[int] = mapped_column(Integer, nullable=False)
    zip_sha256: Mapped[str | None] = mapped_column(String(64))
    xlsx_sha256: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(80))
    plan_hash: Mapped[str | None] = mapped_column(String(64))
    confirmed_hash: Mapped[str | None] = mapped_column(String(64))
    statistics: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LegacyItem(Base):
    __tablename__ = "legacy_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','applying','applied','skipped','needs_review','failed')",
            name="ck_legacy_item_status",
        ),
        CheckConstraint(
            "decision IN ('create','merge','skip','review')", name="ck_legacy_decision"
        ),
        Index("uq_legacy_items_identity", "bundle_id", "identity", unique=True),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    bundle_id: Mapped[UUID] = mapped_column(ForeignKey("legacy_bundles.id"), nullable=False)
    identity: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    candidates: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    merge_id: Mapped[UUID | None] = mapped_column(ForeignKey("components.id"))
    merge_revision: Mapped[int | None] = mapped_column(Integer)
    merge_edit_token: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    result_id: Mapped[UUID | None] = mapped_column(ForeignKey("components.id"))
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80))


class LegacySourceLink(Base):
    __tablename__ = "legacy_source_links"
    identity: Mapped[str] = mapped_column(String(64), primary_key=True)
    component_id: Mapped[UUID] = mapped_column(
        ForeignKey("components.id"), nullable=False, index=True
    )
    item_id: Mapped[UUID] = mapped_column(ForeignKey("legacy_items.id"), nullable=False)
    license_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    license_evidence: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
