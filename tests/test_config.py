"""Settings validation tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from arduino_component_kb.config import Settings


def test_settings_require_database_url() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:///local.db",
        "postgresql://user:password@localhost/database",
        "not-a-url",
    ],
)
def test_settings_reject_non_async_postgresql_urls(url: str) -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg|valid SQLAlchemy URL"):
        Settings(_env_file=None, database_url=url)


def test_database_url_is_not_exposed_by_settings_repr() -> None:
    sensitive_value = "sensitive-placeholder"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"postgresql+asyncpg://ackb:{sensitive_value}@localhost:5432/ackb",
    )
    assert sensitive_value not in repr(settings)


def test_pool_settings_are_bounded() -> None:
    with pytest.raises(ValidationError, match="database_pool_size"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            database_pool_size=0,
        )


def test_production_rejects_insecure_session_cookie() -> None:
    with pytest.raises(ValidationError, match="session_cookie_secure"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            session_cookie_secure=False,
        )


def test_auth_pepper_is_not_exposed_by_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )
    assert "x" * 32 not in repr(settings)


def test_minio_credentials_are_not_exposed_by_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        minio_access_key="media-access-placeholder",
        minio_secret_key=SecretStr("media-secret-placeholder"),
    )
    rendered = repr(settings)
    assert "media-access-placeholder" not in rendered
    assert "media-secret-placeholder" not in rendered


def test_redis_credentials_are_not_exposed_by_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        redis_url="redis://:redis-secret-placeholder@127.0.0.1:6379/0",
    )
    assert "redis-secret-placeholder" not in repr(settings)


def test_production_requires_tls_for_minio() -> None:
    with pytest.raises(ValidationError, match="minio_secure"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            session_cookie_secure=True,
            minio_secure=False,
        )
