"""Stage 6 KiCad index, cache and enrichment-provider tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from import_pipeline_helpers import (
    KICAD_REVISION,
    STARTED_AT,
    SequenceClock,
    kicad_snapshot,
    resolved,
)

from arduino_component_kb.imports.pipeline import (
    EnrichmentProvider,
    KicadCandidateSet,
    KiCadEnrichmentProvider,
    KicadEnrichmentRequest,
    KicadMatchBasis,
    KicadSymbolIndexer,
    PipelineStage,
)
from arduino_component_kb.imports.repository_domain import RepositorySnapshot


class SequenceTimer:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def now(self) -> float:
        return next(self._values)


def test_index_extracts_reusable_symbol_records_and_search_maps() -> None:
    result = KicadSymbolIndexer(timer=SequenceTimer(1.0, 1.012)).build(kicad_snapshot())

    assert result.stats.parsed_files == 10
    assert result.stats.cache_hit is False
    assert result.stats.duration_ms == pytest.approx(12.0)
    assert any(warning.endswith("sexpression_unbalanced") for warning in result.stats.warnings)
    drv8830 = result.index.exact_part_number("drv8830")[0]
    assert drv8830.record_id == "Driver_Motor_Enrichment:DRV8830"
    assert drv8830.aliases == ("DRV8830DGQ", "DRV8830DRC")
    assert drv8830.manufacturer_hints == ("Texas Instruments",)
    assert [pin.electrical_type for pin in drv8830.pins] == [
        "power_in",
        "input",
        "bidirectional",
        "output",
    ]
    assert result.index.alias("drv8830dgq") == (drv8830,)
    assert result.index.normalized_name("DRV-8830") == (drv8830,)
    generic = result.index.normalized_name("connector generic 01x04")[0]
    assert generic.symbol_name == "Connector_Generic_01x04"
    assert drv8830 in result.index.description("I2C motor driver")
    assert result.index.manufacturer_hint("Texas Instruments") == (drv8830,)


def test_index_cache_hit_and_incremental_content_invalidation() -> None:
    timer = SequenceTimer(1.0, 1.01, 2.0, 2.001, 3.0, 3.004)
    indexer = KicadSymbolIndexer(timer=timer)
    original = kicad_snapshot()
    first = indexer.build(original)
    cached = indexer.build(original)
    changed_files = dict(original.files)
    changed_files["Sensor_Environmental.kicad_sym"] += b"\n"
    changed = indexer.build(kicad_snapshot("c" * 40, changed_files))

    assert cached.index is first.index
    assert cached.stats.cache_hit is True
    assert cached.stats.parsed_files == 0
    assert cached.stats.warnings == first.stats.warnings
    assert changed.stats.cache_hit is False
    assert changed.stats.parsed_files == 1
    assert changed.stats.reused_files == 9
    assert {record.source_revision for record in changed.index.records} == {"c" * 40}
    assert changed.index.index_sha256 != first.index.index_sha256


def test_index_cache_accounts_for_removed_libraries() -> None:
    indexer = KicadSymbolIndexer(timer=SequenceTimer(1.0, 1.01, 2.0, 2.01))
    original = kicad_snapshot()
    indexer.build(original)
    reduced = dict(original.files)
    del reduced["Driver_Motor_Enrichment.kicad_sym"]

    result = indexer.build(kicad_snapshot("d" * 40, reduced))

    assert result.stats.removed_files == 1
    assert result.index.exact_part_number("DRV8830") == ()


def test_index_content_hash_invalidates_cache_without_revision_change() -> None:
    indexer = KicadSymbolIndexer(timer=SequenceTimer(1.0, 1.01, 2.0, 2.01))
    original = kicad_snapshot()
    first = indexer.build(original)
    changed_files = dict(original.files)
    changed_files["Display_Graphic.kicad_sym"] += b"\n"

    changed = indexer.build(kicad_snapshot(KICAD_REVISION, changed_files))

    assert changed.stats.cache_hit is False
    assert changed.stats.parsed_files == 1
    assert changed.index.index_sha256 != first.index.index_sha256


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_name", "symbol_name"),
    [
        ("actuator_module.md", "DRV8830"),
        ("environmental_sensor.md", "BME280"),
        ("display_spi.md", "SSD1306"),
    ],
)
async def test_provider_finds_primary_ic_without_creating_cards(
    file_name: str, symbol_name: str
) -> None:
    context, identity = await resolved(file_name)
    index = KicadSymbolIndexer().build(kicad_snapshot()).index
    provider: EnrichmentProvider[KicadEnrichmentRequest, KicadCandidateSet] = (
        KiCadEnrichmentProvider(
            index,
            SequenceClock(
                STARTED_AT + timedelta(seconds=7),
                STARTED_AT + timedelta(seconds=8),
            ),
        )
    )

    result = await provider.enrich(
        context,
        KicadEnrichmentRequest(identity, identity.normalized_facts),
    )

    hit = next(item for item in result.value.hits if item.record.symbol_name == symbol_name)
    assert hit.matched_terms[0].basis is KicadMatchBasis.EXACT_PART_NUMBER
    assert result.stage is PipelineStage.ENRICHMENT
    assert result.context.next_stage is PipelineStage.EVALUATION
    assert "card" not in result.value.as_dict()
    assert KicadCandidateSet.from_json(result.value.to_json()) == result.value


@pytest.mark.asyncio
async def test_generic_symbol_requires_explicit_part_number_evidence() -> None:
    _, identity = await resolved("environmental_sensor.md")
    index = KicadSymbolIndexer().build(kicad_snapshot()).index
    provider = KiCadEnrichmentProvider(index)
    connector_identity = replace(
        identity,
        canonical_name=replace(identity.canonical_name, value="Connector"),
        primary_ic_candidates=(),
    )
    assert provider.find_candidates(connector_identity, connector_identity.normalized_facts) == ()

    explicit_identifier = replace(
        identity.primary_ic_candidates[0],
        trace=replace(
            identity.primary_ic_candidates[0].trace,
            normalized_value="Connector_Generic_01x04",
        ),
    )
    explicit_identity = replace(
        connector_identity,
        primary_ic_candidates=(explicit_identifier,),
    )
    hits = provider.find_candidates(explicit_identity, explicit_identity.normalized_facts)

    assert [hit.record.symbol_name for hit in hits] == ["Connector_Generic_01x04"]
    assert hits[0].matched_terms[0].basis is KicadMatchBasis.EXACT_PART_NUMBER


@pytest.mark.asyncio
async def test_manufacturer_only_annotates_an_existing_candidate() -> None:
    _, identity = await resolved("environmental_sensor.md")
    provider = KiCadEnrichmentProvider(KicadSymbolIndexer().build(kicad_snapshot()).index)
    manufacturer = replace(
        identity.canonical_name,
        value="Bosch",
        rule_id="identity.manufacturer-normalized.v1",
    )
    identified = replace(identity, manufacturer=manufacturer)

    hits = provider.find_candidates(identified, identified.normalized_facts)

    bme280 = next(hit for hit in hits if hit.record.symbol_name == "BME280")
    assert KicadMatchBasis.MANUFACTURER_HINT in {term.basis for term in bme280.matched_terms}
    manufacturer_only = replace(
        identified,
        canonical_name=replace(identified.canonical_name, value="Unrelated board"),
        primary_ic_candidates=(),
    )
    assert provider.find_candidates(manufacturer_only, manufacturer_only.normalized_facts) == ()


def test_index_rejects_non_official_repository() -> None:
    snapshot = RepositorySnapshot(
        "https://example.com/other-symbols",
        KICAD_REVISION,
        {"Sensor_Test.kicad_sym": b"(kicad_symbol_lib)"},
    )
    with pytest.raises(ValueError, match="kicad_index_repository_invalid"):
        KicadSymbolIndexer().build(snapshot)
