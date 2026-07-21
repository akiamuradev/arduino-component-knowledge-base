"""Repository idempotency, source policy and publication licensing tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.imports import _preview_response
from arduino_component_kb.catalog.domain import CatalogValidationError
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.models import ComponentSource, ImportJob, Source
from arduino_component_kb.imports.repository import ImportRepository, _technical_specifications
from arduino_component_kb.imports.repository_domain import (
    ParsedRepositoryComponent,
    RepositoryEntry,
    RepositorySnapshot,
)

FIXTURE = Path(__file__).parent / "fixtures" / "seeed" / "complete.md"


def licensed_source(**changes: object) -> Source:
    values: dict[str, object] = {
        "id": uuid4(),
        "key": "seeed_wiki",
        "display_name": "Seeed Studio Wiki",
        "seed_url": SeeedWikiAdapter.repository_url,
        "adapter": "seeed-wiki-git-v1",
        "adapter_version": "1.0.0",
        "policy": "licensed_content",
        "is_enabled": True,
        "source_type": "git_repository",
        "status": "active",
        "repository_url": SeeedWikiAdapter.repository_url,
        "permission_status": "license_granted",
        "license_spdx": "GPL-3.0-only",
        "license_url": "https://www.gnu.org/licenses/gpl-3.0.html",
        "updated_at": datetime.now(UTC),
    }
    values.update(changes)
    return Source(**values)


async def parsed(revision: str = "b" * 40) -> ParsedRepositoryComponent:
    snapshot = RepositorySnapshot(
        SeeedWikiAdapter.repository_url,
        revision,
        {"complete.md": FIXTURE.read_bytes()},
    )
    return await SeeedWikiAdapter().parse_entry(
        snapshot, RepositoryEntry("complete.md"), parsed_at=datetime.now(UTC)
    )


async def test_repository_idempotency_reuses_same_revision_component() -> None:
    result = await parsed()
    component_id = uuid4()
    session = MagicMock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=component_id)
    job = ImportJob(
        id=uuid4(),
        source_id=uuid4(),
        submitted_url=result.repository_url,
        status="running",
        requested_by=uuid4(),
        idempotency_key=result.idempotency_key,
        attempts=1,
        max_attempts=4,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository = ImportRepository(cast(AsyncSession, session))
    component = await repository.persist_repository_draft(
        job, licensed_source(id=job.source_id), result
    )
    assert component == component_id
    assert job.status == "succeeded"
    assert job.source_revision == "b" * 40
    assert job.draft_component_id == component_id
    session.add.assert_not_called()


async def test_new_revision_has_a_different_idempotency_identity() -> None:
    assert (await parsed("b" * 40)).idempotency_key != (await parsed("c" * 40)).idempotency_key


def test_repository_specifications_are_unique_and_bounded_for_catalog() -> None:
    raw = [
        {"key": "Raspberry pi", "value": "first"},
        {"key": "Raspberry pi", "value": "duplicate"},
        {"key": "Get ONE Now", "value": "first"},
        {"key": "Get ONE Now", "value": "duplicate"},
        {"key": "Operating voltage", "value": "3.3 V"},
        {"key": "Operation voltage", "value": "duplicate"},
        {"key": "Accuracy", "value": "1%"},
    ]

    specifications = _technical_specifications({"specifications": raw})

    assert [item.key for item in specifications] == ["operating-voltage", "accuracy"]
    assert [item.label for item in specifications] == ["Operating voltage", "Accuracy"]
    assert [item.position for item in specifications] == [0, 1]
    assert specifications[0].value_text == "3.3 V"


async def test_preview_is_a_non_persisted_draft_with_source_snapshot() -> None:
    response = _preview_response(await parsed("d" * 40), "docusaurus-version")
    assert response.draft_status == "draft"
    assert response.revision == "d" * 40
    assert response.requested_revision == "docusaurus-version"
    assert response.license.spdx == "GPL-3.0-only"
    assert response.parser_name == "seeed-wiki-git-v1"
    assert response.provenance["title"][0].source_revision == "d" * 40


def relation(**changes: object) -> ComponentSource:
    values: dict[str, object] = {
        "id": uuid4(),
        "component_id": uuid4(),
        "source_id": uuid4(),
        "submitted_url": SeeedWikiAdapter.repository_url,
        "canonical_url": "https://wiki.seeedstudio.com/example/",
        "retrieved_at": datetime.now(UTC),
        "adapter_version": "1.0.0",
        "content_sha256": "a" * 64,
        "source_revision": "a" * 40,
        "original_url": "https://wiki.seeedstudio.com/example/",
        "imported_at": datetime.now(UTC),
        "license_snapshot_name": "GNU General Public License v3.0 only",
        "license_snapshot_spdx": "GPL-3.0-only",
        "license_snapshot_url": "https://www.gnu.org/licenses/gpl-3.0.html",
        "attribution_snapshot": "Seeed Studio Wiki, example",
        "modifications_notice": "Facts extracted and normalized.",
        "parser_name": "seeed-wiki-git-v1",
        "parser_version": "1.0.0",
    }
    values.update(changes)
    return ComponentSource(**values)


def test_publish_policy_rejects_denied_and_incomplete_sources() -> None:
    service = CatalogService(cast(AsyncSession, MagicMock(spec=AsyncSession)))
    denied = licensed_source(status="disabled", permission_status="denied")
    with pytest.raises(CatalogValidationError, match="source_permission_denied"):
        service._validate_publish_sources([(relation(source_id=denied.id), denied)])

    source = licensed_source()
    with pytest.raises(CatalogValidationError, match="source_revision_missing"):
        service._validate_publish_sources(
            [(relation(source_id=source.id, source_revision=None), source)]
        )
    with pytest.raises(CatalogValidationError, match="source_license_missing"):
        service._validate_publish_sources(
            [(relation(source_id=source.id, license_snapshot_spdx=None), source)]
        )


def test_publish_policy_accepts_complete_immutable_license_snapshot() -> None:
    service = CatalogService(cast(AsyncSession, MagicMock(spec=AsyncSession)))
    source = licensed_source()
    service._validate_publish_sources([(relation(source_id=source.id), source)])
