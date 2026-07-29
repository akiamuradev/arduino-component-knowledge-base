"""Stage-20 production deployment contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.production_smoke import validated_base_url

ROOT = Path(__file__).resolve().parents[1]


def test_production_compose_enables_https_without_publishing_data_services() -> None:
    compose = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    assert "ACKB_ENVIRONMENT: production" in compose
    assert 'ACKB_SESSION_COOKIE_SECURE: "true"' in compose
    assert 'ACKB_MINIO_SECURE: "true"' in compose
    assert "SSL_CERT_FILE: /etc/ackb/ca/ca-bundle.crt" in compose
    assert "/root/.minio/certs/CAs/ca-bundle.crt:ro" in compose
    assert "mc alias set ackb-health https://minio:9000" in compose
    assert "ports: !override" in compose
    assert ":80:8080" in compose
    assert ":443:8443" in compose
    assert "5432:5432" not in compose
    assert "6379:6379" not in compose
    assert "9000:9000" not in compose
    assert compose.count(":ro") >= 6


def test_production_compose_uses_dedicated_runtime_credentials() -> None:
    compose = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    for setting in (
        "ACKB_POSTGRES_RUNTIME_USER",
        "ACKB_POSTGRES_RUNTIME_PASSWORD",
        "ACKB_POSTGRES_BACKUP_USER",
        "ACKB_POSTGRES_BACKUP_PASSWORD",
        "ACKB_REDIS_PASSWORD",
        "ACKB_MINIO_ACCESS_KEY",
        "ACKB_MINIO_SECRET_KEY",
    ):
        assert setting in compose
        assert setting in env_example
    assert "database-permissions:" in compose
    assert "minio-identity-init:" in compose
    assert "--requirepass" in compose
    assert "ACKB_TRUSTED_HOSTS" in compose
    assert 'ACKB_LEGACY_KICAD_CARD_IMPORT_ENABLED: "false"' in compose


def test_runtime_database_role_has_no_ddl_or_administration_grants() -> None:
    grants = (ROOT / "deploy" / "postgres" / "runtime-grants.sql").read_text(encoding="utf-8")
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS" in grants
    assert "REVOKE CREATE ON SCHEMA public" in grants
    assert "SELECT, INSERT, UPDATE, DELETE" in grants
    assert "GRANT CREATE" not in grants
    assert "GRANT ALL" not in grants


def test_backup_database_role_and_tools_are_read_only_and_isolated() -> None:
    grants = (ROOT / "deploy" / "postgres" / "runtime-grants.sql").read_text(encoding="utf-8")
    compose = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    assert "ACKB_POSTGRES_BACKUP_USER" in grants
    assert "GRANT SELECT ON ALL TABLES" in grants
    assert "database-backup:" in compose
    assert "database-restore-tools:" in compose
    assert "database-restore-migrate:" in compose
    assert "profiles: [maintenance]" in compose
    assert "profiles: [restore]" in compose


def test_runtime_minio_policy_is_limited_to_private_media_buckets() -> None:
    policy = json.loads(
        (ROOT / "deploy" / "minio" / "ackb-media-policy.json").read_text(encoding="utf-8")
    )
    rendered = json.dumps(policy, sort_keys=True)
    assert "ackb-media-quarantine" in rendered
    assert "ackb-media-variants" in rendered
    assert '"Resource": "*"' not in rendered
    assert "s3:*" not in rendered
    assert "admin:" not in rendered


def test_production_application_and_edge_containers_are_hardened() -> None:
    compose = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    for service, next_service in (
        ("migrate", "database-permissions"),
        ("database-permissions", "database-backup"),
        ("database-backup", "database-restore-tools"),
        ("database-restore-tools", "database-restore-migrate"),
        ("database-restore-migrate", "minio-identity-init"),
        ("minio-identity-init", "media-init"),
        ("media-init", "backend"),
        ("backend", "worker"),
        ("parser-worker", "media-retention"),
        ("frontend", "reverse-proxy"),
    ):
        block = compose.split(f"  {service}:", 1)[1].split(f"\n  {next_service}:", 1)[0]
        assert "read_only: true" in block
        assert "no-new-privileges:true" in block
        assert "cap_drop:" in block

    base_compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    reconciler = base_compose.split("  job-reconciler:", 1)[1].split("\n  frontend:", 1)[0]
    assert 'command: ["ackb-reconcile-jobs", "--loop"]' in reconciler
    assert "read_only: true" in reconciler
    assert "no-new-privileges:true" in reconciler
    assert "cap_drop:" in reconciler
    assert "parser-egress" not in reconciler


def test_internal_nginx_requires_tls_and_exact_redirect_hostname() -> None:
    nginx = (ROOT / "deploy/reverse-proxy/internal-https.conf.template").read_text(encoding="utf-8")
    assert "listen 8443 ssl;" in nginx
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in nginx
    assert "ssl_session_tickets off;" in nginx
    assert "Strict-Transport-Security" in nginx
    assert "return 308 https://${ACKB_INTERNAL_HOSTNAME}$request_uri;" in nginx
    assert "proxy_pass https://ackb_minio/;" in nginx
    assert "proxy_ssl_name minio;" in nginx
    assert "proxy_ssl_verify on;" in nginx
    assert "proxy_ssl_trusted_certificate /etc/nginx/ca/ca-bundle.crt;" in nginx
    assert "ssl_verify_client off" not in nginx
    assert "Access-Control-Allow-Origin" not in nginx


def test_production_templates_contain_no_private_material_or_insecure_smoke_flag() -> None:
    env_example = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    preflight = (ROOT / "scripts/production_preflight.sh").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/production_smoke.py").read_text(encoding="utf-8")
    assert "replace-with" in env_example
    assert "BEGIN PRIVATE KEY" not in env_example
    assert "openssl verify" in preflight
    assert "openssl x509" in preflight
    assert "--insecure" not in smoke
    assert "CERT_NONE" not in smoke
    contract_smoke = (ROOT / "scripts/production_contract_smoke.sh").read_text(encoding="utf-8")
    assert "--add-host backend:127.0.0.1" in contract_smoke
    assert "--add-host frontend:127.0.0.1" in contract_smoke
    assert "--add-host minio:127.0.0.1" in contract_smoke
    identity_smoke = (ROOT / "scripts/production_identity_smoke.sh").read_text(encoding="utf-8")
    assert "has_schema_privilege" in identity_smoke
    assert "redis-cli ping" in identity_smoke
    assert "mc admin info" in identity_smoke


@pytest.mark.parametrize(
    "value",
    (
        "http://kb.college.internal/",
        "https://user@kb.college.internal/",
        "https://kb.college.internal:8443/",
        "https://kb.college.internal/prefix/",
        "https://kb.college.internal/?debug=true",
    ),
)
def test_production_smoke_rejects_noncanonical_or_insecure_origins(value: str) -> None:
    with pytest.raises(ValueError):
        validated_base_url(value)


def test_production_smoke_accepts_https_origin_on_standard_port() -> None:
    assert validated_base_url("https://kb.college.internal") == "https://kb.college.internal/"


def test_deployment_runbook_covers_network_firewall_and_acceptance() -> None:
    runbook = (ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")
    for required in (
        "Ubuntu Server 24.04 LTS",
        "netplan try",
        "внутреннем DNS",
        "internal hostname",
        "ufw default deny incoming",
        "DOCKER-USER",
        "production_smoke.py",
    ):
        assert required in runbook
