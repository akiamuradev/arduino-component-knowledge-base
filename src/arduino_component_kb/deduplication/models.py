"""Durable duplicate candidates and immutable administrator decisions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        CheckConstraint("left_component_id < right_component_id", name="ck_duplicate_pair_order"),
        CheckConstraint("kind IN ('exact','fuzzy')", name="ck_duplicate_candidates_kind"),
        CheckConstraint(
            "status IN ('open','merged','rejected','superseded')",
            name="ck_duplicate_candidates_status",
        ),
        CheckConstraint("score BETWEEN 0 AND 1", name="ck_duplicate_candidates_score"),
        Index(
            "uq_duplicate_candidates_open_version",
            "left_component_id",
            "right_component_id",
            "algorithm_version",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_duplicate_candidates_open_score", "status", "score"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    left_component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    right_component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"))


class MergeDecision(Base):
    __tablename__ = "merge_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('merge','attach','create','reject')",
            name="ck_merge_decisions_decision",
        ),
        CheckConstraint(
            "(decision IN ('merge','attach') AND survivor_component_id IS NOT NULL) OR "
            "(decision IN ('create','reject') AND survivor_component_id IS NULL)",
            name="ck_merge_decisions_survivor",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("duplicate_candidates.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    survivor_component_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id", ondelete="RESTRICT")
    )
    field_resolution_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    decided_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    before_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    after_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
