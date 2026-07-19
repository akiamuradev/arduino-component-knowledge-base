"""Dependency-isolated HTTP smoke test for the backend application factory."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from arduino_component_kb.config import Settings
from arduino_component_kb.main import create_app


class SmokeDatabase:
    """Exercise readiness without requiring an unsafe shared database."""

    def __init__(self) -> None:
        self.disposed = False

    async def ping(self) -> None:
        """Represent a successful bounded PostgreSQL probe."""

    async def dispose(self) -> None:
        """Record lifespan cleanup."""
        self.disposed = True


def main() -> int:
    """Assert liveness, readiness, OpenAPI and lifespan contracts."""
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
        auth_throttle_pepper=SecretStr("x" * 32),
        redis_url="redis://127.0.0.1:6379/15",
        minio_endpoint="127.0.0.1:9000",
        minio_access_key=SecretStr("test-access"),
        minio_secret_key=SecretStr("test-secret-placeholder"),
        minio_secure=False,
    )
    database = SmokeDatabase()
    with TestClient(create_app(settings, database)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        openapi = client.get("/api/v1/openapi.json")
        assert openapi.status_code == 200
        assert {
            "/health",
            "/ready",
            "/api/v1/auth/login",
            "/api/v1/auth/me",
            "/api/v1/auth/logout",
            "/api/v1/admin/users",
            "/api/v1/media/images/uploads",
            "/api/v1/media/images/{asset_id}/complete",
            "/api/v1/media/images/{asset_id}",
            "/api/v1/media/videos/uploads",
            "/api/v1/media/videos/{asset_id}/complete",
            "/api/v1/media/videos/{asset_id}",
            "/api/v1/admin/jobs",
            "/api/v1/admin/jobs/{job_id}/retry",
            "/api/v1/import-jobs",
            "/api/v1/import-jobs/repository",
            "/api/v1/import-jobs/repository/discovery",
            "/api/v1/import-jobs/repository/entries",
            "/api/v1/import-jobs/repository/preview",
            "/api/v1/import-jobs/{job_id}",
            "/api/v1/workspace/categories",
            "/api/v1/workspace/components",
            "/api/v1/workspace/components/{component_id}",
            "/api/v1/workspace/components/{component_id}/publish",
            "/api/v1/workspace/components/{component_id}/archive",
            "/api/v1/admin/catalog/categories",
            "/api/v1/admin/catalog/categories/{category_id}/deactivate",
            "/api/v1/catalog/categories",
            "/api/v1/catalog/sources",
            "/api/v1/catalog/components",
            "/api/v1/catalog/components/{slug}",
        }.issubset(openapi.json()["paths"])
    assert database.disposed is True
    print("Backend HTTP smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
