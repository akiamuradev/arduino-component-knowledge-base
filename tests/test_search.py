"""Published-only full-text and trigram search contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ClauseElement

from arduino_component_kb.api.catalog import DraftRequest
from arduino_component_kb.catalog.domain import Difficulty
from arduino_component_kb.catalog.explain import EXPLAIN_SEARCH_SQL, explain_search
from arduino_component_kb.catalog.models import Component
from arduino_component_kb.catalog.service import CatalogService


def _sql(statement: ClauseElement) -> str:
    return str(statement)


async def test_catalog_search_uses_published_document_indexes_and_sql_filters() -> None:
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=[])
    session.scalar = AsyncMock(return_value=0)
    category_id = uuid4()

    cards, total = await CatalogService(cast(AsyncSession, session)).list_published(
        "Uno R3", category_id, Difficulty.BEGINNER, 25
    )

    assert cards == []
    assert total == 0
    statement = cast(ClauseElement, session.scalars.await_args.args[0])
    sql = _sql(statement)
    assert "published_search_documents" in sql
    assert "plainto_tsquery" in sql
    assert "@@" in sql
    assert "%>" in sql
    assert "word_similarity" in sql
    assert "category_id" in sql
    assert "difficulty" in sql
    assert "component_revisions" not in sql
    assert "teacher_notes" not in sql
    assert "LIMIT" in sql


async def test_empty_query_keeps_filters_without_fuzzy_predicate() -> None:
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=[])
    session.scalar = AsyncMock(return_value=0)
    await CatalogService(cast(AsyncSession, session)).list_published(None, None, None, 50)
    sql = _sql(cast(ClauseElement, session.scalars.await_args.args[0]))
    assert "published_search_documents" in sql
    assert "plainto_tsquery" not in sql
    assert "%>" not in sql


async def test_search_document_upsert_uses_allowed_published_fields_only() -> None:
    category_id = uuid4()
    component = Component(id=uuid4(), revision=7)
    payload = DraftRequest(
        slug="arduino-uno-r3",
        title="Arduino Uno R3",
        aliases=["UNO"],
        manufacturer="Arduino",
        model="A000066",
        primary_category_id=category_id,
        tags=["board"],
        summary="Educational ATmega328P controller board.",
        description="Long student description is not indexed.",
        difficulty="beginner",
        teacher_notes="private answer must not be indexed",
        manual_original=True,
    )
    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock()

    await CatalogService(cast(AsyncSession, session))._upsert_search_document(
        component, payload.domain(), datetime.now(UTC)
    )

    statement = cast(ClauseElement, session.execute.await_args.args[0])
    compiled = statement.compile()
    sql = str(compiled)
    parameter_values = " ".join(str(value) for value in compiled.params.values())
    assert "ON CONFLICT" in sql
    assert "to_tsvector" in sql
    assert "UNO" in parameter_values
    assert "A000066" in parameter_values
    assert "private answer" not in parameter_values
    assert "Long student description" not in parameter_values


async def test_explain_analyze_is_read_only_and_parameterized() -> None:
    session = Mock(spec=AsyncSession)
    first = Mock()
    second = Mock()
    second.scalar_one.return_value = [{"Plan": {"Node Type": "Bitmap Heap Scan"}}]
    session.execute = AsyncMock(side_effect=[first, second])

    plan = await explain_search(cast(AsyncSession, session), "Arduino Uno")

    assert plan == [{"Plan": {"Node Type": "Bitmap Heap Scan"}}]
    first_sql = str(session.execute.await_args_list[0].args[0])
    explain_sql = str(session.execute.await_args_list[1].args[0])
    assert first_sql == "SET TRANSACTION READ ONLY"
    assert "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)" in explain_sql
    assert "published_search_documents" in explain_sql
    assert session.execute.await_args_list[1].args[1] == {"query": "arduino uno"}
    assert "Arduino Uno" not in explain_sql


@pytest.mark.parametrize("query", ["", "x" * 101])
async def test_explain_rejects_unbounded_query(query: str) -> None:
    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock()
    with pytest.raises(ValueError):
        await explain_search(cast(AsyncSession, session), query)
    session.execute.assert_not_awaited()


def test_explain_statement_does_not_read_hidden_content() -> None:
    sql = str(EXPLAIN_SEARCH_SQL)
    assert "teacher_notes" not in sql
    assert "code_examples" not in sql
    assert "component_revisions" not in sql
