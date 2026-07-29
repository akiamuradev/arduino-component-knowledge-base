"""Safe component upload presentation and cancellation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.imports import (
    RepositoryImportRequest,
    _admit_submission,
    _display_status,
    _list_item,
    _owned_job,
    _response,
    _validated_entry,
)
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.imports.processor import _mark_failed
from arduino_component_kb.imports.repository import ImportRepository


def import_job(status: str = "queued") -> ImportJob:
    now = datetime.now(UTC)
    return ImportJob(
        id=uuid4(),
        source_id=uuid4(),
        submitted_url="https://example.test/component",
        status=status,
        requested_by=uuid4(),
        idempotency_key="upload-test",
        attempts=0,
        max_attempts=4,
        error_code="internal_parser_failure" if status == "failed" else None,
        created_at=now,
        updated_at=now,
        repository_url="https://example.test/repository",
        source_file_path="components/Sensor.md",
        source_entry_name=None,
        warnings_json=[],
        metrics_json={"internal": "must-not-leak"},
    )


def principal(role: Role, user_id: UUID) -> Principal:
    return Principal(
        user_id=user_id,
        login=role.value,
        display_name=role.value,
        roles=frozenset({role}),
        session_id=uuid4(),
        csrf_hash="csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


@pytest.mark.parametrize(
    ("status", "component_status", "parse_status", "expected"),
    [
        ("queued", None, None, "pending"),
        ("retrying", None, None, "pending"),
        ("running", None, None, "processing"),
        ("failed", None, None, "error"),
        ("cancelled", None, None, "cancelled"),
        ("succeeded", "draft", "parsed", "ready"),
        ("succeeded", "draft", "parsed_with_warnings", "needs_review"),
        ("succeeded", "in_review", "parsed", "needs_review"),
        ("succeeded", "published", "parsed_with_warnings", "published"),
    ],
)
def test_import_states_are_mapped_to_product_language(
    status: str,
    component_status: str | None,
    parse_status: str | None,
    expected: str,
) -> None:
    job = import_job(status)
    job.parse_status = parse_status
    assert _display_status(job, component_status) == expected


def test_safe_import_item_excludes_internal_processing_details() -> None:
    job = import_job("failed")
    response = _list_item(
        job,
        "База знаний",
        "Редактор",
        None,
        can_retry=True,
        can_cancel=False,
    ).model_dump(mode="json")

    assert response["title"] == "Sensor"
    assert response["status"] == "error"
    assert response["result"] == "Компонент не удалось обработать"
    for internal_field in (
        "error_code",
        "parser_name",
        "parser_version",
        "metrics_json",
        "attempts",
        "heartbeat_at",
    ):
        assert internal_field not in response


def test_editor_job_response_masks_internal_failure_details() -> None:
    job = import_job("failed")

    safe = _response(job).model_dump(mode="json")
    diagnostic = _response(job, include_diagnostics=True).model_dump(mode="json")

    assert safe["error_code"] == "import_processing_failed"
    assert safe["metrics_json"] == {}
    assert safe["heartbeat_at"] is None
    assert diagnostic["error_code"] == "internal_parser_failure"
    assert diagnostic["metrics_json"] == {"internal": "must-not-leak"}


def test_cancellation_is_terminal_and_preserved_by_failure_handling() -> None:
    job = import_job()
    cancelled_at = datetime.now(UTC)

    ImportRepository.cancel(job, cancelled_at)
    _mark_failed(job, "must_not_replace_cancellation")

    assert job.status == "cancelled"
    assert job.error_code is None
    assert job.finished_at == cancelled_at
    with pytest.raises(ValueError, match="import_not_cancellable"):
        ImportRepository.cancel(job, cancelled_at)


@pytest.mark.asyncio
async def test_foreign_editor_cannot_act_on_another_users_import() -> None:
    job = import_job("failed")
    repository = Mock(spec=ImportRepository)
    repository.get_job = AsyncMock(return_value=job)
    actor = principal(Role.EDITOR, uuid4())

    with pytest.raises(HTTPException) as captured:
        await _owned_job(job.id, actor, repository)

    assert captured.value.status_code == 404
    assert cast(object, captured.value.detail) == {"code": "import_job_not_found"}


@pytest.mark.asyncio
async def test_administrator_can_act_on_any_import() -> None:
    job = import_job("failed")
    repository = Mock(spec=ImportRepository)
    repository.get_job = AsyncMock(return_value=job)
    actor = principal(Role.ADMINISTRATOR, uuid4())

    assert await _owned_job(job.id, actor, repository) is job


@pytest.mark.parametrize(
    ("source_key", "file_path"),
    [
        ("seeed_wiki", "../secret.md"),
        ("seeed_wiki", "components//Sensor.md"),
        ("seeed_wiki", "components/Sensor\x00.md"),
        ("seeed_wiki", "components/Sensor.png"),
        ("kicad_symbols", "Sensor_Temperature.md"),
    ],
)
def test_repository_upload_rejects_unsafe_paths_and_file_types(
    source_key: str, file_path: str
) -> None:
    payload = RepositoryImportRequest(
        source_key=cast(Literal["seeed_wiki", "kicad_symbols"], source_key),
        revision="main",
        file_path=file_path,
        entry_name="Sensor" if source_key == "kicad_symbols" else None,
    )

    with pytest.raises(HTTPException) as captured:
        _validated_entry(payload)

    assert captured.value.status_code == 422
    assert cast(dict[str, str], captured.value.detail)["code"] in {
        "repository_path_invalid",
        "repository_path_outside_snapshot",
        "repository_file_type_not_allowed",
    }


@pytest.mark.asyncio
async def test_idempotent_import_replay_bypasses_submission_limits() -> None:
    job = import_job()
    repository = Mock(spec=ImportRepository)
    repository.lock_submissions = AsyncMock()
    repository.get_idempotent_job = AsyncMock(return_value=job)
    repository.count_recent_submissions = AsyncMock()
    repository.count_active = AsyncMock()
    session = Mock(spec=AsyncSession)
    actor = principal(Role.EDITOR, job.requested_by)

    result = await _admit_submission(
        repository,
        cast(AsyncSession, session),
        actor,
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        ),
        job.idempotency_key,
    )

    assert result is job
    repository.count_recent_submissions.assert_not_awaited()
    repository.count_active.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_rate_limit_is_safe_audited_and_returns_retry_after() -> None:
    repository = Mock(spec=ImportRepository)
    repository.lock_submissions = AsyncMock()
    repository.get_idempotent_job = AsyncMock(return_value=None)
    repository.count_recent_submissions = AsyncMock(return_value=10)
    repository.count_active = AsyncMock()
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock()
    actor = principal(Role.EDITOR, uuid4())
    configured = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        import_submission_rate_limit=10,
        import_submission_rate_window_seconds=60,
    )

    with pytest.raises(HTTPException) as captured:
        await _admit_submission(
            repository,
            cast(AsyncSession, session),
            actor,
            configured,
            "new-request",
        )

    assert captured.value.status_code == 429
    assert cast(dict[str, str], captured.value.detail) == {"code": "import_rate_limited"}
    assert captured.value.headers == {"Retry-After": "60"}
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    repository.count_active.assert_not_awaited()


@pytest.mark.parametrize(
    ("active_counts", "expected_code"),
    [
        ([5], "import_pending_quota_exceeded"),
        ([0, 100], "import_global_pending_quota_exceeded"),
    ],
)
@pytest.mark.asyncio
async def test_import_active_quotas_are_checked_under_submission_lock(
    active_counts: list[int], expected_code: str
) -> None:
    repository = Mock(spec=ImportRepository)
    repository.lock_submissions = AsyncMock()
    repository.get_idempotent_job = AsyncMock(return_value=None)
    repository.count_recent_submissions = AsyncMock(return_value=0)
    repository.count_active = AsyncMock(side_effect=active_counts)
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock()
    actor = principal(Role.EDITOR, uuid4())
    configured = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        import_pending_job_limit=5,
        import_global_pending_job_limit=100,
    )

    with pytest.raises(HTTPException) as captured:
        await _admit_submission(
            repository,
            cast(AsyncSession, session),
            actor,
            configured,
            "new-request",
        )

    assert cast(dict[str, str], captured.value.detail) == {"code": expected_code}
    repository.lock_submissions.assert_awaited_once()
    session.commit.assert_awaited_once()
