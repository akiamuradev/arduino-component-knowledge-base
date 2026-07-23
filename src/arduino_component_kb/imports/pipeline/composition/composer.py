"""Evidence-preserving deterministic card composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import CompositionError
from arduino_component_kb.imports.pipeline.models import (
    ComponentSymbolRelationType,
    CompositionInput,
    DraftConfidence,
    DraftDescriptionSection,
    DraftEnrichmentStatus,
    DraftInternalComponent,
    DraftKicadSymbol,
    DraftModuleConnection,
    DraftModulePin,
    DraftResource,
    DraftReviewMetadata,
    DraftSpecification,
    DraftText,
    EnrichmentCandidate,
    EnrichmentDecision,
    EvidenceFragment,
    IdentityConfidence,
    IdentityResolutionStatus,
    NormalizationConfidence,
    QualityRoute,
    ReviewDraft,
)

CARD_COMPOSER_VERSION = "1.0.0"


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DeterministicCardComposer:
    clock: Clock
    composer_version: str = CARD_COMPOSER_VERSION

    def __init__(self, clock: Clock | None = None) -> None:
        object.__setattr__(self, "clock", clock or SystemClock())
        object.__setattr__(self, "composer_version", CARD_COMPOSER_VERSION)

    async def compose(
        self,
        context: ImportPipelineContext,
        value: CompositionInput,
    ) -> StageResult[ReviewDraft]:
        started_at = self.clock.now()
        if context.next_stage is not PipelineStage.COMPOSITION:
            raise CompositionError("composition_stage_out_of_order")
        if context.source_key != value.facts.artifact.source.source_key:
            raise CompositionError("pipeline_source_mismatch")
        if value.quality_report.route is QualityRoute.REJECT:
            raise CompositionError("composition_quality_rejected")
        completed_at = self.clock.now()
        draft = self._compose(value, completed_at)
        updated = context.advance(
            StageExecution(
                PipelineStage.COMPOSITION,
                started_at,
                completed_at,
                tuple(item.code for item in draft.review_warnings),
            )
        )
        return StageResult(PipelineStage.COMPOSITION, updated, draft)

    def _compose(self, value: CompositionInput, composed_at: datetime) -> ReviewDraft:
        facts = value.facts
        extracted = facts.extracted_facts
        identity_review = _identity_review(value)
        summary = (
            DraftText(
                extracted.summary_candidates[0].value,
                extracted.summary_candidates[0].evidence,
                _unreviewed(),
            )
            if extracted.summary_candidates
            else None
        )
        descriptions = tuple(
            DraftDescriptionSection(
                item.value.heading,
                item.value.body,
                item.evidence,
                _unreviewed(),
            )
            for item in extracted.description_sections
        )
        features = tuple(
            DraftText(item.value, item.evidence, _unreviewed()) for item in extracted.feature_facts
        )
        applications = tuple(
            DraftText(item.value, item.evidence, _unreviewed())
            for item in extracted.application_facts
        )
        specifications = tuple(
            DraftSpecification(
                item.taxonomy_path,
                item.canonical_label,
                item.trace.normalized_value,
                item.trace.raw_value,
                item.normalized_unit,
                item.evidence,
                _normalization_review(item.trace.confidence),
            )
            for item in facts.specifications
        ) + tuple(
            DraftSpecification(
                None,
                item.original_label,
                item.original_value,
                item.raw_value,
                None,
                item.evidence,
                DraftReviewMetadata(
                    DraftConfidence.LOW,
                    True,
                    ("composition.unmapped_specification",),
                ),
            )
            for item in facts.unmapped_specifications
        )
        connection = DraftModuleConnection(
            tuple(
                DraftDescriptionSection(
                    item.value.heading,
                    item.value.body,
                    item.evidence,
                    _unreviewed(),
                )
                for item in extracted.usage_sections
            ),
            tuple(
                DraftModulePin(
                    item.value.number,
                    item.value.name,
                    item.value.function,
                    item.evidence,
                )
                for item in extracted.module_pinout
            ),
        )
        included = tuple(
            sorted(
                (
                    item
                    for item in value.enrichments
                    if item.decision
                    in {EnrichmentDecision.AUTO_ACCEPTED, EnrichmentDecision.REVIEW_REQUIRED}
                ),
                key=_enrichment_key,
            )
        )
        symbols = tuple(_symbol(item) for item in included)
        internal = tuple(
            _internal(item)
            for item in included
            if item.relation.relation_type is not ComponentSymbolRelationType.EXACT_COMPONENT
        )
        resources = tuple(
            DraftResource(
                item.value.label,
                item.value.locator,
                item.value.kind,
                item.evidence,
            )
            for item in extracted.resources
        )
        quality_sha256 = sha256(value.quality_report.to_json().encode()).hexdigest()
        return ReviewDraft(
            input_sha256=value.input_sha256,
            artifact=facts.artifact,
            composed_at=composed_at,
            composer_version=self.composer_version,
            quality_report_sha256=quality_sha256,
            quality_route=value.quality_report.route,
            quality_score_basis_points=value.quality_report.overall_score_basis_points,
            title=DraftText(
                value.identity.canonical_name.value,
                value.identity.canonical_name.evidence,
                identity_review,
            ),
            aliases=tuple(
                DraftText(item.value, item.evidence, identity_review)
                for item in value.identity.aliases
            ),
            manufacturer=(
                DraftText(
                    value.identity.manufacturer.value,
                    value.identity.manufacturer.evidence,
                    identity_review,
                )
                if value.identity.manufacturer is not None
                else None
            ),
            selected_category=value.identity.selected_category,
            summary=summary,
            detailed_description=descriptions,
            features=features,
            applications=applications,
            module_specifications=specifications,
            module_connection=connection,
            internal_electronic_components=internal,
            kicad_symbols=symbols,
            resources=resources,
            provenance=_all_primary_evidence(value),
            review_warnings=value.quality_report.issues,
        )


def _unreviewed() -> DraftReviewMetadata:
    return DraftReviewMetadata(DraftConfidence.HIGH, False)


def _identity_review(value: CompositionInput) -> DraftReviewMetadata:
    identity = value.identity
    confidence = {
        IdentityConfidence.HIGH: DraftConfidence.HIGH,
        IdentityConfidence.MEDIUM: DraftConfidence.MEDIUM,
        IdentityConfidence.LOW: DraftConfidence.LOW,
    }[identity.confidence]
    if identity.resolution_status is IdentityResolutionStatus.AUTO_RESOLVED:
        return DraftReviewMetadata(confidence, False)
    return DraftReviewMetadata(
        confidence,
        True,
        ("composition.identity_review_required",),
    )


def _normalization_review(confidence: NormalizationConfidence) -> DraftReviewMetadata:
    mapped = {
        NormalizationConfidence.HIGH: DraftConfidence.HIGH,
        NormalizationConfidence.MEDIUM: DraftConfidence.MEDIUM,
        NormalizationConfidence.LOW: DraftConfidence.LOW,
    }[confidence]
    if confidence is not NormalizationConfidence.LOW:
        return DraftReviewMetadata(mapped, False)
    return DraftReviewMetadata(
        mapped,
        True,
        ("composition.normalization_low_confidence",),
    )


def _enrichment_status(candidate: EnrichmentCandidate) -> DraftEnrichmentStatus:
    if candidate.decision is EnrichmentDecision.AUTO_ACCEPTED:
        return DraftEnrichmentStatus.ACCEPTED
    return DraftEnrichmentStatus.PROPOSED


def _candidate_evidence(candidate: EnrichmentCandidate) -> tuple[EvidenceFragment, ...]:
    return tuple(
        dict.fromkeys(
            evidence
            for contribution in candidate.relation.score_breakdown
            for evidence in contribution.source_evidence
        )
    )


def _enrichment_key(candidate: EnrichmentCandidate) -> tuple[int, str, str]:
    order = {
        EnrichmentDecision.AUTO_ACCEPTED: 0,
        EnrichmentDecision.REVIEW_REQUIRED: 1,
        EnrichmentDecision.REJECTED: 2,
    }
    return (
        order[candidate.decision],
        candidate.relation.relation_type.value,
        candidate.relation.symbol.record_id,
    )


def _internal(candidate: EnrichmentCandidate) -> DraftInternalComponent:
    relation = candidate.relation
    return DraftInternalComponent(
        relation.symbol.record_id,
        relation.symbol.symbol_name,
        relation.relation_type,
        _enrichment_status(candidate),
        relation.confidence_basis_points,
        _candidate_evidence(candidate),
        candidate.review_reasons,
    )


def _symbol(candidate: EnrichmentCandidate) -> DraftKicadSymbol:
    relation = candidate.relation
    symbol = relation.symbol
    return DraftKicadSymbol(
        record_id=symbol.record_id,
        relation_type=relation.relation_type,
        status=_enrichment_status(candidate),
        confidence_basis_points=relation.confidence_basis_points,
        library=symbol.library,
        symbol_name=symbol.symbol_name,
        description=symbol.description,
        datasheet=symbol.datasheet,
        pins=symbol.pins,
        footprint_filters=symbol.footprint_filters,
        source_path=symbol.source_path,
        source_revision=symbol.source_revision,
        source_content_sha256=symbol.source_content_sha256,
        parser_version=symbol.parser_version,
        source_evidence=_candidate_evidence(candidate),
        review_reasons=candidate.review_reasons,
    )


def _all_primary_evidence(value: CompositionInput) -> tuple[EvidenceFragment, ...]:
    extracted = value.facts.extracted_facts
    groups = (
        extracted.title_candidates,
        extracted.summary_candidates,
        extracted.description_sections,
        extracted.feature_facts,
        extracted.application_facts,
        extracted.usage_sections,
        extracted.identifiers,
        extracted.manufacturer_candidates,
        extracted.brand_candidates,
        extracted.interface_facts,
        extracted.module_pinout,
        extracted.primary_ic_candidates,
        extracted.specifications,
        extracted.resources,
        extracted.images,
        extracted.unmapped_facts,
    )
    evidence = list(value.identity.evidence)
    for group in groups:
        for item in group:
            evidence.extend(item.evidence)
    for warning in extracted.warnings:
        evidence.extend(warning.evidence)
    for candidate in value.enrichments:
        evidence.extend(_candidate_evidence(candidate))
    return tuple(dict.fromkeys(evidence))
