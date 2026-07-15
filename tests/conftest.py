"""Shared isolated test configuration."""

from __future__ import annotations

import pytest
from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def isolated_auth_settings(monkeypatch: MonkeyPatch) -> None:
    """Provide a non-secret test-only pepper without reading a local .env."""
    monkeypatch.setenv("ACKB_AUTH_THROTTLE_PEPPER", "x" * 32)
    monkeypatch.setenv("ACKB_REDIS_URL", "redis://127.0.0.1:6379/15")
    monkeypatch.setenv("ACKB_MINIO_ENDPOINT", "127.0.0.1:9000")
    monkeypatch.setenv("ACKB_MINIO_ACCESS_KEY", "test-access")
    monkeypatch.setenv("ACKB_MINIO_SECRET_KEY", "test-secret-placeholder")
    monkeypatch.setenv("ACKB_MINIO_SECURE", "false")
