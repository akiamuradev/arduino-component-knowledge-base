"""Safe bridge from the legacy repository worker into Stage 11 shadow mode."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.config import Settings
from arduino_component_kb.imports.acquisition import AcquiredEntry
from arduino_component_kb.imports.models import ImportJob, Source
from arduino_component_kb.imports.pipeline.models import (
    KicadSymbolIndex,
    OrchestratorPolicy,
    PipelineRunRequest,
    ShadowComparisonReport,
    SourceArtifact,
    SourceArtifactMetadata,
    SourceReference,
)
from arduino_component_kb.imports.pipeline.persistence import PostgresImportPersistenceGateway
from arduino_component_kb.imports.pipeline.runtime import EvidenceFirstImportOrchestrator
from arduino_component_kb.imports.pipeline.shadow import ShadowImportRunner
from arduino_component_kb.imports.repository_domain import ParsedRepositoryComponent

logger = logging.getLogger("arduino_component_kb.imports.pipeline.shadow")
_UNAVAILABLE_KICAD_REVISION = "0" * 40


async def run_repository_shadow(
    session: AsyncSession,
    settings: Settings,
    job: ImportJob,
    source: Source,
    acquired: AcquiredEntry,
    legacy: ParsedRepositoryComponent,
) -> ShadowComparisonReport:
    """Run the new pipeline without publishing it or changing legacy source-of-truth fields."""
    content = acquired.snapshot.read(acquired.file_path)
    acquired_at = datetime.now(UTC)
    artifact = SourceArtifact(
        SourceArtifactMetadata(
            SourceReference(
                source.key,
                acquired.snapshot.repository_url,
                acquired.file_path,
                acquired.snapshot.revision,
            ),
            "text/mdx" if acquired.file_path.casefold().endswith(".mdx") else "text/markdown",
            sha256(content).hexdigest(),
            len(content),
            acquired_at,
        ),
        content,
    )
    policy = OrchestratorPolicy.uniform(
        settings.import_pipeline_stage_timeout_seconds,
        safe_retry_attempts=settings.import_pipeline_safe_retry_attempts,
    )
    orchestrator = EvidenceFirstImportOrchestrator(
        PostgresImportPersistenceGateway(session),
        policy=policy,
    )
    result = await ShadowImportRunner(orchestrator).run(
        PipelineRunRequest(
            job.id,
            source.id,
            artifact,
            KicadSymbolIndex((), _UNAVAILABLE_KICAD_REVISION),
        ),
        legacy,
    )
    report = result.comparison
    logger.info(
        "shadow_import_compared",
        extra={
            "import_run_id": str(job.id),
            "source": source.key,
            "revision": acquired.snapshot.revision,
            "outcome": report.pipeline_status,
            "comparison_conflicts": len(report.conflicts),
            "field_coverage_basis_points": report.field_coverage_basis_points,
            "quality_score": report.quality_score_basis_points,
            "duration_ms": report.execution_time_ms,
            "shadow_mode": True,
        },
    )
    return report
