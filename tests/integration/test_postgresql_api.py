"""Critical HTTP authentication flow against an Alembic-managed PostgreSQL schema."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from arduino_component_kb.auth.domain import Permission, Role, permissions_for_roles
from arduino_component_kb.auth.models import AuditEvent, User, UserRole
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
            assert {
                "users",
                "auth_sessions",
                "audit_events",
                "components",
                "import_pipeline_artifacts",
                "component_identity_candidates",
                "parser_evaluations",
                "import_review_drafts",
                "import_review_states",
                "import_review_actions",
                "component_enrichments",
                "component_enrichment_reviews",
            }.issubset(set(tables))
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
            assert login.json()["user"]["roles"] == ["administrator"]
            assert login.json()["user"]["permissions"] == sorted(
                permission.value
                for permission in permissions_for_roles(frozenset({Role.ADMINISTRATOR}))
            )
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
            assert missing_csrf.json()["error"]["code"] == "csrf_validation_failed"

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
            spoofed_login = student.post(
                "/api/v1/auth/login",
                json={
                    "login": student_login,
                    "password": STUDENT_CREDENTIAL,
                    "role": "administrator",
                },
            )
            assert spoofed_login.status_code == 422
            assert student.cookies.get("ackb_session") is None

            student_login_response = student.post(
                "/api/v1/auth/login",
                json={"login": student_login, "password": STUDENT_CREDENTIAL},
            )
            assert student_login_response.status_code == 200
            assert student_login_response.json()["user"]["roles"] == ["student"]
            assert student_login_response.json()["user"]["permissions"] == [
                Permission.COMPONENTS_VIEW.value
            ]
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
            assert forbidden.json()["error"]["code"] == "permission_denied"
    finally:
        asyncio.run(remove_test_identities(integration_settings, created_ids))


def test_temporary_editor_lifecycle_preserves_history_and_audit(
    integration_settings: Settings,
) -> None:
    """Exercise the bounded administrator workflow against real role grants."""
    import asyncio

    suffix = uuid4().hex[:12]
    admin_login = f"editor-admin-{suffix}"
    editor_login = f"temporary-editor-{suffix}"
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
    editor_id: UUID | None = None
    try:
        first_expiry = datetime.now(UTC) + timedelta(days=7)
        renewed_expiry = datetime.now(UTC) + timedelta(days=14)
        with TestClient(app, base_url="http://testserver") as administrator:
            login = administrator.post(
                "/api/v1/auth/login",
                json={"login": admin_login, "password": ADMIN_CREDENTIAL},
            )
            assert login.status_code == 200
            csrf = administrator.cookies.get("ackb_csrf")
            assert csrf is not None
            administrator_cookies = dict(administrator.cookies.items())

            created = administrator.post(
                "/api/v1/admin/users/editors",
                headers={"X-CSRF-Token": csrf},
                json={
                    "login": editor_login,
                    "display_name": "Temporary Editor",
                    "password": STUDENT_CREDENTIAL,
                    "editor_expires_at": first_expiry.isoformat(),
                },
            )
            assert created.status_code == 201
            assert set(created.json()["roles"]) == {"student", "editor"}
            assert Permission.USERS_MANAGE.value not in created.json()["permissions"]
            editor_id = UUID(created.json()["id"])
            created_ids.add(editor_id)

            listed = administrator.get("/api/v1/admin/users")
            assert listed.status_code == 200
            assert listed.headers["cache-control"] == "no-store"
            listed_editor = next(
                user for user in listed.json()["items"] if user["id"] == str(editor_id)
            )
            assert listed_editor["status"] == "active"
            assert set(listed_editor["roles"]) == {"student", "editor"}
            assert datetime.fromisoformat(listed_editor["editor_expires_at"]) == first_expiry

            administrator.cookies.clear()
            editor_login_response = administrator.post(
                "/api/v1/auth/login",
                json={"login": editor_login, "password": STUDENT_CREDENTIAL},
            )
            assert editor_login_response.status_code == 200
            assert (
                Permission.COMPONENTS_EDIT.value
                in editor_login_response.json()["user"]["permissions"]
            )
            assert (
                Permission.ROLES_ASSIGN.value
                not in editor_login_response.json()["user"]["permissions"]
            )
            editor_cookies = dict(administrator.cookies.items())

            administrator.cookies.clear()
            administrator.cookies.update(administrator_cookies)
            revoked = administrator.delete(
                f"/api/v1/admin/users/{editor_id}/editor",
                headers={"X-CSRF-Token": csrf},
            )
            assert revoked.status_code == 200

            administrator.cookies.clear()
            administrator.cookies.update(editor_cookies)
            assert administrator.get("/api/v1/auth/me").status_code == 401
            administrator.cookies.clear()
            baseline_login = administrator.post(
                "/api/v1/auth/login",
                json={"login": editor_login, "password": STUDENT_CREDENTIAL},
            )
            assert baseline_login.status_code == 200
            assert baseline_login.json()["user"]["roles"] == ["student"]
            assert baseline_login.json()["user"]["permissions"] == [
                Permission.COMPONENTS_VIEW.value
            ]
            baseline_cookies = dict(administrator.cookies.items())

            administrator.cookies.clear()
            administrator.cookies.update(administrator_cookies)
            granted = administrator.put(
                f"/api/v1/admin/users/{editor_id}/editor",
                headers={"X-CSRF-Token": csrf},
                json={"editor_expires_at": renewed_expiry.isoformat()},
            )
            assert granted.status_code == 200

            administrator.cookies.clear()
            administrator.cookies.update(baseline_cookies)
            assert administrator.get("/api/v1/auth/me").status_code == 401
            administrator.cookies.clear()
            administrator.cookies.update(administrator_cookies)

            disabled = administrator.post(
                f"/api/v1/admin/users/{editor_id}/disable",
                headers={"X-CSRF-Token": csrf},
            )
            assert disabled.status_code == 200
            blocked_login = administrator.post(
                "/api/v1/auth/login",
                json={"login": editor_login, "password": STUDENT_CREDENTIAL},
            )
            assert blocked_login.status_code == 401

            disabled_listing = administrator.get("/api/v1/admin/users")
            disabled_editor = next(
                user for user in disabled_listing.json()["items"] if user["id"] == str(editor_id)
            )
            assert disabled_editor["status"] == "disabled"

        async def assert_history() -> None:
            assert editor_id is not None
            async with database.sessions() as session:
                events = (
                    await session.scalars(
                        select(AuditEvent)
                        .where(AuditEvent.object_id == editor_id)
                        .order_by(AuditEvent.occurred_at)
                    )
                ).all()
                editor_grants = (
                    await session.scalars(
                        select(UserRole)
                        .where(
                            UserRole.user_id == editor_id,
                            UserRole.role == Role.EDITOR.value,
                        )
                        .order_by(UserRole.granted_at)
                    )
                ).all()
                assert {
                    "identity.user_created",
                    "identity.editor_revoked",
                    "identity.editor_granted",
                    "identity.user_disabled",
                }.issubset({event.action for event in events})
                assert len(editor_grants) == 2
                assert editor_grants[0].revoked_at is not None
                assert editor_grants[1].expires_at == renewed_expiry

        asyncio.run(assert_history())
    finally:
        asyncio.run(database.dispose())
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


async def test_expired_editor_grant_is_ignored_but_history_is_preserved(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    user_id: UUID | None = None
    try:
        granted_at = datetime.now(UTC) - timedelta(days=2)
        async with database.sessions() as session, session.begin():
            repository = AuthRepository(session)
            user = await repository.create_user(
                login=f"expired-editor-{uuid4().hex}",
                display_name="Expired editor",
                password_hash=PasswordManager().hash(ADMIN_CREDENTIAL),
                roles=frozenset({Role.STUDENT, Role.EDITOR}),
                actor_id=None,
                now=granted_at,
                editor_expires_at=granted_at + timedelta(days=1),
            )
            user_id = user.id

        async with database.sessions() as session:
            identity = await AuthRepository(session).find_user(user_id)
            grants = (
                await session.scalars(select(UserRole).where(UserRole.user_id == user_id))
            ).all()
            assert identity is not None
            assert identity.roles == frozenset({Role.STUDENT})
            assert permissions_for_roles(identity.roles) == frozenset({Permission.COMPONENTS_VIEW})
            assert {grant.role for grant in grants} == {"student", "editor"}
            editor_grant = next(grant for grant in grants if grant.role == "editor")
            assert editor_grant.expires_at is not None
            assert editor_grant.revoked_at is None
    finally:
        if user_id is not None:
            async with database.sessions() as session, session.begin():
                await session.execute(delete(User).where(User.id == user_id))
        await database.dispose()
