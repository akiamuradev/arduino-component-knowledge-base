"""Transactional persistence for durable exact imports."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.domain import Difficulty, DraftData
from arduino_component_kb.catalog.models import Category, Component
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.imports.domain import ParsedComponent
from arduino_component_kb.imports.exact import ExactKeys
from arduino_component_kb.imports.models import ComponentSource, ImportJob, Source

_SLUG_PART = re.compile(r"[^a-z0-9]+")
_CATEGORY_KEYS = {
    "input-controls": "input",
    "motors": "actuators",
}


class ImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def source_for_host(self, host: str) -> Source | None:
        return cast(
            Source | None,
            await self.session.scalar(
                select(Source).where(Source.allowed_host == host, Source.is_enabled.is_(True))
            ),
        )

    async def get_job(self, job_id: UUID, *, lock: bool = False) -> ImportJob | None:
        query = select(ImportJob).where(ImportJob.id == job_id)
        if lock:
            query = query.with_for_update()
        return cast(ImportJob | None, await self.session.scalar(query))

    async def get_idempotent_job(self, actor_id: UUID, key: str) -> ImportJob | None:
        return cast(
            ImportJob | None,
            await self.session.scalar(
                select(ImportJob).where(
                    ImportJob.requested_by == actor_id,
                    ImportJob.idempotency_key == key,
                )
            ),
        )

    def add_job(
        self, source: Source, submitted_url: str, actor_id: UUID, key: str, max_attempts: int
    ) -> ImportJob:
        now = datetime.now(UTC)
        job = ImportJob(
            id=uuid4(),
            source_id=source.id,
            submitted_url=submitted_url,
            status="queued",
            requested_by=actor_id,
            idempotency_key=key,
            attempts=0,
            max_attempts=max_attempts,
            created_at=now,
            updated_at=now,
        )
        self.session.add(job)
        return job

    async def exact_component(self, source_id: UUID, keys: ExactKeys) -> UUID | None:
        source_match = await self.session.scalar(
            select(ComponentSource.component_id).where(
                ComponentSource.source_id == source_id,
                or_(
                    ComponentSource.canonical_url == keys.canonical_url,
                    ComponentSource.source_item_id == keys.source_item_id,
                ),
            )
        )
        if source_match is not None:
            return source_match
        if keys.normalized_manufacturer and keys.normalized_model:
            return cast(
                UUID | None,
                await self.session.scalar(
                    select(Component.id).where(
                        Component.normalized_manufacturer == keys.normalized_manufacturer,
                        Component.normalized_model == keys.normalized_model,
                    )
                ),
            )
        return None

    async def persist_draft(self, job: ImportJob, parsed: ParsedComponent) -> UUID:
        keys = ExactKeys.from_parsed(parsed)
        component_id = await self.exact_component(job.source_id, keys)
        if component_id is None:
            category_key = _CATEGORY_KEYS.get(parsed.category_hint or "", parsed.category_hint)
            category = await self.session.scalar(
                select(Category).where(Category.key == (category_key or "other"))
            )
            if category is None:
                category = await self.session.scalar(
                    select(Category).where(Category.key == "other")
                )
            if category is None:
                raise RuntimeError("catalog_category_seed_missing")
            slug_seed = f"{parsed.source_host}-{parsed.source_item_id}".casefold()
            slug = _SLUG_PART.sub("-", slug_seed).strip("-")[:125]
            slug = f"{slug}-{sha256(parsed.canonical_url.encode()).hexdigest()[:12]}"
            if not slug:
                slug = f"import-{sha256(parsed.canonical_url.encode()).hexdigest()[:20]}"
            card = await CatalogService(self.session).create(
                DraftData(
                    slug=slug,
                    title=parsed.title,
                    aliases=tuple(value[:100] for value in parsed.aliases),
                    manufacturer=parsed.manufacturer,
                    model=parsed.model,
                    primary_category_id=category.id,
                    tags=tuple(value[:100] for value in parsed.tags),
                    summary=parsed.summary,
                    description=parsed.description,
                    purpose=parsed.purpose,
                    usage_notes=parsed.usage_notes,
                    safety_notes=parsed.safety_notes,
                    difficulty=Difficulty.BEGINNER,
                    teacher_notes=None,
                    manual_original=False,
                ),
                job.requested_by,
            )
            component_id = card.id
        existing_source = await self.session.scalar(
            select(ComponentSource.id).where(
                ComponentSource.source_id == job.source_id,
                or_(
                    ComponentSource.canonical_url == keys.canonical_url,
                    ComponentSource.source_item_id == keys.source_item_id,
                ),
            )
        )
        if existing_source is None:
            self.session.add(
                ComponentSource(
                    id=uuid4(),
                    component_id=component_id,
                    source_id=job.source_id,
                    submitted_url=parsed.source_url,
                    canonical_url=parsed.canonical_url,
                    source_item_id=parsed.source_item_id,
                    retrieved_at=parsed.parsed_at,
                    adapter_version=parsed.parser_version,
                    content_sha256=parsed.source_content_sha256,
                    attribution=None,
                )
            )
        now = datetime.now(UTC)
        job.canonical_url = parsed.canonical_url
        job.parser_version = parsed.parser_version
        job.draft_component_id = component_id
        job.status = "succeeded"
        job.error_code = None
        job.finished_at = now
        job.updated_at = now
        return component_id
