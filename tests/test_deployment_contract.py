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
    "media-retention",
    "backend",
    "worker",
    "parser-worker",
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
    assert 'command: ["ackb-retain-media", "--apply"]' in compose
    retention = compose.split("  media-retention:", 1)[1].split("\n  backend:", 1)[0]
    assert 'profiles: ["maintenance"]' in retention
    assert "read_only: true" in retention
    assert compose.count("healthcheck:") >= 7
    assert "condition: service_completed_successfully" in compose
    assert "condition: service_healthy" in compose
    assert "ACKB_IMPORT_PIPELINE_MODE: ${ACKB_IMPORT_PIPELINE_MODE:-disabled}" in compose


def test_compose_isolates_data_and_media_processing_from_parser_egress() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "ingress:\n  edge:" in compose
    assert "edge:\n    internal: true" in compose
    assert "data:\n    internal: true" in compose
    assert "parser-egress:" in compose
    media_command = (
        'command: ["dramatiq", "arduino_component_kb.worker", "--queues", '
        '"images", "videos", "--processes", "2", "--threads", "1"]'
    )
    assert media_command in compose
    assert 'command: ["dramatiq", "arduino_component_kb.worker", "--queues", "imports"]' in compose
    parser_worker = compose.split("  parser-worker:", 1)[1].split("\n  frontend:", 1)[0]
    backend = compose.split("  backend:", 1)[1].split("\n  worker:", 1)[0]
    media_worker = compose.split("  worker:", 1)[1].split("\n  parser-worker:", 1)[0]
    frontend = compose.split("  frontend:", 1)[1].split("\n  reverse-proxy:", 1)[0]
    reverse_proxy = compose.split("  reverse-proxy:", 1)[1].split("\nvolumes:", 1)[0]
    assert "- parser-egress" in parser_worker
    assert "- parser-egress" in backend
    assert "- parser-egress" not in media_worker
    assert "- ingress" not in frontend
    assert "- edge" in reverse_proxy
    assert "- ingress" in reverse_proxy


def test_media_worker_has_a_bounded_runtime_profile() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    worker = compose.split("  worker:", 1)[1].split("\n  parser-worker:", 1)[0]
    tmp_mount = f"{Path('/').joinpath('tmp')}:rw,noexec,nosuid,nodev,size=1g,mode=1777"
    for control in (
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:",
        "- ALL",
        "pids_limit: 128",
        "mem_limit: 2g",
        'cpus: "4.0"',
        tmp_mount,
    ):
        assert control in worker


def test_nginx_healthchecks_use_explicit_ipv4_loopback() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8080/container-health" in compose
    assert "http://127.0.0.1:8080/health" in compose
    assert "http://localhost:8080" not in compose
    assert compose.count("start_period: 10s") == 2


def test_reverse_proxy_overwrites_forwarded_client_address() -> None:
    for path in (
        ROOT / "deploy" / "reverse-proxy" / "default.conf",
        ROOT / "deploy" / "reverse-proxy" / "internal-https.conf.template",
    ):
        nginx = path.read_text(encoding="utf-8")
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
        assert "$proxy_add_x_forwarded_for" not in nginx

    backend_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert '"--proxy-headers"' in backend_dockerfile
    assert '"--forwarded-allow-ips", "*"' in backend_dockerfile


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
    assert (
        "COPY pyproject.toml requirements.lock README.md LICENCE THIRD_PARTY_NOTICES.md "
        "MANIFEST.in alembic.ini ./" in backend_dockerfile
    )
    assert "python -m pip wheel --require-hashes" in backend_dockerfile
