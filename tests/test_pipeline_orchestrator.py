"""Stage 11 full-chain orchestration, retry, timeout and failure-path tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from import_pipeline_helpers import (
    SEEED_FIXTURES,
    SEEED_REVISION,
    kicad_snapshot,
)

from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.pipeline import (
    AcquisitionError,
    DryRunPersistenceGateway,
    EvidenceFirstImportOrchestrator,
    KicadSymbolIndexer,
    OrchestratorPolicy,
    PipelineExecutionStatus,
    PipelineRunRequest,
    PipelineStage,
    PreparedSourceAcquirer,
    SourceArtifact,
    SourceArtifactMetadata,
    SourceReference,
)
from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult
from arduino_component_kb.imports.pipeline.errors import PersistenceError
from arduino_component_kb.imports.pipeline.models import (
    PersistedPipelineDraft,
    PipelinePersistenceInput,
)

RUN_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
SOURCE_ID = UUID("00000000-0000-4000-9000-000000000004")


def artifact(file_name: str) -> SourceArtifact:
    content = (SEEED_FIXTURES / file_name).read_bytes()
    return SourceArtifact(
        SourceArtifactMetadata(
            SourceReference(
                "seeed_wiki",
                SeeedWikiAdapter.repository_url,
                file_name,
                SEEED_REVISION,
            ),
            "text/mdx" if file_name.endswith(".mdx") else "text/markdown",
            sha256(content).hexdigest(),
            len(content),
            datetime.now(UTC) - timedelta(seconds=1),
        ),
        content,
    )


def request(file_name: str = "complete.md") -> PipelineRunRequest:
    return PipelineRunRequest(
        RUN_ID,
        SOURCE_ID,
        artifact(file_name),
        KicadSymbolIndexer().build(kicad_snapshot()).index,
    )


async def test_full_pipeline_integrates_all_eight_stages() -> None:
    outcome = await EvidenceFirstImportOrchestrator(DryRunPersistenceGateway()).run(request())

    assert outcome.status is PipelineExecutionStatus.SUCCEEDED
    assert outcome.result is not None
    assert tuple(item.stage for item in outcome.result.context.executions) == tuple(PipelineStage)
    assert outcome.result.review_draft.title.value == "Grove - Temperature Sensor"
    assert outcome.result.persisted.review_draft_id
    assert outcome.failure is None


async def test_rejected_quality_is_an_observable_composition_failure() -> None:
    outcome = await EvidenceFirstImportOrchestrator(DryRunPersistenceGateway()).run(
        request("minimal_no_summary.md")
    )

    assert outcome.status is PipelineExecutionStatus.FAILED
    assert outcome.failure is not None
    assert outcome.failure.stage is PipelineStage.COMPOSITION
    assert outcome.failure.code == "composition_quality_rejected"
    assert outcome.failure.retryable is False
    assert outcome.result is None


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


class FlakyPreparedAcquirer:
    def __init__(self) -> None:
        self.calls = 0
        self.delegate = PreparedSourceAcquirer()

    async def acquire(
        self, context: ImportPipelineContext, value: SourceArtifact
    ) -> StageResult[SourceArtifact]:
        self.calls += 1
        if self.calls == 1:
            raise AcquisitionError("acquisition_temporarily_unavailable", retryable=True)
        return await self.delegate.acquire(context, value)


async def test_safe_acquisition_retries_then_succeeds() -> None:
    acquirer = FlakyPreparedAcquirer()
    sleeper = RecordingSleeper()
    orchestrator = EvidenceFirstImportOrchestrator(
        DryRunPersistenceGateway(),
        acquirer=acquirer,
        sleeper=sleeper,
        policy=OrchestratorPolicy.uniform(5, retry_delay_seconds=0.01),
    )

    outcome = await orchestrator.run(request())

    assert outcome.status is PipelineExecutionStatus.SUCCEEDED
    assert acquirer.calls == 2
    assert sleeper.delays == [0.01]


class SlowAcquirer:
    def __init__(self) -> None:
        self.calls = 0

    async def acquire(
        self, context: ImportPipelineContext, value: SourceArtifact
    ) -> StageResult[SourceArtifact]:
        self.calls += 1
        await asyncio.sleep(0.05)
        return await PreparedSourceAcquirer().acquire(context, value)


async def test_safe_stage_timeout_retries_then_returns_failure_state() -> None:
    acquirer = SlowAcquirer()
    outcome = await EvidenceFirstImportOrchestrator(
        DryRunPersistenceGateway(),
        acquirer=acquirer,
        sleeper=RecordingSleeper(),
        policy=OrchestratorPolicy.uniform(0.01, retry_delay_seconds=0),
    ).run(request())

    assert outcome.failure is not None
    assert outcome.failure.stage is PipelineStage.ACQUISITION
    assert outcome.failure.code == "pipeline_stage_timeout"
    assert outcome.failure.attempts == 2
    assert acquirer.calls == 2


class FailingPersistence:
    def __init__(self) -> None:
        self.calls = 0

    async def persist(
        self,
        context: ImportPipelineContext,
        value: PipelinePersistenceInput,
    ) -> StageResult[PersistedPipelineDraft]:
        self.calls += 1
        raise PersistenceError("persistence_temporarily_unavailable", retryable=True)


async def test_unsafe_persistence_is_never_retried() -> None:
    persistence = FailingPersistence()
    outcome = await EvidenceFirstImportOrchestrator(
        persistence,
        policy=OrchestratorPolicy.uniform(5, safe_retry_attempts=5),
    ).run(request())

    assert outcome.failure is not None
    assert outcome.failure.stage is PipelineStage.PERSISTENCE
    assert outcome.failure.code == "persistence_temporarily_unavailable"
    assert outcome.failure.attempts == 1
    assert persistence.calls == 1


def test_orchestrator_policy_requires_every_stage_and_bounded_values() -> None:
    policy = OrchestratorPolicy.uniform(12, safe_retry_attempts=3)
    assert set(policy.stage_timeouts_seconds) == set(PipelineStage)
    assert policy.safe_retry_attempts == 3

    try:
        policy.stage_timeouts_seconds[PipelineStage.EXTRACTION] = 99  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("orchestrator policy must be immutable")
