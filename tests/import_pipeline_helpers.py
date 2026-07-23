"""Shared deterministic builders for evidence-first import pipeline tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.pipeline import (
    ComponentIdentity,
    CompositionInput,
    DeterministicQualityEvaluator,
    ImportPipelineContext,
    KiCadEnrichmentProvider,
    KicadEnrichmentRequest,
    KicadSymbolIndexer,
    PipelineStage,
    QualityEvaluationInput,
    SeeedFactExtractor,
    SeeedKicadMatcher,
    SemanticFactNormalizer,
    SourceArtifact,
    SourceArtifactMetadata,
    SourceReference,
    StageExecution,
    WeightedIdentityResolver,
)
from arduino_component_kb.imports.repository_domain import RepositorySnapshot

KICAD_FIXTURES = Path(__file__).parent / "fixtures" / "kicad"
SEEED_FIXTURES = Path(__file__).parent / "fixtures" / "seeed"
KICAD_REVISION = "b" * 40
SEEED_REVISION = "a" * 40
STARTED_AT = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def now(self) -> datetime:
        return next(self._values)


def kicad_snapshot(
    revision: str = KICAD_REVISION,
    files: dict[str, bytes] | None = None,
) -> RepositorySnapshot:
    return RepositorySnapshot(
        "https://gitlab.com/kicad/libraries/kicad-symbols",
        revision,
        files
        if files is not None
        else {
            path.name: path.read_bytes()
            for path in KICAD_FIXTURES.iterdir()
            if path.suffix == ".kicad_sym"
        },
    )


async def resolved(file_name: str) -> tuple[ImportPipelineContext, ComponentIdentity]:
    content = (SEEED_FIXTURES / file_name).read_bytes()
    source = SourceReference(
        "seeed_wiki",
        SeeedWikiAdapter.repository_url,
        file_name,
        SEEED_REVISION,
    )
    artifact = SourceArtifact(
        SourceArtifactMetadata(
            source,
            "text/mdx" if file_name.endswith(".mdx") else "text/markdown",
            sha256(content).hexdigest(),
            len(content),
            STARTED_AT,
        ),
        content,
    )
    context = ImportPipelineContext(
        UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        "seeed_wiki",
        SeeedWikiAdapter.repository_url,
        "2.0.0",
        STARTED_AT,
    ).advance(StageExecution(PipelineStage.ACQUISITION, STARTED_AT, STARTED_AT))
    extracted = await SeeedFactExtractor(
        SequenceClock(STARTED_AT + timedelta(seconds=1), STARTED_AT + timedelta(seconds=2))
    ).extract(context, artifact)
    normalized = await SemanticFactNormalizer(
        SequenceClock(STARTED_AT + timedelta(seconds=3), STARTED_AT + timedelta(seconds=4))
    ).normalize(extracted.context, extracted.value)
    identity = await WeightedIdentityResolver(
        SequenceClock(STARTED_AT + timedelta(seconds=5), STARTED_AT + timedelta(seconds=6))
    ).resolve(normalized.context, normalized.value)
    return identity.context, identity.value


async def quality_input(
    file_name: str,
) -> tuple[ImportPipelineContext, QualityEvaluationInput]:
    context, identity = await resolved(file_name)
    index = KicadSymbolIndexer().build(kicad_snapshot()).index
    enrichment = await KiCadEnrichmentProvider(
        index,
        SequenceClock(STARTED_AT + timedelta(seconds=7), STARTED_AT + timedelta(seconds=8)),
    ).enrich(
        context,
        KicadEnrichmentRequest(identity, identity.normalized_facts),
    )
    relations = SeeedKicadMatcher().match(
        identity,
        identity.normalized_facts,
        enrichment.value,
    )
    return enrichment.context, QualityEvaluationInput(
        identity.normalized_facts,
        identity,
        relations,
    )


async def composition_input(
    file_name: str,
) -> tuple[ImportPipelineContext, CompositionInput]:
    context, value = await quality_input(file_name)
    evaluation = await DeterministicQualityEvaluator(
        SequenceClock(
            STARTED_AT + timedelta(seconds=9),
            STARTED_AT + timedelta(seconds=10),
        )
    ).evaluate(context, value)
    return evaluation.context, CompositionInput(
        value.facts,
        value.identity,
        value.enrichments,
        evaluation.value,
    )
