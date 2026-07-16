"""Shared isolated test configuration."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from arduino_component_kb.config import Settings

INTEGRATION_FLAG = "ACKB_RUN_INTEGRATION"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark real-service tests and require an explicit opt-in outside CI."""
    enabled = os.getenv(INTEGRATION_FLAG) == "1"
    for item in items:
        if "integration" not in item.path.parts:
            continue
        item.add_marker(pytest.mark.integration)
        if not enabled:
            item.add_marker(
                pytest.mark.skip(reason=f"set {INTEGRATION_FLAG}=1 to use real services")
            )


@pytest.fixture(autouse=True)
def isolated_auth_settings(monkeypatch: MonkeyPatch) -> None:
    """Provide a non-secret test-only pepper without reading a local .env."""
    monkeypatch.setenv("ACKB_AUTH_THROTTLE_PEPPER", "x" * 32)
    monkeypatch.setenv("ACKB_REDIS_URL", "redis://127.0.0.1:6379/15")
    monkeypatch.setenv("ACKB_MINIO_ENDPOINT", "127.0.0.1:9000")
    monkeypatch.setenv("ACKB_MINIO_ACCESS_KEY", "test-access")
    monkeypatch.setenv("ACKB_MINIO_SECRET_KEY", "test-secret-placeholder")
    monkeypatch.setenv("ACKB_MINIO_SECURE", "false")


@pytest.fixture
def fixture_html() -> bytes:
    """Return the versioned first-source fixture without network access."""
    return (Path(__file__).parent / "fixtures" / "arduino_tex" / "ky_023.html").read_bytes()


@pytest.fixture
def integration_settings(monkeypatch: MonkeyPatch) -> Iterator[Settings]:
    """Load non-production credentials dedicated to disposable test services."""
    database_url = os.getenv("ACKB_DATABASE_URL")
    if database_url is None:
        pytest.fail("ACKB_DATABASE_URL is required when integration tests are enabled")
    monkeypatch.setenv("ACKB_MINIO_QUARANTINE_BUCKET", "ackb-test-quarantine")
    monkeypatch.setenv("ACKB_MINIO_VARIANTS_BUCKET", "ackb-test-variants")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        session_cookie_secure=False,
    )
    yield settings
