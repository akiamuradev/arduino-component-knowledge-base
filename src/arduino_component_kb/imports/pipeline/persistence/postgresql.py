"""Idempotent PostgreSQL adapter for the evidence-first import pipeline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid5

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.imports.persistence_models import (
    ComponentEnrichmentRecord,
    ComponentEnrichmentReviewRecord,
    ComponentIdentityCandidateRecord,
    ImportPipelineArtifact,
    ImportReviewDraftRecord,
    ParserEvaluationRecord,
)
from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import PersistenceError
from arduino_component_kb.imports.pipeline.identity.resolver import WeightedIdentityResolver
from arduino_component_kb.imports.pipeline.models import EnrichmentDecision
from arduino_component_kb.imports.pipeline.models.persistence import (
    PERSISTENCE_NAMESPACE,
    EnrichmentLifecycleStatus,
    EnrichmentReviewCommand,
    EnrichmentReviewDecision,
    PersistedPipelineDraft,
    PipelinePersistenceInput,
)
from arduino_component_kb.imports.pipeline.normalization.registry import SPECIFICATION_REGISTRY


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _payload(value: str) -> dict[str, object]:
    decoded: object = json.loads(value)
    if not isinstance(decoded, dict):
        raise PersistenceError("persistence_payload_invalid")
    return decoded


class PostgresImportPersistenceGateway:
    """Writes immutable snapshots with deterministic IDs and no implicit commit."""

    def __init__(self, session: AsyncSession, clock: Clock | None = None) -> None:
        self.session = session
        self.clock = clock or SystemClock()

    async def persist(
        self, context: ImportPipelineContext, value: PipelinePersistenceInput
    ) -> StageResult[PersistedPipelineDraft]:
        started_at = self.clock.now()
        if context.next_stage is not PipelineStage.PERSISTENCE:
            raise PersistenceError("persistence_stage_out_of_order")
        if context.source_key != value.draft.artifact.source.source_key:
            raise PersistenceError("pipeline_source_mismatch")

        artifact = value.draft.artifact
        source = artifact.source
        facts_json = value.composition.facts.to_json()
        identity_json = value.composition.identity.to_json()
        report_json = value.composition.quality_report.to_json()
        draft_json = value.draft.to_json()
        created_at = value.draft.composed_at
        parser_version = value.draft.provenance[0].parser_version
        idempotency_key = str(value.artifact_id)

        rows: tuple[tuple[type[object], dict[str, object]], ...] = (
            (
                ImportPipelineArtifact,
                {
                    "id": value.artifact_id,
                    "source_id": value.source_id,
                    "component_id": value.component_id,
                    "run_id": context.run_id,
                    "source_key": source.source_key,
                    "source_url": source.source_url,
                    "source_file_path": source.source_path,
                    "source_revision": source.source_revision,
                    "content_sha256": artifact.content_sha256,
                    "facts_sha256": sha256(facts_json.encode()).hexdigest(),
                    "facts_payload": _payload(facts_json),
                    "parser_version": parser_version,
                    "normalization_version": SPECIFICATION_REGISTRY.version,
                    "idempotency_key": idempotency_key,
                    "created_at": created_at,
                },
            ),
            (
                ComponentIdentityCandidateRecord,
                {
                    "id": value.identity_id,
                    "artifact_id": value.artifact_id,
                    "payload_sha256": sha256(identity_json.encode()).hexdigest(),
                    "payload": _payload(identity_json),
                    "canonical_name": value.composition.identity.canonical_name.value,
                    "component_kind": value.composition.identity.component_kind.value,
                    "selected_category": value.composition.identity.selected_category,
                    "confidence": value.composition.identity.confidence.value,
                    "resolution_status": value.composition.identity.resolution_status.value,
                    "resolver_version": WeightedIdentityResolver.resolver_version,
                    "created_at": created_at,
                },
            ),
            (
                ParserEvaluationRecord,
                {
                    "id": value.evaluation_id,
                    "artifact_id": value.artifact_id,
                    "identity_candidate_id": value.identity_id,
                    "input_sha256": value.composition.quality_report.input_sha256,
                    "report_sha256": sha256(report_json.encode()).hexdigest(),
                    "payload": _payload(report_json),
                    "route": value.composition.quality_report.route.value,
                    "score_basis_points": (
                        value.composition.quality_report.overall_score_basis_points
                    ),
                    "evaluator_version": value.composition.quality_report.evaluator_version,
                    "created_at": created_at,
                },
            ),
            (
                ImportReviewDraftRecord,
                {
                    "id": value.review_draft_id,
                    "artifact_id": value.artifact_id,
                    "identity_candidate_id": value.identity_id,
                    "parser_evaluation_id": value.evaluation_id,
                    "component_id": value.component_id,
                    "input_sha256": value.draft.input_sha256,
                    "payload_sha256": sha256(draft_json.encode()).hexdigest(),
                    "payload": _payload(draft_json),
                    "schema_version": value.draft.SCHEMA_VERSION,
                    "composer_version": value.draft.composer_version,
                    "quality_route": value.draft.quality_route.value,
                    "created_at": created_at,
                },
            ),
        )
        for model, values in rows:
            await self.session.execute(insert(model).values(**values).on_conflict_do_nothing())

        enrichment_ids: list[UUID] = []
        statuses = {
            EnrichmentDecision.AUTO_ACCEPTED: EnrichmentLifecycleStatus.ACCEPTED,
            EnrichmentDecision.REVIEW_REQUIRED: EnrichmentLifecycleStatus.SUGGESTED,
            EnrichmentDecision.REJECTED: EnrichmentLifecycleStatus.REJECTED,
        }
        for candidate in value.composition.enrichments:
            relation = candidate.relation
            symbol = relation.symbol
            enrichment_id = value.enrichment_id(
                symbol.record_id,
                symbol.source_revision,
                relation.relation_type.value,
            )
            enrichment_ids.append(enrichment_id)
            candidate_json = candidate.to_json()
            evidence = tuple(
                dict.fromkeys(
                    item
                    for contribution in relation.score_breakdown
                    for item in contribution.source_evidence
                )
            )
            await self.session.execute(
                insert(ComponentEnrichmentRecord)
                .values(
                    id=enrichment_id,
                    artifact_id=value.artifact_id,
                    review_draft_id=value.review_draft_id,
                    component_id=value.component_id,
                    provider="kicad",
                    relation_type=relation.relation_type.value,
                    external_identity=symbol.record_id,
                    payload=_payload(candidate_json),
                    payload_sha256=sha256(candidate_json.encode()).hexdigest(),
                    confidence_basis_points=relation.confidence_basis_points,
                    status=statuses[candidate.decision].value,
                    parser_version=relation.matcher_version,
                    source_revision=symbol.source_revision,
                    evidence=[item.as_dict() for item in evidence],
                    reviewed_by=None,
                    reviewed_at=None,
                    created_at=created_at,
                    updated_at=created_at,
                )
                .on_conflict_do_nothing()
            )
        await self.session.flush()
        completed_at = self.clock.now()
        updated = context.advance(
            StageExecution(PipelineStage.PERSISTENCE, started_at, completed_at)
        )
        return StageResult(
            PipelineStage.PERSISTENCE,
            updated,
            PersistedPipelineDraft(
                value.artifact_id,
                value.identity_id,
                value.evaluation_id,
                value.review_draft_id,
                tuple(enrichment_ids),
            ),
        )


class EnrichmentLifecycleRepository:
    """Mutates only enrichment lifecycle metadata; source snapshots stay immutable."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def mark_stale(
        self, provider: str, current_source_revision: str, changed_at: datetime
    ) -> int:
        if not provider.strip() or not current_source_revision.strip():
            raise ValueError("enrichment_revision_scope_invalid")
        if changed_at.tzinfo is None or changed_at.utcoffset() is None:
            raise ValueError("enrichment_changed_at_must_be_timezone_aware")
        result = await self.session.execute(
            update(ComponentEnrichmentRecord)
            .where(
                ComponentEnrichmentRecord.provider == provider,
                ComponentEnrichmentRecord.source_revision != current_source_revision,
                ComponentEnrichmentRecord.status.in_(("suggested", "accepted", "conflict")),
            )
            .values(status=EnrichmentLifecycleStatus.STALE.value, updated_at=changed_at)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def mark_conflict(self, enrichment_id: UUID, changed_at: datetime) -> None:
        await self.session.execute(
            update(ComponentEnrichmentRecord)
            .where(ComponentEnrichmentRecord.id == enrichment_id)
            .values(status=EnrichmentLifecycleStatus.CONFLICT.value, updated_at=changed_at)
        )

    async def review(self, command: EnrichmentReviewCommand) -> EnrichmentLifecycleStatus:
        result = await self.session.execute(
            select(ComponentEnrichmentRecord.status)
            .where(ComponentEnrichmentRecord.id == command.enrichment_id)
            .with_for_update()
        )
        previous = result.scalar_one_or_none()
        if previous is None:
            raise PersistenceError("enrichment_not_found")
        if previous == EnrichmentLifecycleStatus.STALE.value:
            raise PersistenceError("stale_enrichment_review_forbidden")
        resulting = (
            EnrichmentLifecycleStatus.ACCEPTED
            if command.decision is EnrichmentReviewDecision.ACCEPT
            else EnrichmentLifecycleStatus.REJECTED
        )
        await self.session.execute(
            update(ComponentEnrichmentRecord)
            .where(ComponentEnrichmentRecord.id == command.enrichment_id)
            .values(
                status=resulting.value,
                reviewed_by=command.reviewer_id,
                reviewed_at=command.reviewed_at,
                updated_at=command.reviewed_at,
            )
        )
        audit_id = uuid5(
            PERSISTENCE_NAMESPACE,
            ":".join(
                (
                    "review",
                    str(command.enrichment_id),
                    str(command.reviewer_id),
                    command.decision.value,
                    command.reviewed_at.isoformat(),
                )
            ),
        )
        await self.session.execute(
            insert(ComponentEnrichmentReviewRecord)
            .values(
                id=audit_id,
                enrichment_id=command.enrichment_id,
                reviewer_id=command.reviewer_id,
                decision=command.decision.value,
                previous_status=previous,
                resulting_status=resulting.value,
                reason=command.reason,
                reviewed_at=command.reviewed_at,
            )
            .on_conflict_do_nothing()
        )
        await self.session.flush()
        return resulting

    async def attach_component(self, review_draft_id: UUID, component_id: UUID) -> None:
        """Attach records without rewriting the source/draft/enrichment JSON payloads."""
        await self.session.execute(
            update(ImportReviewDraftRecord)
            .where(ImportReviewDraftRecord.id == review_draft_id)
            .values(component_id=component_id)
        )
        await self.session.execute(
            update(ImportPipelineArtifact)
            .where(
                ImportPipelineArtifact.id == ImportReviewDraftRecord.artifact_id,
                ImportReviewDraftRecord.id == review_draft_id,
            )
            .values(component_id=component_id)
        )
        await self.session.execute(
            update(ComponentEnrichmentRecord)
            .where(ComponentEnrichmentRecord.review_draft_id == review_draft_id)
            .values(component_id=component_id)
        )
