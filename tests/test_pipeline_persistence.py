"""Stage 10 persistence, idempotency and enrichment lifecycle tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from import_pipeline_helpers import STARTED_AT, SequenceClock, composition_input
from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ClauseElement

from arduino_component_kb.imports.pipeline import (
    DeterministicCardComposer,
    EnrichmentLifecycleRepository,
    EnrichmentLifecycleStatus,
    EnrichmentReviewCommand,
    EnrichmentReviewDecision,
    ImportPipelineContext,
    PipelinePersistenceInput,
    PipelineStage,
    PostgresImportPersistenceGateway,
)
from arduino_component_kb.imports.pipeline.errors import PersistenceError

SOURCE_ID = UUID("11111111-2222-4333-8444-555555555555")
COMPONENT_ID = UUID("22222222-3333-4444-8555-666666666666")
REVIEWER_ID = UUID("33333333-4444-4555-8666-777777777777")
DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]


def session_mock() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


async def persistence_input(
    file_name: str = "display_spi.md",
) -> tuple[ImportPipelineContext, PipelinePersistenceInput]:
    context, composition = await composition_input(file_name)
    composed = await DeterministicCardComposer(
        SequenceClock(
            STARTED_AT + timedelta(seconds=11),
            STARTED_AT + timedelta(seconds=12),
        )
    ).compose(context, composition)
    return composed.context, PipelinePersistenceInput(SOURCE_ID, composition, composed.value)


def sql(statement: ClauseElement) -> str:
    return str(statement.compile(dialect=DIALECT))


async def test_persistence_is_idempotent_and_keeps_all_matcher_decisions() -> None:
    context, value = await persistence_input()
    session = session_mock()
    gateway = PostgresImportPersistenceGateway(
        session,
        SequenceClock(
            STARTED_AT + timedelta(seconds=13),
            STARTED_AT + timedelta(seconds=14),
            STARTED_AT + timedelta(seconds=15),
            STARTED_AT + timedelta(seconds=16),
        ),
    )

    first = await gateway.persist(context, value)
    second = await gateway.persist(context, value)

    assert first.value == second.value
    assert first.stage is PipelineStage.PERSISTENCE
    assert first.context.next_stage is None
    assert len(first.value.enrichment_ids) == len(value.composition.enrichments)
    statements = [
        sql(cast(ClauseElement, call.args[0])) for call in session.execute.await_args_list
    ]
    assert all("ON CONFLICT DO NOTHING" in item for item in statements)
    assert sum("INSERT INTO import_pipeline_artifacts" in item for item in statements) == 2
    assert sum("INSERT INTO component_enrichments" in item for item in statements) == (
        2 * len(value.composition.enrichments)
    )


async def test_review_draft_identity_ignores_observational_composition_timestamp() -> None:
    _, value = await persistence_input()
    recomposed = PipelinePersistenceInput(
        value.source_id,
        value.composition,
        replace(value.draft, composed_at=value.draft.composed_at + timedelta(minutes=5)),
    )

    assert recomposed.artifact_id == value.artifact_id
    assert recomposed.review_draft_id == value.review_draft_id
    assert recomposed.draft.to_json() != value.draft.to_json()


async def test_persistence_rejects_wrong_stage_source_and_unbound_draft() -> None:
    context, value = await persistence_input()
    session = session_mock()
    gateway = PostgresImportPersistenceGateway(session)

    with pytest.raises(PersistenceError, match="persistence_stage_out_of_order"):
        await gateway.persist(replace(context, executions=context.executions[:-1]), value)
    with pytest.raises(PersistenceError, match="pipeline_source_mismatch"):
        await gateway.persist(replace(context, source_key="other_source"), value)
    with pytest.raises(ValueError, match="persistence_composition_input_mismatch"):
        PipelinePersistenceInput(
            SOURCE_ID,
            value.composition,
            replace(value.draft, input_sha256="0" * 64),
        )
    session.execute.assert_not_awaited()


async def test_revision_update_marks_only_enrichments_stale() -> None:
    session = session_mock()
    session.execute.return_value = SimpleNamespace(rowcount=3)
    repository = EnrichmentLifecycleRepository(session)

    affected = await repository.mark_stale("kicad", "c" * 40, STARTED_AT + timedelta(hours=1))

    assert affected == 3
    statement = cast(ClauseElement, session.execute.await_args.args[0])
    rendered = sql(statement)
    assert rendered.startswith("UPDATE component_enrichments")
    assert "import_pipeline_artifacts" not in rendered
    assert "components" not in rendered
    assert statement.compile(dialect=DIALECT).params["status"] == "stale"


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (EnrichmentReviewDecision.ACCEPT, EnrichmentLifecycleStatus.ACCEPTED),
        (EnrichmentReviewDecision.REJECT, EnrichmentLifecycleStatus.REJECTED),
    ],
)
async def test_human_review_updates_lifecycle_and_appends_audit(
    decision: EnrichmentReviewDecision,
    expected: EnrichmentLifecycleStatus,
) -> None:
    session = session_mock()
    selected = SimpleNamespace(scalar_one_or_none=lambda: "suggested")
    session.execute.side_effect = [selected, SimpleNamespace(), SimpleNamespace()]
    repository = EnrichmentLifecycleRepository(session)
    command = EnrichmentReviewCommand(
        UUID("44444444-5555-4666-8777-888888888888"),
        REVIEWER_ID,
        decision,
        "Evidence verified against the upstream symbol.",
        STARTED_AT + timedelta(hours=2),
    )

    result = await repository.review(command)

    assert result is expected
    statements = [
        sql(cast(ClauseElement, call.args[0])) for call in session.execute.await_args_list
    ]
    assert statements[0].startswith("SELECT component_enrichments.status")
    assert statements[1].startswith("UPDATE component_enrichments")
    assert statements[2].startswith("INSERT INTO component_enrichment_reviews")
    assert "ON CONFLICT DO NOTHING" in statements[2]
    session.flush.assert_awaited_once()


async def test_stale_enrichment_cannot_be_reviewed() -> None:
    session = session_mock()
    selected = SimpleNamespace(scalar_one_or_none=lambda: "stale")
    session.execute.return_value = selected
    repository = EnrichmentLifecycleRepository(session)
    command = EnrichmentReviewCommand(
        UUID("44444444-5555-4666-8777-888888888888"),
        REVIEWER_ID,
        EnrichmentReviewDecision.ACCEPT,
        "Would otherwise be accepted.",
        STARTED_AT,
    )

    with pytest.raises(PersistenceError, match="stale_enrichment_review_forbidden"):
        await repository.review(command)
    assert session.execute.await_count == 1


async def test_component_attachment_never_rewrites_snapshot_payloads() -> None:
    session = session_mock()
    repository = EnrichmentLifecycleRepository(session)

    await repository.attach_component(UUID("55555555-6666-4777-8888-999999999999"), COMPONENT_ID)

    statements = [
        sql(cast(ClauseElement, call.args[0])) for call in session.execute.await_args_list
    ]
    assert len(statements) == 3
    assert statements[0].startswith("UPDATE import_review_drafts")
    assert statements[1].startswith("UPDATE import_pipeline_artifacts")
    assert statements[2].startswith("UPDATE component_enrichments")
    assert all("payload=" not in item and "facts_payload=" not in item for item in statements)


def test_orm_schema_has_lifecycle_and_idempotency_guards() -> None:
    from arduino_component_kb.imports.persistence_models import (
        ComponentEnrichmentRecord,
        ComponentEnrichmentReviewRecord,
        ImportPipelineArtifact,
    )

    artifact_table = cast(Table, ImportPipelineArtifact.__table__)
    enrichment_table = cast(Table, ComponentEnrichmentRecord.__table__)
    assert {item.name for item in artifact_table.constraints} >= {
        "uq_import_artifacts_idempotency",
        "ck_import_artifacts_content_sha",
    }
    assert {item.name for item in enrichment_table.constraints} >= {
        "uq_component_enrichments_identity",
        "ck_component_enrichments_status",
        "ck_component_enrichments_review_pair",
    }
    assert "component_enrichment_reviews" == ComponentEnrichmentReviewRecord.__tablename__


def test_stage_10_downgrade_only_removes_new_parallel_tables() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations/versions/20260723_17_import_pipeline_persistence.py"
    ).read_text("utf-8")
    downgrade = migration.split("def downgrade() -> None:", maxsplit=1)[1]
    assert 'drop_table("components")' not in downgrade
    assert 'drop_table("component_sources")' not in downgrade
    assert 'drop_table("sources")' not in downgrade
    assert downgrade.count("op.drop_table(") == 6
