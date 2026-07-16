"""Transactional catalog CRUD and lifecycle policy."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.domain import (
    CatalogCard,
    CatalogValidationError,
    CategoryItem,
    ComponentNotFoundError,
    ComponentStatus,
    Difficulty,
    DraftData,
    RevisionConflictError,
)
from arduino_component_kb.catalog.models import (
    Category,
    Component,
    ComponentAlias,
    ComponentRevision,
    ComponentTag,
    Tag,
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _snapshot_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CatalogValidationError
    return tuple(value)


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def categories(self) -> list[CategoryItem]:
        rows = await self.session.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.position, Category.name)
        )
        return [CategoryItem(row.id, row.key, row.name) for row in rows]

    async def create_category(
        self, key: str, name: str, parent_id: UUID | None, description: str | None, position: int
    ) -> CategoryItem:
        if not _SLUG.fullmatch(key) or not name.strip():
            raise CatalogValidationError
        if parent_id is not None:
            parent = await self.session.get(Category, parent_id)
            if parent is None or not parent.is_active:
                raise CatalogValidationError
        row = Category(
            id=uuid4(),
            key=key,
            name=name.strip(),
            parent_id=parent_id,
            description=description,
            is_active=True,
            position=position,
        )
        self.session.add(row)
        await self.session.flush()
        return CategoryItem(row.id, row.key, row.name)

    async def deactivate_category(self, category_id: UUID) -> None:
        row = await self.session.scalar(
            select(Category).where(Category.id == category_id).with_for_update()
        )
        if row is None:
            raise ComponentNotFoundError
        usage = await self.session.scalar(
            select(func.count())
            .select_from(Component)
            .where(Component.primary_category_id == category_id)
        )
        children = await self.session.scalar(
            select(func.count())
            .select_from(Category)
            .where(Category.parent_id == category_id, Category.is_active.is_(True))
        )
        if usage != 0 or children != 0:
            raise CatalogValidationError
        row.is_active = False

    async def list_cards(self, status: ComponentStatus | None = None) -> list[CatalogCard]:
        query = select(Component).order_by(Component.updated_at.desc())
        if status is not None:
            query = query.where(Component.status == status.value)
        return [await self._card(row) for row in await self.session.scalars(query)]

    async def list_published(
        self,
        query: str | None,
        category_id: UUID | None,
        difficulty: Difficulty | None,
        limit: int,
    ) -> tuple[list[CatalogCard], int]:
        rows = await self.session.scalars(
            select(Component)
            .where(Component.status != ComponentStatus.ARCHIVED.value)
            .order_by(Component.updated_at.desc())
        )
        needle = _normalized(query) if query else None
        cards: list[CatalogCard] = []
        for row in rows:
            card = await self._published_card(row)
            if card is None:
                continue
            haystack = _normalized(
                " ".join((card.data.title, card.data.summary, *card.data.aliases, *card.data.tags))
            )
            if needle and needle not in haystack:
                continue
            if category_id is not None and card.data.primary_category_id != category_id:
                continue
            if difficulty is not None and card.data.difficulty is not difficulty:
                continue
            cards.append(card)
        return cards[:limit], len(cards)

    async def get_published(self, slug: str) -> CatalogCard:
        row = await self.session.scalar(
            select(Component).where(
                Component.slug == slug,
                Component.status != ComponentStatus.ARCHIVED.value,
            )
        )
        if row is None:
            raise ComponentNotFoundError
        card = await self._published_card(row)
        if card is None:
            raise ComponentNotFoundError
        return card

    async def get_card(self, component_id: UUID) -> CatalogCard:
        row = await self.session.get(Component, component_id)
        if row is None:
            raise ComponentNotFoundError
        return await self._card(row)

    async def create(self, data: DraftData, actor_id: UUID) -> CatalogCard:
        await self._validate(data)
        now = datetime.now(UTC)
        row = Component(
            id=uuid4(),
            status=ComponentStatus.DRAFT.value,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
            revision=1,
            published_at=None,
            **self._columns(data),
        )
        self.session.add(row)
        await self.session.flush()
        await self._replace_lists(row.id, data)
        await self._snapshot(row, data, actor_id, now)
        return await self._card(row)

    async def update(
        self, component_id: UUID, expected_revision: int, data: DraftData, actor_id: UUID
    ) -> CatalogCard:
        row = await self._locked(component_id)
        if row.revision != expected_revision:
            raise RevisionConflictError
        if row.published_at is not None and data.slug != row.slug:
            raise CatalogValidationError
        await self._validate(data)
        for key, value in self._columns(data).items():
            setattr(row, key, value)
        now = datetime.now(UTC)
        row.status = ComponentStatus.DRAFT.value
        row.updated_by = actor_id
        row.updated_at = now
        row.revision += 1
        await self._replace_lists(row.id, data)
        await self._snapshot(row, data, actor_id, now)
        return await self._card(row)

    async def transition(
        self, component_id: UUID, expected_revision: int, target: ComponentStatus, actor_id: UUID
    ) -> CatalogCard:
        row = await self._locked(component_id)
        if row.revision != expected_revision:
            raise RevisionConflictError
        if target is ComponentStatus.PUBLISHED:
            if (
                row.status != ComponentStatus.DRAFT.value
                or not row.manual_original
                or not row.description.strip()
            ):
                raise CatalogValidationError
            row.published_at = datetime.now(UTC)
        elif target is ComponentStatus.ARCHIVED:
            if row.status != ComponentStatus.PUBLISHED.value:
                raise CatalogValidationError
        else:
            raise CatalogValidationError
        row.status = target.value
        row.revision += 1
        row.updated_by = actor_id
        row.updated_at = datetime.now(UTC)
        data = await self._data(row)
        await self._snapshot(row, data, actor_id, row.updated_at)
        return await self._card(row)

    async def _locked(self, component_id: UUID) -> Component:
        row = await self.session.scalar(
            select(Component).where(Component.id == component_id).with_for_update()
        )
        if row is None:
            raise ComponentNotFoundError
        return row

    async def _validate(self, data: DraftData) -> None:
        if (
            not _SLUG.fullmatch(data.slug)
            or len(data.aliases) > 20
            or len(data.tags) > 20
            or any(not value.strip() or len(value.strip()) > 100 for value in data.aliases)
            or any(not value.strip() or len(value.strip()) > 100 for value in data.tags)
        ):
            raise CatalogValidationError
        category = await self.session.get(Category, data.primary_category_id)
        if category is None or not category.is_active:
            raise CatalogValidationError
        if len({_normalized(x) for x in data.aliases}) != len(data.aliases) or len(
            {_normalized(x) for x in data.tags}
        ) != len(data.tags):
            raise CatalogValidationError

    @staticmethod
    def _columns(data: DraftData) -> dict[str, object]:
        return {
            key: getattr(data, key)
            for key in (
                "slug",
                "title",
                "manufacturer",
                "model",
                "summary",
                "description",
                "purpose",
                "usage_notes",
                "safety_notes",
                "difficulty",
                "teacher_notes",
                "primary_category_id",
                "manual_original",
            )
        }

    async def _replace_lists(self, component_id: UUID, data: DraftData) -> None:
        await self.session.execute(
            delete(ComponentAlias).where(ComponentAlias.component_id == component_id)
        )
        await self.session.execute(
            delete(ComponentTag).where(ComponentTag.component_id == component_id)
        )
        self.session.add_all(
            [
                ComponentAlias(
                    id=uuid4(),
                    component_id=component_id,
                    alias=value.strip(),
                    normalized_alias=_normalized(value),
                    position=i,
                )
                for i, value in enumerate(data.aliases)
            ]
        )
        for value in data.tags:
            normalized = _normalized(value)
            tag = await self.session.scalar(select(Tag).where(Tag.normalized_name == normalized))
            if tag is None:
                tag = Tag(id=uuid4(), name=value.strip(), normalized_name=normalized)
                self.session.add(tag)
                await self.session.flush()
            self.session.add(ComponentTag(component_id=component_id, tag_id=tag.id))

    async def _data(self, row: Component) -> DraftData:
        aliases = await self.session.scalars(
            select(ComponentAlias.alias)
            .where(ComponentAlias.component_id == row.id)
            .order_by(ComponentAlias.position)
        )
        tags = await self.session.scalars(
            select(Tag.name)
            .join(ComponentTag, ComponentTag.tag_id == Tag.id)
            .where(ComponentTag.component_id == row.id)
            .order_by(Tag.name)
        )
        return DraftData(
            aliases=tuple(aliases),
            tags=tuple(tags),
            **{
                key: getattr(row, key)
                for key in (
                    "slug",
                    "title",
                    "manufacturer",
                    "model",
                    "primary_category_id",
                    "summary",
                    "description",
                    "purpose",
                    "usage_notes",
                    "safety_notes",
                    "difficulty",
                    "teacher_notes",
                    "manual_original",
                )
            },
        )

    async def _card(self, row: Component) -> CatalogCard:
        category = await self.session.get(Category, row.primary_category_id)
        if category is None:
            raise CatalogValidationError
        return CatalogCard(
            row.id,
            ComponentStatus(row.status),
            await self._data(row),
            CategoryItem(category.id, category.key, category.name),
            row.revision,
            row.updated_at,
            row.published_at,
        )

    async def _snapshot(
        self, row: Component, data: DraftData, actor_id: UUID, now: datetime
    ) -> None:
        content = {
            key: value for key, value in self._columns(data).items() if not isinstance(value, UUID)
        }
        content.update(
            {
                "primary_category_id": str(data.primary_category_id),
                "aliases": list(data.aliases),
                "tags": list(data.tags),
            }
        )
        self.session.add(
            ComponentRevision(
                id=uuid4(),
                component_id=row.id,
                revision=row.revision,
                status=row.status,
                content_json=content,
                actor_id=actor_id,
                created_at=now,
            )
        )

    async def _published_card(self, row: Component) -> CatalogCard | None:
        snapshot = await self.session.scalar(
            select(ComponentRevision)
            .where(
                ComponentRevision.component_id == row.id,
                ComponentRevision.status == ComponentStatus.PUBLISHED.value,
            )
            .order_by(ComponentRevision.revision.desc())
            .limit(1)
        )
        if snapshot is None:
            return None
        content = snapshot.content_json
        category_id = UUID(str(content["primary_category_id"]))
        category = await self.session.get(Category, category_id)
        if category is None or not category.is_active:
            return None
        data = DraftData(
            slug=str(content["slug"]),
            title=str(content["title"]),
            aliases=_snapshot_strings(content["aliases"]),
            manufacturer=str(content["manufacturer"]) if content.get("manufacturer") else None,
            model=str(content["model"]) if content.get("model") else None,
            primary_category_id=category_id,
            tags=_snapshot_strings(content["tags"]),
            summary=str(content["summary"]),
            description=str(content["description"]),
            purpose=str(content["purpose"]) if content.get("purpose") else None,
            usage_notes=str(content["usage_notes"]) if content.get("usage_notes") else None,
            safety_notes=str(content["safety_notes"]) if content.get("safety_notes") else None,
            difficulty=Difficulty(str(content["difficulty"])),
            teacher_notes=None,
            manual_original=bool(content["manual_original"]),
        )
        return CatalogCard(
            row.id,
            ComponentStatus.PUBLISHED,
            data,
            CategoryItem(category.id, category.key, category.name),
            snapshot.revision,
            snapshot.created_at,
            snapshot.created_at,
        )
