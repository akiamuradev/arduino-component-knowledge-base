"""Stage 9 deterministic card composition and compatibility tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from import_pipeline_helpers import (
    SEEED_FIXTURES,
    STARTED_AT,
    SequenceClock,
    composition_input,
    quality_input,
)

from arduino_component_kb.imports.pipeline import (
    ComponentSymbolRelationType,
    CompositionInput,
    DeterministicCardComposer,
    DeterministicQualityEvaluator,
    DraftEnrichmentStatus,
    EnrichmentDecision,
    LegacyRepositoryDraftMapper,
    LegacyRepositoryMappingMetadata,
    PipelineStage,
    QualityIssueSeverity,
    QualityRoute,
    ReviewDraft,
)
from arduino_component_kb.imports.pipeline.errors import CompositionError
from arduino_component_kb.imports.repository_domain import (
    LicenseSnapshot,
    ParsedRepositoryComponent,
    ParseStatus,
)

GOLDEN = Path(__file__).parent / "golden" / "imports" / "review_drafts_v1.json"
COMPOSABLE_CASES = tuple(
    sorted(
        path.name
        for path in SEEED_FIXTURES.iterdir()
        if path.suffix in {".md", ".mdx"} and path.name != "minimal_no_summary.md"
    )
)


def composer() -> DeterministicCardComposer:
    return DeterministicCardComposer(
        SequenceClock(
            STARTED_AT + timedelta(seconds=11),
            STARTED_AT + timedelta(seconds=12),
        )
    )


async def composed(file_name: str) -> ReviewDraft:
    context, value = await composition_input(file_name)
    result = await composer().compose(context, value)
    assert result.stage is PipelineStage.COMPOSITION
    assert result.context.next_stage is PipelineStage.PERSISTENCE
    return result.value


def projection(draft: ReviewDraft) -> dict[str, object]:
    return {
        "payload_sha256": sha256(draft.to_json().encode()).hexdigest(),
        "quality": [draft.quality_route.value, draft.quality_score_basis_points],
        "title": draft.title.value,
        "title_review_required": draft.title.review.review_required,
        "selected_category": draft.selected_category,
        "section_counts": [
            int(draft.summary is not None),
            len(draft.detailed_description),
            len(draft.features),
            len(draft.applications),
            len(draft.module_specifications),
            len(draft.module_connection.instructions),
            len(draft.module_connection.pins),
            len(draft.internal_electronic_components),
            len(draft.kicad_symbols),
            len(draft.resources),
        ],
        "review_specifications": [
            item.taxonomy_path or item.label
            for item in draft.module_specifications
            if item.review.review_required
        ],
        "enrichments": [
            [
                item.record_id,
                item.relation_type.value,
                item.status.value,
                item.confidence_basis_points,
            ]
            for item in draft.kicad_symbols
        ],
        "review_warnings": [item.code for item in draft.review_warnings],
    }


async def test_fourteen_review_drafts_match_golden_and_round_trip() -> None:
    expected = cast(dict[str, dict[str, object]], json.loads(GOLDEN.read_text("utf-8")))
    actual: dict[str, dict[str, object]] = {}
    for file_name in COMPOSABLE_CASES:
        draft = await composed(file_name)
        assert ReviewDraft.from_json(draft.to_json()) == draft
        actual[file_name] = projection(draft)

    assert len(actual) == 14
    assert actual == expected


async def test_rejected_quality_cannot_create_a_review_draft() -> None:
    context, value = await composition_input("minimal_no_summary.md")
    assert value.quality_report.route is QualityRoute.REJECT

    with pytest.raises(CompositionError, match="composition_quality_rejected"):
        await composer().compose(context, value)


async def test_composer_rejects_wrong_stage_and_source() -> None:
    context, value = await composition_input("complete.md")
    evaluation_context = replace(context, executions=context.executions[:-1])
    wrong_source = replace(context, source_key="other_source")

    with pytest.raises(CompositionError, match="composition_stage_out_of_order"):
        await composer().compose(evaluation_context, value)
    with pytest.raises(CompositionError, match="pipeline_source_mismatch"):
        await composer().compose(wrong_source, value)


async def test_composition_input_rejects_unrelated_quality_report() -> None:
    _, complete = await composition_input("complete.md")
    _, display = await composition_input("display_spi.md")

    with pytest.raises(ValueError, match="composition_quality_input_mismatch"):
        CompositionInput(
            complete.facts,
            complete.identity,
            complete.enrichments,
            display.quality_report,
        )


async def test_proposed_kicad_match_is_never_presented_as_accepted() -> None:
    draft = await composed("display_spi.md")

    assert len(draft.kicad_symbols) == 1
    assert draft.kicad_symbols[0].status is DraftEnrichmentStatus.PROPOSED
    assert draft.kicad_symbols[0].review_reasons
    assert draft.internal_electronic_components[0].status is DraftEnrichmentStatus.PROPOSED


async def test_rejected_enrichment_is_not_composed() -> None:
    _, value = await composition_input("environmental_sensor.md")
    rejected_ids = {
        item.relation.symbol.record_id
        for item in value.enrichments
        if item.decision is EnrichmentDecision.REJECTED
    }
    draft = await composed("environmental_sensor.md")

    assert rejected_ids
    assert rejected_ids.isdisjoint(item.record_id for item in draft.kicad_symbols)


async def test_module_and_kicad_pinouts_are_separate_structures() -> None:
    draft = await composed("display_spi.md")

    module_pins = draft.module_connection.pins
    symbol_pins = draft.kicad_symbols[0].pins
    assert module_pins and symbol_pins
    assert {item.name for item in module_pins} != {item.name for item in symbol_pins}
    payload = draft.kicad_symbols[0].as_dict()
    assert payload["pinout_level"] == "kicad_symbol"
    assert "pins" not in draft.module_connection.as_dict() or payload != (
        draft.module_connection.as_dict()
    )


async def test_low_confidence_and_unmapped_fields_use_review_metadata_only() -> None:
    complete = await composed("complete.md")
    actuator = await composed("actuator_module.md")
    low = next(item for item in complete.module_specifications if item.review.review_required)
    unmapped = next(item for item in actuator.module_specifications if item.taxonomy_path is None)

    assert low.review.reason_codes == ("composition.normalization_low_confidence",)
    assert unmapped.review.reason_codes == ("composition.unmapped_specification",)
    assert "low confidence" not in low.value.casefold()
    assert "review" not in unmapped.value.casefold()


async def test_composer_copies_only_input_facts_without_generating_public_text() -> None:
    _, value = await composition_input("complete.md")
    draft = await composed("complete.md")
    extracted = value.facts.extracted_facts

    assert draft.title.value == value.identity.canonical_name.value
    assert draft.summary is not None
    assert draft.summary.value in {item.value for item in extracted.summary_candidates}
    assert {item.body for item in draft.detailed_description} <= {
        item.value.body for item in extracted.description_sections
    }
    assert {item.value for item in draft.features} <= {
        item.value for item in extracted.feature_facts
    }
    assert {item.value for item in draft.applications} <= {
        item.value for item in extracted.application_facts
    }
    assert {item.value for item in draft.module_specifications if item.taxonomy_path} == {
        item.trace.normalized_value for item in value.facts.specifications
    }


async def test_auto_accepted_relation_is_composed_as_accepted_symbol_data() -> None:
    context, quality_value = await quality_input("environmental_sensor.md")
    proposed = quality_value.enrichments[0]
    accepted = replace(
        proposed,
        relation=replace(
            proposed.relation,
            relation_type=ComponentSymbolRelationType.EXACT_COMPONENT,
        ),
        decision=EnrichmentDecision.AUTO_ACCEPTED,
        review_reasons=(),
    )
    accepted_enrichments = (accepted, *quality_value.enrichments[1:])
    accepted_quality_input = replace(quality_value, enrichments=accepted_enrichments)
    evaluation = await DeterministicQualityEvaluator(
        SequenceClock(
            STARTED_AT + timedelta(seconds=9),
            STARTED_AT + timedelta(seconds=10),
        )
    ).evaluate(context, accepted_quality_input)
    composition = CompositionInput(
        accepted_quality_input.facts,
        accepted_quality_input.identity,
        accepted_enrichments,
        evaluation.value,
    )
    result = await composer().compose(evaluation.context, composition)

    assert result.value.kicad_symbols[0].status is DraftEnrichmentStatus.ACCEPTED
    assert result.value.internal_electronic_components == ()


async def test_legacy_mapper_preserves_review_state_and_field_provenance() -> None:
    draft = await composed("display_spi.md")
    mapped = LegacyRepositoryDraftMapper().map(
        draft,
        LegacyRepositoryMappingMetadata(
            original_url="https://wiki.seeedstudio.com/display_spi/",
            license_snapshot=LicenseSnapshot(
                "GNU General Public License v3.0 only",
                "GPL-3.0-only",
                "https://www.gnu.org/licenses/gpl-3.0.html",
                "Seeed Studio Wiki fixture attribution",
            ),
            modifications_notice="Facts composed into a review draft; no missing text generated.",
        ),
    )

    assert isinstance(mapped, ParsedRepositoryComponent)
    assert mapped.status is ParseStatus.PARSED_WITH_WARNINGS
    assert mapped.draft_status == "draft"
    assert set(mapped.normalized_fields) == set(mapped.provenance)
    kicad = mapped.normalized_fields["kicad_symbols"]
    assert isinstance(kicad, list)
    assert kicad[0]["status"] == "proposed"
    assert mapped.normalized_fields["module_pinout"] != kicad[0]["pins"]


async def test_composition_is_deterministic_for_equal_input_and_clock() -> None:
    context, value = await composition_input("development_board.md")

    first = (await composer().compose(context, value)).value
    second = (await composer().compose(context, value)).value

    assert first == second
    assert first.to_json() == second.to_json()


async def test_review_draft_rejects_forged_status_and_schema() -> None:
    draft = await composed("complete.md")
    payload = json.loads(draft.to_json())
    payload["schema_version"] = "review-draft/v999"

    with pytest.raises(ValueError, match="review_draft_rejected_quality_forbidden"):
        replace(draft, quality_route=QualityRoute.REJECT)
    with pytest.raises(ValueError, match="review_draft_schema_version_unsupported"):
        ReviewDraft.from_dict(payload)


async def test_review_draft_rejects_missing_provenance_and_relation_state_drift() -> None:
    complete = await composed("complete.md")
    display = await composed("display_spi.md")
    internal = replace(
        display.internal_electronic_components[0],
        status=DraftEnrichmentStatus.ACCEPTED,
        review_reasons=(),
    )
    blocking = replace(
        complete.review_warnings[0],
        severity=QualityIssueSeverity.BLOCKING,
    )

    with pytest.raises(ValueError, match="review_draft_field_provenance_missing"):
        replace(complete, provenance=complete.title.evidence)
    with pytest.raises(ValueError, match="review_draft_internal_component_relation_mismatch"):
        replace(display, internal_electronic_components=(internal,))
    with pytest.raises(ValueError, match="review_draft_blocking_warning_forbidden"):
        replace(complete, review_warnings=(blocking, *complete.review_warnings[1:]))
