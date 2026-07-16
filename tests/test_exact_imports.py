"""Exact import identity tests without network or infrastructure."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.normalization import normalize_exact_identity
from arduino_component_kb.imports.domain import ParsedComponent
from arduino_component_kb.imports.exact import ExactKeys
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.imports.repository import ImportRepository


def parsed(**changes: str | None) -> ParsedComponent:
    values: dict[str, object] = {
        "source_host": "arduino-tex.ru",
        "source_url": "https://arduino-tex.ru/news/229/item.html",
        "canonical_url": "https://arduino-tex.ru/news/229/item.html",
        "source_item_id": "229",
        "source_content_sha256": "a" * 64,
        "parser_name": "arduino_tex_component",
        "parser_version": "1.0.0",
        "parsed_at": datetime.now(UTC),
        "title": "Joystick KY-023",
        "summary": "Joystick module",
        "description": "Draft description",
        "manufacturer": " Keyes ",
        "model": "KY-023",
    }
    values.update(changes)
    return ParsedComponent(**values)  # type: ignore[arg-type]


def test_exact_identity_is_nfkc_case_and_punctuation_insensitive() -> None:
    assert normalize_exact_identity("  КЕЙЕС, Inc. ") == normalize_exact_identity("кейес-inc")
    assert normalize_exact_identity("ＫＹ－０２３") == "ky023"
    assert normalize_exact_identity(None) is None


def test_exact_keys_cover_source_and_manufacturer_model() -> None:
    first = ExactKeys.from_parsed(parsed())
    repeated = ExactKeys.from_parsed(parsed(manufacturer="KEYES", model="ky 023"))
    assert first.canonical_url == repeated.canonical_url
    assert first.source_item_id == repeated.source_item_id
    assert first.normalized_manufacturer == repeated.normalized_manufacturer
    assert first.normalized_model == repeated.normalized_model
    assert first.lock_name == repeated.lock_name


def test_parser_result_is_always_draft() -> None:
    assert parsed().status == "draft"


async def test_repeated_exact_import_reuses_component_without_new_record() -> None:
    component_id = uuid4()
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[component_id, uuid4()])
    session.add = MagicMock()
    now = datetime.now(UTC)
    job = ImportJob(
        id=uuid4(),
        source_id=uuid4(),
        submitted_url="https://arduino-tex.ru/news/229/item.html",
        status="running",
        requested_by=uuid4(),
        idempotency_key="repeat-229",
        attempts=1,
        max_attempts=4,
        created_at=now,
        updated_at=now,
    )
    result = await ImportRepository(cast(AsyncSession, session)).persist_draft(job, parsed())
    assert result == component_id
    assert job.draft_component_id == component_id
    assert job.status == "succeeded"
    session.add.assert_not_called()
