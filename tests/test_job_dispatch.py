"""Bounded PostgreSQL-to-Redis delivery contracts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from arduino_component_kb.dispatch.reconciler import publish_safely
from arduino_component_kb.dispatch.repository import DispatchIntent, DispatchRepository

ROOT = Path(__file__).resolve().parents[1]


class UnavailableRedisPublisher:
    def publish(self, intent: DispatchIntent) -> None:
        del intent
        raise RedisError("redis://internal-host:6379 must not leak")


def intent(attempt: int = 1) -> DispatchIntent:
    return DispatchIntent(
        id=uuid4(),
        job_type="import",
        job_id=uuid4(),
        queue_name="imports",
        attempt=attempt,
    )


def test_redis_failure_is_caught_without_inventing_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    assert publish_safely(UnavailableRedisPublisher(), intent()) is False
    assert "internal-host" not in caplog.text
    assert "redis://" not in caplog.text


def test_dispatch_backoff_is_finite_and_bounded() -> None:
    assert [DispatchRepository._backoff_seconds(value) for value in range(1, 8)] == [
        5,
        10,
        20,
        40,
        60,
        60,
        60,
    ]


def test_dispatch_intent_contains_only_opaque_job_identity() -> None:
    value = intent()
    assert value.job_type == "import"
    assert value.queue_name == "imports"
    assert value.attempt == 1
    assert isinstance(value.job_id, type(uuid4()))
    assert datetime.now(UTC).tzinfo is not None


def test_browser_requests_only_commit_dispatch_intent_and_never_call_redis() -> None:
    for relative_path in (
        "src/arduino_component_kb/api/imports.py",
        "src/arduino_component_kb/api/media.py",
        "src/arduino_component_kb/api/jobs.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert ".enqueue(" not in source
        assert "broker_unavailable" not in source
