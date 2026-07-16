"""Read-only EXPLAIN ANALYZE helper for the published catalog search plan."""

from __future__ import annotations

import argparse
import asyncio
import json
import unicodedata
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database

EXPLAIN_SEARCH_SQL = text(
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
    SELECT component_id
    FROM published_search_documents
    WHERE search_vector @@ plainto_tsquery('simple', :query)
       OR search_text %> :query
    ORDER BY (
        ts_rank_cd(search_vector, plainto_tsquery('simple', :query))
        + word_similarity(:query, search_text) * 0.35
    ) DESC, published_at DESC, component_id
    LIMIT 50
    """
)


async def explain_search(session: AsyncSession, query: str) -> object:
    normalized = unicodedata.normalize("NFKC", query).strip().casefold()
    if not normalized or len(normalized) > 100:
        raise ValueError("query must contain 1 to 100 characters")
    await session.execute(text("SET TRANSACTION READ ONLY"))
    result = await session.execute(EXPLAIN_SEARCH_SQL, {"query": normalized})
    return result.scalar_one()


async def _run(query: str, settings: Settings) -> object:
    database = Database(settings)
    try:
        async with database.sessions() as session:
            plan = await explain_search(session, query)
            await session.rollback()
            return plan
    finally:
        await database.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Explain published catalog search")
    parser.add_argument("--query", required=True, help="Synthetic search query, 1-100 chars")
    args = parser.parse_args(argv)
    print(json.dumps(asyncio.run(_run(args.query, Settings())), ensure_ascii=False, indent=2))
