"""Settings validation tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from arduino_component_kb.api.imports import _adapter
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter


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


def test_kicad_library_allowlist_is_bounded_backend_configuration() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        kicad_library_allowlist="Sensor_,MCU_,Relay",
    )
    assert settings.kicad_library_prefixes == ("Sensor_", "MCU_", "Relay")
    with pytest.raises(ValidationError, match="kicad_library_allowlist"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            kicad_library_allowlist="../untrusted",
        )


def test_legacy_kicad_card_import_flag_defaults_on_for_rollback() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )
    assert settings.legacy_kicad_card_import_enabled is True
    assert isinstance(_adapter(settings, "kicad_symbols"), KicadSymbolsAdapter)


def test_legacy_kicad_card_import_can_be_disabled() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        legacy_kicad_card_import_enabled=False,
    )
    with pytest.raises(ValueError, match="legacy_kicad_card_import_disabled"):
        _adapter(settings, "kicad_symbols")


def test_shadow_mode_requires_a_pinned_kicad_index() -> None:
    with pytest.raises(ValidationError, match="pinned KiCad index"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            import_pipeline_mode="shadow",
        )

    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        import_pipeline_mode="shadow",
        kicad_index_artifact_path="/var/lib/ackb/kicad/index.json",
        kicad_index_expected_revision="B" * 40,
        kicad_index_expected_sha256="C" * 64,
    )
    assert settings.kicad_index_expected_revision == "b" * 40
    assert settings.kicad_index_expected_sha256 == "c" * 64


def test_kicad_index_configuration_rejects_unpinned_or_relative_values() -> None:
    with pytest.raises(ValidationError, match="absolute file path"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            kicad_index_artifact_path="../index.json",
        )
    with pytest.raises(ValidationError, match="full commit SHA"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            kicad_index_expected_revision="main",
        )
    with pytest.raises(ValidationError, match="SHA-256 digest"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            kicad_index_expected_sha256="not-a-digest",
        )
