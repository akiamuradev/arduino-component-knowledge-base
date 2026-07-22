"""Stage 5 weighted identity resolution and false-positive regression tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.pipeline import (
    ComponentIdentity,
    ComponentKind,
    ExtractedFacts,
    IdentityAlias,
    IdentityResolutionStatus,
    IdentityResolver,
    ImportPipelineContext,
    NormalizedFacts,
    PipelineStage,
    SeeedFactExtractor,
    SemanticFactNormalizer,
    SourceArtifact,
    SourceArtifactMetadata,
    SourceReference,
    StageExecution,
    WeightedIdentityResolver,
)

FIXTURES = Path(__file__).parent / "fixtures" / "seeed"
GOLDEN = Path(__file__).parent / "golden" / "imports" / "seeed_identity_v1.json"
REVISION = "a" * 40
STARTED_AT = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
SEEED_CASES = tuple(
    sorted(path.name for path in FIXTURES.iterdir() if path.suffix in {".md", ".mdx"})
)


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def now(self) -> datetime:
        return next(self._values)


def artifact(file_name: str) -> SourceArtifact:
    content = (FIXTURES / file_name).read_bytes()
    return SourceArtifact(
        SourceArtifactMetadata(
            SourceReference(
                "seeed_wiki",
                SeeedWikiAdapter.repository_url,
                file_name,
                REVISION,
            ),
            "text/mdx" if file_name.endswith(".mdx") else "text/markdown",
            sha256(content).hexdigest(),
            len(content),
            STARTED_AT,
        ),
        content,
    )


def initial_context() -> ImportPipelineContext:
    return ImportPipelineContext(
        UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        "seeed_wiki",
        SeeedWikiAdapter.repository_url,
        "2.0.0",
        STARTED_AT,
    ).advance(StageExecution(PipelineStage.ACQUISITION, STARTED_AT, STARTED_AT))


async def extracted(file_name: str) -> tuple[ImportPipelineContext, ExtractedFacts]:
    result = await SeeedFactExtractor(
        SequenceClock(STARTED_AT + timedelta(seconds=1), STARTED_AT + timedelta(seconds=2))
    ).extract(initial_context(), artifact(file_name))
    return result.context, result.value


async def normalize_facts(
    context: ImportPipelineContext, facts: ExtractedFacts
) -> tuple[ImportPipelineContext, NormalizedFacts]:
    result = await SemanticFactNormalizer(
        SequenceClock(STARTED_AT + timedelta(seconds=3), STARTED_AT + timedelta(seconds=4))
    ).normalize(context, facts)
    return result.context, result.value


async def resolved(file_name: str) -> tuple[ImportPipelineContext, ComponentIdentity]:
    extraction_context, facts = await extracted(file_name)
    normalization_context, normalized = await normalize_facts(extraction_context, facts)
    resolver: IdentityResolver[NormalizedFacts, ComponentIdentity] = WeightedIdentityResolver(
        SequenceClock(STARTED_AT + timedelta(seconds=5), STARTED_AT + timedelta(seconds=6))
    )
    result = await resolver.resolve(normalization_context, normalized)
    assert result.stage is PipelineStage.IDENTITY
    assert result.context.next_stage is PipelineStage.ENRICHMENT
    return result.context, result.value


def projection(identity: ComponentIdentity) -> dict[str, object]:
    return {
        "payload_sha256": sha256(identity.to_json().encode()).hexdigest(),
        "canonical_name": identity.canonical_name.value,
        "manufacturer": identity.manufacturer.value if identity.manufacturer else None,
        "product_identifiers": [
            [item.kind.value, item.trace.normalized_value] for item in identity.product_identifiers
        ],
        "part_numbers": [item.trace.normalized_value for item in identity.part_numbers],
        "primary_ics": [item.trace.normalized_value for item in identity.primary_ic_candidates],
        "aliases": [item.value for item in identity.aliases],
        "component_kind": identity.component_kind.value,
        "kind_candidates": [
            {
                "kind": item.kind.value,
                "score": item.score,
                "breakdown": [
                    [contribution.rule_id, contribution.weight] for contribution in item.breakdown
                ],
            }
            for item in identity.kind_candidates
        ],
        "selected_category": identity.selected_category,
        "category_candidates": [
            {
                "category": item.category_key,
                "score": item.score,
                "breakdown": [
                    [contribution.rule_id, contribution.weight] for contribution in item.breakdown
                ],
            }
            for item in identity.category_candidates
        ],
        "confidence": identity.confidence.value,
        "resolution_status": identity.resolution_status.value,
        "warnings": list(identity.warnings),
    }


async def test_fifteen_identity_examples_match_golden_score_breakdown() -> None:
    expected = cast(dict[str, dict[str, object]], json.loads(GOLDEN.read_text("utf-8")))
    actual = {file_name: projection((await resolved(file_name))[1]) for file_name in SEEED_CASES}

    assert len(actual) == 15
    assert actual == expected


@pytest.mark.parametrize(
    ("file_name", "primary_ic", "category"),
    [
        ("actuator_module.md", "DRV8830", "actuators"),
        ("can_bus_module.md", "MCP2515", "communication"),
        ("display_spi.md", "SSD1306", "displays"),
        ("environmental_sensor.md", "BME280", "sensors"),
        ("motor_shield.md", "L298P", None),
    ],
)
async def test_primary_ic_never_replaces_module_identity(
    file_name: str, primary_ic: str, category: str | None
) -> None:
    _, identity = await resolved(file_name)

    assert identity.component_kind is ComponentKind.MODULE
    assert identity.canonical_name.value != primary_ic
    assert primary_ic in {item.trace.normalized_value for item in identity.primary_ic_candidates}
    assert primary_ic not in {item.value for item in identity.aliases}
    assert identity.selected_category == category


async def test_identity_model_rejects_primary_ic_as_module_alias() -> None:
    _, identity = await resolved("display_spi.md")
    primary_ic = identity.primary_ic_candidates[0]

    with pytest.raises(ValueError, match="identity_module_primary_ic_alias_forbidden"):
        replace(
            identity,
            aliases=(
                IdentityAlias(
                    primary_ic.trace.normalized_value,
                    "identity.invalid-test-alias.v1",
                    primary_ic.evidence,
                ),
            ),
        )


async def test_thresholds_distinguish_auto_review_and_unresolved() -> None:
    complete = (await resolved("complete.md"))[1]
    ambiguous = (await resolved("motor_shield.md"))[1]
    sparse = (await resolved("minimal_no_summary.md"))[1]

    assert complete.resolution_status is IdentityResolutionStatus.AUTO_RESOLVED
    assert complete.selected_category == "sensors"
    assert ambiguous.resolution_status is IdentityResolutionStatus.REVIEW_REQUIRED
    assert ambiguous.selected_category is None
    assert ambiguous.warnings == ("identity_review_required", "category_ambiguous")
    assert sparse.resolution_status is IdentityResolutionStatus.UNRESOLVED
    assert sparse.category_candidates == ()


async def test_category_and_kind_candidates_explain_every_score_with_evidence() -> None:
    _, identity = await resolved("development_board.md")

    assert len(identity.category_candidates) >= 2
    assert all(candidate.breakdown for candidate in identity.category_candidates)
    assert all(
        contribution.reason
        for candidate in identity.category_candidates
        for contribution in candidate.breakdown
    )
    assert all(
        contribution.evidence
        for candidate in identity.kind_candidates
        for contribution in candidate.breakdown
    )
    assert all(evidence.source == identity.artifact.source for evidence in identity.evidence)


async def test_incidental_resistor_and_connector_mentions_do_not_change_module_kind() -> None:
    button = (await resolved("without_specifications.md"))[1]
    sensor = (await resolved("complete.md"))[1]

    assert button.component_kind is ComponentKind.MODULE
    assert ComponentKind.DISCRETE_COMPONENT not in {item.kind for item in button.kind_candidates}
    assert sensor.component_kind is ComponentKind.MODULE
    assert ComponentKind.CONNECTOR not in {item.kind for item in sensor.kind_candidates}
    assert "connectors" not in {item.category_key for item in sensor.category_candidates}


async def test_connector_is_a_distinct_component_kind() -> None:
    _, identity = await resolved("connector_module.md")

    assert identity.component_kind is ComponentKind.CONNECTOR
    assert identity.selected_category == "connectors"
    assert identity.manufacturer is not None
    assert identity.manufacturer.value == "Seeed Studio"


async def test_exact_primary_ic_title_can_resolve_as_integrated_circuit() -> None:
    context, facts = await extracted("actuator_module.md")
    source_title = facts.title_candidates[0]
    title = replace(
        source_title,
        value="DRV8830",
        raw_value="# DRV8830",
        evidence=tuple(replace(item, raw_text="# DRV8830") for item in source_title.evidence),
    )
    changed = replace(facts, title_candidates=(title,))
    normalization_context, normalized = await normalize_facts(context, changed)
    result = await WeightedIdentityResolver(
        SequenceClock(STARTED_AT + timedelta(seconds=5), STARTED_AT + timedelta(seconds=6))
    ).resolve(normalization_context, normalized)

    assert result.value.component_kind is ComponentKind.INTEGRATED_CIRCUIT
    assert result.value.selected_category == "integrated-circuits"


async def test_discrete_component_requires_title_evidence() -> None:
    context, facts = await extracted("minimal_no_summary.md")
    source_title = facts.title_candidates[0]
    title = replace(
        source_title,
        value="2N3904 transistor",
        raw_value="# 2N3904 transistor",
        evidence=tuple(
            replace(item, raw_text="# 2N3904 transistor") for item in source_title.evidence
        ),
    )
    changed = replace(facts, title_candidates=(title,))
    normalization_context, normalized = await normalize_facts(context, changed)
    result = await WeightedIdentityResolver(
        SequenceClock(STARTED_AT + timedelta(seconds=5), STARTED_AT + timedelta(seconds=6))
    ).resolve(normalization_context, normalized)

    assert result.value.component_kind is ComponentKind.DISCRETE_COMPONENT
    assert result.value.category_candidates[0].category_key == "semiconductors"


async def test_component_identity_json_round_trip_preserves_all_prior_stages() -> None:
    _, identity = await resolved("display_spi.md")

    restored = ComponentIdentity.from_json(identity.to_json())
    assert restored == identity
    assert restored.normalized_facts == identity.normalized_facts
    assert restored.normalized_facts.extracted_facts == identity.normalized_facts.extracted_facts


async def test_identity_result_has_no_card_or_persistence_fields() -> None:
    _, identity = await resolved("complete.md")

    assert set(identity.as_dict()).isdisjoint(
        {"card_id", "draft_status", "publication_status", "persisted_at"}
    )
