"""Transactional repository for the evidence-first import review workspace."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.imports.persistence_models import (
    ComponentEnrichmentRecord,
    ComponentIdentityCandidateRecord,
    ImportPipelineArtifact,
    ImportReviewActionRecord,
    ImportReviewDraftRecord,
    ImportReviewStateRecord,
    ParserEvaluationRecord,
)
from arduino_component_kb.imports.pipeline.models.enrichment import ComponentSymbolRelationType
from arduino_component_kb.imports.pipeline.models.persistence import (
    EnrichmentLifecycleStatus,
    EnrichmentReviewCommand,
    EnrichmentReviewDecision,
)
from arduino_component_kb.imports.pipeline.normalization.registry import SPECIFICATION_REGISTRY
from arduino_component_kb.imports.pipeline.persistence.postgresql import (
    EnrichmentLifecycleRepository,
)


class ImportReviewNotFoundError(Exception):
    """The requested draft or a nested review target does not exist."""


class ImportReviewConflictError(Exception):
    """The submitted revision or current lifecycle state conflicts."""


class ImportReviewValidationError(Exception):
    """A reviewer choice is outside the persisted draft contract."""


@dataclass(frozen=True, slots=True)
class ImportReviewBundle:
    draft: ImportReviewDraftRecord
    artifact: ImportPipelineArtifact
    evaluation: ParserEvaluationRecord
    identities: tuple[ComponentIdentityCandidateRecord, ...]
    enrichments: tuple[ComponentEnrichmentRecord, ...]
    state: ImportReviewStateRecord | None
    actions: tuple[ImportReviewActionRecord, ...]


@dataclass(frozen=True, slots=True)
class ImportReviewSummary:
    draft: ImportReviewDraftRecord
    state: ImportReviewStateRecord | None


def unmapped_specification_key(value: dict[str, object]) -> str:
    """Return a stable opaque key without exposing source text in mutation URLs."""
    selected = {
        "original_label": value.get("original_label"),
        "original_value": value.get("original_value"),
        "raw_value": value.get("raw_value"),
    }
    digest = sha256(
        json.dumps(selected, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return f"spec-{digest}"


def unmapped_specifications(facts_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    values = facts_payload.get("unmapped_specifications", [])
    if not isinstance(values, list):
        return ()
    result: list[dict[str, object]] = []
    for value in values:
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            result.append({"key": unmapped_specification_key(value), **value})
    return tuple(result)


class ImportReviewRepository:
    """Locks one draft state for every mutation and appends an immutable action."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, status: str | None, limit: int) -> tuple[ImportReviewSummary, ...]:
        statement = (
            select(ImportReviewDraftRecord, ImportReviewStateRecord)
            .outerjoin(
                ImportReviewStateRecord,
                ImportReviewStateRecord.review_draft_id == ImportReviewDraftRecord.id,
            )
            .order_by(ImportReviewDraftRecord.created_at.desc())
            .limit(limit)
        )
        if status == "confirmed":
            statement = statement.where(ImportReviewStateRecord.status == "confirmed")
        elif status == "pending":
            statement = statement.where(
                (ImportReviewStateRecord.status == "pending")
                | (ImportReviewStateRecord.status.is_(None))
            )
        rows = (await self.session.execute(statement)).all()
        return tuple(ImportReviewSummary(row[0], row[1]) for row in rows)

    async def get(self, review_draft_id: UUID) -> ImportReviewBundle:
        draft = await self.session.scalar(
            select(ImportReviewDraftRecord).where(ImportReviewDraftRecord.id == review_draft_id)
        )
        if draft is None:
            raise ImportReviewNotFoundError("import_review_draft_not_found")
        artifact = await self.session.get(ImportPipelineArtifact, draft.artifact_id)
        evaluation = await self.session.get(ParserEvaluationRecord, draft.parser_evaluation_id)
        if artifact is None or evaluation is None:
            raise ImportReviewNotFoundError("import_review_snapshot_incomplete")
        identities = tuple(
            (
                await self.session.scalars(
                    select(ComponentIdentityCandidateRecord)
                    .where(ComponentIdentityCandidateRecord.artifact_id == draft.artifact_id)
                    .order_by(ComponentIdentityCandidateRecord.created_at)
                )
            ).all()
        )
        enrichments = tuple(
            (
                await self.session.scalars(
                    select(ComponentEnrichmentRecord)
                    .where(ComponentEnrichmentRecord.review_draft_id == review_draft_id)
                    .order_by(
                        ComponentEnrichmentRecord.confidence_basis_points.desc(),
                        ComponentEnrichmentRecord.external_identity,
                    )
                )
            ).all()
        )
        state = await self.session.get(ImportReviewStateRecord, review_draft_id)
        actions = tuple(
            (
                await self.session.scalars(
                    select(ImportReviewActionRecord)
                    .where(ImportReviewActionRecord.review_draft_id == review_draft_id)
                    .order_by(
                        ImportReviewActionRecord.review_revision,
                        ImportReviewActionRecord.occurred_at,
                    )
                )
            ).all()
        )
        return ImportReviewBundle(
            draft, artifact, evaluation, identities, enrichments, state, actions
        )

    async def review_enrichment(
        self,
        *,
        review_draft_id: UUID,
        enrichment_id: UUID,
        reviewer_id: UUID,
        decision: EnrichmentReviewDecision,
        reason: str,
        expected_revision: int,
        now: datetime,
    ) -> int:
        state = await self._lock_state(review_draft_id, expected_revision, now)
        enrichment = await self._lock_enrichment(review_draft_id, enrichment_id)
        previous = enrichment.status
        resulting = await EnrichmentLifecycleRepository(self.session).review(
            EnrichmentReviewCommand(enrichment_id, reviewer_id, decision, reason, now)
        )
        action = (
            "enrichment_accepted"
            if decision is EnrichmentReviewDecision.ACCEPT
            else "enrichment_rejected"
        )
        return await self._record(
            state=state,
            actor_id=reviewer_id,
            action=action,
            target_type="enrichment",
            target_key=str(enrichment_id),
            previous_value={"status": previous},
            resulting_value={"status": resulting.value},
            reason=reason,
            now=now,
        )

    async def change_relation(
        self,
        *,
        review_draft_id: UUID,
        enrichment_id: UUID,
        reviewer_id: UUID,
        relation_type: ComponentSymbolRelationType,
        reason: str,
        expected_revision: int,
        now: datetime,
    ) -> int:
        state = await self._lock_state(review_draft_id, expected_revision, now)
        enrichment = await self._lock_enrichment(review_draft_id, enrichment_id)
        if enrichment.status == EnrichmentLifecycleStatus.STALE.value:
            raise ImportReviewConflictError("stale_enrichment_review_forbidden")
        previous = enrichment.relation_type
        if previous == relation_type.value:
            raise ImportReviewValidationError("enrichment_relation_unchanged")
        collision = await self.session.scalar(
            select(ComponentEnrichmentRecord.id).where(
                ComponentEnrichmentRecord.review_draft_id == review_draft_id,
                ComponentEnrichmentRecord.id != enrichment_id,
                ComponentEnrichmentRecord.provider == enrichment.provider,
                ComponentEnrichmentRecord.external_identity == enrichment.external_identity,
                ComponentEnrichmentRecord.source_revision == enrichment.source_revision,
                ComponentEnrichmentRecord.relation_type == relation_type.value,
            )
        )
        if collision is not None:
            raise ImportReviewConflictError("enrichment_relation_conflict")
        await self.session.execute(
            update(ComponentEnrichmentRecord)
            .where(ComponentEnrichmentRecord.id == enrichment_id)
            .values(
                relation_type=relation_type.value,
                status=EnrichmentLifecycleStatus.SUGGESTED.value,
                reviewed_by=None,
                reviewed_at=None,
                updated_at=now,
            )
        )
        return await self._record(
            state=state,
            actor_id=reviewer_id,
            action="enrichment_relation_changed",
            target_type="enrichment",
            target_key=str(enrichment_id),
            previous_value={"relation_type": previous, "status": enrichment.status},
            resulting_value={
                "relation_type": relation_type.value,
                "status": EnrichmentLifecycleStatus.SUGGESTED.value,
            },
            reason=reason,
            now=now,
        )

    async def select_identity(
        self,
        *,
        review_draft_id: UUID,
        identity_candidate_id: UUID,
        reviewer_id: UUID,
        reason: str,
        expected_revision: int,
        now: datetime,
    ) -> int:
        state = await self._lock_state(review_draft_id, expected_revision, now)
        draft = await self._draft(review_draft_id)
        identity = await self.session.scalar(
            select(ComponentIdentityCandidateRecord.id).where(
                ComponentIdentityCandidateRecord.id == identity_candidate_id,
                ComponentIdentityCandidateRecord.artifact_id == draft.artifact_id,
            )
        )
        if identity is None:
            raise ImportReviewNotFoundError("identity_candidate_not_found")
        previous = state.selected_identity_candidate_id
        if previous == identity_candidate_id:
            raise ImportReviewValidationError("identity_candidate_already_selected")
        state.selected_identity_candidate_id = identity_candidate_id
        return await self._record(
            state=state,
            actor_id=reviewer_id,
            action="identity_selected",
            target_type="identity_candidate",
            target_key=str(identity_candidate_id),
            previous_value={"identity_candidate_id": str(previous)},
            resulting_value={"identity_candidate_id": str(identity_candidate_id)},
            reason=reason,
            now=now,
        )

    async def map_specification(
        self,
        *,
        review_draft_id: UUID,
        specification_key: str,
        taxonomy_path: str,
        reviewer_id: UUID,
        reason: str,
        expected_revision: int,
        now: datetime,
    ) -> int:
        state = await self._lock_state(review_draft_id, expected_revision, now)
        if taxonomy_path not in SPECIFICATION_REGISTRY.taxonomy_paths():
            raise ImportReviewValidationError("specification_taxonomy_path_unknown")
        draft = await self._draft(review_draft_id)
        artifact = await self.session.get(ImportPipelineArtifact, draft.artifact_id)
        if artifact is None:
            raise ImportReviewNotFoundError("import_review_snapshot_incomplete")
        known = {str(item["key"]) for item in unmapped_specifications(artifact.facts_payload)}
        if specification_key not in known:
            raise ImportReviewNotFoundError("unmapped_specification_not_found")
        previous = state.specification_mappings.get(specification_key)
        mappings = dict(state.specification_mappings)
        mappings[specification_key] = taxonomy_path
        state.specification_mappings = mappings
        return await self._record(
            state=state,
            actor_id=reviewer_id,
            action="specification_mapped",
            target_type="unmapped_specification",
            target_key=specification_key,
            previous_value={"taxonomy_path": previous},
            resulting_value={"taxonomy_path": taxonomy_path},
            reason=reason,
            now=now,
        )

    async def mark_parser_issue(
        self,
        *,
        review_draft_id: UUID,
        code: str,
        note: str,
        reviewer_id: UUID,
        expected_revision: int,
        now: datetime,
    ) -> int:
        state = await self._lock_state(review_draft_id, expected_revision, now)
        previous = state.parser_issues.get(code)
        issues = dict(state.parser_issues)
        issue: dict[str, object] = {
            "code": code,
            "note": note,
            "reported_by": str(reviewer_id),
            "reported_at": now.isoformat(),
        }
        issues[code] = issue
        state.parser_issues = issues
        return await self._record(
            state=state,
            actor_id=reviewer_id,
            action="parser_issue_marked",
            target_type="parser_issue",
            target_key=code,
            previous_value=previous or {},
            resulting_value=issue,
            reason=note,
            now=now,
        )

    async def confirm(
        self,
        *,
        review_draft_id: UUID,
        reviewer_id: UUID,
        reason: str,
        expected_revision: int,
        now: datetime,
    ) -> int:
        state = await self._lock_state(review_draft_id, expected_revision, now)
        bundle = await self.get(review_draft_id)
        unresolved = [
            item.id
            for item in bundle.enrichments
            if item.status
            in {
                EnrichmentLifecycleStatus.SUGGESTED.value,
                EnrichmentLifecycleStatus.STALE.value,
                EnrichmentLifecycleStatus.CONFLICT.value,
            }
        ]
        if unresolved:
            raise ImportReviewValidationError("draft_enrichments_unresolved")
        expected_mappings = {
            str(item["key"]) for item in unmapped_specifications(bundle.artifact.facts_payload)
        }
        if not expected_mappings.issubset(state.specification_mappings):
            raise ImportReviewValidationError("draft_specifications_unmapped")
        state.status = "confirmed"
        state.confirmed_by = reviewer_id
        state.confirmed_at = now
        return await self._record(
            state=state,
            actor_id=reviewer_id,
            action="draft_confirmed",
            target_type="review_draft",
            target_key=str(review_draft_id),
            previous_value={"status": "pending"},
            resulting_value={"status": "confirmed"},
            reason=reason,
            now=now,
        )

    async def _draft(self, review_draft_id: UUID) -> ImportReviewDraftRecord:
        draft = await self.session.get(ImportReviewDraftRecord, review_draft_id)
        if draft is None:
            raise ImportReviewNotFoundError("import_review_draft_not_found")
        return draft

    async def _lock_state(
        self, review_draft_id: UUID, expected_revision: int, now: datetime
    ) -> ImportReviewStateRecord:
        draft = await self._draft(review_draft_id)
        await self.session.execute(
            insert(ImportReviewStateRecord)
            .values(
                review_draft_id=review_draft_id,
                revision=1,
                status="pending",
                selected_identity_candidate_id=draft.identity_candidate_id,
                specification_mappings={},
                parser_issues={},
                confirmed_by=None,
                confirmed_at=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
        state = await self.session.scalar(
            select(ImportReviewStateRecord)
            .where(ImportReviewStateRecord.review_draft_id == review_draft_id)
            .with_for_update()
        )
        if state is None:
            raise ImportReviewNotFoundError("import_review_state_not_found")
        if state.revision != expected_revision:
            raise ImportReviewConflictError("import_review_revision_conflict")
        if state.status == "confirmed":
            raise ImportReviewConflictError("import_review_already_confirmed")
        return state

    async def _lock_enrichment(
        self, review_draft_id: UUID, enrichment_id: UUID
    ) -> ComponentEnrichmentRecord:
        enrichment = await self.session.scalar(
            select(ComponentEnrichmentRecord)
            .where(
                ComponentEnrichmentRecord.id == enrichment_id,
                ComponentEnrichmentRecord.review_draft_id == review_draft_id,
            )
            .with_for_update()
        )
        if enrichment is None:
            raise ImportReviewNotFoundError("enrichment_not_found")
        return enrichment

    async def _record(
        self,
        *,
        state: ImportReviewStateRecord,
        actor_id: UUID,
        action: str,
        target_type: str,
        target_key: str,
        previous_value: dict[str, object],
        resulting_value: dict[str, object],
        reason: str,
        now: datetime,
    ) -> int:
        state.revision += 1
        state.updated_at = now
        self.session.add(
            ImportReviewActionRecord(
                id=uuid4(),
                review_draft_id=state.review_draft_id,
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_key=target_key,
                previous_value=previous_value,
                resulting_value=resulting_value,
                reason=reason,
                review_revision=state.revision,
                occurred_at=now,
            )
        )
        await self.session.flush()
        return state.revision
