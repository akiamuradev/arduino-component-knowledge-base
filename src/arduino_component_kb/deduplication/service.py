"""Bounded PostgreSQL preselection and durable fuzzy candidate generation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.catalog.models import (
    Component,
    ComponentAlias,
    ComponentProperty,
    PropertyDefinition,
)
from arduino_component_kb.deduplication.models import DuplicateCandidate
from arduino_component_kb.deduplication.scoring import (
    ALGORITHM_VERSION,
    CANDIDATE_THRESHOLD,
    ComponentSignals,
    score_pair,
    text_hashes,
)
from arduino_component_kb.media.models import MediaAsset

_PRESELECTION_THRESHOLD = 0.20
_PRESELECTION_LIMIT = 50


class FuzzyCandidateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate(self, component_id: UUID) -> int:
        component = await self.session.get(Component, component_id)
        if component is None:
            return 0
        source_signals = await self._signals(component)
        created = 0
        for candidate_id, trigram in await self._preselect(component):
            candidate = await self.session.get(Component, candidate_id)
            if candidate is None:
                continue
            result = score_pair(source_signals, await self._signals(candidate), trigram)
            if result.score < CANDIDATE_THRESHOLD:
                continue
            left_id, right_id = sorted((component.id, candidate.id), key=lambda value: value.int)
            row = await self.session.scalar(
                select(DuplicateCandidate).where(
                    DuplicateCandidate.left_component_id == left_id,
                    DuplicateCandidate.right_component_id == right_id,
                    DuplicateCandidate.algorithm_version == ALGORITHM_VERSION,
                    DuplicateCandidate.status == "open",
                )
            )
            evidence = {
                **result.evidence,
                "preselection": {"pg_trgm": round(trigram, 4)},
            }
            if row is None:
                self.session.add(
                    DuplicateCandidate(
                        id=uuid4(),
                        left_component_id=left_id,
                        right_component_id=right_id,
                        kind="fuzzy",
                        status="open",
                        score=Decimal(str(result.score)),
                        algorithm_version=ALGORITHM_VERSION,
                        evidence_json=evidence,
                        created_at=datetime.now(UTC),
                    )
                )
                created += 1
            else:
                row.score = Decimal(str(result.score))
                row.evidence_json = evidence
        return created

    async def _preselect(self, source: Component) -> list[tuple[UUID, float]]:
        await self.session.execute(
            select(
                func.set_config(
                    "pg_trgm.similarity_threshold",
                    str(_PRESELECTION_THRESHOLD),
                    True,
                )
            )
        )
        title_similarity = func.similarity(Component.title, source.title)
        model_similarity = func.similarity(func.coalesce(Component.model, ""), source.model or "")
        similarity = func.greatest(title_similarity, model_similarity)
        indexed_matches = [Component.title.op("%")(source.title)]
        if source.model:
            indexed_matches.append(Component.model.op("%")(source.model))
        rows = await self.session.execute(
            select(Component.id, similarity.label("trigram"))
            .where(
                Component.id != source.id,
                Component.status != "archived",
                or_(*indexed_matches),
            )
            .order_by(similarity.desc(), Component.id)
            .limit(_PRESELECTION_LIMIT)
        )
        return [(component_id, float(trigram)) for component_id, trigram in rows]

    async def _signals(self, component: Component) -> ComponentSignals:
        aliases = tuple(
            await self.session.scalars(
                select(ComponentAlias.alias)
                .where(ComponentAlias.component_id == component.id)
                .order_by(ComponentAlias.position)
            )
        )
        property_rows = await self.session.execute(
            select(PropertyDefinition.key, ComponentProperty.value_text)
            .join(
                PropertyDefinition,
                PropertyDefinition.id == ComponentProperty.definition_id,
            )
            .where(ComponentProperty.component_id == component.id)
            .order_by(ComponentProperty.position)
        )
        media_rows = await self.session.execute(
            select(MediaAsset.sha256, MediaAsset.phash).where(
                MediaAsset.component_id == component.id,
                MediaAsset.status == "ready",
            )
        )
        media = list(media_rows)
        return ComponentSignals(
            title=component.title,
            aliases=aliases,
            manufacturer=component.manufacturer,
            model=component.model,
            specifications=tuple((key, value) for key, value in property_rows),
            text_hashes=text_hashes(component.title, component.summary, component.description),
            media_sha256=frozenset(
                cast(str, sha_value) for sha_value, _ in media if sha_value is not None
            ),
            media_phashes=frozenset(cast(str, phash) for _, phash in media if phash is not None),
        )
