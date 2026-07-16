"""Administrator API for evidence-based duplicate decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.catalog import ComponentResponse
from arduino_component_kb.api.catalog import response as component_response
from arduino_component_kb.api.dependencies import csrf_principal, database_session, require_roles
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.domain import CatalogError, RevisionConflictError
from arduino_component_kb.deduplication.review import (
    CandidateNotFoundError,
    CandidateResolvedError,
    CandidateReview,
    DuplicateDecision,
    DuplicateReviewService,
    InvalidDecisionError,
)
from arduino_component_kb.logging import current_request_id

router = APIRouter(prefix="/api/v1/admin/duplicates", tags=["duplicate-review"])
administrator = require_roles(Role.ADMINISTRATOR)


class CandidateResponse(BaseModel):
    id: str
    kind: str
    status: str
    score: float
    algorithm_version: str
    evidence: dict[str, object]
    created_at: datetime
    left: ComponentResponse
    right: ComponentResponse


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int


class DecisionRequest(BaseModel):
    decision: DuplicateDecision
    left_revision: int = Field(ge=1)
    right_revision: int = Field(ge=1)
    survivor_component_id: UUID | None = None
    field_sources: dict[str, UUID] = Field(default_factory=dict, max_length=16)
    reason: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def consistent_action(self) -> DecisionRequest:
        combines = self.decision in {DuplicateDecision.MERGE, DuplicateDecision.ATTACH}
        if combines != (self.survivor_component_id is not None):
            raise ValueError("survivor must be supplied only for merge or attach")
        if self.decision is not DuplicateDecision.MERGE and self.field_sources:
            raise ValueError("field sources belong only to merge")
        return self


class DecisionResponse(BaseModel):
    id: str
    candidate_id: str
    decision: DuplicateDecision
    decided_at: datetime


def candidate_response(item: CandidateReview) -> CandidateResponse:
    return CandidateResponse(
        id=str(item.id),
        kind=item.kind,
        status=item.status,
        score=float(item.score),
        algorithm_version=item.algorithm_version,
        evidence=item.evidence,
        created_at=item.created_at,
        left=component_response(item.left),
        right=component_response(item.right),
    )


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    _: Annotated[Principal, Depends(administrator)],
    session: Annotated[AsyncSession, Depends(database_session)],
    candidate_status: Annotated[
        str, Query(alias="status", pattern=r"^(open|merged|rejected|superseded)$")
    ] = "open",
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> CandidateListResponse:
    items = [
        candidate_response(item)
        for item in await DuplicateReviewService(session).list(candidate_status, limit)
    ]
    return CandidateListResponse(items=items, total=len(items))


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    _: Annotated[Principal, Depends(administrator)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> CandidateResponse:
    try:
        return candidate_response(await DuplicateReviewService(session).get(candidate_id))
    except CandidateNotFoundError as error:
        raise HTTPException(404, detail={"code": "duplicate_candidate_not_found"}) from error


@router.post("/{candidate_id}/decision", response_model=DecisionResponse)
async def decide_candidate(
    candidate_id: UUID,
    payload: DecisionRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> DecisionResponse:
    try:
        decision = await DuplicateReviewService(session).decide(
            candidate_id=candidate_id,
            actor_id=actor.user_id,
            **payload.model_dump(),
        )
        await AuthRepository(session).audit(
            now=datetime.now(UTC),
            actor_user_id=actor.user_id,
            action=f"duplicate.{decision.decision}",
            object_type="duplicate_candidate",
            object_id=candidate_id,
            request_id=current_request_id(),
            outcome="success",
            details={
                "decision_id": str(decision.id),
                "survivor_component_id": (
                    str(decision.survivor_component_id)
                    if decision.survivor_component_id is not None
                    else None
                ),
            },
        )
        await session.commit()
        return DecisionResponse(
            id=str(decision.id),
            candidate_id=str(decision.candidate_id),
            decision=DuplicateDecision(decision.decision),
            decided_at=decision.decided_at,
        )
    except CandidateNotFoundError as error:
        await session.rollback()
        raise HTTPException(404, detail={"code": "duplicate_candidate_not_found"}) from error
    except CandidateResolvedError as error:
        await session.rollback()
        raise HTTPException(409, detail={"code": "duplicate_candidate_resolved"}) from error
    except RevisionConflictError as error:
        await session.rollback()
        raise HTTPException(409, detail={"code": "revision_conflict"}) from error
    except (InvalidDecisionError, CatalogError, IntegrityError) as error:
        await session.rollback()
        raise HTTPException(409, detail={"code": "duplicate_decision_conflict"}) from error
