"""Alembic-only schema management tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch

ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def test_alembic_has_one_backend_head() -> None:
    scripts = ScriptDirectory.from_config(alembic_config())
    assert scripts.get_heads() == ["20260716_10"]


def test_alembic_upgrade_renders_offline_postgresql_sql(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(
        "ACKB_DATABASE_URL",
        "postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
    )
    command.upgrade(alembic_config(), "head", sql=True)
    sql = capsys.readouterr().out
    assert "CREATE TABLE alembic_version" in sql
    assert "20260716_06" in sql
    assert "CREATE TABLE users" in sql
    assert "CREATE TABLE auth_sessions" in sql
    assert "CREATE TABLE auth_throttles" in sql
    assert "CREATE TABLE audit_events" in sql
    assert "CREATE TABLE media_assets" in sql
    assert "CREATE TABLE media_variants" in sql
    assert "CREATE TABLE media_jobs" in sql
    assert "ADD COLUMN duration_ms" in sql
    assert "ADD COLUMN progress_percent" in sql
    assert "ADD COLUMN idempotency_key" in sql
    assert "ADD COLUMN max_attempts" in sql
    assert "status IN ('queued', 'running', 'retrying', 'succeeded', 'failed')" in sql
    assert "CREATE TABLE categories" in sql
    assert "CREATE TABLE components" in sql
    assert "CREATE TABLE component_revisions" in sql
    assert "CREATE TABLE boards" in sql
    assert "CREATE TABLE units" in sql
    assert "CREATE TABLE property_definitions" in sql
    assert "CREATE TABLE component_compatibility" in sql
    assert "20260716_07" in sql
    assert "CREATE TABLE sources" in sql
    assert "CREATE TABLE component_sources" in sql
    assert "CREATE TABLE import_jobs" in sql
    assert "uq_components_manufacturer_model_exact" in sql
    assert "20260716_08" in sql
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in sql
    assert "CREATE TABLE duplicate_candidates" in sql
    assert "gin_trgm_ops" in sql
    assert "20260716_09" in sql
    assert "CREATE TABLE merge_decisions" in sql
    assert "decision IN ('merge','attach','create','reject')" in sql
    assert "20260716_10" in sql


def test_runtime_has_no_create_all_escape_hatch() -> None:
    source_files = [
        *ROOT.joinpath("src").rglob("*.py"),
        *ROOT.joinpath("migrations").rglob("*.py"),
    ]
    runtime_source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    assert ".create_all(" not in runtime_source
