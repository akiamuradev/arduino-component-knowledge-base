"""Deterministic quality scoring before card composition."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import QualityError
from arduino_component_kb.imports.pipeline.models import (
    ComponentKind,
    EnrichmentDecision,
    EvidenceFragment,
    IdentityResolutionStatus,
    NormalizationProfile,
    QualityDimension,
    QualityDimensionScore,
    QualityEvaluationInput,
    QualityIssue,
    QualityIssueCause,
    QualityIssueSeverity,
    QualityReport,
    QualityRoute,
)

QUALITY_EVALUATOR_VERSION = "1.0.0"
DEFAULT_QUALITY_REJECT_THRESHOLD = Decimal("0.500")
DEFAULT_QUALITY_READY_THRESHOLD = Decimal("0.800")

_DIMENSION_WEIGHTS = {
    QualityDimension.IDENTITY_CONFIDENCE: 150,
    QualityDimension.DESCRIPTION_COMPLETENESS: 120,
    QualityDimension.SPECIFICATION_COVERAGE: 150,
    QualityDimension.MODULE_PINOUT_PRESENCE: 80,
    QualityDimension.SOURCE_PROVENANCE_COMPLETENESS: 150,
    QualityDimension.CONFLICTS: 120,
    QualityDimension.ENRICHMENT_CONFIDENCE: 80,
    QualityDimension.EDUCATIONAL_USEFULNESS: 80,
    QualityDimension.PUBLICATION_READINESS: 70,
}
_SEVERITY_ORDER = {
    QualityIssueSeverity.BLOCKING: 0,
    QualityIssueSeverity.WARNING: 1,
    QualityIssueSeverity.SUGGESTION: 2,
}


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ProfileExpectation:
    code: str
    label: str
    patterns: tuple[str, ...]
    satisfied: bool


class DeterministicQualityEvaluator:
    evaluator_version = QUALITY_EVALUATOR_VERSION

    def __init__(
        self,
        clock: Clock | None = None,
        *,
        reject_threshold: float | Decimal = 0.5,
        ready_threshold: float | Decimal = 0.8,
    ) -> None:
        reject = _threshold(reject_threshold, "quality_reject_threshold_invalid")
        ready = _threshold(ready_threshold, "quality_ready_threshold_invalid")
        if not Decimal("0.300") <= reject <= Decimal("0.700"):
            raise ValueError("quality_reject_threshold_invalid")
        if not Decimal("0.700") <= ready <= Decimal("0.950") or reject >= ready:
            raise ValueError("quality_ready_threshold_invalid")
        self.reject_threshold_basis_points = _basis_points(reject)
        self.ready_threshold_basis_points = _basis_points(ready)
        self.clock = clock or SystemClock()

    async def evaluate(
        self,
        context: ImportPipelineContext,
        value: QualityEvaluationInput,
    ) -> StageResult[QualityReport]:
        started_at = self.clock.now()
        if context.next_stage is not PipelineStage.EVALUATION:
            raise QualityError("quality_stage_out_of_order")
        if context.source_key != value.facts.artifact.source.source_key:
            raise QualityError("pipeline_source_mismatch")
        report = self._evaluate(value)
        completed_at = self.clock.now()
        stage_warnings = tuple(
            item.code
            for item in report.issues
            if item.severity is not QualityIssueSeverity.SUGGESTION
        )
        updated = context.advance(
            StageExecution(
                PipelineStage.EVALUATION,
                started_at,
                completed_at,
                stage_warnings,
            )
        )
        return StageResult(PipelineStage.EVALUATION, updated, report)

    def _evaluate(self, value: QualityEvaluationInput) -> QualityReport:
        dimensions: list[QualityDimensionScore] = []
        issues: list[QualityIssue] = []
        for builder in (
            self._identity,
            self._description,
            self._specifications,
            self._module_pinout,
            self._provenance,
            self._conflicts,
            self._enrichment,
            self._educational,
        ):
            dimension, found = builder(value)
            dimensions.append(dimension)
            issues.extend(found)
        publication, publication_issues = self._publication(value, tuple(issues))
        dimensions.append(publication)
        issues.extend(publication_issues)
        overall = _overall(tuple(dimensions))
        if overall < self.reject_threshold_basis_points and not any(
            item.severity is QualityIssueSeverity.BLOCKING for item in issues
        ):
            issue = QualityIssue(
                "quality.overall_below_reject_threshold",
                QualityIssueSeverity.BLOCKING,
                QualityIssueCause.POLICY,
                QualityDimension.PUBLICATION_READINESS,
                "The weighted quality score is below the configured rejection threshold.",
            )
            issues.append(issue)
            dimensions[-1] = replace(
                dimensions[-1],
                issue_codes=(*dimensions[-1].issue_codes, issue.code),
            )
        ordered_issues = tuple(
            sorted(
                issues,
                key=lambda item: (
                    _SEVERITY_ORDER[item.severity],
                    item.dimension.value,
                    item.code,
                ),
            )
        )
        route = _route(
            overall,
            ordered_issues,
            self.reject_threshold_basis_points,
            self.ready_threshold_basis_points,
        )
        return QualityReport(
            input_sha256=value.input_sha256,
            profile=value.facts.profile,
            dimensions=tuple(dimensions),
            overall_score_basis_points=overall,
            route=route,
            issues=ordered_issues,
            reject_threshold_basis_points=self.reject_threshold_basis_points,
            ready_threshold_basis_points=self.ready_threshold_basis_points,
            evaluator_version=self.evaluator_version,
        )

    def _identity(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        identity = value.identity
        issues: tuple[QualityIssue, ...] = ()
        if identity.resolution_status is IdentityResolutionStatus.AUTO_RESOLVED:
            score = 1_000
            explanation = "Identity and category were resolved automatically from evidence."
        elif identity.resolution_status is IdentityResolutionStatus.REVIEW_REQUIRED:
            score = 650
            explanation = "Identity is plausible but requires a reviewer decision."
            issues = (
                QualityIssue(
                    "quality.identity_review_required",
                    QualityIssueSeverity.WARNING,
                    QualityIssueCause.POLICY,
                    QualityDimension.IDENTITY_CONFIDENCE,
                    "The identity resolver requires manual review.",
                    identity.canonical_name.evidence,
                ),
            )
        else:
            score = 200
            explanation = "Identity is unresolved and cannot be composed safely."
            issues = (
                QualityIssue(
                    "quality.identity_unresolved",
                    QualityIssueSeverity.BLOCKING,
                    QualityIssueCause.POLICY,
                    QualityDimension.IDENTITY_CONFIDENCE,
                    "A publication draft cannot be composed from an unresolved identity.",
                    identity.canonical_name.evidence,
                ),
            )
        return self._dimension(
            QualityDimension.IDENTITY_CONFIDENCE,
            score,
            True,
            explanation,
            issues,
        ), issues

    def _description(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        extracted = value.facts.extracted_facts
        has_summary = bool(extracted.summary_candidates)
        has_description = bool(extracted.description_sections)
        if has_summary and has_description:
            return self._dimension(
                QualityDimension.DESCRIPTION_COMPLETENESS,
                1_000,
                True,
                "Both a summary and detailed description are present.",
                (),
            ), ()
        matching = _matching_evidence(
            value, (r"\bdescription\b", r"\boverview\b", r"\bintroduction\b")
        )
        cause = (
            QualityIssueCause.EXTRACTION_MISSING if matching else QualityIssueCause.SOURCE_MISSING
        )
        severity = (
            QualityIssueSeverity.WARNING
            if cause is QualityIssueCause.EXTRACTION_MISSING
            else QualityIssueSeverity.SUGGESTION
        )
        if has_summary or has_description:
            score = 750
            message = "Only one of summary or detailed description is available."
        else:
            score = 250 if matching else 550
            message = "The source does not provide usable summary or description content."
        issue = QualityIssue(
            "quality.description_incomplete",
            severity,
            cause,
            QualityDimension.DESCRIPTION_COMPLETENESS,
            message,
            matching,
        )
        return self._dimension(
            QualityDimension.DESCRIPTION_COMPLETENESS,
            score,
            True,
            message,
            (issue,),
        ), (issue,)

    def _specifications(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        facts = value.facts
        expectations = _profile_expectations(value)
        issues: list[QualityIssue] = []
        scores: list[int] = []
        for expectation in expectations:
            if expectation.satisfied:
                scores.append(1_000)
                continue
            evidence = _matching_evidence(value, expectation.patterns)
            cause = (
                QualityIssueCause.EXTRACTION_MISSING
                if evidence
                else QualityIssueCause.SOURCE_MISSING
            )
            severity = QualityIssueSeverity.WARNING if evidence else QualityIssueSeverity.SUGGESTION
            scores.append(250 if evidence else 700)
            issues.append(
                QualityIssue(
                    expectation.code,
                    severity,
                    cause,
                    QualityDimension.SPECIFICATION_COVERAGE,
                    f"The {facts.profile.value} profile is missing {expectation.label}.",
                    evidence,
                )
            )
        if not expectations:
            if len(facts.specifications) >= 2:
                scores.append(1_000)
            elif facts.specifications:
                scores.append(850)
            else:
                scores.append(700)
                issues.append(
                    QualityIssue(
                        "quality.specifications_source_missing",
                        QualityIssueSeverity.SUGGESTION,
                        QualityIssueCause.SOURCE_MISSING,
                        QualityDimension.SPECIFICATION_COVERAGE,
                        "No structured specifications are available in the source.",
                    )
                )
        if facts.unmapped_specifications:
            evidence = tuple(
                dict.fromkeys(
                    item
                    for specification in facts.unmapped_specifications
                    for item in specification.evidence
                )
            )
            issues.append(
                QualityIssue(
                    "quality.unmapped_specifications",
                    QualityIssueSeverity.WARNING,
                    QualityIssueCause.EXTRACTION_MISSING,
                    QualityDimension.SPECIFICATION_COVERAGE,
                    "Some source specifications remain unmapped and require taxonomy review.",
                    evidence,
                )
            )
            scores.append(max(300, 1_000 - len(facts.unmapped_specifications) * 150))
        score = sum(scores) // len(scores)
        explanation = (
            f"Profile expectations satisfied with {len(facts.specifications)} normalized and "
            f"{len(facts.unmapped_specifications)} unmapped specifications."
        )
        found = tuple(issues)
        return self._dimension(
            QualityDimension.SPECIFICATION_COVERAGE,
            score,
            True,
            explanation,
            found,
        ), found

    def _module_pinout(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        expected = value.identity.component_kind in {
            ComponentKind.MODULE,
            ComponentKind.DEVELOPMENT_BOARD,
            ComponentKind.CONNECTOR,
        }
        if not expected:
            return self._dimension(
                QualityDimension.MODULE_PINOUT_PRESENCE,
                1_000,
                False,
                "Module pinout is not applicable to this component kind.",
                (),
            ), ()
        if value.facts.extracted_facts.module_pinout:
            return self._dimension(
                QualityDimension.MODULE_PINOUT_PRESENCE,
                1_000,
                True,
                "The source provides an evidenced module-level pinout.",
                (),
            ), ()
        evidence = _matching_evidence(
            value,
            (r"\bpin(?:out| map| definition| assignment|s)?\b", r"\b(?:sda|scl|vcc|gnd)\b"),
        )
        cause = (
            QualityIssueCause.EXTRACTION_MISSING if evidence else QualityIssueCause.SOURCE_MISSING
        )
        severity = QualityIssueSeverity.WARNING if evidence else QualityIssueSeverity.SUGGESTION
        score = 200 if evidence else 750
        issue = QualityIssue(
            "quality.module_pinout_missing",
            severity,
            cause,
            QualityDimension.MODULE_PINOUT_PRESENCE,
            "A module-level pinout is not available; KiCad symbol pins cannot replace it.",
            evidence,
        )
        return self._dimension(
            QualityDimension.MODULE_PINOUT_PRESENCE,
            score,
            True,
            "Module pinout absence is classified from retained source evidence.",
            (issue,),
        ), (issue,)

    def _provenance(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        source = value.facts.artifact.source
        evidence = _all_evidence(value)
        score = 1_000
        issues: list[QualityIssue] = []
        if source.source_revision is None:
            score -= 250
            issues.append(
                QualityIssue(
                    "quality.source_revision_missing",
                    QualityIssueSeverity.WARNING,
                    QualityIssueCause.SOURCE_MISSING,
                    QualityDimension.SOURCE_PROVENANCE_COMPLETENESS,
                    "The source has no immutable revision identifier.",
                )
            )
        if not evidence:
            score = 0
            issues.append(
                QualityIssue(
                    "quality.provenance_missing",
                    QualityIssueSeverity.BLOCKING,
                    QualityIssueCause.EXTRACTION_MISSING,
                    QualityDimension.SOURCE_PROVENANCE_COMPLETENESS,
                    "No source evidence remains for the evaluated facts.",
                )
            )
        elif any(item.source != source for item in evidence):
            score = 0
            issues.append(
                QualityIssue(
                    "quality.provenance_source_mismatch",
                    QualityIssueSeverity.BLOCKING,
                    QualityIssueCause.CONFLICT,
                    QualityDimension.SOURCE_PROVENANCE_COMPLETENESS,
                    "Evidence points to a source other than the evaluated artifact.",
                    evidence,
                )
            )
        found = tuple(issues)
        return self._dimension(
            QualityDimension.SOURCE_PROVENANCE_COMPLETENESS,
            max(0, score),
            True,
            f"Validated {len(evidence)} distinct provenance fragments.",
            found,
        ), found

    def _conflicts(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        issues: list[QualityIssue] = []
        deduction = 0
        for conflict_number, conflict in enumerate(value.facts.conflicts, start=1):
            code = (
                "quality.normalization_conflict."
                f"{_code_suffix(conflict.taxonomy_path)}.{conflict_number}"
            )
            issues.append(
                QualityIssue(
                    code,
                    QualityIssueSeverity.BLOCKING,
                    QualityIssueCause.CONFLICT,
                    QualityDimension.CONFLICTS,
                    f"Conflicting normalized values remain for {conflict.taxonomy_path}.",
                    conflict.evidence,
                )
            )
            deduction += 350
        grouped_warnings: dict[str, list[EvidenceFragment]] = {}
        for warning in value.facts.extracted_facts.warnings:
            grouped_warnings.setdefault(warning.code, []).extend(warning.evidence)
        for code, evidence in sorted(grouped_warnings.items()):
            issues.append(
                QualityIssue(
                    f"quality.extraction_warning.{_code_suffix(code)}",
                    QualityIssueSeverity.WARNING,
                    QualityIssueCause.EXTRACTION_MISSING,
                    QualityDimension.CONFLICTS,
                    f"The extractor reported {code}.",
                    tuple(dict.fromkeys(evidence)),
                )
            )
            deduction += 100
        for code in sorted(set(value.identity.warnings)):
            issues.append(
                QualityIssue(
                    f"quality.identity_warning.{_code_suffix(code)}",
                    QualityIssueSeverity.WARNING,
                    QualityIssueCause.POLICY,
                    QualityDimension.CONFLICTS,
                    f"The identity resolver reported {code}.",
                    value.identity.canonical_name.evidence,
                )
            )
            deduction += 120
        accepted = [
            item for item in value.enrichments if item.decision is EnrichmentDecision.AUTO_ACCEPTED
        ]
        if len(accepted) > 1:
            issues.append(
                QualityIssue(
                    "quality.multiple_auto_accepted_enrichments",
                    QualityIssueSeverity.BLOCKING,
                    QualityIssueCause.CONFLICT,
                    QualityDimension.CONFLICTS,
                    "Multiple KiCad relations were automatically accepted for one identity.",
                    tuple(
                        dict.fromkeys(
                            evidence
                            for item in accepted
                            for contribution in item.relation.score_breakdown
                            for evidence in contribution.source_evidence
                        )
                    ),
                )
            )
            deduction += 500
        for candidate in value.enrichments:
            if candidate.decision is not EnrichmentDecision.REVIEW_REQUIRED:
                continue
            for contribution in candidate.relation.negative_evidence:
                issues.append(
                    QualityIssue(
                        "quality.enrichment_conflict."
                        f"{_code_suffix(candidate.relation.symbol.record_id)}."
                        f"{candidate.relation.relation_type.value}."
                        f"{_code_suffix(contribution.rule_id)}",
                        QualityIssueSeverity.WARNING,
                        QualityIssueCause.CONFLICT,
                        QualityDimension.CONFLICTS,
                        contribution.reason,
                        contribution.source_evidence,
                    )
                )
                deduction += min(150, abs(contribution.weight_basis_points) // 2)
        found = tuple(issues)
        return self._dimension(
            QualityDimension.CONFLICTS,
            max(0, 1_000 - deduction),
            True,
            f"Detected {len(found)} conflict or parser-warning conditions.",
            found,
        ), found

    def _enrichment(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        accepted = tuple(
            item for item in value.enrichments if item.decision is EnrichmentDecision.AUTO_ACCEPTED
        )
        review = tuple(
            item
            for item in value.enrichments
            if item.decision is EnrichmentDecision.REVIEW_REQUIRED
        )
        if accepted:
            score = max(item.relation.confidence_basis_points for item in accepted)
            explanation = "At least one strict KiCad relation is automatically accepted."
            return self._dimension(
                QualityDimension.ENRICHMENT_CONFIDENCE,
                score,
                True,
                explanation,
                (),
            ), ()
        if review:
            score = min(850, max(item.relation.confidence_basis_points for item in review))
            issue = QualityIssue(
                "quality.enrichment_review_required",
                QualityIssueSeverity.WARNING,
                QualityIssueCause.POLICY,
                QualityDimension.ENRICHMENT_CONFIDENCE,
                "One or more KiCad relations require a reviewer decision.",
                tuple(
                    dict.fromkeys(
                        evidence
                        for item in review
                        for contribution in item.relation.score_breakdown
                        for evidence in contribution.source_evidence
                    )
                ),
            )
            return self._dimension(
                QualityDimension.ENRICHMENT_CONFIDENCE,
                score,
                True,
                "The best available enrichment is review-only.",
                (issue,),
            ), (issue,)
        if value.identity.primary_ic_candidates:
            issue = QualityIssue(
                "quality.expected_enrichment_missing",
                QualityIssueSeverity.WARNING,
                QualityIssueCause.SOURCE_MISSING,
                QualityDimension.ENRICHMENT_CONFIDENCE,
                "The source identifies a primary IC but no usable KiCad relation was found.",
                tuple(
                    dict.fromkeys(
                        evidence
                        for item in value.identity.primary_ic_candidates
                        for evidence in item.evidence
                    )
                ),
            )
            return self._dimension(
                QualityDimension.ENRICHMENT_CONFIDENCE,
                400,
                True,
                "A primary IC is known but enrichment is unavailable.",
                (issue,),
            ), (issue,)
        return self._dimension(
            QualityDimension.ENRICHMENT_CONFIDENCE,
            1_000,
            False,
            "No enrichment is objectively required by the source identity.",
            (),
        ), ()

    def _educational(
        self, value: QualityEvaluationInput
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        extracted = value.facts.extracted_facts
        signals = (
            (bool(extracted.summary_candidates or extracted.description_sections), 250),
            (bool(extracted.feature_facts), 200),
            (bool(extracted.application_facts), 200),
            (bool(extracted.usage_sections), 200),
            (bool(extracted.resources), 150),
        )
        score = sum(weight for present, weight in signals if present)
        if score >= 600:
            return self._dimension(
                QualityDimension.EDUCATIONAL_USEFULNESS,
                score,
                True,
                "The source provides enough explanatory or practical learning content.",
                (),
            ), ()
        issue = QualityIssue(
            "quality.educational_content_limited",
            QualityIssueSeverity.SUGGESTION,
            QualityIssueCause.SOURCE_MISSING,
            QualityDimension.EDUCATIONAL_USEFULNESS,
            "The source contains limited features, applications, usage or reference material.",
        )
        return self._dimension(
            QualityDimension.EDUCATIONAL_USEFULNESS,
            score,
            True,
            "Educational usefulness is based only on retained source sections.",
            (issue,),
        ), (issue,)

    def _publication(
        self,
        value: QualityEvaluationInput,
        existing_issues: tuple[QualityIssue, ...],
    ) -> tuple[QualityDimensionScore, tuple[QualityIssue, ...]]:
        extracted = value.facts.extracted_facts
        score = 200
        if value.identity.resolution_status is IdentityResolutionStatus.AUTO_RESOLVED:
            score += 300
        elif value.identity.resolution_status is IdentityResolutionStatus.REVIEW_REQUIRED:
            score += 150
        if extracted.summary_candidates or extracted.description_sections:
            score += 250
        if value.facts.specifications or value.facts.unmapped_specifications:
            score += 150
        if value.facts.artifact.source.source_revision is not None:
            score += 100
        blocking_count = sum(
            item.severity is QualityIssueSeverity.BLOCKING for item in existing_issues
        )
        warning_count = sum(
            item.severity is QualityIssueSeverity.WARNING for item in existing_issues
        )
        score = max(0, score - blocking_count * 400 - warning_count * 75)
        return self._dimension(
            QualityDimension.PUBLICATION_READINESS,
            score,
            True,
            "Readiness combines identity, content, specifications, provenance and open issues.",
            (),
        ), ()

    @staticmethod
    def _dimension(
        dimension: QualityDimension,
        score: int,
        applicable: bool,
        explanation: str,
        issues: tuple[QualityIssue, ...],
    ) -> QualityDimensionScore:
        return QualityDimensionScore(
            dimension,
            max(0, min(1_000, score)),
            _DIMENSION_WEIGHTS[dimension],
            applicable,
            explanation,
            tuple(item.code for item in issues),
        )


def _threshold(value: float | Decimal, code: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(code) from error
    if not result.is_finite():
        raise ValueError(code)
    return result


def _basis_points(value: Decimal) -> int:
    return int((value * 1_000).to_integral_value(rounding=ROUND_CEILING))


def _overall(dimensions: tuple[QualityDimensionScore, ...]) -> int:
    return sum(item.score_basis_points * item.weight_basis_points for item in dimensions) // 1_000


def _route(
    overall: int,
    issues: tuple[QualityIssue, ...],
    reject_threshold: int,
    ready_threshold: int,
) -> QualityRoute:
    if overall < reject_threshold or any(
        item.severity is QualityIssueSeverity.BLOCKING for item in issues
    ):
        return QualityRoute.REJECT
    if overall < ready_threshold or any(
        item.severity is QualityIssueSeverity.WARNING for item in issues
    ):
        return QualityRoute.MANUAL_REVIEW
    return QualityRoute.READY_TO_COMPOSE


def _profile_expectations(value: QualityEvaluationInput) -> tuple[ProfileExpectation, ...]:
    facts = value.facts
    paths = {item.taxonomy_path for item in facts.specifications}
    has_interface = bool(facts.interfaces)
    has_power = any(path.startswith("electrical.voltage") for path in paths)
    if facts.profile is NormalizationProfile.DISPLAY:
        return (
            ProfileExpectation(
                "quality.profile.display.interface_missing",
                "a communication interface",
                (r"\b(?:i2c|i²c|spi|interface)\b",),
                has_interface,
            ),
            ProfileExpectation(
                "quality.profile.display.resolution_missing",
                "display resolution",
                (r"\bresolution\b", r"\b\d{2,4}\s*[x×]\s*\d{2,4}\b"),
                "display.resolution" in paths,
            ),
        )
    if facts.profile is NormalizationProfile.SENSOR:
        return (
            ProfileExpectation(
                "quality.profile.sensor.quantity_missing",
                "a measured quantity",
                (r"\b(?:temperature|humidity|pressure|distance|range|sensor)\b",),
                any(path.startswith(("sensor.", "measurement.")) for path in paths),
            ),
            ProfileExpectation(
                "quality.profile.sensor.range_missing",
                "a measurement range",
                (r"\b(?:measurement|measuring|temperature|humidity|pressure)?\s*range\b",),
                any("range" in path for path in paths),
            ),
        )
    if facts.profile is NormalizationProfile.BOARD:
        return (
            ProfileExpectation(
                "quality.profile.board.mcu_missing",
                "an MCU or primary IC",
                (r"\b(?:mcu|microcontroller|processor|esp32|atmega|rp2040)\b",),
                bool(value.identity.primary_ic_candidates),
            ),
            ProfileExpectation(
                "quality.profile.board.power_missing",
                "power or supply-voltage data",
                (r"\b(?:power|supply|voltage|vcc|vin)\b",),
                has_power,
            ),
            ProfileExpectation(
                "quality.profile.board.interface_missing",
                "at least one communication interface",
                (r"\b(?:i2c|spi|uart|usb|wi-?fi|bluetooth|interface)\b",),
                has_interface,
            ),
        )
    if facts.profile is NormalizationProfile.ACTUATOR:
        return (
            ProfileExpectation(
                "quality.profile.actuator.power_missing",
                "power or supply-voltage data",
                (r"\b(?:power|supply|voltage|current|vcc|vin)\b",),
                has_power,
            ),
            ProfileExpectation(
                "quality.profile.actuator.control_missing",
                "a control interface",
                (r"\b(?:i2c|spi|pwm|digital|interface|control)\b",),
                has_interface,
            ),
        )
    if facts.profile is NormalizationProfile.COMMUNICATION:
        return (
            ProfileExpectation(
                "quality.profile.communication.interface_missing",
                "a communication interface",
                (r"\b(?:can|i2c|spi|uart|lora|radio|interface)\b",),
                has_interface,
            ),
            ProfileExpectation(
                "quality.profile.communication.frequency_missing",
                "frequency or band data",
                (r"\b(?:frequency|mhz|ghz|band)\b",),
                any("frequency" in path for path in paths),
            ),
        )
    return ()


def _matching_evidence(
    value: QualityEvaluationInput,
    patterns: tuple[str, ...],
) -> tuple[EvidenceFragment, ...]:
    compiled = tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    return tuple(
        evidence
        for evidence in _all_evidence(value)
        if any(pattern.search(evidence.raw_text) is not None for pattern in compiled)
    )


def _all_evidence(value: QualityEvaluationInput) -> tuple[EvidenceFragment, ...]:
    extracted = value.facts.extracted_facts
    result = list(value.identity.evidence)
    for title in extracted.title_candidates:
        result.extend(title.evidence)
    for summary in extracted.summary_candidates:
        result.extend(summary.evidence)
    for description in extracted.description_sections:
        result.extend(description.evidence)
    for feature in extracted.feature_facts:
        result.extend(feature.evidence)
    for application in extracted.application_facts:
        result.extend(application.evidence)
    for usage in extracted.usage_sections:
        result.extend(usage.evidence)
    for identifier in extracted.identifiers:
        result.extend(identifier.evidence)
    for manufacturer in extracted.manufacturer_candidates:
        result.extend(manufacturer.evidence)
    for brand in extracted.brand_candidates:
        result.extend(brand.evidence)
    for interface in extracted.interface_facts:
        result.extend(interface.evidence)
    for pin in extracted.module_pinout:
        result.extend(pin.evidence)
    for primary_ic in extracted.primary_ic_candidates:
        result.extend(primary_ic.evidence)
    for specification in extracted.specifications:
        result.extend(specification.evidence)
    for resource in extracted.resources:
        result.extend(resource.evidence)
    for image in extracted.images:
        result.extend(image.evidence)
    for unmapped in extracted.unmapped_facts:
        result.extend(unmapped.evidence)
    for warning in extracted.warnings:
        result.extend(warning.evidence)
    for candidate in value.enrichments:
        for contribution in candidate.relation.score_breakdown:
            result.extend(contribution.source_evidence)
    return tuple(dict.fromkeys(result))


def _code_suffix(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")[:80] or "unknown"
