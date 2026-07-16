"""Durable fuzzy duplicate candidates; decisions belong to the next stage."""

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
