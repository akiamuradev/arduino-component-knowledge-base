"""Catalog values and typed lifecycle failures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from arduino_component_kb.media.domain import ComponentMedia


class ComponentStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    PUBLISHED = "published"
    HIDDEN = "hidden"
    ARCHIVED = "archived"


class ComponentChangeAction(StrEnum):
    CREATED = "component.created"
    UPDATED = "component.updated"
    MEDIA_ATTACHED = "component.media_attached"
    IMAGES_UPDATED = "component.images_updated"
    SUBMITTED_FOR_REVIEW = "component.submitted_for_review"
    CHANGES_REQUESTED = "component.changes_requested"
    APPROVED = "component.approved"
    PUBLISHED = "component.published"
    HIDDEN = "component.hidden"
    SHOWN = "component.shown"
    ARCHIVED = "component.archived"
    RESTORED = "component.restored"
    MERGED = "component.merged"
    ARCHIVED_BY_MERGE = "component.archived_by_merge"


COMPONENT_CHANGE_SUMMARIES: dict[ComponentChangeAction, str] = {
    ComponentChangeAction.CREATED: "Карточка создана",
    ComponentChangeAction.UPDATED: "Содержимое карточки изменено",
    ComponentChangeAction.MEDIA_ATTACHED: "К карточке добавлен медиафайл",
    ComponentChangeAction.IMAGES_UPDATED: "Изображения карточки изменены",
    ComponentChangeAction.SUBMITTED_FOR_REVIEW: "Карточка отправлена на проверку",
    ComponentChangeAction.CHANGES_REQUESTED: "Карточка возвращена на исправление",
    ComponentChangeAction.APPROVED: "Карточка одобрена",
    ComponentChangeAction.PUBLISHED: "Карточка опубликована",
    ComponentChangeAction.HIDDEN: "Карточка скрыта из каталога",
    ComponentChangeAction.SHOWN: "Карточка возвращена в каталог",
    ComponentChangeAction.ARCHIVED: "Карточка архивирована",
    ComponentChangeAction.RESTORED: "Карточка восстановлена из архива",
    ComponentChangeAction.MERGED: "В карточку объединены данные дубликата",
    ComponentChangeAction.ARCHIVED_BY_MERGE: "Карточка архивирована после объединения дубликатов",
}


LIFECYCLE_TRANSITION_SOURCES: dict[ComponentStatus, frozenset[ComponentStatus]] = {
    ComponentStatus.IN_REVIEW: frozenset(
        {
            ComponentStatus.DRAFT,
            ComponentStatus.CHANGES_REQUESTED,
        }
    ),
    ComponentStatus.CHANGES_REQUESTED: frozenset(
        {
            ComponentStatus.IN_REVIEW,
            ComponentStatus.APPROVED,
        }
    ),
    ComponentStatus.APPROVED: frozenset({ComponentStatus.IN_REVIEW}),
    ComponentStatus.PUBLISHED: frozenset({ComponentStatus.APPROVED}),
    ComponentStatus.HIDDEN: frozenset({ComponentStatus.PUBLISHED}),
    ComponentStatus.ARCHIVED: frozenset(
        status for status in ComponentStatus if status is not ComponentStatus.ARCHIVED
    ),
}

EDITABLE_COMPONENT_STATUSES = frozenset(
    {
        ComponentStatus.DRAFT,
        ComponentStatus.CHANGES_REQUESTED,
        ComponentStatus.PUBLISHED,
    }
)


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CodeExampleVisibility(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"


class CorrectionProposalStatus(StrEnum):
    OPEN = "open"
    APPLIED = "applied"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class CorrectionProposal:
    id: UUID
    component_id: UUID
    author_display_name: str
    message: str
    status: CorrectionProposalStatus
    created_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class CategoryItem:
    id: UUID
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class TechnicalSpecification:
    key: str
    label: str
    value_text: str
    value_number: str | None
    unit: str | None
    position: int


@dataclass(frozen=True, slots=True)
class CompatibilityItem:
    target_type: str
    name: str
    version_constraint: str | None
    notes: str | None
    position: int


@dataclass(frozen=True, slots=True)
class CodeExample:
    title: str
    language: str
    practical_task: str
    hints: tuple[str, ...]
    body: str
    libraries: tuple[str, ...]
    explanation: str | None
    visibility: CodeExampleVisibility
    position: int


@dataclass(frozen=True, slots=True)
class DraftData:
    slug: str
    title: str
    aliases: tuple[str, ...]
    manufacturer: str | None
    model: str | None
    primary_category_id: UUID
    tags: tuple[str, ...]
    summary: str
    description: str
    purpose: str | None
    usage_notes: str | None
    safety_notes: str | None
    difficulty: Difficulty
    teacher_notes: str | None
    manual_original: bool
    specifications: tuple[TechnicalSpecification, ...] = ()
    compatibility: tuple[CompatibilityItem, ...] = ()
    code_examples: tuple[CodeExample, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    display_name: str
    original_url: str | None
    repository_url: str | None
    license_name: str
    license_spdx: str
    license_url: str
    source_revision: str
    source_tag: str | None
    source_file_path: str | None
    source_entry_name: str | None
    modifications_notice: str
    imported_at: datetime
    attribution: str
    parser_name: str
    parser_version: str


@dataclass(frozen=True, slots=True)
class CatalogCard:
    id: UUID
    status: ComponentStatus
    data: DraftData
    category: CategoryItem
    revision: int
    updated_at: datetime
    published_at: datetime | None
    sources: tuple[SourceSnapshot, ...] = ()
    media: tuple[ComponentMedia, ...] = ()
    archived_from_status: ComponentStatus | None = None


@dataclass(frozen=True, slots=True)
class ComponentHistoryEntry:
    revision: int
    previous_status: ComponentStatus | None
    status: ComponentStatus
    action: ComponentChangeAction
    summary: str
    actor_display_name: str
    occurred_at: datetime


class CatalogError(Exception):
    pass


class ComponentNotFoundError(CatalogError):
    pass


class ComponentMediaNotFoundError(CatalogError):
    pass


class RevisionConflictError(CatalogError):
    pass


class CatalogValidationError(CatalogError):
    def __init__(self, code: str = "catalog_conflict") -> None:
        self.code = code
        super().__init__(code)
