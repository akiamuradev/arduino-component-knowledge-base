"""Stage 11 shadow comparison, feature flag and batch command tests."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_pipeline_orchestrator import request

from arduino_component_kb.config import Settings
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.pipeline import (
    DryRunPersistenceGateway,
    EvidenceFirstImportOrchestrator,
    PipelineExecutionStatus,
    ShadowImportRunner,
)
from arduino_component_kb.imports.repository_domain import (
    ParsedRepositoryComponent,
    RepositoryEntry,
    RepositorySnapshot,
)
from arduino_component_kb.imports.shadow_dry_run import batch_shadow_run

ROOT = Path(__file__).parent


async def legacy(file_name: str) -> ParsedRepositoryComponent:
    content = (ROOT / "fixtures/seeed" / file_name).read_bytes()
    snapshot = RepositorySnapshot(
        SeeedWikiAdapter.repository_url,
        "a" * 40,
        {file_name: content},
    )
    return await SeeedWikiAdapter().parse_entry(
        snapshot,
        RepositoryEntry(file_name),
        parsed_at=datetime(2026, 7, 23, 10, 0, tzinfo=UTC),
    )


async def test_shadow_report_compares_coverage_conflicts_quality_and_kicad() -> None:
    result = await ShadowImportRunner(
        EvidenceFirstImportOrchestrator(DryRunPersistenceGateway())
    ).run(request("complete.md"), await legacy("complete.md"))

    report = result.comparison
    assert result.outcome.status is PipelineExecutionStatus.SUCCEEDED
    assert report.pipeline_status == "succeeded"
    assert report.field_coverage_basis_points > 0
    assert report.conflicts
    assert all(
        len(item.legacy_sha256) == len(item.pipeline_sha256) == 64 for item in report.conflicts
    )
    assert report.quality_score_basis_points is not None
    assert report.kicad_candidate_count >= report.kicad_auto_accepted_count
    assert report.kicad_precision_status == "proxy_unreviewed"
    assert "Grove Environmental Sensor" not in report.to_json()


async def test_shadow_failure_does_not_claim_a_pipeline_result() -> None:
    result = await ShadowImportRunner(
        EvidenceFirstImportOrchestrator(DryRunPersistenceGateway())
    ).run(request("minimal_no_summary.md"), await legacy("minimal_no_summary.md"))

    assert result.outcome.status is PipelineExecutionStatus.FAILED
    assert result.comparison.pipeline_status == "failed"
    assert result.comparison.failure is not None
    assert result.comparison.failure["stage"] == "composition"
    assert result.comparison.quality_score_basis_points is None


async def test_batch_shadow_run_covers_full_fixture_set() -> None:
    report = await batch_shadow_run(
        argparse.Namespace(
            seeed_root=ROOT / "fixtures/seeed",
            kicad_root=ROOT / "fixtures/kicad",
            seeed_revision="a" * 40,
            kicad_revision="b" * 40,
            limit=15,
            kicad_file_limit=500,
        )
    )

    assert report["production_default_changed"] is False
    assert report["summary"] == {
        "total": 15,
        "succeeded": 14,
        "failed": 1,
        "conflicts": 18,
    }
    assert len(report["reports"]) == 15  # type: ignore[arg-type]


def test_pipeline_feature_flag_is_disabled_by_default_and_has_no_primary_mode() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
    )
    assert settings.import_pipeline_mode == "disabled"
    assert settings.import_pipeline_shadow_enabled is False

    with pytest.raises(ValidationError, match="import_pipeline_mode"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
            import_pipeline_mode="primary",
        )
