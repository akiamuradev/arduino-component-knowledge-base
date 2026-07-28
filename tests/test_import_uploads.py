"""Safe component upload presentation and cancellation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from arduino_component_kb.api.imports import (
    _display_status,
    _list_item,
    _owned_job,
)
from arduino_component_kb.auth.domain import Principal, Role
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
