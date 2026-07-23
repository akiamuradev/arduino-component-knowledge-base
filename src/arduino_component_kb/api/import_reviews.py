"""Administrator API for evidence-first import review decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import csrf_principal, database_session, require_roles
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.imports.pipeline.models.enrichment import ComponentSymbolRelationType
from arduino_component_kb.imports.pipeline.models.persistence import (
    EnrichmentReviewDecision,
)
from arduino_component_kb.imports.pipeline.normalization.registry import SPECIFICATION_REGISTRY
from arduino_component_kb.imports.review import (
    ImportReviewBundle,
    ImportReviewConflictError,
    ImportReviewNotFoundError,
    ImportReviewRepository,
    ImportReviewSummary,
    ImportReviewValidationError,
    unmapped_specifications,
)
from arduino_component_kb.logging import current_request_id

router = APIRouter(prefix="/api/v1/admin/import-reviews", tags=["import-review"])
administrator = require_roles(Role.ADMINISTRATOR)

ReviewStatus = Literal["pending", "confirmed"]
RelationType = Literal[
    "exact_component",
    "main_integrated_circuit",
    "onboard_component",
    "connector",
    "functional_equivalent",
]


class ImportReviewSummaryResponse(BaseModel):
    id: UUID
    title: str
    status: ReviewStatus
    revision: int
    quality_route: str
    quality_score_basis_points: int
    source_key: str
    created_at: datetime


class ImportReviewListResponse(BaseModel):
    items: list[ImportReviewSummaryResponse]


class IdentityCandidateResponse(BaseModel):
    id: UUID
    selected: bool
    canonical_name: str
    component_kind: str
    selected_category: str | None
    confidence: str
    resolution_status: str
    evidence: dict[str, object]


class EnrichmentCandidateResponse(BaseModel):
    id: UUID
    provider: str
    external_identity: str
    relation_type: RelationType
    confidence_basis_points: int
    status: str
    evidence: list[dict[str, object]]
    score_breakdown: list[dict[str, object]]
    symbol: dict[str, object]
    review_reasons: list[str]
    updated_at: datetime


class UnmappedSpecificationResponse(BaseModel):
    key: str
    original_label: str
    original_value: str
    reason: str
    evidence: list[dict[str, object]]
    mapped_taxonomy_path: str | None


class ImportReviewActionResponse(BaseModel):
    id: UUID
    actor_id: UUID
    action: str
    target_type: str
    target_key: str
    previous_value: dict[str, object]
    resulting_value: dict[str, object]
    reason: str
    review_revision: int
    occurred_at: datetime


class ImportReviewWorkspaceResponse(BaseModel):
    id: UUID
    status: ReviewStatus
    revision: int
    source: dict[str, object]
    facts: dict[str, object]
    provenance: list[dict[str, object]]
    field_confidence: dict[str, str]
    identity_candidates: list[IdentityCandidateResponse]
    quality_report: dict[str, object]
    unmapped_specifications: list[UnmappedSpecificationResponse]
    conflicts: list[dict[str, object]]
    enrichments: list[EnrichmentCandidateResponse]
    module_connection: dict[str, object]
    internal_electronic_components: list[dict[str, object]]
    kicad_symbols: list[dict[str, object]]
    parser_issues: list[dict[str, object]]
    taxonomy_options: list[str]
    draft: dict[str, object]
    audit_trail: list[ImportReviewActionResponse]


class ReviewActionResponse(BaseModel):
    review_draft_id: UUID
    revision: int
    status: ReviewStatus


class EnrichmentDecisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=3, max_length=1_000)


class RelationChangeRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    relation_type: RelationType
    reason: str = Field(min_length=3, max_length=1_000)


class IdentitySelectionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    identity_candidate_id: UUID
    reason: str = Field(min_length=3, max_length=1_000)


class SpecificationMappingRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    specification_key: str = Field(pattern=r"^spec-[0-9a-f]{64}$")
    taxonomy_path: str = Field(min_length=3, max_length=160)
    reason: str = Field(min_length=3, max_length=1_000)


class ParserIssueRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    note: str = Field(min_length=3, max_length=1_000)


class DraftConfirmationRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1_000)


def _dict(value: object) -> dict[str, object]:
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return value
    return {}


def _objects(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_dict(item) for item in value if isinstance(item, dict)]


def _text(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _summary(value: ImportReviewSummary) -> ImportReviewSummaryResponse:
    title = _text(_dict(value.draft.payload.get("title")).get("value"), "Untitled review draft")
    score = value.draft.payload.get("quality_score_basis_points", 0)
    return ImportReviewSummaryResponse(
        id=value.draft.id,
        title=title,
        status=value.state.status if value.state is not None else "pending",
        revision=value.state.revision if value.state is not None else 1,
        quality_route=value.draft.quality_route,
        quality_score_basis_points=score if isinstance(score, int) else 0,
        source_key=_text(
            _dict(_dict(value.draft.payload.get("artifact")).get("source")).get("source_key"),
            "unknown",
        ),
        created_at=value.draft.created_at,
    )


def _field_confidence(draft: dict[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            review = _dict(value.get("review"))
            confidence = review.get("confidence")
            if path and isinstance(confidence, str):
                result[path] = confidence
            for key, item in value.items():
                if key != "review":
                    visit(item, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}.{index}")

    visit(draft, "")
    return result


def _enrichment(value: object) -> tuple[list[dict[str, object]], dict[str, object], list[str]]:
    payload = _dict(value)
    relation = _dict(payload.get("relation"))
    reasons = payload.get("review_reasons", [])
    return (
        _objects(relation.get("score_breakdown")),
        _dict(relation.get("symbol")),
        [item for item in reasons if isinstance(item, str)] if isinstance(reasons, list) else [],
    )


def _workspace(bundle: ImportReviewBundle) -> ImportReviewWorkspaceResponse:
    state = bundle.state
    selected_identity_id = (
        state.selected_identity_candidate_id
        if state is not None
        else bundle.draft.identity_candidate_id
    )
    mappings = state.specification_mappings if state is not None else {}
    draft = bundle.draft.payload
    artifact = bundle.artifact.facts_payload
    enrichments: list[EnrichmentCandidateResponse] = []
    for item in bundle.enrichments:
        score_breakdown, symbol, review_reasons = _enrichment(item.payload)
        enrichments.append(
            EnrichmentCandidateResponse(
                id=item.id,
                provider=item.provider,
                external_identity=item.external_identity,
                relation_type=cast(RelationType, item.relation_type),
                confidence_basis_points=item.confidence_basis_points,
                status=item.status,
                evidence=list(item.evidence),
                score_breakdown=score_breakdown,
                symbol=symbol,
                review_reasons=review_reasons,
                updated_at=item.updated_at,
            )
        )
    unmapped = [
        UnmappedSpecificationResponse(
            key=str(item["key"]),
            original_label=_text(item.get("original_label"), "Unknown"),
            original_value=_text(item.get("original_value"), "Unknown"),
            reason=_text(item.get("reason"), "unmapped"),
            evidence=_objects(item.get("evidence")),
            mapped_taxonomy_path=mappings.get(str(item["key"])),
        )
        for item in unmapped_specifications(artifact)
    ]
    source = _dict(_dict(artifact.get("artifact")).get("source"))
    provenance = _objects(draft.get("provenance"))
    return ImportReviewWorkspaceResponse(
        id=bundle.draft.id,
        status=state.status if state is not None else "pending",
        revision=state.revision if state is not None else 1,
        source=source,
        facts=artifact,
        provenance=provenance,
        field_confidence=_field_confidence(draft),
        identity_candidates=[
            IdentityCandidateResponse(
                id=item.id,
                selected=item.id == selected_identity_id,
                canonical_name=item.canonical_name,
                component_kind=item.component_kind,
                selected_category=item.selected_category,
                confidence=item.confidence,
                resolution_status=item.resolution_status,
                evidence=item.payload,
            )
            for item in bundle.identities
        ],
        quality_report=bundle.evaluation.payload,
        unmapped_specifications=unmapped,
        conflicts=_objects(artifact.get("conflicts")),
        enrichments=enrichments,
        module_connection=_dict(draft.get("module_connection")),
        internal_electronic_components=_objects(draft.get("internal_electronic_components")),
        kicad_symbols=_objects(draft.get("kicad_symbols")),
        parser_issues=(list(state.parser_issues.values()) if state is not None else []),
        taxonomy_options=sorted(SPECIFICATION_REGISTRY.taxonomy_paths()),
        draft=draft,
        audit_trail=[
            ImportReviewActionResponse(
                id=item.id,
                actor_id=item.actor_id,
                action=item.action,
                target_type=item.target_type,
                target_key=item.target_key,
                previous_value=item.previous_value,
                resulting_value=item.resulting_value,
                reason=item.reason,
                review_revision=item.review_revision,
                occurred_at=item.occurred_at,
            )
            for item in bundle.actions
        ],
    )


def _review_error(error: Exception) -> HTTPException:
    if isinstance(error, ImportReviewNotFoundError):
        return HTTPException(404, detail={"code": str(error)})
    if isinstance(error, IntegrityError):
        return HTTPException(409, detail={"code": "import_review_write_conflict"})
    if isinstance(error, ImportReviewConflictError):
        return HTTPException(409, detail={"code": str(error)})
    return HTTPException(422, detail={"code": str(error)})


async def _commit(
    session: AsyncSession,
    actor: Principal,
    review_draft_id: UUID,
    revision: int,
    action: str,
) -> ReviewActionResponse:
    now = datetime.now(UTC)
    await AuthRepository(session).audit(
        now=now,
        actor_user_id=actor.user_id,
        action=f"import_review.{action}",
        object_type="import_review_draft",
        object_id=review_draft_id,
        request_id=current_request_id(),
        outcome="success",
        details={"review_revision": revision},
    )
    await session.commit()
    status_value: ReviewStatus = "confirmed" if action == "draft_confirmed" else "pending"
    return ReviewActionResponse(
        review_draft_id=review_draft_id,
        revision=revision,
        status=status_value,
    )


@router.get("", response_model=ImportReviewListResponse)
async def list_import_reviews(
    response: Response,
    _: Annotated[Principal, Depends(administrator)],
    session: Annotated[AsyncSession, Depends(database_session)],
    status: Annotated[ReviewStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ImportReviewListResponse:
    items = await ImportReviewRepository(session).list(status, limit)
    response.headers["Cache-Control"] = "no-store"
    return ImportReviewListResponse(items=[_summary(item) for item in items])


@router.get("/{review_draft_id}", response_model=ImportReviewWorkspaceResponse)
async def get_import_review(
    review_draft_id: UUID,
    response: Response,
    _: Annotated[Principal, Depends(administrator)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ImportReviewWorkspaceResponse:
    try:
        result = _workspace(await ImportReviewRepository(session).get(review_draft_id))
    except ImportReviewNotFoundError as error:
        raise _review_error(error) from error
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/{review_draft_id}/enrichments/{enrichment_id}/decision",
    response_model=ReviewActionResponse,
)
async def decide_enrichment(
    review_draft_id: UUID,
    enrichment_id: UUID,
    payload: EnrichmentDecisionRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ReviewActionResponse:
    try:
        revision = await ImportReviewRepository(session).review_enrichment(
            review_draft_id=review_draft_id,
            enrichment_id=enrichment_id,
            reviewer_id=actor.user_id,
            decision=EnrichmentReviewDecision(payload.decision),
            reason=payload.reason,
            expected_revision=payload.expected_revision,
            now=datetime.now(UTC),
        )
        return await _commit(
            session, actor, review_draft_id, revision, f"enrichment_{payload.decision}ed"
        )
    except (
        ImportReviewNotFoundError,
        ImportReviewConflictError,
        ImportReviewValidationError,
        IntegrityError,
    ) as error:
        await session.rollback()
        raise _review_error(error) from error


@router.post(
    "/{review_draft_id}/enrichments/{enrichment_id}/relation",
    response_model=ReviewActionResponse,
)
async def change_enrichment_relation(
    review_draft_id: UUID,
    enrichment_id: UUID,
    payload: RelationChangeRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ReviewActionResponse:
    try:
        revision = await ImportReviewRepository(session).change_relation(
            review_draft_id=review_draft_id,
            enrichment_id=enrichment_id,
            reviewer_id=actor.user_id,
            relation_type=ComponentSymbolRelationType(payload.relation_type),
            reason=payload.reason,
            expected_revision=payload.expected_revision,
            now=datetime.now(UTC),
        )
        return await _commit(
            session, actor, review_draft_id, revision, "enrichment_relation_changed"
        )
    except (
        ImportReviewNotFoundError,
        ImportReviewConflictError,
        ImportReviewValidationError,
        IntegrityError,
    ) as error:
        await session.rollback()
        raise _review_error(error) from error


@router.post(
    "/{review_draft_id}/identity",
    response_model=ReviewActionResponse,
)
async def select_identity_candidate(
    review_draft_id: UUID,
    payload: IdentitySelectionRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ReviewActionResponse:
    try:
        revision = await ImportReviewRepository(session).select_identity(
            review_draft_id=review_draft_id,
            identity_candidate_id=payload.identity_candidate_id,
            reviewer_id=actor.user_id,
            reason=payload.reason,
            expected_revision=payload.expected_revision,
            now=datetime.now(UTC),
        )
        return await _commit(session, actor, review_draft_id, revision, "identity_selected")
    except (
        ImportReviewNotFoundError,
        ImportReviewConflictError,
        ImportReviewValidationError,
        IntegrityError,
    ) as error:
        await session.rollback()
        raise _review_error(error) from error


@router.post(
    "/{review_draft_id}/specification-mappings",
    response_model=ReviewActionResponse,
)
async def map_unmapped_specification(
    review_draft_id: UUID,
    payload: SpecificationMappingRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ReviewActionResponse:
    try:
        revision = await ImportReviewRepository(session).map_specification(
            review_draft_id=review_draft_id,
            specification_key=payload.specification_key,
            taxonomy_path=payload.taxonomy_path,
            reviewer_id=actor.user_id,
            reason=payload.reason,
            expected_revision=payload.expected_revision,
            now=datetime.now(UTC),
        )
        return await _commit(session, actor, review_draft_id, revision, "specification_mapped")
    except (
        ImportReviewNotFoundError,
        ImportReviewConflictError,
        ImportReviewValidationError,
        IntegrityError,
    ) as error:
        await session.rollback()
        raise _review_error(error) from error


@router.post(
    "/{review_draft_id}/parser-issues",
    response_model=ReviewActionResponse,
)
async def mark_parser_issue(
    review_draft_id: UUID,
    payload: ParserIssueRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ReviewActionResponse:
    try:
        revision = await ImportReviewRepository(session).mark_parser_issue(
            review_draft_id=review_draft_id,
            code=payload.code,
            note=payload.note,
            reviewer_id=actor.user_id,
            expected_revision=payload.expected_revision,
            now=datetime.now(UTC),
        )
        return await _commit(session, actor, review_draft_id, revision, "parser_issue_marked")
    except (
        ImportReviewNotFoundError,
        ImportReviewConflictError,
        ImportReviewValidationError,
        IntegrityError,
    ) as error:
        await session.rollback()
        raise _review_error(error) from error


@router.post(
    "/{review_draft_id}/confirm",
    response_model=ReviewActionResponse,
)
async def confirm_import_review(
    review_draft_id: UUID,
    payload: DraftConfirmationRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ReviewActionResponse:
    try:
        revision = await ImportReviewRepository(session).confirm(
            review_draft_id=review_draft_id,
            reviewer_id=actor.user_id,
            reason=payload.reason,
            expected_revision=payload.expected_revision,
            now=datetime.now(UTC),
        )
        return await _commit(session, actor, review_draft_id, revision, "draft_confirmed")
    except (
        ImportReviewNotFoundError,
        ImportReviewConflictError,
        ImportReviewValidationError,
        IntegrityError,
    ) as error:
        await session.rollback()
        raise _review_error(error) from error
