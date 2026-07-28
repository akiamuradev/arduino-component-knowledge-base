"""Application factory and health endpoint tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from arduino_component_kb.config import Settings
from arduino_component_kb.main import create_app


class FakeDatabase:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.ping_calls = 0
        self.disposed = False

    async def ping(self) -> None:
        self.ping_calls += 1
        if self.failure is not None:
            raise self.failure

    async def dispose(self) -> None:
        self.disposed = True


def settings(*, docs_enabled: bool = False) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
        docs_enabled=docs_enabled,
    )


def test_application_factory_creates_isolated_apps() -> None:
    first = create_app(settings(), FakeDatabase())
    second = create_app(settings(), FakeDatabase())
    assert isinstance(first, FastAPI)
    assert first is not second
    assert first.state.database is not second.state.database


def test_liveness_does_not_touch_database_and_preserves_safe_request_id() -> None:
    database = FakeDatabase()
    with TestClient(create_app(settings(), database)) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request-1"})
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Arduino Component Knowledge Base",
        "version": "0.21.0",
    }
    assert response.headers["X-Request-ID"] == "test-request-1"
    assert database.ping_calls == 0
    assert database.disposed is True


def test_invalid_request_id_is_replaced() -> None:
    with TestClient(create_app(settings(), FakeDatabase())) as client:
        response = client.get("/health", headers={"X-Request-ID": "contains spaces"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "contains spaces"
    assert len(response.headers["X-Request-ID"]) == 36


def test_readiness_reports_ready_after_database_probe() -> None:
    database = FakeDatabase()
    with TestClient(create_app(settings(), database)) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": {"status": "ready"}}}
    assert database.ping_calls == 1


def test_readiness_reports_503_without_leaking_exception() -> None:
    sensitive_detail = "do-not-leak"
    database = FakeDatabase(RuntimeError(sensitive_detail))
    with TestClient(create_app(settings(), database)) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": {"status": "not_ready"}},
    }
    assert sensitive_detail not in response.text
    assert database.ping_calls == 1


def test_openapi_is_versioned_and_interactive_docs_are_opt_in() -> None:
    with TestClient(create_app(settings(), FakeDatabase())) as client:
        openapi = client.get("/api/v1/openapi.json")
        docs = client.get("/docs")
    assert openapi.status_code == 200
    assert "/health" in openapi.json()["paths"]
    assert "/ready" in openapi.json()["paths"]
    assert docs.status_code == 404


def test_interactive_docs_can_be_enabled_explicitly() -> None:
    with TestClient(create_app(settings(docs_enabled=True), FakeDatabase())) as client:
        response = client.get("/docs")
    assert response.status_code == 200


def test_unhandled_error_is_typed_and_correlated_without_detail_leak(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(settings(), FakeDatabase())

    @app.get("/test-error")
    async def test_error(_: Request) -> None:
        raise RuntimeError("sensitive failure detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error", headers={"X-Request-ID": "error-request-1"})
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Не удалось выполнить запрос. Попробуйте снова.",
            "retryable": True,
            "request_id": "error-request-1",
        }
    }
    assert "sensitive failure detail" not in response.text
    captured = capsys.readouterr().out
    assert '"error_type":"RuntimeError"' in captured
    assert "sensitive failure detail" not in captured


def test_http_errors_use_one_safe_envelope_and_preserve_retry_headers() -> None:
    app = create_app(settings(), FakeDatabase())

    @app.get("/test-temporary-error")
    async def test_temporary_error() -> None:
        raise HTTPException(
            status_code=503,
            detail={"code": "media_enqueue_failed", "database": "must-not-leak"},
            headers={"Retry-After": "3"},
        )

    with TestClient(app) as client:
        response = client.get(
            "/test-temporary-error",
            headers={"X-Request-ID": "temporary-request-1"},
        )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "3"
    assert response.json() == {
        "error": {
            "code": "media_enqueue_failed",
            "message": "Обработка файла временно недоступна. Попробуйте снова.",
            "retryable": True,
            "request_id": "temporary-request-1",
        }
    }
    assert "database" not in response.text


def test_validation_errors_hide_field_internals() -> None:
    app = create_app(settings(), FakeDatabase())

    @app.get("/test-validation")
    async def test_validation(amount: int) -> dict[str, int]:
        return {"amount": amount}

    with TestClient(app) as client:
        response = client.get(
            "/test-validation",
            params={"amount": "secret-invalid-value"},
            headers={"X-Request-ID": "validation-request-1"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_failed",
            "message": "Проверьте заполнение полей.",
            "retryable": False,
            "request_id": "validation-request-1",
        }
    }
    assert "secret-invalid-value" not in response.text


def test_framework_not_found_uses_the_same_error_envelope() -> None:
    with TestClient(create_app(settings(), FakeDatabase())) as client:
        response = client.get(
            "/api/v1/does-not-exist",
            headers={"X-Request-ID": "not-found-request-1"},
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Запрашиваемые данные не найдены.",
            "retryable": False,
            "request_id": "not-found-request-1",
        }
    }
