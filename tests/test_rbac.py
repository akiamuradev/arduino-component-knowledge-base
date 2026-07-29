"""Backend permission matrix, route dependency, and CSRF tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from arduino_component_kb.api.admin import administrator as user_administrator
from arduino_component_kb.api.catalog import (
    archiver,
    creator,
    publisher,
    reviewer,
    submitter,
    viewer,
)
from arduino_component_kb.api.catalog import (
    editor as component_editor,
)
from arduino_component_kb.api.dependencies import csrf_principal, require_permissions
from arduino_component_kb.api.duplicates import administrator as duplicate_reviewer
from arduino_component_kb.api.imports import editor as import_creator
from arduino_component_kb.api.jobs import administrator as jobs_administrator
from arduino_component_kb.api.media import media_editor
from arduino_component_kb.auth.domain import (
    Permission,
    Principal,
    Role,
    permissions_for_roles,
)
from arduino_component_kb.auth.service import token_hash

EDITOR_PERMISSIONS = frozenset(
    {
        Permission.COMPONENTS_VIEW,
        Permission.COMPONENTS_CREATE,
        Permission.COMPONENTS_EDIT,
        Permission.COMPONENTS_ARCHIVE,
        Permission.COMPONENTS_SUBMIT_FOR_REVIEW,
        Permission.IMPORTS_VIEW,
        Permission.IMPORTS_CREATE,
        Permission.IMPORTS_RETRY,
        Permission.IMPORTS_CANCEL,
    }
)
ROLE_MATRIX = {
    Role.STUDENT: frozenset({Permission.COMPONENTS_VIEW}),
    Role.TEACHER: frozenset(
        {
            Permission.COMPONENTS_VIEW,
            Permission.COMPONENTS_PROPOSE_CORRECTION,
        }
    ),
    Role.EDITOR: EDITOR_PERMISSIONS,
    Role.ADMINISTRATOR: frozenset(Permission),
}


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


@pytest.mark.parametrize(("role", "expected"), ROLE_MATRIX.items())
def test_role_permission_matrix_is_exact(
    role: Role,
    expected: frozenset[Permission],
) -> None:
    assert permissions_for_roles(frozenset({role})) == expected
    assert principal(role).permissions == expected


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("permission", list(Permission))
async def test_every_role_permission_pair_is_default_deny(
    role: Role,
    permission: Permission,
) -> None:
    actor = principal(role)
    dependency = require_permissions(permission)
    if permission in ROLE_MATRIX[role]:
        assert await dependency(actor) is actor
    else:
        with pytest.raises(HTTPException) as error:
            await dependency(actor)
        assert error.value.status_code == 403
        assert cast(object, error.value.detail) == {"code": "permission_denied"}


async def test_permission_dependency_requires_every_declared_capability() -> None:
    dependency = require_permissions(
        Permission.COMPONENTS_CREATE,
        Permission.COMPONENTS_PUBLISH,
    )
    administrator = principal(Role.ADMINISTRATOR)
    assert await dependency(administrator) is administrator
    with pytest.raises(HTTPException):
        await dependency(principal(Role.EDITOR))


def test_multiple_roles_receive_only_the_union_of_server_mapping() -> None:
    assert permissions_for_roles(frozenset({Role.TEACHER, Role.EDITOR})) == (
        EDITOR_PERMISSIONS | frozenset({Permission.COMPONENTS_PROPOSE_CORRECTION})
    )


async def test_csrf_is_bound_to_session_and_double_submit() -> None:
    actor = principal(Role.ADMINISTRATOR)
    assert await csrf_principal(actor, "csrf-value", "csrf-value") is actor
    with pytest.raises(HTTPException) as error:
        await csrf_principal(actor, "csrf-value", "different")
    assert error.value.status_code == 403


async def test_catalog_dependencies_separate_view_edit_publish_and_archive() -> None:
    student = principal(Role.STUDENT)
    teacher = principal(Role.TEACHER)
    editor = principal(Role.EDITOR)
    administrator = principal(Role.ADMINISTRATOR)

    assert await viewer(student) is student
    assert await viewer(teacher) is teacher
    assert await creator(editor) is editor
    assert await component_editor(editor) is editor
    assert await archiver(editor) is editor
    assert await submitter(editor) is editor
    assert await reviewer(administrator) is administrator
    assert await publisher(administrator) is administrator

    for dependency in (creator, component_editor, archiver, submitter, reviewer, publisher):
        with pytest.raises(HTTPException):
            await dependency(teacher)
    with pytest.raises(HTTPException):
        await reviewer(editor)
    with pytest.raises(HTTPException):
        await publisher(editor)


async def test_editor_can_upload_and_import_without_administrative_access() -> None:
    editor = principal(Role.EDITOR)
    assert await media_editor(editor) is editor
    assert await import_creator(editor) is editor
    for dependency in (
        jobs_administrator,
        duplicate_reviewer,
        user_administrator,
    ):
        with pytest.raises(HTTPException):
            await dependency(editor)


async def test_administrator_has_every_protected_dependency() -> None:
    administrator = principal(Role.ADMINISTRATOR)
    for dependency in (
        viewer,
        creator,
        component_editor,
        archiver,
        submitter,
        reviewer,
        publisher,
        media_editor,
        import_creator,
        jobs_administrator,
        duplicate_reviewer,
        user_administrator,
    ):
        assert await dependency(administrator) is administrator
