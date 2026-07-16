"""Critical HTTP authentication flow against an Alembic-managed PostgreSQL schema."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from arduino_component_kb.auth.domain import Role
from arduino_component_kb.auth.models import AuditEvent, User
from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.main import create_app

pytestmark = pytest.mark.integration

ADMIN_CREDENTIAL = "integration-admin-passphrase"
STUDENT_CREDENTIAL = "integration-student-passphrase"


async def seed_administrator(settings: Settings, login: str) -> UUID:
    database = Database(settings)
    try:
        async with database.sessions() as session, session.begin():
            repository = AuthRepository(session)
            now = datetime.now(UTC)
            user = await repository.create_user(
                login=login,
                display_name="Integration Administrator",
                password_hash=PasswordManager().hash(ADMIN_CREDENTIAL),
                roles=frozenset({Role.ADMINISTRATOR}),
                actor_id=None,
                now=now,
            )
            return user.id
    finally:
        await database.dispose()


async def remove_test_identities(settings: Settings, user_ids: set[UUID]) -> None:
    database = Database(settings)
    try:
        async with database.sessions() as session, session.begin():
            await session.execute(
                delete(AuditEvent).where(
                    (AuditEvent.actor_user_id.in_(user_ids)) | (AuditEvent.object_id.in_(user_ids))
                )
            )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
    finally:
        await database.dispose()


async def assert_migrated_schema(settings: Settings) -> None:
    database = Database(settings)
    try:
        async with database.engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            tables = await connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            assert revision is not None
            assert {"users", "auth_sessions", "audit_events", "components"}.issubset(set(tables))
    finally:
        await database.dispose()


def test_real_postgresql_login_rbac_csrf_and_logout(integration_settings: Settings) -> None:
    """Prove the backend, not the browser, controls administrator mutations."""
    import asyncio

    suffix = uuid4().hex[:12]
    admin_login = f"integration-admin-{suffix}"
    student_login = f"integration-student-{suffix}"
    admin_id = asyncio.run(seed_administrator(integration_settings, admin_login))
    created_ids = {admin_id}
    database = Database(integration_settings)
    app = create_app(
        integration_settings,
        database,
        media_storage=Mock(),
        media_queue=Mock(),
        import_queue=Mock(),
    )
    try:
        asyncio.run(assert_migrated_schema(integration_settings))
        with TestClient(app, base_url="http://testserver") as administrator:
            login = administrator.post(
                "/api/v1/auth/login",
                json={"login": admin_login, "password": ADMIN_CREDENTIAL},
            )
            assert login.status_code == 200
            csrf = administrator.cookies.get("ackb_csrf")
            assert csrf is not None

            missing_csrf = administrator.post(
                "/api/v1/admin/users",
                json={
                    "login": student_login,
                    "display_name": "Integration Student",
                    "password": STUDENT_CREDENTIAL,
                    "roles": ["student"],
                },
            )
            assert missing_csrf.status_code == 403
            assert missing_csrf.json()["detail"]["code"] == "csrf_validation_failed"

            created = administrator.post(
                "/api/v1/admin/users",
                headers={"X-CSRF-Token": csrf},
                json={
                    "login": student_login,
                    "display_name": "Integration Student",
                    "password": STUDENT_CREDENTIAL,
                    "roles": ["student"],
                },
            )
            assert created.status_code == 201
            student_id = UUID(created.json()["id"])
            created_ids.add(student_id)

            logout = administrator.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
            assert logout.status_code == 200
            assert administrator.get("/api/v1/auth/me").status_code == 401

        with TestClient(app, base_url="http://testserver") as student:
            assert (
                student.post(
                    "/api/v1/auth/login",
                    json={"login": student_login, "password": STUDENT_CREDENTIAL},
                ).status_code
                == 200
            )
            student_csrf = student.cookies.get("ackb_csrf")
            assert student_csrf is not None
            forbidden = student.post(
                "/api/v1/admin/users",
                headers={"X-CSRF-Token": student_csrf},
                json={
                    "login": f"forbidden-{suffix}",
                    "display_name": "Must Not Exist",
                    "password": STUDENT_CREDENTIAL,
                    "roles": ["student"],
                },
            )
            assert forbidden.status_code == 403
            assert forbidden.json()["detail"]["code"] == "permission_denied"
    finally:
        asyncio.run(remove_test_identities(integration_settings, created_ids))


async def test_postgresql_rejects_duplicate_normalized_login(
    integration_settings: Settings,
) -> None:
    """Exercise a real database uniqueness constraint, not a mocked repository."""
    database = Database(integration_settings)
    login = f"unique-{uuid4().hex}"
    first_id: UUID | None = None
    try:
        now = datetime.now(UTC)
        async with database.sessions() as session, session.begin():
            repository = AuthRepository(session)
            first = await repository.create_user(
                login=login,
                display_name="First",
                password_hash=PasswordManager().hash(ADMIN_CREDENTIAL),
                roles=frozenset({Role.STUDENT}),
                actor_id=None,
                now=now,
            )
            first_id = first.id
        async with database.sessions() as session:
            assert await session.scalar(select(User.id).where(User.login == login)) == first_id
        with pytest.raises(IntegrityError):
            async with database.sessions() as session, session.begin():
                duplicate = AuthRepository(session)
                await duplicate.create_user(
                    login=login,
                    display_name="Duplicate",
                    password_hash=PasswordManager().hash(ADMIN_CREDENTIAL),
                    roles=frozenset({Role.STUDENT}),
                    actor_id=None,
                    now=now,
                )
    finally:
        if first_id is not None:
            async with database.sessions() as session, session.begin():
                await session.execute(delete(User).where(User.id == first_id))
        await database.dispose()
