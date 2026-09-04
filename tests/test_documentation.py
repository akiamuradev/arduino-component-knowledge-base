"""Regression tests for the approved stage-zero documentation."""

from __future__ import annotations

import re

from scripts.docs_contract import (
    DOCS,
    PUBLIC_MARKDOWN,
    ROOT,
    URLS,
    read_documents,
    validate,
    validate_markdown_links,
)


def test_required_documents_exist_and_contract_is_consistent() -> None:
    assert validate() == []


def test_registered_repositories_and_deactivated_sources_are_declared() -> None:
    requirements = read_documents()["REQUIREMENTS.md"]
    source_table = requirements.split("## Источники импорта", 1)[1].split("## Роли", 1)[0]
    assert len(URLS) == 2
    assert all(source_table.count(url) == 1 for url in URLS)
    assert "owner_denied_usage" in source_table
    assert "permission_status=denied" in source_table
    assert "status=inactive" in source_table


def test_data_licenses_are_separate_from_application_license() -> None:
    licensing = (ROOT / "docs" / "DATA_LICENSING.md").read_text(encoding="utf-8")
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for token in ("PolyForm Noncommercial", "GPL-3.0-only", "CC-BY-SA-4.0"):
        assert token in licensing
        assert token in notices
    assert "owner_denied_usage" in licensing
    assert "THIRD_PARTY_NOTICES.md" in manifest
    assert '"THIRD_PARTY_NOTICES.md"' in project


def test_requirement_identifiers_are_unique() -> None:
    requirements = read_documents()["REQUIREMENTS.md"]
    identifiers = re.findall(r"\bREQ-[A-Z]+-\d{3}\b", requirements)
    assert len(identifiers) >= 20
    assert len(identifiers) == len(set(identifiers))


def test_binary_media_storage_boundary_is_explicit() -> None:
    documents = read_documents()
    combined = "\n".join(documents.values()).casefold()
    assert "binary media" in combined
    assert "private minio" in combined
    assert "metadata" in combined
    assert "postgresql" in combined


def test_no_runtime_ddl_escape_hatch_is_approved() -> None:
    documents = read_documents()
    for document in documents.values():
        assert "Alembic" in document
    combined = "\n".join(documents.values()).casefold()
    assert "create_all" in combined
    assert "create_all` запрещ" in combined or "`create_all` в runtime запрещ" in combined


def test_local_environment_file_is_ignored_and_not_packaged() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert ".env" not in manifest
    assert '".env"' not in project
    assert all(path.is_relative_to(ROOT / "docs") for path in DOCS)


def test_markdown_files_have_no_absolute_local_links() -> None:
    local_drive_link = re.compile(r"\]\([A-Za-z]:[/\\]")
    for path in PUBLIC_MARKDOWN:
        assert not local_drive_link.search(path.read_text(encoding="utf-8"))


def test_public_markdown_local_links_and_anchors_resolve() -> None:
    assert validate_markdown_links() == []


def test_readme_languages_and_contributor_workflows_stay_discoverable() -> None:
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    russian = (ROOT / "README.ru.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "[Русский](README.ru.md)" in english
    assert "[English](README.md)" in russian
    for content in (english, russian, contributing):
        assert "upstream/main" in content
        assert "PolyForm Noncommercial License 1.0.0" in content
    for forbidden in ("ACKB_1.0.0_STAGE_", "MULTIPLE_IMAGES_STAGE_", "XRAY_AUDIT_"):
        assert forbidden not in english
        assert forbidden not in russian


def test_media_limits_are_unambiguous() -> None:
    requirements = read_documents()["REQUIREMENTS.md"]
    assert "| Изображение | 12 | 8 MiB |" in requirements
    assert "| Видео | 2 | 256 MiB |" in requirements
    assert "не более 600 MiB" in requirements


def test_media_retention_requires_explicit_apply_mode() -> None:
    deployment = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "ackb-retain-media" in deployment
    assert "--apply" in deployment
    assert "dry-run" in deployment


def test_only_administrator_can_confirm_merge() -> None:
    requirements = read_documents()["REQUIREMENTS.md"]
    security = read_documents()["SECURITY.md"]
    assert "Только administrator создаёт\nmerge decision" in requirements
    assert "Только administrator управляет" in security


def test_parser_cannot_publish() -> None:
    documents = read_documents()
    requirements = documents["REQUIREMENTS.md"]
    assert "parser не может установить" in requirements
    assert "только `draft`" in requirements
    assert "`published`" in requirements
    assert "Parser создаёт только draft" in documents["SECURITY.md"]


def test_authentication_baseline_is_synchronized_across_documents() -> None:
    documents = read_documents()
    combined = "\n".join(documents.values())
    assert "Argon2id" in combined
    assert "opaque server-side sessions" in combined
    assert "auth_sessions" in documents["DATA_MODEL.md"]
    assert "auth_throttles" in documents["DATA_MODEL.md"]
    assert "REQ-AUTH-006" in documents["REQUIREMENTS.md"]
