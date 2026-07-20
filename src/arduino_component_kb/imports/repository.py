"""Transactional persistence for durable exact imports."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.domain import Difficulty, DraftData, TechnicalSpecification
from arduino_component_kb.catalog.models import Category, Component
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.deduplication.service import FuzzyCandidateService
from arduino_component_kb.imports.domain import ParsedComponent
from arduino_component_kb.imports.exact import ExactKeys
from arduino_component_kb.imports.models import ComponentSource, ImportJob, Source
from arduino_component_kb.imports.repository_domain import (
    ParsedRepositoryComponent,
    ParseStatus,
)

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
                select(Source).where(
                    Source.allowed_host == host,
                    Source.is_enabled.is_(True),
                    Source.status == "active",
                    Source.permission_status == "license_granted",
                )
            ),
        )

    async def source_for_key(self, key: str) -> Source | None:
        return cast(
            Source | None,
            await self.session.scalar(
                select(Source).where(
                    Source.key == key,
                    Source.is_enabled.is_(True),
                    Source.status == "active",
                    Source.permission_status == "license_granted",
                )
            ),
        )

    async def get_job(self, job_id: UUID, *, lock: bool = False) -> ImportJob | None:
        query = select(ImportJob).where(ImportJob.id == job_id)
        if lock:
            query = query.with_for_update()
        return cast(ImportJob | None, await self.session.scalar(query))

    async def list_jobs(
        self, *, status: str | None, limit: int, offset: int
    ) -> tuple[Sequence[ImportJob], int]:
        filters = (ImportJob.status == status,) if status is not None else ()
        total = int(
            await self.session.scalar(select(func.count()).select_from(ImportJob).where(*filters))
            or 0
        )
        jobs = tuple(
            (
                await self.session.scalars(
                    select(ImportJob)
                    .where(*filters)
                    .order_by(ImportJob.updated_at.desc(), ImportJob.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        return jobs, total

    @staticmethod
    def is_manually_retryable(job: ImportJob, now: datetime, lease_seconds: int) -> bool:
        if job.status == "failed":
            return True
        lease_reference = job.heartbeat_at or job.updated_at
        stale_before = now - timedelta(seconds=lease_seconds)
        if job.status == "running":
            return lease_reference <= stale_before
        return (
            job.status == "retrying"
            and job.next_retry_at is not None
            and job.next_retry_at <= stale_before
            and lease_reference <= stale_before
        )

    def prepare_manual_retry(self, job: ImportJob, now: datetime, lease_seconds: int) -> bool:
        if job.status == "queued":
            return False
        if not self.is_manually_retryable(job, now, lease_seconds):
            raise ValueError("job_not_retryable")
        job.status = "queued"
        job.attempts = 0
        job.error_code = None
        job.started_at = None
        job.next_retry_at = None
        job.finished_at = None
        job.heartbeat_at = None
        job.updated_at = now
        return True

    async def active_source(self, source_id: UUID) -> Source | None:
        return cast(
            Source | None,
            await self.session.scalar(
                select(Source).where(
                    Source.id == source_id,
                    Source.is_enabled.is_(True),
                    Source.status == "active",
                    Source.permission_status == "license_granted",
                )
            ),
        )

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

    def add_repository_job(
        self,
        source: Source,
        requested_revision: str,
        file_path: str,
        entry_name: str | None,
        actor_id: UUID,
        key: str,
        max_attempts: int,
    ) -> ImportJob:
        if source.repository_url is None:
            raise ValueError("repository_source_url_missing")
        now = datetime.now(UTC)
        job = ImportJob(
            id=uuid4(),
            source_id=source.id,
            submitted_url=source.repository_url,
            repository_url=source.repository_url,
            requested_revision=requested_revision,
            source_file_path=file_path,
            source_entry_name=entry_name,
            status="queued",
            requested_by=actor_id,
            idempotency_key=key,
            attempts=0,
            max_attempts=max_attempts,
            warnings_json=[],
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
            await self.session.flush()
            await FuzzyCandidateService(self.session).generate(component_id)
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

    async def persist_repository_draft(
        self, job: ImportJob, source: Source, parsed: ParsedRepositoryComponent
    ) -> UUID:
        if parsed.status not in {ParseStatus.PARSED, ParseStatus.PARSED_WITH_WARNINGS}:
            raise ValueError("repository_parse_not_persistable")
        if (
            source.key != parsed.source_key
            or source.status != "active"
            or not source.is_enabled
            or source.permission_status != "license_granted"
            or source.repository_url != parsed.repository_url
        ):
            raise ValueError("repository_source_not_importable")
        if (
            source.license_spdx != parsed.license_snapshot.spdx
            or source.license_url != parsed.license_snapshot.url
        ):
            raise ValueError("repository_license_snapshot_mismatch")
        existing = await self.session.scalar(
            select(ComponentSource.component_id).where(
                ComponentSource.source_id == source.id,
                ComponentSource.source_revision == parsed.source_revision,
                ComponentSource.source_file_path == parsed.source_file_path,
                ComponentSource.source_entry_name == parsed.source_entry_name,
            )
        )
        if existing is not None:
            self._complete_repository_job(job, parsed, existing)
            return existing
        fields = parsed.normalized_fields
        title = str(fields.get("title") or fields.get("symbol_name") or "")[:160]
        if not title:
            raise ValueError("repository_title_missing")
        summary = str(fields.get("summary") or fields.get("description") or "").strip()[:500]
        if len(summary) < 20:
            summary = f"Structured metadata for {title} imported from {source.display_name}."[:500]
        description = str(fields.get("description") or summary).strip()[:2_000] or summary
        category_hint = str(fields.get("category_hint") or "other")
        category = await self.session.scalar(select(Category).where(Category.key == category_hint))
        if category is None:
            category = await self.session.scalar(select(Category).where(Category.key == "other"))
        if category is None:
            raise RuntimeError("catalog_category_seed_missing")
        specifications = _technical_specifications(fields)
        slug_identity = (
            f"{source.key}-{parsed.source_file_path}-{parsed.source_entry_name or ''}"
        ).casefold()
        slug_base = _SLUG_PART.sub("-", slug_identity).strip("-")[:125] or "repository-import"
        slug = f"{slug_base}-{sha256(parsed.idempotency_key.encode()).hexdigest()[:12]}"
        card = await CatalogService(self.session).create(
            DraftData(
                slug=slug,
                title=title,
                aliases=(),
                manufacturer=None,
                model=str(fields.get("value"))[:120] if fields.get("value") else None,
                primary_category_id=category.id,
                tags=(source.key.replace("_", "-"),),
                summary=summary,
                description=description,
                purpose=None,
                usage_notes=None,
                safety_notes=None,
                difficulty=Difficulty.BEGINNER,
                teacher_notes=None,
                manual_original=False,
                specifications=tuple(specifications),
            ),
            job.requested_by,
        )
        await self.session.flush()
        provenance = {
            key: [item.as_dict() for item in values] for key, values in parsed.provenance.items()
        }
        content_digest = sha256(
            json.dumps(parsed.as_dict(), sort_keys=True, ensure_ascii=True).encode()
        ).hexdigest()
        source_item_id = f"{parsed.source_file_path}#{parsed.source_entry_name or ''}"
        if len(source_item_id) > 160:
            source_item_id = f"repo:{sha256(source_item_id.encode()).hexdigest()}"
        self.session.add(
            ComponentSource(
                id=uuid4(),
                component_id=card.id,
                source_id=source.id,
                submitted_url=parsed.repository_url,
                canonical_url=parsed.original_url,
                source_item_id=source_item_id,
                retrieved_at=parsed.parsed_at,
                adapter_version=parsed.parser_version,
                content_sha256=content_digest,
                attribution=parsed.license_snapshot.attribution,
                source_revision=parsed.source_revision,
                source_tag=parsed.source_tag,
                source_file_path=parsed.source_file_path,
                source_entry_name=parsed.source_entry_name,
                original_url=parsed.original_url,
                imported_at=parsed.parsed_at,
                imported_fields=list(parsed.normalized_fields),
                provenance_json=provenance,
                modifications_notice=parsed.modifications_notice,
                license_snapshot_name=parsed.license_snapshot.name,
                license_snapshot_spdx=parsed.license_snapshot.spdx,
                license_snapshot_url=parsed.license_snapshot.url,
                attribution_snapshot=parsed.license_snapshot.attribution,
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
            )
        )
        await FuzzyCandidateService(self.session).generate(card.id)
        self._complete_repository_job(job, parsed, card.id)
        return card.id

    def _complete_repository_job(
        self, job: ImportJob, parsed: ParsedRepositoryComponent, component_id: UUID
    ) -> None:
        now = datetime.now(UTC)
        job.repository_url = parsed.repository_url
        job.canonical_url = parsed.original_url
        job.source_revision = parsed.source_revision
        job.source_file_path = parsed.source_file_path
        job.source_entry_name = parsed.source_entry_name
        job.parser_name = parsed.parser_name
        job.parser_version = parsed.parser_version
        job.parse_status = parsed.status.value
        job.warnings_json = list(parsed.warnings)
        job.draft_component_id = component_id
        job.status = "succeeded"
        job.error_code = None
        job.finished_at = now
        job.updated_at = now


def _technical_specifications(fields: Mapping[str, object]) -> list[TechnicalSpecification]:
    raw_specifications = fields.get("specifications", [])
    if not isinstance(raw_specifications, list):
        return []
    specifications: list[TechnicalSpecification] = []
    keys: set[str] = set()
    for item in raw_specifications:
        if not isinstance(item, dict) or not item.get("key") or not item.get("value"):
            continue
        label = str(item["key"])[:160]
        key = _SLUG_PART.sub("-", label.casefold()).strip("-")[:100]
        if not key or key in keys:
            continue
        keys.add(key)
        specifications.append(
            TechnicalSpecification(
                key=key,
                label=label,
                value_text=str(item["value"])[:2_000],
                value_number=None,
                unit=None,
                position=len(specifications),
            )
        )
        if len(specifications) == 50:
            break
    return specifications
