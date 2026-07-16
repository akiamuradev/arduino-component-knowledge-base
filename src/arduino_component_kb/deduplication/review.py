"""Administrator-owned, evidence-preserving duplicate review workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.domain import (
    CatalogCard,
    ComponentNotFoundError,
    RevisionConflictError,
)
from arduino_component_kb.catalog.models import Component
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.deduplication.models import DuplicateCandidate, MergeDecision


class DuplicateDecision(StrEnum):
    MERGE = "merge"
    ATTACH = "attach"
    CREATE = "create"
    REJECT = "reject"


class DuplicateReviewError(Exception):
    pass


class CandidateNotFoundError(DuplicateReviewError):
    pass


class CandidateResolvedError(DuplicateReviewError):
    pass


class InvalidDecisionError(DuplicateReviewError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateReview:
    id: UUID
    kind: str
    status: str
    score: Decimal
    algorithm_version: str
    evidence: dict[str, object]
    created_at: datetime
    left: CatalogCard
    right: CatalogCard


def _snapshot(card: CatalogCard) -> dict[str, object]:
    data = asdict(card.data)
    data["primary_category_id"] = str(card.data.primary_category_id)
    data["difficulty"] = card.data.difficulty.value
    data["specifications"] = [asdict(item) for item in card.data.specifications]
    data["compatibility"] = [asdict(item) for item in card.data.compatibility]
    return {
        "id": str(card.id),
        "status": card.status.value,
        "revision": card.revision,
        "data": data,
    }


class DuplicateReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, candidate_status: str = "open", limit: int = 100) -> list[CandidateReview]:
        rows = await self.session.scalars(
            select(DuplicateCandidate)
            .where(DuplicateCandidate.status == candidate_status)
            .order_by(DuplicateCandidate.score.desc(), DuplicateCandidate.created_at)
            .limit(limit)
        )
        return [await self._review(row) for row in rows]

    async def get(self, candidate_id: UUID) -> CandidateReview:
        row = await self.session.get(DuplicateCandidate, candidate_id)
        if row is None:
            raise CandidateNotFoundError
        return await self._review(row)

    async def decide(
        self,
        candidate_id: UUID,
        decision: DuplicateDecision,
        left_revision: int,
        right_revision: int,
        actor_id: UUID,
        reason: str,
        survivor_component_id: UUID | None,
        field_sources: dict[str, UUID],
    ) -> MergeDecision:
        candidate = await self.session.scalar(
            select(DuplicateCandidate)
            .where(DuplicateCandidate.id == candidate_id)
            .with_for_update()
        )
        if candidate is None:
            raise CandidateNotFoundError
        if candidate.status != "open":
            raise CandidateResolvedError
        pair = {candidate.left_component_id, candidate.right_component_id}
        if decision in {DuplicateDecision.MERGE, DuplicateDecision.ATTACH}:
            if survivor_component_id not in pair:
                raise InvalidDecisionError
        elif survivor_component_id is not None or field_sources:
            raise InvalidDecisionError
        if decision is not DuplicateDecision.MERGE and field_sources:
            raise InvalidDecisionError

        catalog = CatalogService(self.session)
        before_left = await catalog.get_card(candidate.left_component_id)
        before_right = await catalog.get_card(candidate.right_component_id)
        after: CatalogCard | None = None
        if decision in {DuplicateDecision.MERGE, DuplicateDecision.ATTACH}:
            if survivor_component_id is None:
                raise InvalidDecisionError
            before_left, before_right, after = await catalog.resolve_duplicate_pair(
                candidate.left_component_id,
                candidate.right_component_id,
                left_revision,
                right_revision,
                survivor_component_id,
                field_sources,
                actor_id,
                merge_fields=decision is DuplicateDecision.MERGE,
            )
        else:
            rows = list(
                await self.session.scalars(
                    select(Component)
                    .where(Component.id.in_(sorted(pair)))
                    .order_by(Component.id)
                    .with_for_update()
                )
            )
            revisions = {row.id: row.revision for row in rows}
            if len(rows) != 2:
                raise ComponentNotFoundError
            if (
                revisions[candidate.left_component_id] != left_revision
                or revisions[candidate.right_component_id] != right_revision
            ):
                raise RevisionConflictError

        now = datetime.now(UTC)
        candidate.status = (
            "merged"
            if decision is DuplicateDecision.MERGE
            else "rejected"
            if decision is DuplicateDecision.REJECT
            else "superseded"
        )
        candidate.resolved_at = now
        candidate.resolved_by = actor_id
        resolution = {field: str(source) for field, source in field_sources.items()}
        row = MergeDecision(
            id=uuid4(),
            candidate_id=candidate.id,
            decision=decision.value,
            survivor_component_id=survivor_component_id,
            field_resolution_json=resolution,
            reason=reason.strip(),
            decided_by=actor_id,
            decided_at=now,
            before_snapshot={"left": _snapshot(before_left), "right": _snapshot(before_right)},
            after_snapshot=_snapshot(after) if after is not None else None,
        )
        self.session.add(row)
        if decision in {DuplicateDecision.MERGE, DuplicateDecision.ATTACH}:
            loser = next(
                component_id for component_id in pair if component_id != survivor_component_id
            )
            await self.session.execute(
                update(DuplicateCandidate)
                .where(
                    DuplicateCandidate.id != candidate.id,
                    DuplicateCandidate.status == "open",
                    or_(
                        DuplicateCandidate.left_component_id == loser,
                        DuplicateCandidate.right_component_id == loser,
                    ),
                )
                .values(status="superseded", resolved_at=now, resolved_by=actor_id)
            )
        await self.session.flush()
        return row

    async def _review(self, row: DuplicateCandidate) -> CandidateReview:
        catalog = CatalogService(self.session)
        return CandidateReview(
            id=row.id,
            kind=row.kind,
            status=row.status,
            score=row.score,
            algorithm_version=row.algorithm_version,
            evidence=row.evidence_json,
            created_at=row.created_at,
            left=await catalog.get_card(row.left_component_id),
            right=await catalog.get_card(row.right_component_id),
        )
