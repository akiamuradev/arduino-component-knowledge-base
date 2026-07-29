"""Settings validation tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from arduino_component_kb.api.imports import _adapter
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "database_echo": False,
        "docs_enabled": False,
        "log_level": "INFO",
        "database_url": (
            "postgresql+asyncpg://ackb_runtime:runtime-password-0000000000000000@postgres:5432/ackb"
        ),
        "auth_throttle_pepper": "production-pepper-000000000000000000",
        "redis_url": "redis://:redis-password-000000000000000000@redis:6379/0",
        "minio_endpoint": "minio:9000",
        "minio_access_key": "ackb-media-runtime",
        "minio_secret_key": "minio-password-000000000000000000",
        "minio_secure": True,
        "session_cookie_secure": True,
        "trusted_hosts": "components.college.internal",
        "legacy_kicad_card_import_enabled": False,
    }
    values.update(overrides)
    return Settings.model_validate(values)


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


def test_review_metrics_minimum_sample_is_bounded_and_defaults_to_decision_record() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )
    assert settings.import_review_metrics_min_sample == 100
    with pytest.raises(ValidationError, match="import_review_metrics_min_sample"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            import_review_metrics_min_sample=0,
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


def test_secure_production_settings_are_accepted() -> None:
    configured = production_settings()
    assert configured.trusted_host_values == ("components.college.internal",)
    assert configured.docs_enabled is False
    assert configured.database_echo is False


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"database_echo": True}, "database_echo"),
        ({"docs_enabled": True}, "docs_enabled"),
        ({"log_level": "DEBUG"}, "log_level"),
        ({"legacy_kicad_card_import_enabled": True}, "legacy_kicad"),
        ({"session_ttl_minutes": 481}, "session_ttl_minutes"),
        ({"trusted_hosts": "localhost"}, "internal DNS trusted host"),
        ({"trusted_hosts": "192.0.2.10"}, "internal DNS trusted host"),
        (
            {"database_url": "postgresql+asyncpg://ackb:password@postgres:5432/ackb"},
            "dedicated runtime role",
        ),
        (
            {"database_url": "postgresql+asyncpg://ackb_runtime:short@postgres:5432/ackb"},
            "non-placeholder password",
        ),
        ({"redis_url": "redis://redis:6379/0"}, "redis_url needs a non-placeholder password"),
        ({"minio_access_key": "minioadmin"}, "runtime identity"),
        ({"minio_secret_key": "too-short"}, "at least 32"),
    ],
)
def test_production_rejects_development_or_privileged_settings(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        production_settings(**override)


@pytest.mark.parametrize("value", ("*", "safe.example,*", "bad host", ""))
def test_trusted_hosts_reject_wildcards_and_malformed_values(value: str) -> None:
    with pytest.raises(ValidationError, match="trusted_hosts"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            trusted_hosts=value,
        )


@pytest.mark.parametrize(
    "value",
    ("media-storage", "//storage", "/storage/", "/storage?debug=1", "/storage#fragment"),
)
def test_media_public_path_prefix_must_stay_same_origin(value: str) -> None:
    with pytest.raises(ValidationError, match="media_public_path_prefix"):
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
            media_public_path_prefix=value,
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
