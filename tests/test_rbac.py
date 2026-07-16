"""Backend RBAC and CSRF dependency tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from arduino_component_kb.api.dependencies import csrf_principal, require_roles
from arduino_component_kb.api.duplicates import administrator as duplicate_administrator
from arduino_component_kb.api.imports import editor as import_editor
from arduino_component_kb.api.jobs import administrator as jobs_administrator
from arduino_component_kb.api.media import media_editor
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.service import token_hash


def principal(*roles: Role) -> Principal:
    return Principal(
        user_id=uuid4(),
        login="user",
        display_name="User",
        roles=frozenset(roles),
        session_id=uuid4(),
        csrf_hash=token_hash("csrf-value"),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def test_administrator_dependency_accepts_only_administrator() -> None:
    dependency = require_roles(Role.ADMINISTRATOR)
    admin = principal(Role.ADMINISTRATOR)
    assert await dependency(admin) is admin
    with pytest.raises(HTTPException) as error:
        await dependency(principal(Role.TEACHER))
    assert error.value.status_code == 403


async def test_csrf_is_bound_to_session_and_double_submit() -> None:
    actor = principal(Role.ADMINISTRATOR)
    assert await csrf_principal(actor, "csrf-value", "csrf-value") is actor
    with pytest.raises(HTTPException) as error:
        await csrf_principal(actor, "csrf-value", "different")
    assert error.value.status_code == 403


async def test_media_upload_dependency_rejects_student() -> None:
    teacher = principal(Role.TEACHER)
    assert await media_editor(teacher) is teacher
    with pytest.raises(HTTPException) as error:
        await media_editor(principal(Role.STUDENT))
    assert error.value.status_code == 403


async def test_job_monitor_dependency_rejects_teacher() -> None:
    admin = principal(Role.ADMINISTRATOR)
    assert await jobs_administrator(admin) is admin
    with pytest.raises(HTTPException) as error:
        await jobs_administrator(principal(Role.TEACHER))
    assert error.value.status_code == 403


async def test_duplicate_review_dependency_rejects_teacher() -> None:
    admin = principal(Role.ADMINISTRATOR)
    assert await duplicate_administrator(admin) is admin
    with pytest.raises(HTTPException) as error:
        await duplicate_administrator(principal(Role.TEACHER))
    assert error.value.status_code == 403


async def test_import_dependency_accepts_teacher_and_rejects_student() -> None:
    teacher = principal(Role.TEACHER)
    assert await import_editor(teacher) is teacher
    with pytest.raises(HTTPException) as error:
        await import_editor(principal(Role.STUDENT))
    assert error.value.status_code == 403
