"""Complete evidence-first import orchestrator with bounded retries and observability."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Protocol, TypeVar

from arduino_component_kb.imports.pipeline.acquisition import PreparedSourceAcquirer
from arduino_component_kb.imports.pipeline.composition import DeterministicCardComposer
from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageResult,
)
from arduino_component_kb.imports.pipeline.enrichment import (
    KiCadEnrichmentProvider,
    SeeedKicadMatcher,
)
from arduino_component_kb.imports.pipeline.errors import ImportPipelineError
from arduino_component_kb.imports.pipeline.evaluation import DeterministicQualityEvaluator
from arduino_component_kb.imports.pipeline.extractors import SeeedFactExtractor
from arduino_component_kb.imports.pipeline.identity import WeightedIdentityResolver
from arduino_component_kb.imports.pipeline.models import (
    CompositionInput,
    KicadEnrichmentRequest,
    OrchestratorPolicy,
    PersistedPipelineDraft,
    PipelineExecutionStatus,
    PipelinePersistenceInput,
    PipelineRunFailure,
    PipelineRunOutcome,
    PipelineRunRequest,
    PipelineRunResult,
    QualityEvaluationInput,
    SourceArtifact,
)
from arduino_component_kb.imports.pipeline.normalization import SemanticFactNormalizer

StageValueT = TypeVar("StageValueT")
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class PersistencePort(Protocol):
    async def persist(
        self, context: ImportPipelineContext, value: PipelinePersistenceInput
    ) -> StageResult[PersistedPipelineDraft]: ...


class AcquisitionPort(Protocol):
    async def acquire(
        self, context: ImportPipelineContext, artifact: SourceArtifact
    ) -> StageResult[SourceArtifact]: ...


class Sleeper(Protocol):
    async def sleep(self, delay: float) -> None: ...


class AsyncioSleeper:
    async def sleep(self, delay: float) -> None:
        await asyncio.sleep(delay)


class EvidenceFirstImportOrchestrator:
    """Assemble all eight stages without making the pipeline production-primary."""

    def __init__(
        self,
        persistence: PersistencePort,
        *,
        policy: OrchestratorPolicy | None = None,
        acquirer: AcquisitionPort | None = None,
        sleeper: Sleeper | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.persistence = persistence
        self.policy = policy or OrchestratorPolicy.uniform()
        self.acquirer = acquirer or PreparedSourceAcquirer()
        self.sleeper = sleeper or AsyncioSleeper()
        self.logger = logger or logging.getLogger("arduino_component_kb.imports.pipeline")

    async def run(self, request: PipelineRunRequest) -> PipelineRunOutcome:
        started = perf_counter()
        context = ImportPipelineContext(
            request.run_id,
            request.artifact.metadata.source.source_key,
            request.artifact.metadata.source.source_url
            or request.artifact.metadata.source.source_path
            or "missing",
            request.pipeline_version,
            request.artifact.metadata.acquired_at,
        )
        active_stage = PipelineStage.ACQUISITION
        attempts = 1
        try:
            acquired, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: self.acquirer.acquire(context, request.artifact),
                retry_safe=True,
            )
            context = acquired.context

            active_stage = PipelineStage.EXTRACTION
            extracted, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: SeeedFactExtractor().extract(context, acquired.value),
            )
            context = extracted.context

            active_stage = PipelineStage.NORMALIZATION
            normalized, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: SemanticFactNormalizer().normalize(context, extracted.value),
            )
            context = normalized.context

            active_stage = PipelineStage.IDENTITY
            identity, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: WeightedIdentityResolver().resolve(context, normalized.value),
            )
            context = identity.context

            active_stage = PipelineStage.ENRICHMENT
            candidates, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: KiCadEnrichmentProvider(request.kicad_index).enrich(
                    context,
                    KicadEnrichmentRequest(identity.value, normalized.value),
                ),
                retry_safe=True,
            )
            context = candidates.context
            enrichments = SeeedKicadMatcher().match(
                identity.value,
                normalized.value,
                candidates.value,
            )

            active_stage = PipelineStage.EVALUATION
            quality, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: DeterministicQualityEvaluator().evaluate(
                    context,
                    QualityEvaluationInput(normalized.value, identity.value, enrichments),
                ),
            )
            context = quality.context
            composition_input = CompositionInput(
                normalized.value,
                identity.value,
                enrichments,
                quality.value,
            )

            active_stage = PipelineStage.COMPOSITION
            composed, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: DeterministicCardComposer().compose(context, composition_input),
            )
            context = composed.context

            active_stage = PipelineStage.PERSISTENCE
            persisted, attempts = await self._invoke(
                request.run_id,
                active_stage,
                lambda: self.persistence.persist(
                    context,
                    PipelinePersistenceInput(
                        request.source_id,
                        composition_input,
                        composed.value,
                        request.component_id,
                    ),
                ),
            )
            context = persisted.context
            duration_ms = round((perf_counter() - started) * 1_000, 3)
            self.logger.info(
                "import_pipeline_completed",
                extra={
                    "import_run_id": str(request.run_id),
                    "outcome": "succeeded",
                    "duration_ms": duration_ms,
                    "quality_score": quality.value.overall_score_basis_points,
                    "shadow_mode": True,
                },
            )
            return PipelineRunOutcome(
                PipelineExecutionStatus.SUCCEEDED,
                result=PipelineRunResult(
                    context,
                    extracted.value,
                    normalized.value,
                    identity.value,
                    enrichments,
                    quality.value,
                    composed.value,
                    persisted.value,
                    duration_ms,
                ),
            )
        except Exception as error:
            attempts = int(getattr(error, "pipeline_attempts", attempts))
            duration_ms = round((perf_counter() - started) * 1_000, 3)
            code, retryable = self._failure(error)
            failure = PipelineRunFailure(
                request.run_id,
                active_stage,
                code,
                retryable,
                attempts,
                duration_ms,
                type(error).__name__,
            )
            self.logger.error(
                "import_pipeline_failed",
                extra={
                    "import_run_id": str(request.run_id),
                    "import_stage": active_stage.value,
                    "outcome": "failed",
                    "failure_code": code,
                    "attempt": attempts,
                    "duration_ms": duration_ms,
                    "error_type": type(error).__name__,
                    "shadow_mode": True,
                },
            )
            return PipelineRunOutcome(PipelineExecutionStatus.FAILED, failure=failure)

    async def _invoke(
        self,
        run_id: object,
        stage: PipelineStage,
        operation: Callable[[], Awaitable[StageResult[StageValueT]]],
        *,
        retry_safe: bool = False,
    ) -> tuple[StageResult[StageValueT], int]:
        maximum = self.policy.safe_retry_attempts if retry_safe else 1
        for attempt in range(1, maximum + 1):
            started = perf_counter()
            self.logger.info(
                "import_pipeline_stage_started",
                extra={
                    "import_run_id": str(run_id),
                    "import_stage": stage.value,
                    "attempt": attempt,
                    "shadow_mode": True,
                },
            )
            try:
                async with asyncio.timeout(self.policy.stage_timeouts_seconds[stage]):
                    result = await operation()
                self.logger.info(
                    "import_pipeline_stage_completed",
                    extra={
                        "import_run_id": str(run_id),
                        "import_stage": stage.value,
                        "attempt": attempt,
                        "outcome": "succeeded",
                        "duration_ms": round((perf_counter() - started) * 1_000, 3),
                        "warnings_count": len(result.context.executions[-1].warnings),
                        "shadow_mode": True,
                    },
                )
                return result, attempt
            except Exception as error:
                should_retry = retry_safe and attempt < maximum and self._retryable(error)
                self.logger.warning(
                    "import_pipeline_stage_attempt_failed",
                    extra={
                        "import_run_id": str(run_id),
                        "import_stage": stage.value,
                        "attempt": attempt,
                        "outcome": "retrying" if should_retry else "failed",
                        "failure_code": self._failure(error)[0],
                        "duration_ms": round((perf_counter() - started) * 1_000, 3),
                        "shadow_mode": True,
                    },
                )
                if not should_retry:
                    error.pipeline_attempts = attempt  # type: ignore[attr-defined]
                    raise
                await self.sleeper.sleep(self.policy.retry_delay_seconds * attempt)
        raise RuntimeError("pipeline_retry_state_invalid")

    @staticmethod
    def _retryable(error: Exception) -> bool:
        return isinstance(error, TimeoutError) or bool(getattr(error, "retryable", False))

    @staticmethod
    def _failure(error: Exception) -> tuple[str, bool]:
        if isinstance(error, TimeoutError):
            return "pipeline_stage_timeout", True
        if isinstance(error, ImportPipelineError):
            return error.code, error.retryable
        value = str(error)
        return (
            value if _SAFE_CODE.fullmatch(value) else "pipeline_internal_failure",
            bool(getattr(error, "retryable", False)),
        )
