"""End-to-end acceptance of the supported ACKB 0.21.0 to 1.0.0 upgrade."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.main import create_app
from arduino_component_kb.media.storage import MediaStorage

pytestmark = pytest.mark.integration

ADMIN_ID = UUID("22000000-0000-4000-8000-000000000001")
STUDENT_ID = UUID("22000000-0000-4000-8000-000000000002")
COMPONENT_ID = UUID("22000000-0000-4000-8000-000000000003")
REVISION_ID = UUID("22000000-0000-4000-8000-000000000004")
IMPORT_ID = UUID("22000000-0000-4000-8000-000000000005")
AUDIT_ID = UUID("22000000-0000-4000-8000-000000000006")
SENSORS_CATEGORY_ID = UUID("00000000-0000-4000-8000-000000000002")
ADMIN_PASSWORD = "upgrade-administrator-passphrase"  # noqa: S105 - disposable test identity
STUDENT_PASSWORD = "upgrade-student-passphrase"  # noqa: S105 - disposable test identity
EDITOR_PASSWORD = "upgrade-editor-passphrase"  # noqa: S105 - disposable test identity


def _database_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)


async def _create_database(base_url: URL, database_name: str) -> None:
    engine = create_async_engine(_database_url(base_url.set(database="postgres")))
    try:
        async with engine.connect() as raw_connection:
            connection = await raw_connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await engine.dispose()


async def _drop_database(base_url: URL, database_name: str) -> None:
    engine = create_async_engine(_database_url(base_url.set(database="postgres")))
    try:
        async with engine.connect() as raw_connection:
            connection = await raw_connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
    finally:
        await engine.dispose()


def _upgrade(database_url: str, revision: str, monkeypatch: MonkeyPatch) -> None:
    with monkeypatch.context() as environment:
        environment.setenv("ACKB_DATABASE_URL", database_url)
        command.upgrade(Config("alembic.ini"), revision)


async def _seed_previous_release(database_url: str) -> None:
    """Insert data using only columns available at the tagged 0.21.0 head."""
    engine = create_async_engine(database_url)
    now = datetime(2026, 7, 21, tzinfo=UTC)
    password_manager = PasswordManager()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, display_name, password_hash, status, created_at, updated_at
                    ) VALUES
                    (
                        :admin_id, 'upgrade-api-administrator', 'Upgrade API Administrator',
                        :admin_hash, 'active', :now, :now
                    ),
                    (
                        :student_id, 'upgrade-api-student', 'Upgrade API Student',
                        :student_hash, 'active', :now, :now
                    )
                    """
                ),
                {
                    "admin_id": ADMIN_ID,
                    "student_id": STUDENT_ID,
                    "admin_hash": password_manager.hash(ADMIN_PASSWORD),
                    "student_hash": password_manager.hash(STUDENT_PASSWORD),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO user_roles (user_id, role, granted_by, granted_at)
                    VALUES
                        (:admin_id, 'administrator', NULL, :now),
                        (:student_id, 'student', :admin_id, :now)
                    """
                ),
                {"admin_id": ADMIN_ID, "student_id": STUDENT_ID, "now": now},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO components (
                        id, slug, status, title, manufacturer, model,
                        normalized_manufacturer, normalized_model, summary, description,
                        difficulty, primary_category_id, manual_original, created_by, updated_by,
                        created_at, updated_at, revision
                    ) VALUES (
                        :component_id, 'upgrade-api-preserved', 'draft',
                        'Upgrade API preserved component', 'ACKB', 'API-021',
                        'ackb', 'api021',
                        'A component retained from the previous ACKB release.',
                        'The upgrade acceptance test verifies this exact card and its history.',
                        'beginner', :category_id, true, :admin_id, :admin_id, :now, :now, 1
                    )
                    """
                ),
                {
                    "component_id": COMPONENT_ID,
                    "category_id": SENSORS_CATEGORY_ID,
                    "admin_id": ADMIN_ID,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO component_revisions (
                        id, component_id, revision, status, content_json, actor_id, created_at
                    ) VALUES (
                        :revision_id, :component_id, 1, 'draft',
                        CAST(:content AS jsonb), :admin_id, :now
                    )
                    """
                ),
                {
                    "revision_id": REVISION_ID,
                    "component_id": COMPONENT_ID,
                    "content": (
                        '{"source":"ackb-0.21.0","title":"Upgrade API preserved component"}'
                    ),
                    "admin_id": ADMIN_ID,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO import_jobs (
                        id, source_id, submitted_url, canonical_url, status, requested_by,
                        idempotency_key, attempts, max_attempts, parser_version,
                        draft_component_id, created_at, started_at, finished_at, updated_at,
                        repository_url, requested_revision, source_revision, source_file_path,
                        parser_name, parse_status, warnings_json, heartbeat_at, metrics_json
                    ) VALUES (
                        :import_id, (SELECT id FROM sources WHERE key='seeed_wiki'),
                        'https://github.com/Seeed-Studio/wiki-documents',
                        'https://github.com/Seeed-Studio/wiki-documents',
                        'succeeded', :admin_id, 'upgrade-api-preserved-import', 1, 4, '1.1.0',
                        :component_id, :now, :now, :finished,
                        :finished, 'https://github.com/Seeed-Studio/wiki-documents', 'master',
                        '0123456789abcdef0123456789abcdef01234567',
                        'docs/Sensor/Upgrade.md', 'seeed-wiki-git-v1', 'parsed',
                        CAST('[]' AS jsonb), :now, CAST(:metrics AS jsonb)
                    )
                    """
                ),
                {
                    "import_id": IMPORT_ID,
                    "admin_id": ADMIN_ID,
                    "component_id": COMPONENT_ID,
                    "now": now,
                    "finished": now + timedelta(minutes=1),
                    "metrics": '{"items":1}',
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, occurred_at, actor_user_id, actor_type, action, object_type,
                        object_id, request_id, outcome, details_safe_json
                    ) VALUES (
                        :audit_id, :now, :admin_id, 'user', 'upgrade.fixture_created',
                        'component', :component_id, 'upgrade-api-0.21.0', 'success',
                        CAST('{"source":"release-upgrade-acceptance"}' AS jsonb)
                    )
                    """
                ),
                {
                    "audit_id": AUDIT_ID,
                    "now": now,
                    "admin_id": ADMIN_ID,
                    "component_id": COMPONENT_ID,
                },
            )
    finally:
        await engine.dispose()


async def _assert_migrated_data(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "20260729_27"
            )
            users = await connection.scalar(
                text("SELECT count(*) FROM users WHERE id IN (:admin_id, :student_id)"),
                {"admin_id": ADMIN_ID, "student_id": STUDENT_ID},
            )
            roles = await connection.scalar(
                text(
                    """
                    SELECT count(*) FROM user_roles
                    WHERE user_id IN (:admin_id, :student_id)
                      AND revoked_at IS NULL
                    """
                ),
                {"admin_id": ADMIN_ID, "student_id": STUDENT_ID},
            )
            card = (
                await connection.execute(
                    text(
                        """
                        SELECT title, status, revision
                        FROM components
                        WHERE id=:component_id
                        """
                    ),
                    {"component_id": COMPONENT_ID},
                )
            ).one()
            history = (
                await connection.execute(
                    text(
                        """
                        SELECT status, action, change_summary, content_json->>'source'
                        FROM component_revisions
                        WHERE id=:revision_id
                        """
                    ),
                    {"revision_id": REVISION_ID},
                )
            ).one()
            import_job = (
                await connection.execute(
                    text(
                        """
                        SELECT status, draft_component_id, source_file_path
                        FROM import_jobs
                        WHERE id=:import_id
                        """
                    ),
                    {"import_id": IMPORT_ID},
                )
            ).one()
            audit_action = await connection.scalar(
                text("SELECT action FROM audit_events WHERE id=:audit_id"),
                {"audit_id": AUDIT_ID},
            )
            assert users == 2
            assert roles == 2
            assert tuple(card) == ("Upgrade API preserved component", "draft", 1)
            assert tuple(history) == (
                "draft",
                "component.created",
                "Карточка создана",
                "ackb-0.21.0",
            )
            assert tuple(import_job) == (
                "succeeded",
                COMPONENT_ID,
                "docs/Sensor/Upgrade.md",
            )
            assert audit_action == "upgrade.fixture_created"
    finally:
        await engine.dispose()


async def _attach_ready_image(database_url: str, component_id: UUID, owner_id: UUID) -> None:
    """Attach a deterministic processed image without involving an external object store."""
    engine = create_async_engine(database_url)
    asset_id = uuid4()
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO media_assets (
                        id, owner_user_id, component_id, kind, purpose, alt_text, caption,
                        display_order, is_primary, attribution, status, bucket, object_key,
                        declared_mime, declared_size_bytes, detected_mime, size_bytes,
                        sha256, phash, width, height, upload_expires_at, created_at, updated_at
                    ) VALUES (
                        :asset_id, :owner_id, :component_id, 'image', 'product',
                        'Release upgrade acceptance image', NULL, 0, true, NULL, 'ready',
                        'ackb-test-variants', :asset_key, 'image/png', 128, 'image/png', 128,
                        :asset_sha, '0123456789abcdef', 640, 480, :expires_at, :now, :now
                    )
                    """
                ),
                {
                    "asset_id": asset_id,
                    "owner_id": owner_id,
                    "component_id": component_id,
                    "asset_key": f"release-upgrade/{asset_id}.png",
                    "asset_sha": "1" * 64,
                    "expires_at": now + timedelta(hours=1),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO media_variants (
                        id, asset_id, variant, bucket, object_key, mime,
                        size_bytes, sha256, width, height
                    ) VALUES (
                        :variant_id, :asset_id, '320w', 'ackb-test-variants',
                        :variant_key, 'image/webp', 64, :variant_sha, 320, 240
                    )
                    """
                ),
                {
                    "variant_id": uuid4(),
                    "asset_id": asset_id,
                    "variant_key": f"release-upgrade/{asset_id}/320w.webp",
                    "variant_sha": "2" * 64,
                },
            )
    finally:
        await engine.dispose()


def _component_payload(suffix: str) -> dict[str, object]:
    return {
        "slug": f"upgrade-editor-card-{suffix}",
        "title": "Upgrade editor acceptance card",
        "aliases": [],
        "manufacturer": "ACKB",
        "model": f"RELEASE-{suffix}",
        "primary_category_id": str(SENSORS_CATEGORY_ID),
        "tags": ["release-upgrade"],
        "summary": "A card created by a temporary editor after the release upgrade.",
        "description": "This card proves the post-upgrade editorial workflow.",
        "purpose": "Release acceptance",
        "usage_notes": None,
        "safety_notes": None,
        "difficulty": "beginner",
        "teacher_notes": None,
        "manual_original": True,
        "specifications": [],
        "compatibility": [],
        "code_examples": [],
    }


def test_release_upgrade_preserves_data_and_supports_critical_api_flows(
    integration_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    """Prove preserved identities can immediately use all release-critical workflows."""
    base_url = make_url(integration_settings.database_url)
    database_name = f"ackb_release_upgrade_{uuid4().hex[:12]}"
    database_url = _database_url(base_url.set(database=database_name))
    asyncio.run(_create_database(base_url, database_name))
    try:
        _upgrade(database_url, "20260721_16", monkeypatch)
        asyncio.run(_seed_previous_release(database_url))
        _upgrade(database_url, "head", monkeypatch)
        asyncio.run(_assert_migrated_data(database_url))

        settings = Settings(
            _env_file=None,
            environment="test",
            database_url=database_url,
            session_cookie_secure=False,
        )
        database = Database(settings)
        media_storage = Mock(spec=MediaStorage)
        media_storage.presigned_get = AsyncMock(
            return_value="https://storage.invalid/release-upgrade.webp"
        )
        app = create_app(
            settings,
            database,
            media_storage=media_storage,
            media_queue=Mock(),
            import_queue=Mock(),
        )
        suffix = uuid4().hex[:10]
        editor_login = f"upgrade-editor-{suffix}"

        with TestClient(app, base_url="http://testserver") as client:
            admin_login = client.post(
                "/api/v1/auth/login",
                json={
                    "login": "upgrade-api-administrator",
                    "password": ADMIN_PASSWORD,
                },
            )
            assert admin_login.status_code == 200
            assert admin_login.json()["user"]["roles"] == ["administrator"]
            admin_csrf = client.cookies.get("ackb_csrf")
            assert admin_csrf is not None
            admin_cookies = dict(client.cookies.items())

            imports = client.get("/api/v1/import-jobs")
            assert imports.status_code == 200
            assert any(item["id"] == str(IMPORT_ID) for item in imports.json()["items"])

            client.cookies.clear()
            student_login = client.post(
                "/api/v1/auth/login",
                json={"login": "upgrade-api-student", "password": STUDENT_PASSWORD},
            )
            assert student_login.status_code == 200
            assert student_login.json()["user"]["roles"] == ["student"]
            assert student_login.json()["user"]["permissions"] == ["components.view"]

            client.cookies.clear()
            client.cookies.update(admin_cookies)
            editor_expiry = datetime.now(UTC) + timedelta(days=7)
            created_editor = client.post(
                "/api/v1/admin/users/editors",
                headers={"X-CSRF-Token": admin_csrf},
                json={
                    "login": editor_login,
                    "display_name": "Upgrade Temporary Editor",
                    "password": EDITOR_PASSWORD,
                    "editor_expires_at": editor_expiry.isoformat(),
                },
            )
            assert created_editor.status_code == 201
            assert set(created_editor.json()["roles"]) == {"student", "editor"}

            client.cookies.clear()
            editor_login_response = client.post(
                "/api/v1/auth/login",
                json={"login": editor_login, "password": EDITOR_PASSWORD},
            )
            assert editor_login_response.status_code == 200
            assert set(editor_login_response.json()["user"]["roles"]) == {
                "student",
                "editor",
            }
            editor_csrf = client.cookies.get("ackb_csrf")
            assert editor_csrf is not None

            submitted_import = client.post(
                "/api/v1/import-jobs/repository",
                headers={
                    "X-CSRF-Token": editor_csrf,
                    "Idempotency-Key": f"upgrade-import-{suffix}",
                },
                json={
                    "source_key": "seeed_wiki",
                    "revision": "0123456789abcdef0123456789abcdef01234567",
                    "file_path": "docs/Sensor/UpgradeAcceptance.md",
                    "entry_name": None,
                },
            )
            assert submitted_import.status_code == 202
            assert submitted_import.json()["status"] == "queued"

            created_card = client.post(
                "/api/v1/workspace/components",
                headers={"X-CSRF-Token": editor_csrf},
                json=_component_payload(suffix),
            )
            assert created_card.status_code == 201
            component_id = created_card.json()["id"]
            asyncio.run(
                _attach_ready_image(
                    database_url,
                    UUID(component_id),
                    UUID(created_editor.json()["id"]),
                )
            )
            submitted_card = client.post(
                f"/api/v1/workspace/components/{component_id}/submit-for-review",
                headers={"X-CSRF-Token": editor_csrf},
                json={"revision": created_card.json()["revision"]},
            )
            assert submitted_card.status_code == 200
            assert submitted_card.json()["status"] == "in_review"

            client.cookies.clear()
            client.cookies.update(admin_cookies)
            approved = client.post(
                f"/api/v1/workspace/components/{component_id}/approve",
                headers={"X-CSRF-Token": admin_csrf},
                json={"revision": submitted_card.json()["revision"]},
            )
            assert approved.status_code == 200
            published = client.post(
                f"/api/v1/workspace/components/{component_id}/publish",
                headers={"X-CSRF-Token": admin_csrf},
                json={"revision": approved.json()["revision"]},
            )
            assert published.status_code == 200
            assert published.json()["status"] == "published"

            public_card = client.get(
                f"/api/v1/catalog/components/{_component_payload(suffix)['slug']}"
            )
            assert public_card.status_code == 200
            assert public_card.json()["id"] == component_id
    finally:
        asyncio.run(_drop_database(base_url, database_name))
