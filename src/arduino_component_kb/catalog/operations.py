"""Application operations coordinating catalog mutations and transactions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.domain import (
    LIFECYCLE_TRANSITION_ACTIONS,
    CatalogCard,
    ComponentChangeAction,
    ComponentStatus,
)
from arduino_component_kb.catalog.models import ComponentRevision
from arduino_component_kb.catalog.service import CatalogService

CatalogLifecycleMutation = Callable[[], Awaitable[CatalogCard]]


class CatalogLifecycleOperations:
    """Run one lifecycle mutation, its audit event, and commit as one unit."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        catalog: CatalogService | None = None,
        audit: AuthRepository | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog or CatalogService(session)
        self.audit = audit or AuthRepository(session)

    async def transition(
        self,
        component_id: UUID,
        expected_revision: int,
        target: ComponentStatus,
        actor_id: UUID,
        request_id: str | None,
    ) -> CatalogCard:
        return await self._execute(
            lambda: self.catalog.transition(
                component_id,
                expected_revision,
                target,
                actor_id,
            ),
            action=LIFECYCLE_TRANSITION_ACTIONS.get(target),
            actor_id=actor_id,
            request_id=request_id,
        )

    async def show_hidden(
        self,
        component_id: UUID,
        expected_revision: int,
        actor_id: UUID,
        request_id: str | None,
    ) -> CatalogCard:
        return await self._execute(
            lambda: self.catalog.show_hidden(component_id, expected_revision, actor_id),
            action=ComponentChangeAction.SHOWN,
            actor_id=actor_id,
            request_id=request_id,
        )

    async def restore_archived(
        self,
        component_id: UUID,
        expected_revision: int,
        actor_id: UUID,
        request_id: str | None,
    ) -> CatalogCard:
        return await self._execute(
            lambda: self.catalog.restore_archived(component_id, expected_revision, actor_id),
            action=ComponentChangeAction.RESTORED,
            actor_id=actor_id,
            request_id=request_id,
        )

    async def _execute(
        self,
        mutation: CatalogLifecycleMutation,
        *,
        action: ComponentChangeAction | None,
        actor_id: UUID,
        request_id: str | None,
    ) -> CatalogCard:
        try:
            card = await mutation()
            if action is None:
                raise RuntimeError("catalog lifecycle action is not configured")
            await self._audit_and_commit(card, action, actor_id, request_id)
        except Exception:
            await self.session.rollback()
            raise
        return card

    async def _audit_and_commit(
        self,
        card: CatalogCard,
        action: ComponentChangeAction,
        actor_id: UUID,
        request_id: str | None,
    ) -> None:
        await self.session.flush()
        revision = await self.session.scalar(
            select(ComponentRevision).where(
                ComponentRevision.component_id == card.id,
                ComponentRevision.revision == card.revision,
            )
        )
        if revision is None or revision.action != action.value:
            raise RuntimeError("component revision history is inconsistent with audit action")
        await self.audit.audit(
            now=datetime.now(UTC),
            actor_user_id=actor_id,
            action=action.value,
            object_type="component",
            object_id=card.id,
            request_id=request_id,
            outcome="success",
            details={
                "revision": card.revision,
                "previous_status": revision.previous_status,
                "status": revision.status,
                "summary": revision.change_summary,
            },
        )
        await self.session.commit()


class CatalogMediaAttachments:
    """Expose only the catalog mutation required by upload reservation."""

    def __init__(self, catalog: CatalogService) -> None:
        self.catalog = catalog

    async def touch_media_attachment(
        self,
        component_id: UUID,
        expected_revision: int,
        actor_id: UUID,
        now: datetime,
    ) -> int:
        card = await self.catalog.touch_media_attachment(
            component_id,
            expected_revision,
            actor_id,
            now,
        )
        return card.revision
