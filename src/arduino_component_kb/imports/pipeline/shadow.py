"""Shadow-mode execution and old/new comparison without changing source of truth."""

from __future__ import annotations

from arduino_component_kb.imports.pipeline.composition import (
    LegacyRepositoryDraftMapper,
    LegacyRepositoryMappingMetadata,
)
from arduino_component_kb.imports.pipeline.models import (
    EnrichmentDecision,
    PipelineExecutionStatus,
    PipelineRunRequest,
    ShadowComparisonReport,
    ShadowFieldConflict,
    ShadowRunResult,
    shadow_value_sha256,
)
from arduino_component_kb.imports.pipeline.runtime import EvidenceFirstImportOrchestrator
from arduino_component_kb.imports.repository_domain import ParsedRepositoryComponent


class ShadowImportRunner:
    def __init__(self, orchestrator: EvidenceFirstImportOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def run(
        self,
        request: PipelineRunRequest,
        legacy: ParsedRepositoryComponent,
    ) -> ShadowRunResult:
        outcome = await self.orchestrator.run(request)
        source_path = request.artifact.metadata.source.source_path or "unknown"
        legacy_fields = dict(legacy.normalized_fields)
        if outcome.status is PipelineExecutionStatus.FAILED:
            if outcome.failure is None:
                raise RuntimeError("shadow_failed_outcome_missing_failure")
            report = ShadowComparisonReport(
                request.run_id,
                legacy.source_key,
                source_path,
                legacy.status.value,
                outcome.status.value,
                len(legacy_fields),
                0,
                0,
                tuple(sorted(legacy_fields)),
                (),
                (),
                None,
                None,
                tuple(legacy.warnings),
                0,
                0,
                0,
                0,
                None,
                "unavailable",
                outcome.failure.duration_ms,
                outcome.failure.as_dict(),
            )
            return ShadowRunResult(outcome, report)

        if outcome.result is None:
            raise RuntimeError("shadow_success_outcome_missing_result")
        result = outcome.result
        mapped = LegacyRepositoryDraftMapper().map(
            result.review_draft,
            LegacyRepositoryMappingMetadata(
                legacy.original_url,
                legacy.license_snapshot,
                legacy.modifications_notice,
                legacy.source_tag,
            ),
        )
        pipeline_fields = dict(mapped.normalized_fields)
        legacy_keys = set(legacy_fields)
        pipeline_keys = set(pipeline_fields)
        common = legacy_keys.intersection(pipeline_keys)
        conflicts = tuple(
            ShadowFieldConflict(
                field,
                shadow_value_sha256(legacy_fields[field]),
                shadow_value_sha256(pipeline_fields[field]),
            )
            for field in sorted(common)
            if shadow_value_sha256(legacy_fields[field])
            != shadow_value_sha256(pipeline_fields[field])
        )
        decisions = tuple(item.decision for item in result.enrichments)
        accepted = decisions.count(EnrichmentDecision.AUTO_ACCEPTED)
        review = decisions.count(EnrichmentDecision.REVIEW_REQUIRED)
        rejected = decisions.count(EnrichmentDecision.REJECTED)
        reviewed_population = accepted + rejected
        precision = accepted * 1_000 // reviewed_population if reviewed_population else None
        parser_warnings = tuple(
            dict.fromkeys(
                (
                    *legacy.warnings,
                    *(warning.code for warning in result.extracted_facts.warnings),
                    *(issue.code for issue in result.quality_report.issues),
                )
            )
        )
        report = ShadowComparisonReport(
            request.run_id,
            legacy.source_key,
            source_path,
            legacy.status.value,
            outcome.status.value,
            len(legacy_fields),
            len(pipeline_fields),
            len(common),
            tuple(sorted(legacy_keys.difference(pipeline_keys))),
            tuple(sorted(pipeline_keys.difference(legacy_keys))),
            conflicts,
            result.quality_report.route.value,
            result.quality_report.overall_score_basis_points,
            parser_warnings,
            len(decisions),
            accepted,
            review,
            rejected,
            precision,
            "proxy_unreviewed",
            result.duration_ms,
        )
        return ShadowRunResult(outcome, report)
