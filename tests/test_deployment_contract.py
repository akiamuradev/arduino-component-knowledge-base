"""Static acceptance checks for the stage-one container contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SERVICES = {
    "postgres",
    "redis",
    "minio",
    "migrate",
    "media-init",
    "backend",
    "worker",
    "frontend",
    "reverse-proxy",
}


def test_required_container_files_exist() -> None:
    paths = (
        ROOT / "Dockerfile",
        ROOT / "compose.yaml",
        ROOT / "frontend" / "Dockerfile",
        ROOT / "frontend" / "deploy" / "default.conf",
        ROOT / "deploy" / "reverse-proxy" / "Dockerfile",
        ROOT / "deploy" / "reverse-proxy" / "default.conf",
        ROOT / ".github" / "workflows" / "quality.yml",
        ROOT / "scripts" / "linux_bootstrap.sh",
        ROOT / "LICENCE",
    )
    assert all(path.is_file() for path in paths)


def test_compose_declares_only_expected_runtime_services_and_volumes() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    declared = {
        line.strip()[:-1]
        for line in compose.splitlines()
        if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":")
    }
    assert REQUIRED_SERVICES <= declared
    assert {"postgres-data", "redis-data", "minio-data"} <= declared
    assert "create_all" not in compose
    assert '"${ACKB_HTTP_PORT:-8080}:8080"' in compose
    assert "5432:5432" not in compose
    assert "6379:6379" not in compose
    assert "9000:9000" not in compose


def test_compose_has_migrations_private_media_and_health_gates() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert 'command: ["alembic", "upgrade", "head"]' in compose
    assert 'command: ["ackb-provision-media"]' in compose
    assert compose.count("healthcheck:") >= 7
    assert "condition: service_completed_successfully" in compose
    assert "condition: service_healthy" in compose


def test_images_are_versioned_and_env_example_contains_only_placeholders() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "Dockerfile", ROOT / "frontend" / "Dockerfile", ROOT / "compose.yaml")
    )
    assert ":latest" not in combined
    assert combined.count("@sha256:") >= 6
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "replace-with" in env_example
    assert "ACKB_POSTGRES_PASSWORD=" in env_example
    assert "ACKB_MINIO_ROOT_PASSWORD=" in env_example


def test_ci_runs_existing_quality_and_container_build_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
    for command in (
        "ruff check .",
        "mypy --strict",
        "pytest",
        "npm run lint",
        "npm run typecheck",
        "npm test",
        "npm run build",
        "bash -n scripts/linux_bootstrap.sh",
        "docker compose config --quiet",
        "docker compose build backend frontend reverse-proxy",
    ):
        assert command in workflow


def test_linux_bootstrap_is_fail_closed_and_does_not_print_secrets() -> None:
    script = (ROOT / "scripts" / "linux_bootstrap.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail")
    assert "docker compose config --quiet" in script
    assert "docker compose up --build --detach" in script
    assert "openssl rand" in script
    assert "chmod 600 .env" in script
    assert "replace-with" in script
    assert "echo $" not in script


def test_project_declares_exact_requested_license() -> None:
    license_text = (ROOT / "LICENCE").read_text(encoding="utf-8")
    assert license_text.startswith("# PolyForm Noncommercial License 1.0.0")
    assert "https://polyformproject.org/licenses/noncommercial/1.0.0" in license_text
    assert "Any noncommercial purpose is a permitted purpose." in license_text
    assert "## No Liability" in license_text

    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "PolyForm-Noncommercial-1.0.0"' in project
    assert 'license-files = ["LICENCE"]' in project

    backend_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY pyproject.toml README.md LICENCE MANIFEST.in alembic.ini ./" in backend_dockerfile
