"""Async SQLAlchemy infrastructure tests."""

from __future__ import annotations

from arduino_component_kb.auth.models import User
from arduino_component_kb.catalog.models import Component
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Base, Database
from arduino_component_kb.media.models import MediaAsset


async def test_database_uses_asyncpg_without_connecting() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
    )
    database = Database(settings)
    try:
        assert database.engine.url.drivername == "postgresql+asyncpg"
        assert database.engine.pool._pre_ping is True
        assert database.sessions.kw["expire_on_commit"] is False
    finally:
        await database.dispose()


def test_metadata_contains_authentication_catalog_and_media_tables() -> None:
    assert User.__tablename__ == "users"
    assert Component.__tablename__ == "components"
    assert MediaAsset.__tablename__ == "media_assets"
    assert set(Base.metadata.tables) == {
        "audit_events",
        "auth_sessions",
        "auth_throttles",
        "boards",
        "categories",
        "component_aliases",
        "component_compatibility",
        "component_enrichment_reviews",
        "component_enrichments",
        "component_identity_candidates",
        "code_example_hints",
        "code_examples",
        "component_properties",
        "component_revisions",
        "component_tags",
        "component_sources",
        "components",
        "duplicate_candidates",
        "import_jobs",
        "import_pipeline_artifacts",
        "import_review_actions",
        "import_review_drafts",
        "import_review_states",
        "media_assets",
        "media_jobs",
        "media_variants",
        "merge_decisions",
        "property_definitions",
        "parser_evaluations",
        "published_search_documents",
        "sources",
        "tags",
        "units",
        "user_roles",
        "users",
    }
