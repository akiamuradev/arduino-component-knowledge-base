"""Regression tests for the approved stage-zero documentation."""

from __future__ import annotations

import re

from scripts.docs_contract import DOCS, ROOT, URLS, read_documents, validate


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


def test_repository_contains_no_real_environment_file() -> None:
    assert not (ROOT / ".env").exists()
    assert all(path.is_relative_to(ROOT / "docs") for path in DOCS)


def test_markdown_files_have_no_absolute_local_links() -> None:
    markdown_files = (ROOT / "README.md", *DOCS)
    local_drive_link = re.compile(r"\]\([A-Za-z]:[/\\]")
    for path in markdown_files:
        assert not local_drive_link.search(path.read_text(encoding="utf-8"))


def test_media_limits_are_unambiguous() -> None:
    requirements = read_documents()["REQUIREMENTS.md"]
    assert "| Изображение | 12 | 8 MiB |" in requirements
    assert "| Видео | 2 | 256 MiB |" in requirements
    assert "не более 600 MiB" in requirements


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
