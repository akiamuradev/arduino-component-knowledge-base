"""Catalog-aware review plans and conservative additive draft merges."""

from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.domain import Difficulty, DraftData, TechnicalSpecification
from arduino_component_kb.catalog.models import Category, Component
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.deduplication.scoring import ComponentSignals, score_pair, text_hashes
from arduino_component_kb.legacy.models import LegacyBundle, LegacyItem
from arduino_component_kb.legacy.parser import Target, digest, models, normalize

CATEGORY_KEYS = {
    "РАДИОКОМПОНЕНТЫ": "semiconductors",
    "МАКЕТНЫЕ ПЛАТЫ И ПИТАНИЕ": "power",
    "КНОПОЧНЫЕ ПЕРЕКЛЮЧАТЕЛИ И ВЫКЛЮЧАТЕЛИ": "input",
    "ИНТЕГРАЛЬНЫЕ СХЕМЫ": "integrated-circuits",
    "РЕЛЕ": "actuators",
    "СВЕТОДИОДНЫЕ МОДУЛЯ": "displays",
    "ДВИГАТЕЛИ И СЕРВОПРИВОДЫ": "actuators",
    "ДАТЧИКИ": "sensors",
    "МОДУЛЯ": "other",
    "ДИСПЛЕИ": "displays",
    "ПЛАТФОРМЫ РАЗРАБОТКИ": "boards",
    "ПЛАТЫ РАСШИРЕНИЯ": "boards",
}


async def category_id(session: AsyncSession, target: Target) -> UUID:
    result = await session.scalar(
        select(Category.id).where(
            Category.key == CATEGORY_KEYS[target.category],
            Category.is_active.is_(True),
        )
    )
    if result is None:
        raise ValueError("legacy_category_unavailable")
    return result


async def candidates(session: AsyncSession, target: Target) -> list[dict[str, object]]:
    """Use the existing weighted scorer; preserve conflicts, never auto-merge them."""
    category = await category_id(session, target)
    similarity = func.similarity(Component.title, target.title)
    rows = await session.scalars(
        select(Component)
        .where(
            Component.primary_category_id == category,
            similarity >= 0.15,
        )
        .order_by(similarity.desc(), Component.id)
        .limit(20)
    )
    result: list[dict[str, object]] = []
    for row in rows:
        card = await CatalogService(session).get_card(row.id)
        left = ComponentSignals(
            title=target.title,
            specifications=tuple((s.label, s.value) for s in target.specifications),
            text_hashes=text_hashes(target.description),
            media_sha256=frozenset(i.sha256 for i in target.images),
        )
        right = ComponentSignals(
            title=row.title,
            aliases=card.data.aliases,
            manufacturer=row.manufacturer,
            model=row.model,
            specifications=tuple((s.label, s.value_text) for s in card.data.specifications),
            text_hashes=text_hashes(row.description),
        )
        score = score_pair(
            left,
            right,
            SequenceMatcher(None, normalize(target.title), normalize(row.title)).ratio(),
        )
        conflict = bool(
            models(target.title) and models(row.title) and models(target.title) != models(row.title)
        )
        if score.score >= 0.35 or normalize(target.title) == normalize(row.title):
            result.append(
                {
                    "id": str(row.id),
                    "title": row.title,
                    "revision": row.revision,
                    "status": row.status,
                    "score": score.score,
                    "evidence": score.evidence,
                    "merge_allowed": row.status == "draft"
                    and row.published_at is None
                    and not conflict,
                    "model_conflict": conflict,
                }
            )
    return sorted(result, key=lambda r: (-float(str(r["score"])), str(r["id"])))[:5]


def review_hash(bundle: LegacyBundle, items: list[LegacyItem]) -> str:
    return digest(
        [
            bundle.plan_hash,
            [
                [str(i.id), i.decision, str(i.merge_id) if i.merge_id else None, i.merge_revision]
                for i in sorted(items, key=lambda item: item.position)
            ],
        ]
    )


def draft_data(target: Target, category: UUID) -> DraftData:
    specs: dict[str, TechnicalSpecification] = {}
    for spec in target.specifications:
        key = "legacy-" + digest(normalize(spec.label))[:24]
        if key not in specs:
            specs[key] = TechnicalSpecification(
                key=key,
                label=spec.label,
                value_text=spec.value,
                value_number=None,
                unit=spec.unit,
                position=len(specs),
            )
    return DraftData(
        slug="",
        title=target.title,
        aliases=(),
        manufacturer=None,
        model=None,
        primary_category_id=category,
        tags=(),
        summary="",
        description=target.description,
        purpose=None,
        usage_notes=None,
        safety_notes=None,
        difficulty=Difficulty.BEGINNER,
        teacher_notes=None,
        manual_original=False,
        specifications=tuple(specs.values()),
    )


def merge_data(existing: DraftData, incoming: DraftData) -> tuple[DraftData, list[str]]:
    warnings: list[str] = []
    by_label = {normalize(s.label): s for s in existing.specifications}
    specs = list(existing.specifications)
    for spec in incoming.specifications:
        previous = by_label.get(normalize(spec.label))
        if previous is None:
            specs.append(replace(spec, position=len(specs)))
            by_label[normalize(spec.label)] = spec
        elif (previous.value_text, previous.unit) != (spec.value_text, spec.unit):
            warnings.append("existing_specification_preserved")
    if (
        existing.description
        and incoming.description
        and existing.description != incoming.description
    ):
        warnings.append("existing_description_preserved")
    aliases = tuple(dict.fromkeys((*existing.aliases, *incoming.aliases, incoming.title)))
    aliases = tuple(a for a in aliases if normalize(a) != normalize(existing.title))
    return replace(
        existing,
        description=existing.description or incoming.description,
        summary=existing.summary or incoming.summary,
        aliases=aliases,
        specifications=tuple(specs),
    ), warnings
