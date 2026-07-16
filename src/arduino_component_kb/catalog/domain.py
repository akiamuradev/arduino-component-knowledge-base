"""Catalog values and typed lifecycle failures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ComponentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


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


@dataclass(frozen=True, slots=True)
class CatalogCard:
    id: UUID
    status: ComponentStatus
    data: DraftData
    category: CategoryItem
    revision: int
    updated_at: datetime
    published_at: datetime | None


class CatalogError(Exception):
    pass


class ComponentNotFoundError(CatalogError):
    pass


class RevisionConflictError(CatalogError):
    pass


class CatalogValidationError(CatalogError):
    pass
