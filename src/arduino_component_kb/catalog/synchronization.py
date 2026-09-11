"""Document mutations: edit tokens are not semantic history revisions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.domain import (
    CatalogCard,
    CatalogValidationError,
    ComponentMediaNotFoundError,
    ComponentStatus,
    DraftData,
    RevisionConflictError,
)
from arduino_component_kb.catalog.models import Component, EditorCreation
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.logging import current_request_id
from arduino_component_kb.media.domain import ComponentImageMutation
from arduino_component_kb.media.models import MediaAsset
from arduino_component_kb.media.repository import MediaRepository


class DocumentSynchronization:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.catalog = CatalogService(session)

    async def lock(self, component_id: UUID, token: int) -> Component:
        row = await self.catalog._locked(component_id)
        if row.edit_token != token:
            raise RevisionConflictError
        return row

    async def create(self, request_id: UUID, data: DraftData, actor_id: UUID) -> CatalogCard:
        # Protect a retry after a lost HTTP response, including parallel initial POSTs.
        lock_key = int.from_bytes(request_id.bytes[:8], "big", signed=True)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        existing = await self.session.get(EditorCreation, request_id)
        if existing is not None:
            if existing.owner_id != actor_id:
                raise CatalogValidationError("creation_key_unavailable")
            return await self.catalog.get_card(existing.component_id)
        card = await self.catalog.create(data, actor_id)
        self.session.add(
            EditorCreation(
                request_id=request_id,
                owner_id=actor_id,
                component_id=card.id,
                created_at=datetime.now(UTC),
            )
        )
        await AuthRepository(self.session).audit(
            now=datetime.now(UTC),
            actor_user_id=actor_id,
            action="component.created",
            object_type="component",
            object_id=card.id,
            request_id=current_request_id(),
            outcome="success",
        )
        return card

    async def synchronize(
        self,
        component_id: UUID,
        token: int,
        data: DraftData,
        images: tuple[ComponentImageMutation, ...],
        primary_id: UUID | None,
        actor_id: UUID,
    ) -> CatalogCard:
        row = await self.lock(component_id, token)
        self.catalog._require_editable(row)
        if not data.slug:
            raise CatalogValidationError("invalid_slug")
        previous = await self.catalog.get_card(component_id)
        before_ids = {image.asset_id for image in previous.media if image.kind.value == "image"}
        requested = {image.asset_id for image in images}
        if len(images) > 12 or len(requested) != len(images):
            raise CatalogValidationError("component_images_invalid")
        new_ids = requested - before_ids
        new_assets = (
            list(
                await self.session.scalars(
                    select(MediaAsset)
                    .where(
                        MediaAsset.id.in_(new_ids),
                    )
                    .order_by(MediaAsset.id)
                    .with_for_update()
                )
            )
            if new_ids
            else []
        )
        if len(new_assets) != len(new_ids):
            raise ComponentMediaNotFoundError
        usage = await MediaRepository(self.session).component_usage(component_id)
        if (
            usage.original_bytes + sum(a.declared_size_bytes for a in new_assets)
            > 600 * 1024 * 1024
        ):
            raise CatalogValidationError("media_component_size_exceeded")
        for asset in new_assets:
            if (
                asset.owner_user_id != actor_id
                or asset.component_id is not None
                or asset.kind != "image"
                or asset.status not in {"processing", "ready"}
                or asset.storage_cleaned_at is not None
            ):
                raise ComponentMediaNotFoundError
            # Primary/order/metadata are set together below after all checks.
            asset.component_id = component_id
            asset.is_primary = False
        await self.session.flush()
        await self.catalog.update(component_id, row.revision, data, actor_id, record_history=False)
        card = await self.catalog.mutate_images(
            component_id,
            row.revision,
            images,
            primary_id,
            actor_id,
            record_history=False,
        )
        if requested != before_ids:
            await AuthRepository(self.session).audit(
                now=datetime.now(UTC),
                actor_user_id=actor_id,
                action="component.images_updated",
                object_type="component",
                object_id=component_id,
                request_id=current_request_id(),
                outcome="success",
                details={"summary": "Изменён состав изображений"},
            )
        return card

    async def approve_and_publish(
        self, component_id: UUID, token: int, actor_id: UUID
    ) -> CatalogCard:
        row = await self.lock(component_id, token)
        if row.status != ComponentStatus.IN_REVIEW:
            raise CatalogValidationError("lifecycle_transition_denied")
        for state, action in (
            (ComponentStatus.APPROVED, "component.approved"),
            (ComponentStatus.PUBLISHED, "component.published"),
        ):
            card = await self.catalog.transition(component_id, row.revision, state, actor_id)
            await AuthRepository(self.session).audit(
                now=datetime.now(UTC),
                actor_user_id=actor_id,
                action=action,
                object_type="component",
                object_id=component_id,
                request_id=current_request_id(),
                outcome="success",
                details={"revision": card.revision, "status": state.value},
            )
        return card
