"""Establish the backend infrastructure migration baseline.

Revision ID: 20260715_01
Revises: None
Create Date: 2026-07-15
"""

from collections.abc import Sequence

revision: str = "20260715_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No domain tables are introduced at the infrastructure stage."""


def downgrade() -> None:
    """The empty baseline has no domain objects to remove."""
