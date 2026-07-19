"""Transactional catalog CRUD and lifecycle policy."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.domain import (
    CatalogCard,
    CatalogValidationError,
    CategoryItem,
    CodeExample,
    CodeExampleVisibility,
    CompatibilityItem,
    ComponentNotFoundError,
    ComponentStatus,
    Difficulty,
    DraftData,
    RevisionConflictError,
    SourceSnapshot,
    TechnicalSpecification,
)
from arduino_component_kb.catalog.models import (
    Category,
    CodeExampleHint,
    Component,
    ComponentAlias,
    ComponentCompatibility,
    ComponentProperty,
    ComponentRevision,
    ComponentTag,
    PropertyDefinition,
    PublishedSearchDocument,
    Tag,
    Unit,
)
from arduino_component_kb.catalog.models import (
    CodeExample as CodeExampleRow,
)
from arduino_component_kb.catalog.normalization import normalize_exact_identity

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _snapshot_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CatalogValidationError
    return tuple(value)


def _snapshot_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CatalogValidationError
    return value


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
        needle = _normalized(query) if query else ""
        conditions = [
            Component.status != ComponentStatus.ARCHIVED.value,
            Category.is_active.is_(True),
        ]
        if category_id is not None:
            conditions.append(PublishedSearchDocument.category_id == category_id)
        if difficulty is not None:
            conditions.append(PublishedSearchDocument.difficulty == difficulty.value)

        rank = None
        if needle:
            tsquery = func.plainto_tsquery("simple", needle)
            full_text_match = PublishedSearchDocument.search_vector.op("@@")(tsquery)
            trigram_match = PublishedSearchDocument.search_text.op("%>")(needle)
            conditions.append(or_(full_text_match, trigram_match))
            rank = (
                func.ts_rank_cd(PublishedSearchDocument.search_vector, tsquery)
                + func.word_similarity(needle, PublishedSearchDocument.search_text) * 0.35
            )

        base = (
            select(Component.id)
            .join(
                PublishedSearchDocument,
                PublishedSearchDocument.component_id == Component.id,
            )
            .join(Category, Category.id == PublishedSearchDocument.category_id)
            .where(*conditions)
        )
        if rank is not None:
            base = base.order_by(
                rank.desc(), PublishedSearchDocument.published_at.desc(), Component.id
            )
        else:
            base = base.order_by(PublishedSearchDocument.published_at.desc(), Component.id)
        rows = await self.session.scalars(base.limit(limit))
        total = await self.session.scalar(
            select(func.count())
            .select_from(PublishedSearchDocument)
            .join(Component, Component.id == PublishedSearchDocument.component_id)
            .join(Category, Category.id == PublishedSearchDocument.category_id)
            .where(*conditions)
        )
        cards = [
            card
            for component_id in rows
            if (card := await self._published_card(component_id)) is not None
        ]
        return cards, int(total or 0)

    async def get_published(self, slug: str) -> CatalogCard:
        row = await self.session.scalar(
            select(Component).where(
                Component.slug == slug,
                Component.status != ComponentStatus.ARCHIVED.value,
            )
        )
        if row is None:
            raise ComponentNotFoundError
        card = await self._published_card(row.id)
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
        await self._replace_technical(row.id, data)
        await self._replace_learning(row.id, data, actor_id, now)
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
        await self._replace_technical(row.id, data)
        await self._replace_learning(row.id, data, actor_id, now)
        await self._snapshot(row, data, actor_id, now)
        return await self._card(row)

    async def transition(
        self, component_id: UUID, expected_revision: int, target: ComponentStatus, actor_id: UUID
    ) -> CatalogCard:
        row = await self._locked(component_id)
        if row.revision != expected_revision:
            raise RevisionConflictError
        if target is ComponentStatus.PUBLISHED:
            from arduino_component_kb.deduplication.models import DuplicateCandidate
            from arduino_component_kb.deduplication.scoring import HIGH_SCORE_THRESHOLD

            source_rows = await self._component_source_rows(row.id)
            high_duplicates = await self.session.scalar(
                select(func.count())
                .select_from(DuplicateCandidate)
                .where(
                    DuplicateCandidate.status == "open",
                    DuplicateCandidate.score >= HIGH_SCORE_THRESHOLD,
                    or_(
                        DuplicateCandidate.left_component_id == row.id,
                        DuplicateCandidate.right_component_id == row.id,
                    ),
                )
            )
            if (
                row.status != ComponentStatus.DRAFT.value
                or (not row.manual_original and not source_rows)
                or high_duplicates != 0
                or not row.description.strip()
            ):
                raise CatalogValidationError
            if not row.manual_original:
                self._validate_publish_sources(source_rows)
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
        if target is ComponentStatus.PUBLISHED:
            await self._upsert_search_document(row, data, row.updated_at)
        else:
            await self.session.execute(
                delete(PublishedSearchDocument).where(
                    PublishedSearchDocument.component_id == row.id
                )
            )
        return await self._card(row)

    async def resolve_duplicate_pair(
        self,
        left_component_id: UUID,
        right_component_id: UUID,
        left_revision: int,
        right_revision: int,
        survivor_component_id: UUID,
        field_sources: dict[str, UUID],
        actor_id: UUID,
        *,
        merge_fields: bool,
    ) -> tuple[CatalogCard, CatalogCard, CatalogCard]:
        """Merge or attach one card into another under deterministic row locks."""
        ids = sorted((left_component_id, right_component_id))
        rows = list(
            await self.session.scalars(
                select(Component)
                .where(Component.id.in_(ids))
                .order_by(Component.id)
                .with_for_update()
            )
        )
        if len(rows) != 2:
            raise ComponentNotFoundError
        by_id = {row.id: row for row in rows}
        left = by_id[left_component_id]
        right = by_id[right_component_id]
        if left.revision != left_revision or right.revision != right_revision:
            raise RevisionConflictError
        if survivor_component_id not in by_id:
            raise CatalogValidationError
        survivor = by_id[survivor_component_id]
        loser = right if survivor is left else left
        before_left = await self._card(left)
        before_right = await self._card(right)
        survivor_data = await self._data(survivor)

        if merge_fields:
            allowed = {
                "title",
                "aliases",
                "manufacturer",
                "model",
                "primary_category_id",
                "tags",
                "summary",
                "description",
                "purpose",
                "usage_notes",
                "safety_notes",
                "difficulty",
                "teacher_notes",
                "specifications",
                "compatibility",
                "code_examples",
            }
            if not set(field_sources).issubset(allowed) or any(
                source_id not in by_id for source_id in field_sources.values()
            ):
                raise CatalogValidationError
            source_data = {
                component_id: await self._data(row) for component_id, row in by_id.items()
            }

            def chosen(field: str) -> object:
                source_id = field_sources.get(field, survivor.id)
                return getattr(source_data[source_id], field)

            survivor_data = DraftData(
                slug=survivor_data.slug,
                title=cast(str, chosen("title")),
                aliases=cast(tuple[str, ...], chosen("aliases")),
                manufacturer=cast(str | None, chosen("manufacturer")),
                model=cast(str | None, chosen("model")),
                primary_category_id=cast(UUID, chosen("primary_category_id")),
                tags=cast(tuple[str, ...], chosen("tags")),
                summary=cast(str, chosen("summary")),
                description=cast(str, chosen("description")),
                purpose=cast(str | None, chosen("purpose")),
                usage_notes=cast(str | None, chosen("usage_notes")),
                safety_notes=cast(str | None, chosen("safety_notes")),
                difficulty=cast(Difficulty, chosen("difficulty")),
                teacher_notes=cast(str | None, chosen("teacher_notes")),
                manual_original=survivor_data.manual_original,
                specifications=cast(tuple[TechnicalSpecification, ...], chosen("specifications")),
                compatibility=cast(tuple[CompatibilityItem, ...], chosen("compatibility")),
                code_examples=cast(tuple[CodeExample, ...], chosen("code_examples")),
            )
            await self._validate(survivor_data)
            for key, value in self._columns(survivor_data).items():
                setattr(survivor, key, value)
            await self._replace_lists(survivor.id, survivor_data)
            await self._replace_technical(survivor.id, survivor_data)
            await self._replace_learning(survivor.id, survivor_data, actor_id, datetime.now(UTC))

        from arduino_component_kb.imports.models import ComponentSource
        from arduino_component_kb.media.models import MediaAsset

        await self.session.execute(
            update(ComponentSource)
            .where(ComponentSource.component_id == loser.id)
            .values(component_id=survivor.id)
        )
        await self.session.execute(
            update(MediaAsset)
            .where(MediaAsset.component_id == loser.id)
            .values(component_id=survivor.id)
        )
        now = datetime.now(UTC)
        survivor.status = ComponentStatus.DRAFT.value
        survivor.revision += 1
        survivor.updated_by = actor_id
        survivor.updated_at = now
        loser.status = ComponentStatus.ARCHIVED.value
        loser.revision += 1
        loser.updated_by = actor_id
        loser.updated_at = now
        await self.session.execute(
            delete(PublishedSearchDocument).where(PublishedSearchDocument.component_id == loser.id)
        )
        await self._snapshot(survivor, survivor_data, actor_id, now)
        await self._snapshot(loser, await self._data(loser), actor_id, now)
        await self.session.flush()
        return before_left, before_right, await self._card(survivor)

    async def _upsert_search_document(
        self, row: Component, data: DraftData, published_at: datetime
    ) -> None:
        identity_text = " ".join((*data.aliases, data.manufacturer or "", data.model or ""))
        content_text = " ".join((data.summary, *data.tags))
        search_text = _normalized(" ".join((data.title, identity_text, content_text)))
        search_vector = (
            func.setweight(func.to_tsvector("simple", data.title), "A")
            .op("||")(func.setweight(func.to_tsvector("simple", identity_text), "B"))
            .op("||")(func.setweight(func.to_tsvector("simple", content_text), "C"))
        )
        values: dict[str, object] = {
            "component_id": row.id,
            "revision": row.revision,
            "category_id": data.primary_category_id,
            "difficulty": data.difficulty.value,
            "title": data.title,
            "aliases_text": " ".join(data.aliases),
            "manufacturer": data.manufacturer or "",
            "model": data.model or "",
            "summary": data.summary,
            "tags_text": " ".join(data.tags),
            "search_text": search_text,
            "search_vector": search_vector,
            "published_at": published_at,
        }
        statement = insert(PublishedSearchDocument).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[PublishedSearchDocument.component_id],
                set_={key: value for key, value in values.items() if key != "component_id"},
            )
        )

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
            or len(data.specifications) > 50
            or len(data.compatibility) > 30
            or len(data.code_examples) > 10
        ):
            raise CatalogValidationError
        category = await self.session.get(Category, data.primary_category_id)
        if category is None or not category.is_active:
            raise CatalogValidationError
        if len({_normalized(x) for x in data.aliases}) != len(data.aliases) or len(
            {_normalized(x) for x in data.tags}
        ) != len(data.tags):
            raise CatalogValidationError
        specification_keys: set[str] = set()
        for item in data.specifications:
            if (
                not _SLUG.fullmatch(item.key)
                or not item.label.strip()
                or len(item.label.strip()) > 160
                or not item.value_text.strip()
                or len(item.value_text.strip()) > 2000
                or (item.unit is not None and len(item.unit.strip()) > 32)
                or item.key in specification_keys
            ):
                raise CatalogValidationError
            if item.value_number is not None:
                try:
                    number = Decimal(item.value_number)
                except InvalidOperation as error:
                    raise CatalogValidationError from error
                exponent = number.as_tuple().exponent
                if (
                    not number.is_finite()
                    or not isinstance(exponent, int)
                    or exponent < -8
                    or number.adjusted() > 15
                ):
                    raise CatalogValidationError
            specification_keys.add(item.key)
        compatibility_keys: set[tuple[str, str, str]] = set()
        for compatibility_item in data.compatibility:
            key = (
                compatibility_item.target_type,
                _normalized(compatibility_item.name),
                _normalized(compatibility_item.version_constraint or ""),
            )
            if (
                compatibility_item.target_type not in {"board", "library", "platform"}
                or not compatibility_item.name.strip()
                or len(compatibility_item.name.strip()) > 160
                or (
                    compatibility_item.version_constraint is not None
                    and len(compatibility_item.version_constraint) > 120
                )
                or (compatibility_item.notes is not None and len(compatibility_item.notes) > 2000)
                or key in compatibility_keys
            ):
                raise CatalogValidationError
            compatibility_keys.add(key)
        for example in data.code_examples:
            if (
                not example.title.strip()
                or len(example.title.strip()) > 160
                or not re.fullmatch(r"[a-z0-9][a-z0-9_+.#-]{0,31}", example.language)
                or not example.practical_task.strip()
                or len(example.practical_task) > 5000
                or not example.body.strip()
                or len(example.body.encode("utf-8")) > 65536
                or (example.explanation is not None and len(example.explanation) > 10000)
                or len(example.hints) > 10
                or any(not hint.strip() or len(hint) > 2000 for hint in example.hints)
                or len(example.libraries) > 20
                or any(not item.strip() or len(item) > 100 for item in example.libraries)
                or len({_normalized(item) for item in example.libraries}) != len(example.libraries)
            ):
                raise CatalogValidationError

    @staticmethod
    def _columns(data: DraftData) -> dict[str, object]:
        columns = {
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
        columns["normalized_manufacturer"] = normalize_exact_identity(data.manufacturer)
        columns["normalized_model"] = normalize_exact_identity(data.model)
        return columns

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

    async def _replace_technical(self, component_id: UUID, data: DraftData) -> None:
        await self.session.execute(
            delete(ComponentProperty).where(ComponentProperty.component_id == component_id)
        )
        await self.session.execute(
            delete(ComponentCompatibility).where(
                ComponentCompatibility.component_id == component_id
            )
        )
        for position, item in enumerate(data.specifications):
            unit = await self._unit(item.unit)
            definition = await self.session.scalar(
                select(PropertyDefinition).where(PropertyDefinition.key == item.key)
            )
            value_type = "number" if item.value_number is not None else "text"
            if definition is None:
                definition = PropertyDefinition(
                    id=uuid4(),
                    key=item.key,
                    label=item.label.strip(),
                    value_type=value_type,
                    unit_id=unit.id if unit is not None else None,
                    is_multivalue=False,
                )
                self.session.add(definition)
                await self.session.flush()
            elif (
                definition.label != item.label.strip()
                or definition.value_type != value_type
                or definition.unit_id != (unit.id if unit is not None else None)
            ):
                raise CatalogValidationError
            self.session.add(
                ComponentProperty(
                    id=uuid4(),
                    component_id=component_id,
                    definition_id=definition.id,
                    value_text=item.value_text.strip(),
                    value_number=(
                        Decimal(item.value_number) if item.value_number is not None else None
                    ),
                    position=position,
                )
            )
        self.session.add_all(
            [
                ComponentCompatibility(
                    id=uuid4(),
                    component_id=component_id,
                    target_type=item.target_type,
                    name=item.name.strip(),
                    version_constraint=(
                        item.version_constraint.strip() if item.version_constraint else None
                    ),
                    notes=item.notes.strip() if item.notes else None,
                    position=position,
                )
                for position, item in enumerate(data.compatibility)
            ]
        )

    async def _unit(self, symbol: str | None) -> Unit | None:
        if symbol is None or not symbol.strip():
            return None
        normalized = symbol.strip()
        unit = await self.session.scalar(select(Unit).where(Unit.symbol == normalized))
        if unit is None:
            unit = Unit(
                id=uuid4(),
                key=f"custom-{sha256(normalized.encode()).hexdigest()[:16]}",
                symbol=normalized,
                name=normalized,
            )
            self.session.add(unit)
            await self.session.flush()
        return unit

    async def _replace_learning(
        self, component_id: UUID, data: DraftData, actor_id: UUID, now: datetime
    ) -> None:
        await self.session.execute(
            delete(CodeExampleRow).where(CodeExampleRow.component_id == component_id)
        )
        for position, item in enumerate(data.code_examples):
            example = CodeExampleRow(
                id=uuid4(),
                component_id=component_id,
                title=item.title.strip(),
                language=item.language,
                practical_task=item.practical_task.strip(),
                body=item.body,
                libraries_json=[library.strip() for library in item.libraries],
                explanation=item.explanation.strip() if item.explanation else None,
                visibility=item.visibility.value,
                position=position,
                created_by=actor_id,
                updated_at=now,
            )
            self.session.add(example)
            self.session.add_all(
                [
                    CodeExampleHint(
                        id=uuid4(), example_id=example.id, body=hint.strip(), position=hint_position
                    )
                    for hint_position, hint in enumerate(item.hints)
                ]
            )

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
        specification_rows = await self.session.execute(
            select(ComponentProperty, PropertyDefinition, Unit)
            .join(PropertyDefinition, PropertyDefinition.id == ComponentProperty.definition_id)
            .outerjoin(Unit, Unit.id == PropertyDefinition.unit_id)
            .where(ComponentProperty.component_id == row.id)
            .order_by(ComponentProperty.position)
        )
        compatibility_rows = await self.session.scalars(
            select(ComponentCompatibility)
            .where(ComponentCompatibility.component_id == row.id)
            .order_by(ComponentCompatibility.position)
        )
        example_rows = list(
            await self.session.scalars(
                select(CodeExampleRow)
                .where(CodeExampleRow.component_id == row.id)
                .order_by(CodeExampleRow.position)
            )
        )
        code_examples: list[CodeExample] = []
        for example in example_rows:
            hints = await self.session.scalars(
                select(CodeExampleHint.body)
                .where(CodeExampleHint.example_id == example.id)
                .order_by(CodeExampleHint.position)
            )
            code_examples.append(
                CodeExample(
                    title=example.title,
                    language=example.language,
                    practical_task=example.practical_task,
                    hints=tuple(hints),
                    body=example.body,
                    libraries=tuple(example.libraries_json),
                    explanation=example.explanation,
                    visibility=CodeExampleVisibility(example.visibility),
                    position=example.position,
                )
            )
        return DraftData(
            aliases=tuple(aliases),
            tags=tuple(tags),
            specifications=tuple(
                TechnicalSpecification(
                    key=definition.key,
                    label=definition.label,
                    value_text=property_row.value_text,
                    value_number=(
                        str(property_row.value_number)
                        if property_row.value_number is not None
                        else None
                    ),
                    unit=unit.symbol if unit is not None else None,
                    position=property_row.position,
                )
                for property_row, definition, unit in specification_rows
            ),
            compatibility=tuple(
                CompatibilityItem(
                    target_type=item.target_type,
                    name=item.name,
                    version_constraint=item.version_constraint,
                    notes=item.notes,
                    position=item.position,
                )
                for item in compatibility_rows
            ),
            code_examples=tuple(code_examples),
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
            await self._source_snapshots(row.id),
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
                "specifications": [
                    {
                        "key": item.key,
                        "label": item.label,
                        "value_text": item.value_text,
                        "value_number": item.value_number,
                        "unit": item.unit,
                        "position": item.position,
                    }
                    for item in data.specifications
                ],
                "compatibility": [
                    {
                        "target_type": item.target_type,
                        "name": item.name,
                        "version_constraint": item.version_constraint,
                        "notes": item.notes,
                        "position": item.position,
                    }
                    for item in data.compatibility
                ],
                "code_examples": [
                    {
                        "title": item.title,
                        "language": item.language,
                        "practical_task": item.practical_task,
                        "hints": list(item.hints),
                        "body": item.body,
                        "libraries": list(item.libraries),
                        "explanation": item.explanation,
                        "visibility": item.visibility.value,
                        "position": item.position,
                    }
                    for item in data.code_examples
                ],
                "sources": [
                    self._source_snapshot_dict(item)
                    for item in await self._source_snapshots(row.id)
                ],
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

    async def _published_card(self, component_id: UUID) -> CatalogCard | None:
        snapshot = await self.session.scalar(
            select(ComponentRevision)
            .where(
                ComponentRevision.component_id == component_id,
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
        specifications = _snapshot_records(content.get("specifications", []))
        compatibility = _snapshot_records(content.get("compatibility", []))
        code_examples = _snapshot_records(content.get("code_examples", []))
        source_records = _snapshot_records(content.get("sources", []))
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
            specifications=tuple(
                TechnicalSpecification(
                    key=str(item["key"]),
                    label=str(item["label"]),
                    value_text=str(item["value_text"]),
                    value_number=(
                        str(item["value_number"]) if item.get("value_number") is not None else None
                    ),
                    unit=str(item["unit"]) if item.get("unit") else None,
                    position=int(str(item["position"])),
                )
                for item in specifications
            ),
            compatibility=tuple(
                CompatibilityItem(
                    target_type=str(item["target_type"]),
                    name=str(item["name"]),
                    version_constraint=(
                        str(item["version_constraint"]) if item.get("version_constraint") else None
                    ),
                    notes=str(item["notes"]) if item.get("notes") else None,
                    position=int(str(item["position"])),
                )
                for item in compatibility
            ),
            code_examples=tuple(
                CodeExample(
                    title=str(item["title"]),
                    language=str(item["language"]),
                    practical_task=str(item["practical_task"]),
                    hints=_snapshot_strings(item.get("hints", [])),
                    body=str(item["body"]),
                    libraries=_snapshot_strings(item.get("libraries", [])),
                    explanation=(str(item["explanation"]) if item.get("explanation") else None),
                    visibility=CodeExampleVisibility(str(item["visibility"])),
                    position=int(str(item["position"])),
                )
                for item in code_examples
                if item.get("visibility") == CodeExampleVisibility.STUDENT.value
            ),
        )
        return CatalogCard(
            component_id,
            ComponentStatus.PUBLISHED,
            data,
            CategoryItem(category.id, category.key, category.name),
            snapshot.revision,
            snapshot.created_at,
            snapshot.created_at,
            tuple(self._source_snapshot_from_dict(item) for item in source_records),
        )

    async def _component_source_rows(self, component_id: UUID) -> list[tuple[object, object]]:
        from arduino_component_kb.imports.models import ComponentSource, Source

        rows = await self.session.execute(
            select(ComponentSource, Source)
            .join(Source, Source.id == ComponentSource.source_id)
            .where(ComponentSource.component_id == component_id)
            .order_by(ComponentSource.imported_at, ComponentSource.id)
        )
        return [(row[0], row[1]) for row in rows]

    def _validate_publish_sources(self, rows: list[tuple[object, object]]) -> None:
        from arduino_component_kb.imports.models import ComponentSource, Source

        for raw_relation, raw_source in rows:
            relation = cast(ComponentSource, raw_relation)
            source = cast(Source, raw_source)
            if source.permission_status == "denied":
                raise CatalogValidationError("source_permission_denied")
            if source.status != "active" or not source.is_enabled:
                raise CatalogValidationError("source_inactive")
            if source.permission_status != "license_granted":
                raise CatalogValidationError("source_license_unknown")
            if not relation.source_revision:
                raise CatalogValidationError("source_revision_missing")
            if not relation.original_url and not source.repository_url:
                raise CatalogValidationError("source_origin_missing")
            if not all(
                (
                    relation.license_snapshot_name,
                    relation.license_snapshot_spdx,
                    relation.license_snapshot_url,
                )
            ):
                raise CatalogValidationError("source_license_missing")
            if not relation.attribution_snapshot:
                raise CatalogValidationError("source_attribution_missing")
            if not relation.modifications_notice:
                raise CatalogValidationError("source_modifications_notice_missing")

    async def _source_snapshots(self, component_id: UUID) -> tuple[SourceSnapshot, ...]:
        from arduino_component_kb.imports.models import ComponentSource, Source

        result: list[SourceSnapshot] = []
        for raw_relation, raw_source in await self._component_source_rows(component_id):
            relation = cast(ComponentSource, raw_relation)
            source = cast(Source, raw_source)
            if not all(
                (
                    source.display_name,
                    relation.source_revision,
                    relation.license_snapshot_name,
                    relation.license_snapshot_spdx,
                    relation.license_snapshot_url,
                    relation.modifications_notice,
                    relation.imported_at,
                    relation.attribution_snapshot,
                    relation.parser_name,
                    relation.parser_version,
                )
            ):
                continue
            result.append(
                SourceSnapshot(
                    display_name=source.display_name,
                    original_url=relation.original_url,
                    repository_url=source.repository_url,
                    license_name=cast(str, relation.license_snapshot_name),
                    license_spdx=cast(str, relation.license_snapshot_spdx),
                    license_url=cast(str, relation.license_snapshot_url),
                    source_revision=cast(str, relation.source_revision),
                    source_tag=relation.source_tag,
                    source_file_path=relation.source_file_path,
                    source_entry_name=relation.source_entry_name,
                    modifications_notice=cast(str, relation.modifications_notice),
                    imported_at=cast(datetime, relation.imported_at),
                    attribution=cast(str, relation.attribution_snapshot),
                    parser_name=cast(str, relation.parser_name),
                    parser_version=cast(str, relation.parser_version),
                )
            )
        return tuple(result)

    def _source_snapshot_dict(self, item: SourceSnapshot) -> dict[str, object]:
        return {
            "display_name": item.display_name,
            "original_url": item.original_url,
            "repository_url": item.repository_url,
            "license_name": item.license_name,
            "license_spdx": item.license_spdx,
            "license_url": item.license_url,
            "source_revision": item.source_revision,
            "source_tag": item.source_tag,
            "source_file_path": item.source_file_path,
            "source_entry_name": item.source_entry_name,
            "modifications_notice": item.modifications_notice,
            "imported_at": item.imported_at.isoformat(),
            "attribution": item.attribution,
            "parser_name": item.parser_name,
            "parser_version": item.parser_version,
        }

    def _source_snapshot_from_dict(self, item: dict[str, object]) -> SourceSnapshot:
        return SourceSnapshot(
            display_name=str(item["display_name"]),
            original_url=str(item["original_url"]) if item.get("original_url") else None,
            repository_url=str(item["repository_url"]) if item.get("repository_url") else None,
            license_name=str(item["license_name"]),
            license_spdx=str(item["license_spdx"]),
            license_url=str(item["license_url"]),
            source_revision=str(item["source_revision"]),
            source_tag=str(item["source_tag"]) if item.get("source_tag") else None,
            source_file_path=(
                str(item["source_file_path"]) if item.get("source_file_path") else None
            ),
            source_entry_name=(
                str(item["source_entry_name"]) if item.get("source_entry_name") else None
            ),
            modifications_notice=str(item["modifications_notice"]),
            imported_at=datetime.fromisoformat(str(item["imported_at"])),
            attribution=str(item["attribution"]),
            parser_name=str(item["parser_name"]),
            parser_version=str(item["parser_version"]),
        )
