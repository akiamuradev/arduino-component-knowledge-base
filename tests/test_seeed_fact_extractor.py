"""Golden and contract tests for the evidence-first Seeed extractor."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.pipeline import (
    ExtractedFacts,
    FactExtractor,
    ImportPipelineContext,
    ParsingError,
    PipelineStage,
    SeeedFactExtractor,
    SourceArtifact,
    SourceArtifactMetadata,
    SourceReference,
    StageExecution,
)
from arduino_component_kb.imports.repository_domain import RepositoryEntry, RepositorySnapshot

FIXTURES = Path(__file__).parent / "fixtures" / "seeed"
GOLDEN = Path(__file__).parent / "golden" / "imports" / "seeed_extractor_v2.json"
REVISION = "a" * 40
ACQUIRED_AT = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
EXTRACTION_STARTED_AT = ACQUIRED_AT + timedelta(seconds=1)
EXTRACTION_COMPLETED_AT = ACQUIRED_AT + timedelta(seconds=2)
SEEED_CASES = {
    "actuator_module.md": "actuator",
    "alternative_headings.mdx": "display/alternate-headings",
    "broken_frontmatter.mdx": "malformed-mdx",
    "can_bus_module.md": "communication",
    "communication_module.md": "communication",
    "complete.md": "sensor/complete",
    "connector_module.md": "connector",
    "development_board.md": "development-board",
    "display_spi.md": "display",
    "environmental_sensor.md": "sensor",
    "minimal_no_summary.md": "minimal/missing-summary",
    "motor_shield.md": "shield",
    "power_module.md": "power",
    "unknown_structure.md": "legacy/unknown-section",
    "without_specifications.md": "input/missing-specifications",
}
PRE_REFACTOR_CASES = (
    "alternative_headings.mdx",
    "broken_frontmatter.mdx",
    "communication_module.md",
    "complete.md",
    "development_board.md",
    "power_module.md",
    "unknown_structure.md",
    "without_specifications.md",
)


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def now(self) -> datetime:
        return next(self._values)


def artifact(file_name: str, *, source_key: str = "seeed_wiki") -> SourceArtifact:
    content = (FIXTURES / file_name).read_bytes()
    media_type = "text/mdx" if file_name.endswith(".mdx") else "text/markdown"
    return SourceArtifact(
        metadata=SourceArtifactMetadata(
            source=SourceReference(
                source_key=source_key,
                source_url=SeeedWikiAdapter.repository_url,
                source_path=file_name,
                source_revision=REVISION,
            ),
            media_type=media_type,
            content_sha256=sha256(content).hexdigest(),
            byte_length=len(content),
            acquired_at=ACQUIRED_AT,
        ),
        content=content,
    )


def context(*, source_key: str = "seeed_wiki") -> ImportPipelineContext:
    initial = ImportPipelineContext(
        run_id=UUID("12345678-1234-5678-1234-567812345678"),
        source_key=source_key,
        source_locator=SeeedWikiAdapter.repository_url,
        pipeline_version="2.0.0",
        started_at=ACQUIRED_AT,
    )
    return initial.advance(
        StageExecution(
            stage=PipelineStage.ACQUISITION,
            started_at=ACQUIRED_AT,
            completed_at=ACQUIRED_AT,
        )
    )


async def extract(file_name: str) -> ExtractedFacts:
    extractor: FactExtractor[SourceArtifact, ExtractedFacts] = SeeedFactExtractor(
        SequenceClock(EXTRACTION_STARTED_AT, EXTRACTION_COMPLETED_AT)
    )
    result = await extractor.extract(context(), artifact(file_name))
    assert result.stage is PipelineStage.EXTRACTION
    assert result.context.next_stage is PipelineStage.NORMALIZATION
    assert result.context.executions[-1].started_at == EXTRACTION_STARTED_AT
    assert result.context.executions[-1].completed_at == EXTRACTION_COMPLETED_AT
    return result.value


def projection(facts: ExtractedFacts, profile: str) -> dict[str, object]:
    return {
        "profile": profile,
        "payload_sha256": sha256(facts.to_json().encode()).hexdigest(),
        "titles": [item.value for item in facts.title_candidates],
        "summaries": [item.value for item in facts.summary_candidates],
        "description_sections": [item.value.as_dict() for item in facts.description_sections],
        "features": [item.value for item in facts.feature_facts],
        "applications": [item.value for item in facts.application_facts],
        "usage_sections": [item.value.as_dict() for item in facts.usage_sections],
        "identifiers": [item.value.as_dict() for item in facts.identifiers],
        "manufacturers": [item.value for item in facts.manufacturer_candidates],
        "brands": [item.value for item in facts.brand_candidates],
        "interfaces": [item.value for item in facts.interface_facts],
        "module_pinout": [item.value.as_dict() for item in facts.module_pinout],
        "primary_ics": [item.value.as_dict() for item in facts.primary_ic_candidates],
        "specifications": [item.value.as_dict() for item in facts.specifications],
        "resources": [item.value.as_dict() for item in facts.resources],
        "images": [item.value.as_dict() for item in facts.images],
        "unmapped": [item.value.as_dict() for item in facts.unmapped_facts],
        "warnings": [item.code for item in facts.warnings],
    }


async def test_seeed_fifteen_profile_corpus_matches_golden_result() -> None:
    expected = cast(dict[str, dict[str, object]], json.loads(GOLDEN.read_text("utf-8")))
    actual = {
        file_name: projection(await extract(file_name), profile)
        for file_name, profile in SEEED_CASES.items()
    }

    assert len(actual) == 15
    assert actual == expected


@pytest.mark.parametrize(
    ("file_name", "expected_ic"),
    [
        ("actuator_module.md", "DRV8830"),
        ("can_bus_module.md", "MCP2515"),
        ("display_spi.md", "SSD1306"),
        ("environmental_sensor.md", "BME280"),
        ("motor_shield.md", "L298P"),
    ],
)
async def test_primary_ic_candidates_are_evidenced(file_name: str, expected_ic: str) -> None:
    facts = await extract(file_name)
    candidate = next(
        item for item in facts.primary_ic_candidates if item.value.value == expected_ic
    )

    assert candidate.evidence
    assert all(item.source == facts.artifact.source for item in candidate.evidence)
    assert all(item.parser_version == "2.0.0" for item in candidate.evidence)


async def test_summary_description_and_pinout_remain_distinct_source_facts() -> None:
    facts = await extract("actuator_module.md")

    assert facts.summary_candidates[0].value == (
        "A dual-channel motor driver module controlled over I2C."
    )
    assert facts.description_sections[0].value.body == (
        "The module is built around DRV8830 and drives two small DC motors."
    )
    assert [pin.value.name for pin in facts.module_pinout] == ["SDA", "SCL", "VIN"]
    assert {pin.evidence[0].section for pin in facts.module_pinout} == {"Pinout"}

    shield = await extract("motor_shield.md")
    assert [pin.value.name for pin in shield.module_pinout] == ["DIR_A", "PWM_A"]
    assert [pin.value.number for pin in shield.module_pinout] == ["D8", "D9"]


async def test_unknown_specs_and_sections_are_retained_without_normalization() -> None:
    expected = {
        "actuator_module.md": ("Peak channel behavior", "internally limited"),
        "connector_module.md": ("Wire range", "16-30 AWG"),
        "display_spi.md": ("Display color", "monochrome"),
        "minimal_no_summary.md": ("Vendor tuning code", "X-17"),
        "motor_shield.md": ("Maximum current", "2A per channel"),
    }
    for file_name, raw_pair in expected.items():
        facts = await extract(file_name)
        assert raw_pair in {(item.value.label, item.value.value) for item in facts.specifications}

    minimal = await extract("minimal_no_summary.md")
    assert [item.value.label for item in minimal.unmapped_facts] == ["Prototype Notes"]
    assert "unknown_section" in {item.code for item in minimal.warnings}


async def test_missing_summary_is_a_warning_not_generated_content() -> None:
    facts = await extract("minimal_no_summary.md")

    assert facts.summary_candidates == ()
    assert "summary_missing" in {item.code for item in facts.warnings}
    assert "Technical facts imported" not in facts.to_json()


@pytest.mark.parametrize("file_name", ["complete.md", "alternative_headings.mdx"])
async def test_executable_markdown_and_mdx_constructs_are_never_extracted(
    file_name: str,
) -> None:
    facts = await extract(file_name)
    payload = facts.to_json()

    assert 'system(\\"must never run\\")' not in payload
    assert "127.0.0.1" not in payload
    assert "executable_construct_ignored" in {item.code for item in facts.warnings}


async def test_new_extractor_preserves_more_structure_than_release_adapter() -> None:
    legacy_specifications = 0
    legacy_resources = 0
    new_specifications = 0
    new_resources = 0
    new_module_pins = 0
    new_semantic_sections = 0
    adapter = SeeedWikiAdapter()

    for file_name in PRE_REFACTOR_CASES:
        content = (FIXTURES / file_name).read_bytes()
        parsed = await adapter.parse_entry(
            RepositorySnapshot(adapter.repository_url, REVISION, {file_name: content}),
            RepositoryEntry(file_name),
            parsed_at=ACQUIRED_AT,
        )
        legacy_specifications += len(
            cast(list[object], parsed.normalized_fields.get("specifications", []))
        )
        legacy_resources += len(cast(list[object], parsed.normalized_fields.get("resources", [])))

        facts = await extract(file_name)
        new_specifications += len(facts.specifications)
        new_resources += len(facts.resources)
        new_module_pins += len(facts.module_pinout)
        new_semantic_sections += sum(
            len(items)
            for items in (
                facts.description_sections,
                facts.feature_facts,
                facts.application_facts,
                facts.usage_sections,
            )
        )

    assert new_specifications > legacy_specifications
    assert new_resources >= legacy_resources
    assert new_module_pins > 0
    assert new_semantic_sections > 0


async def test_extractor_rejects_foreign_source_before_parsing() -> None:
    extractor = SeeedFactExtractor(SequenceClock(EXTRACTION_STARTED_AT))

    with pytest.raises(ParsingError, match="seeed_source_invalid"):
        await extractor.extract(
            context(source_key="foreign_source"),
            artifact("complete.md", source_key="foreign_source"),
        )


async def test_extractor_rejects_artifact_from_another_pipeline_source() -> None:
    foreign_context = ImportPipelineContext(
        run_id=UUID("12345678-1234-5678-1234-567812345678"),
        source_key="foreign_source",
        source_locator="https://example.com/source",
        pipeline_version="2.0.0",
        started_at=ACQUIRED_AT,
    ).advance(
        StageExecution(
            stage=PipelineStage.ACQUISITION,
            started_at=ACQUIRED_AT,
            completed_at=ACQUIRED_AT,
        )
    )
    extractor = SeeedFactExtractor(SequenceClock(EXTRACTION_STARTED_AT))

    with pytest.raises(ParsingError, match="pipeline_source_mismatch"):
        await extractor.extract(foreign_context, artifact("complete.md"))


def test_source_artifact_rejects_content_that_does_not_match_metadata() -> None:
    valid = artifact("complete.md")

    with pytest.raises(ValueError, match="source_artifact_digest_mismatch"):
        SourceArtifact(metadata=valid.metadata, content=b"x" * valid.metadata.byte_length)
