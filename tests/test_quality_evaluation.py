"""Stage 8 deterministic pre-composition quality evaluation tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from import_pipeline_helpers import SEEED_FIXTURES, STARTED_AT, SequenceClock, quality_input

from arduino_component_kb.imports.pipeline import (
    DeterministicQualityEvaluator,
    NormalizationConflict,
    PipelineStage,
    QualityDimension,
    QualityEvaluationInput,
    QualityIssueCause,
    QualityIssueSeverity,
    QualityReport,
    QualityRoute,
)
from arduino_component_kb.imports.pipeline.errors import QualityError
from arduino_component_kb.imports.pipeline.models import (
    ComponentIdentity,
    EnrichmentCandidate,
    ExtractedFacts,
    NormalizedFacts,
    NormalizedIdentifier,
)

BENCHMARK = Path(__file__).parent / "fixtures" / "quality" / "benchmark_v1.json"
SEEED_CASES = tuple(
    sorted(path.name for path in SEEED_FIXTURES.iterdir() if path.suffix in {".md", ".mdx"})
)


def evaluator(**thresholds: float) -> DeterministicQualityEvaluator:
    return DeterministicQualityEvaluator(
        SequenceClock(
            STARTED_AT + timedelta(seconds=9),
            STARTED_AT + timedelta(seconds=10),
        ),
        **thresholds,
    )


async def evaluated(
    file_name: str,
    value: QualityEvaluationInput | None = None,
    *,
    quality_evaluator: DeterministicQualityEvaluator | None = None,
) -> QualityReport:
    context, default_value = await quality_input(file_name)
    result = await (quality_evaluator or evaluator()).evaluate(context, value or default_value)
    assert result.stage is PipelineStage.EVALUATION
    assert result.context.next_stage is PipelineStage.COMPOSITION
    return result.value


def _with_extracted(
    value: QualityEvaluationInput,
    extracted: ExtractedFacts,
    *,
    primary_ics: tuple[NormalizedIdentifier, ...] | None = None,
) -> QualityEvaluationInput:
    facts = replace(
        value.facts,
        extracted_facts=extracted,
        extracted_facts_sha256=sha256(extracted.to_json().encode()).hexdigest(),
        primary_ics=value.facts.primary_ics if primary_ics is None else primary_ics,
    )
    return _with_facts(value, facts)


def _with_facts(
    value: QualityEvaluationInput,
    facts: NormalizedFacts,
    *,
    primary_ic_candidates: tuple[NormalizedIdentifier, ...] | None = None,
    keep_enrichments: bool = True,
) -> QualityEvaluationInput:
    identity = replace(
        value.identity,
        normalized_facts=facts,
        normalized_facts_sha256=sha256(facts.to_json().encode()).hexdigest(),
        primary_ic_candidates=(
            value.identity.primary_ic_candidates
            if primary_ic_candidates is None
            else primary_ic_candidates
        ),
    )
    enrichments: tuple[EnrichmentCandidate, ...] = ()
    if keep_enrichments:
        identity_sha256 = sha256(identity.to_json().encode()).hexdigest()
        enrichments = tuple(
            replace(item, relation=replace(item.relation, identity_sha256=identity_sha256))
            for item in value.enrichments
        )
    return QualityEvaluationInput(facts, identity, enrichments)


def _projection(report: QualityReport) -> dict[str, object]:
    return {
        "profile": report.profile.value,
        "overall_score_basis_points": report.overall_score_basis_points,
        "route": report.route.value,
        "issue_counts": {
            severity.value: sum(item.severity is severity for item in report.issues)
            for severity in QualityIssueSeverity
        },
        "dimensions": {item.dimension.value: item.score_basis_points for item in report.dimensions},
        "issues": [item.code for item in report.issues],
    }


async def test_fifteen_fixture_quality_reports_match_benchmark() -> None:
    expected = cast(dict[str, dict[str, object]], json.loads(BENCHMARK.read_text("utf-8")))
    actual = {file_name: _projection(await evaluated(file_name)) for file_name in SEEED_CASES}

    assert len(actual) == 15
    assert actual == expected


async def test_report_has_all_weighted_dimensions_and_round_trips() -> None:
    report = await evaluated("environmental_sensor.md")

    assert tuple(item.dimension for item in report.dimensions) == tuple(QualityDimension)
    assert sum(item.weight_basis_points for item in report.dimensions) == 1_000
    assert QualityReport.from_json(report.to_json()) == report
    assert json.loads(report.to_json())["schema_version"] == "quality-report/v1"


async def test_complete_warning_free_input_is_ready_to_compose() -> None:
    _, value = await quality_input("display_spi.md")
    extracted = replace(
        value.facts.extracted_facts,
        primary_ic_candidates=(),
        warnings=(),
    )
    clean = _with_extracted(
        value,
        extracted,
        primary_ics=(),
    )
    clean = _with_facts(
        clean,
        clean.facts,
        primary_ic_candidates=(),
        keep_enrichments=False,
    )

    report = await evaluated("display_spi.md", clean)

    assert report.route is QualityRoute.READY_TO_COMPOSE
    assert report.blocking_issues == ()
    assert not any(item.severity is QualityIssueSeverity.WARNING for item in report.issues)


async def test_unresolved_identity_is_rejected_with_blocking_issue() -> None:
    report = await evaluated("minimal_no_summary.md")

    assert report.route is QualityRoute.REJECT
    assert {item.code for item in report.blocking_issues} == {"quality.identity_unresolved"}


async def test_ambiguous_identity_is_sent_to_manual_review() -> None:
    report = await evaluated("motor_shield.md")

    assert report.route is QualityRoute.MANUAL_REVIEW
    assert "quality.identity_review_required" in {item.code for item in report.issues}
    assert report.blocking_issues == ()


async def test_source_missing_and_extraction_missing_are_separate_causes() -> None:
    report = await evaluated("alternative_headings.mdx")
    issues = {item.code: item for item in report.issues}

    assert issues["quality.profile.display.interface_missing"].cause is (
        QualityIssueCause.EXTRACTION_MISSING
    )
    assert issues["quality.profile.display.interface_missing"].severity is (
        QualityIssueSeverity.WARNING
    )
    assert issues["quality.profile.display.resolution_missing"].cause is (
        QualityIssueCause.SOURCE_MISSING
    )
    assert issues["quality.profile.display.resolution_missing"].severity is (
        QualityIssueSeverity.SUGGESTION
    )


@pytest.mark.parametrize(
    ("file_name", "issue_code"),
    [
        ("alternative_headings.mdx", "quality.profile.display.interface_missing"),
        ("unknown_structure.md", "quality.profile.sensor.quantity_missing"),
        ("development_board.md", "quality.profile.board.mcu_missing"),
        ("motor_shield.md", "quality.profile.actuator.control_missing"),
    ],
)
async def test_profile_expectations_are_independent(
    file_name: str,
    issue_code: str,
) -> None:
    report = await evaluated(file_name)

    assert issue_code in {item.code for item in report.issues}


async def test_kicad_symbol_pins_do_not_replace_missing_module_pinout() -> None:
    _, value = await quality_input("display_spi.md")
    assert value.enrichments
    assert any(item.relation.symbol_pinout for item in value.enrichments)
    extracted = replace(value.facts.extracted_facts, module_pinout=())
    missing_module_pins = _with_extracted(value, extracted)

    report = await evaluated("display_spi.md", missing_module_pins)
    score = next(
        item
        for item in report.dimensions
        if item.dimension is QualityDimension.MODULE_PINOUT_PRESENCE
    )

    assert score.score_basis_points < 1_000
    assert score.applicable
    assert "quality.module_pinout_missing" in score.issue_codes


async def test_normalization_conflict_is_blocking() -> None:
    _, value = await quality_input("complete.md")
    evidence = value.identity.canonical_name.evidence
    facts = replace(
        value.facts,
        conflicts=(
            NormalizationConflict(
                "electrical.voltage.input",
                ("3.3 V", "5 V"),
                evidence,
            ),
        ),
    )
    conflicted = _with_facts(value, facts, keep_enrichments=False)

    report = await evaluated("complete.md", conflicted)

    assert report.route is QualityRoute.REJECT
    assert any(
        item.code == "quality.normalization_conflict.electrical_voltage_input.1"
        and item.severity is QualityIssueSeverity.BLOCKING
        for item in report.issues
    )


async def test_evaluator_does_not_mutate_input() -> None:
    context, value = await quality_input("environmental_sensor.md")
    before = (
        value.facts.to_json(),
        value.identity.to_json(),
        tuple(item.to_json() for item in value.enrichments),
    )

    await evaluator().evaluate(context, value)

    assert before == (
        value.facts.to_json(),
        value.identity.to_json(),
        tuple(item.to_json() for item in value.enrichments),
    )


async def test_quality_input_rejects_stale_enrichment_identity_hash() -> None:
    _, value = await quality_input("display_spi.md")
    changed_identity: ComponentIdentity = replace(
        value.identity,
        canonical_name=replace(value.identity.canonical_name, value="Changed display"),
    )

    with pytest.raises(ValueError, match="quality_input_enrichment_identity_mismatch"):
        QualityEvaluationInput(value.facts, changed_identity, value.enrichments)


async def test_evaluator_rejects_wrong_stage_and_source() -> None:
    context, value = await quality_input("complete.md")
    previous_context = replace(context, executions=context.executions[:-1])
    wrong_source = replace(context, source_key="other_source")

    with pytest.raises(QualityError, match="quality_stage_out_of_order"):
        await evaluator().evaluate(previous_context, value)
    with pytest.raises(QualityError, match="pipeline_source_mismatch"):
        await evaluator().evaluate(wrong_source, value)


@pytest.mark.parametrize(
    ("reject", "ready", "message"),
    [
        (0.2, 0.8, "quality_reject_threshold_invalid"),
        (0.5, 0.96, "quality_ready_threshold_invalid"),
        (0.7, 0.7, "quality_ready_threshold_invalid"),
        (float("nan"), 0.8, "quality_reject_threshold_invalid"),
    ],
)
def test_thresholds_are_bounded(reject: float, ready: float, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        DeterministicQualityEvaluator(reject_threshold=reject, ready_threshold=ready)


async def test_report_rejects_forged_route_and_schema() -> None:
    report = await evaluated("minimal_no_summary.md")
    payload = json.loads(report.to_json())
    payload["schema_version"] = "quality-report/v999"

    with pytest.raises(ValueError, match="quality_report_route_mismatch"):
        replace(report, route=QualityRoute.READY_TO_COMPOSE)
    with pytest.raises(ValueError, match="quality_report_schema_version_unsupported"):
        QualityReport.from_dict(payload)
