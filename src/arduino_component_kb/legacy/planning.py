"""Catalog-aware review plans and conservative additive draft merges."""

from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.domain import Difficulty, DraftData, TechnicalSpecification
from arduino_component_kb.catalog.models import Category, Component, ComponentAlias
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.deduplication.scoring import ComponentSignals, score_pair, text_hashes
from arduino_component_kb.legacy.models import LegacyBundle, LegacyItem
from arduino_component_kb.legacy.parser import Target, digest, models, normalize
from arduino_component_kb.media.models import MediaAsset

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
    model_match = func.lower(func.trim(Component.model)).in_(models(target.title))
    alias_match = (
        select(ComponentAlias.id)
        .where(
            ComponentAlias.component_id == Component.id,
            func.lower(ComponentAlias.alias) == target.title.casefold(),
        )
        .exists()
    )
    image_hashes = frozenset(image.sha256 for image in target.images)
    image_match = (
        select(MediaAsset.id)
        .where(
            MediaAsset.component_id == Component.id,
            MediaAsset.status != "rejected",
            MediaAsset.sha256.in_(image_hashes),
        )
        .exists()
    )
    rows = await session.scalars(
        select(Component)
        .where(
            or_(
                and_(Component.primary_category_id == category, similarity >= 0.15),
                model_match,
                alias_match,
                image_match,
            ),
        )
        .order_by(
            model_match.desc().nulls_last(),
            alias_match.desc(),
            image_match.desc(),
            similarity.desc(),
            Component.id,
        )
        .limit(20)
    )
    result: list[dict[str, object]] = []
    for row in rows:
        card = await CatalogService(session).get_card(row.id)
        assets = list(
            await session.scalars(
                select(MediaAsset).where(
                    MediaAsset.component_id == row.id,
                    MediaAsset.status != "rejected",
                )
            )
        )
        existing_hashes = frozenset(asset.sha256 for asset in assets if asset.sha256)
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
            media_sha256=existing_hashes,
        )
        score = score_pair(
            left,
            right,
            SequenceMatcher(None, normalize(target.title), normalize(row.title)).ratio(),
        )
        wanted_models = models(target.title)
        found_models = models(row.title) | models(row.model or "")
        conflict = bool(wanted_models and found_models and wanted_models != found_models)
        strong_identity = normalize(row.model or "") in models(target.title) or any(
            normalize(alias) == normalize(target.title) for alias in card.data.aliases
        )
        if (
            score.score >= 0.35
            or normalize(target.title) == normalize(row.title)
            or strong_identity
            or image_hashes & existing_hashes
        ):
            result.append(
                {
                    "id": str(row.id),
                    "title": row.title,
                    "revision": row.revision,
                    "edit_token": row.edit_token,
                    "status": row.status,
                    "score": score.score,
                    "evidence": score.evidence,
                    "merge_allowed": row.status == "draft"
                    and row.primary_category_id == category
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
                [
                    i.identity,
                    i.decision,
                    str(i.merge_id) if i.merge_id else None,
                    i.merge_revision,
                    i.merge_edit_token,
                ]
                for i in sorted(items, key=lambda item: item.position)
            ],
        ]
    )


def exceeds_draft_limits(target: Target) -> bool:
    return (
        len(target.description) > 30000
        or len(target.specifications) > 50
        or any(len(spec.unit or "") > 32 for spec in target.specifications)
    )


def draft_data(target: Target, category: UUID) -> DraftData:
    if exceeds_draft_limits(target):
        raise ValueError("legacy_draft_limits_review_required")
    specs: dict[str, TechnicalSpecification] = {}
    for spec in target.specifications:
        key = "legacy-" + digest([normalize(spec.label), normalize(spec.unit or "")])[:24]
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
            if len(specs) < 50:
                specs.append(replace(spec, position=len(specs)))
                by_label[normalize(spec.label)] = spec
            else:
                warnings.append("specification_limit_preserved_in_plan")
        elif (previous.value_text, previous.unit) != (spec.value_text, spec.unit):
            warnings.append("existing_specification_preserved")
    if (
        existing.description
        and incoming.description
        and existing.description != incoming.description
    ):
        warnings.append("existing_description_preserved")
    aliases = list(existing.aliases)
    seen = {normalize(a) for a in (*existing.aliases, existing.title)}
    for alias in (*incoming.aliases, incoming.title):
        canonical = normalize(alias)
        if canonical in seen:
            continue
        if len(aliases) >= 20 or len(alias.strip()) > 100:
            warnings.append("alias_limit_preserved_in_plan")
            continue
        aliases.append(alias.strip())
        seen.add(canonical)
    return replace(
        existing,
        description=existing.description or incoming.description,
        summary=existing.summary or incoming.summary,
        aliases=tuple(aliases),
        specifications=tuple(specs),
    ), warnings
