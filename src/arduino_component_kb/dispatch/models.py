"""Transactional dispatch intent persisted beside background jobs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from arduino_component_kb.db import Base


class JobDispatch(Base):
    """Bounded delivery state; Redis is never the source of job truth."""

    __tablename__ = "job_dispatches"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('import','media')",
            name="ck_job_dispatches_type",
        ),
        CheckConstraint(
            "queue_name IN ('imports','images','videos')",
            name="ck_job_dispatches_queue",
        ),
        CheckConstraint(
            "status IN ('pending','delivered','failed')",
            name="ck_job_dispatches_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_job_dispatches_attempts"),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_job_dispatches_max_attempts",
        ),
        CheckConstraint(
            "attempts <= max_attempts",
            name="ck_job_dispatches_attempt_bound",
        ),
        CheckConstraint(
            "(job_type = 'import' AND queue_name = 'imports') OR "
            "(job_type = 'media' AND queue_name IN ('images','videos'))",
            name="ck_job_dispatches_type_queue",
        ),
        UniqueConstraint("job_type", "job_id", name="uq_job_dispatches_job"),
        Index("ix_job_dispatches_due", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_type: Mapped[str] = mapped_column(String(16), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    queue_name: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
