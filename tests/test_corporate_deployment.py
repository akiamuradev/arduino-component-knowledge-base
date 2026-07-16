"""Stage-20 production deployment contracts."""

from __future__ import annotations

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


def test_internal_nginx_requires_tls_and_exact_redirect_hostname() -> None:
    nginx = (ROOT / "deploy/reverse-proxy/internal-https.conf.template").read_text(encoding="utf-8")
    assert "listen 8443 ssl;" in nginx
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in nginx
    assert "ssl_session_tickets off;" in nginx
    assert "Strict-Transport-Security" in nginx
    assert "return 308 https://${ACKB_INTERNAL_HOSTNAME}$request_uri;" in nginx
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
