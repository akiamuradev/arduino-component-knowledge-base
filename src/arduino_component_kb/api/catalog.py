"""Teacher workspace API for catalog cards."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import (
    csrf_principal,
    current_principal,
    database_session,
    require_roles,
)
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.domain import (
    CatalogCard,
    CatalogError,
    CatalogValidationError,
    CodeExample,
    CodeExampleVisibility,
    CompatibilityItem,
    ComponentMediaNotFoundError,
    ComponentStatus,
    Difficulty,
    DraftData,
    RevisionConflictError,
    SourceSnapshot,
    TechnicalSpecification,
)
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.imports.models import Source
from arduino_component_kb.logging import current_request_id
from arduino_component_kb.media.domain import (
    ComponentImageMutation,
    ComponentMedia,
    ComponentMediaVariant,
)

router = APIRouter(prefix="/api/v1/workspace", tags=["catalog-workspace"])
admin_router = APIRouter(prefix="/api/v1/admin/catalog", tags=["catalog-administration"])
public_router = APIRouter(prefix="/api/v1/catalog", tags=["student-catalog"])
editor = require_roles(Role.TEACHER, Role.ADMINISTRATOR)
administrator = require_roles(Role.ADMINISTRATOR)


class CategoryResponse(BaseModel):
    id: str
    slug: str
    name: str


class CatalogSourceResponse(BaseModel):
    key: str
    display_name: str
    repository_url: str | None
    source_type: str
    status: str
    content_policy: str
    license_name: str | None
    license_spdx: str | None
    license_url: str | None
    attribution_template: str | None
    adapter_version: str
    default_revision_policy: str
    disable_reason: str | None


class CategoryCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=160)
    parent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    position: int = Field(default=0, ge=0, le=10000)


class SpecificationRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    label: str = Field(min_length=1, max_length=160)
    value_text: str = Field(min_length=1, max_length=2000)
    value_number: str | None = Field(default=None, max_length=64)
    unit: str | None = Field(default=None, max_length=32)

    def domain(self, position: int) -> TechnicalSpecification:
        return TechnicalSpecification(position=position, **self.model_dump())


class CompatibilityRequest(BaseModel):
    target_type: str = Field(pattern=r"^(board|library|platform)$")
    name: str = Field(min_length=1, max_length=160)
    version_constraint: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)

    def domain(self, position: int) -> CompatibilityItem:
        return CompatibilityItem(position=position, **self.model_dump())


class SpecificationResponse(BaseModel):
    key: str
    label: str
    value_text: str
    value_number: str | None
    unit: str | None
    position: int


class CompatibilityResponse(BaseModel):
    target_type: str
    name: str
    version_constraint: str | None
    notes: str | None
    position: int


class CodeExampleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    language: str = Field(pattern=r"^[a-z0-9][a-z0-9_+.#-]{0,31}$")
    practical_task: str = Field(min_length=1, max_length=5000)
    hints: list[str] = Field(default_factory=list, max_length=10)
    body: str = Field(min_length=1, max_length=65536)
    libraries: list[str] = Field(default_factory=list, max_length=20)
    explanation: str | None = Field(default=None, max_length=10000)
    visibility: CodeExampleVisibility = CodeExampleVisibility.STUDENT

    def domain(self, position: int) -> CodeExample:
        return CodeExample(
            title=self.title,
            language=self.language,
            practical_task=self.practical_task,
            hints=tuple(self.hints),
            body=self.body,
            libraries=tuple(self.libraries),
            explanation=self.explanation,
            visibility=self.visibility,
            position=position,
        )


class CodeExampleResponse(BaseModel):
    title: str
    language: str
    practical_task: str
    hints: list[str]
    body: str
    libraries: list[str]
    explanation: str | None
    visibility: CodeExampleVisibility
    position: int


class DraftRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=2, max_length=160)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    primary_category_id: UUID
    tags: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=20, max_length=500)
    description: str = Field(max_length=30000)
    purpose: str | None = Field(default=None, max_length=2000)
    usage_notes: str | None = Field(default=None, max_length=5000)
    safety_notes: str | None = Field(default=None, max_length=5000)
    difficulty: Difficulty
    teacher_notes: str | None = Field(default=None, max_length=10000)
    manual_original: bool
    specifications: list[SpecificationRequest] = Field(default_factory=list, max_length=50)
    compatibility: list[CompatibilityRequest] = Field(default_factory=list, max_length=30)
    code_examples: list[CodeExampleRequest] = Field(default_factory=list, max_length=10)

    @field_validator("description")
    @classmethod
    def reject_raw_html(cls, value: str) -> str:
        if "<" in value or ">" in value:
            raise ValueError("raw HTML is not allowed")
        return value

    def domain(self) -> DraftData:
        return DraftData(
            **self.model_dump(
                exclude={"revision", "specifications", "compatibility", "code_examples"}
            ),
            specifications=tuple(
                item.domain(position) for position, item in enumerate(self.specifications)
            ),
            compatibility=tuple(
                item.domain(position) for position, item in enumerate(self.compatibility)
            ),
            code_examples=tuple(
                item.domain(position) for position, item in enumerate(self.code_examples)
            ),
        )


class UpdateRequest(DraftRequest):
    revision: int = Field(ge=1)


class LifecycleRequest(BaseModel):
    revision: int = Field(ge=1)


class ComponentImageMutationRequest(BaseModel):
    asset_id: UUID
    purpose: str = Field(min_length=1, max_length=40)
    alt_text: str = Field(min_length=1, max_length=500)
    caption: str | None = Field(default=None, max_length=1000)

    def domain(self) -> ComponentImageMutation:
        return ComponentImageMutation(
            asset_id=self.asset_id,
            purpose=self.purpose,
            alt_text=self.alt_text,
            caption=self.caption,
        )


class ComponentImagesUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    images: list[ComponentImageMutationRequest] = Field(max_length=12)
    primary_asset_id: UUID | None = None


class SourceSnapshotResponse(BaseModel):
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


class ComponentMediaVariantResponse(BaseModel):
    name: str
    mime: str
    width: int
    height: int
    sha256: str


class ComponentMediaResponse(BaseModel):
    asset_id: UUID
    kind: str
    purpose: str
    alt_text: str
    caption: str | None
    display_order: int
    is_primary: bool
    status: str
    width: int | None
    height: int | None
    variants: list[ComponentMediaVariantResponse]


class ComponentResponse(BaseModel):
    id: str
    slug: str
    status: ComponentStatus
    title: str
    summary: str
    primary_category: CategoryResponse
    revision: int
    updated_at: datetime
    aliases: list[str]
    manufacturer: str | None
    model: str | None
    primary_category_id: str
    tags: list[str]
    description: str
    purpose: str | None
    usage_notes: str | None
    safety_notes: str | None
    difficulty: Difficulty
    teacher_notes: str | None
    manual_original: bool
    published_at: datetime | None
    specifications: list[SpecificationResponse]
    compatibility: list[CompatibilityResponse]
    code_examples: list[CodeExampleResponse]
    sources: list[SourceSnapshotResponse]
    media: list[ComponentMediaResponse]


class ComponentListResponse(BaseModel):
    items: list[ComponentResponse]
    total: int


class PublicComponentResponse(BaseModel):
    id: str
    slug: str
    title: str
    summary: str
    primary_category: CategoryResponse
    aliases: list[str]
    manufacturer: str | None
    model: str | None
    tags: list[str]
    description: str
    purpose: str | None
    usage_notes: str | None
    safety_notes: str | None
    difficulty: Difficulty
    published_at: datetime
    specifications: list[SpecificationResponse]
    compatibility: list[CompatibilityResponse]
    code_examples: list[CodeExampleResponse]
    sources: list[SourceSnapshotResponse]
    media: list[ComponentMediaResponse]


class PublicComponentListResponse(BaseModel):
    items: list[PublicComponentResponse]
    total: int


def specification_response(item: TechnicalSpecification) -> SpecificationResponse:
    return SpecificationResponse(
        key=item.key,
        label=item.label,
        value_text=item.value_text,
        value_number=item.value_number,
        unit=item.unit,
        position=item.position,
    )


def compatibility_response(item: CompatibilityItem) -> CompatibilityResponse:
    return CompatibilityResponse(
        target_type=item.target_type,
        name=item.name,
        version_constraint=item.version_constraint,
        notes=item.notes,
        position=item.position,
    )


def code_example_response(item: CodeExample) -> CodeExampleResponse:
    return CodeExampleResponse(
        title=item.title,
        language=item.language,
        practical_task=item.practical_task,
        hints=list(item.hints),
        body=item.body,
        libraries=list(item.libraries),
        explanation=item.explanation,
        visibility=item.visibility,
        position=item.position,
    )


def source_snapshot_response(item: SourceSnapshot) -> SourceSnapshotResponse:
    return SourceSnapshotResponse.model_validate(item, from_attributes=True)


def component_media_variant_response(
    item: ComponentMediaVariant,
) -> ComponentMediaVariantResponse:
    return ComponentMediaVariantResponse.model_validate(item, from_attributes=True)


def component_media_response(item: ComponentMedia) -> ComponentMediaResponse:
    return ComponentMediaResponse(
        asset_id=item.asset_id,
        kind=item.kind.value,
        purpose=item.purpose,
        alt_text=item.alt_text,
        caption=item.caption,
        display_order=item.display_order,
        is_primary=item.is_primary,
        status=item.status.value,
        width=item.width,
        height=item.height,
        variants=[component_media_variant_response(value) for value in item.variants],
    )


def response(card: CatalogCard) -> ComponentResponse:
    data = card.data
    return ComponentResponse(
        id=str(card.id),
        status=card.status,
        primary_category=CategoryResponse(
            id=str(card.category.id), slug=card.category.slug, name=card.category.name
        ),
        revision=card.revision,
        updated_at=card.updated_at,
        published_at=card.published_at,
        primary_category_id=str(data.primary_category_id),
        aliases=list(data.aliases),
        tags=list(data.tags),
        specifications=[specification_response(item) for item in data.specifications],
        compatibility=[compatibility_response(item) for item in data.compatibility],
        code_examples=[code_example_response(item) for item in data.code_examples],
        sources=[source_snapshot_response(item) for item in card.sources],
        media=[component_media_response(item) for item in card.media],
        **{
            key: getattr(data, key)
            for key in (
                "slug",
                "title",
                "summary",
                "manufacturer",
                "model",
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


def public_response(card: CatalogCard) -> PublicComponentResponse:
    data = card.data
    if card.published_at is None:
        raise ValueError("published card requires published_at")
    return PublicComponentResponse(
        id=str(card.id),
        slug=data.slug,
        title=data.title,
        summary=data.summary,
        primary_category=CategoryResponse(
            id=str(card.category.id), slug=card.category.slug, name=card.category.name
        ),
        aliases=list(data.aliases),
        manufacturer=data.manufacturer,
        model=data.model,
        tags=list(data.tags),
        description=data.description,
        purpose=data.purpose,
        usage_notes=data.usage_notes,
        safety_notes=data.safety_notes,
        difficulty=data.difficulty,
        published_at=card.published_at,
        specifications=[specification_response(item) for item in data.specifications],
        compatibility=[compatibility_response(item) for item in data.compatibility],
        code_examples=[code_example_response(item) for item in data.code_examples],
        sources=[source_snapshot_response(item) for item in card.sources],
        media=[component_media_response(item) for item in card.media],
    )


@public_router.get("/categories", response_model=list[CategoryResponse])
async def public_categories(
    _: Annotated[Principal, Depends(current_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> list[CategoryResponse]:
    return [
        CategoryResponse(id=str(x.id), slug=x.slug, name=x.name)
        for x in await CatalogService(session).categories()
    ]


@public_router.get("/sources", response_model=list[CatalogSourceResponse])
async def public_sources(
    _: Annotated[Principal, Depends(current_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> list[CatalogSourceResponse]:
    sources = (
        await session.scalars(select(Source).order_by(Source.status, Source.display_name))
    ).all()
    return [
        CatalogSourceResponse.model_validate(source, from_attributes=True) for source in sources
    ]


@public_router.get("/components", response_model=PublicComponentListResponse)
async def public_components(
    _: Annotated[Principal, Depends(current_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
    query: Annotated[str | None, Query(alias="q", min_length=1, max_length=100)] = None,
    category_id: UUID | None = None,
    difficulty: Difficulty | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PublicComponentListResponse:
    cards, total = await CatalogService(session).list_published(
        query, category_id, difficulty, limit
    )
    return PublicComponentListResponse(items=[public_response(card) for card in cards], total=total)


@public_router.get("/components/{slug}", response_model=PublicComponentResponse)
async def public_component(
    slug: str,
    _: Annotated[Principal, Depends(current_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> PublicComponentResponse:
    try:
        return public_response(await CatalogService(session).get_published(slug))
    except CatalogError as error:
        raise HTTPException(404, detail={"code": "component_not_found"}) from error


async def _commit(session: AsyncSession, action: str, actor: Principal, card: CatalogCard) -> None:
    await AuthRepository(session).audit(
        now=datetime.now(UTC),
        actor_user_id=actor.user_id,
        action=action,
        object_type="component",
        object_id=card.id,
        request_id=current_request_id(),
        outcome="success",
        details={"revision": card.revision},
    )
    await session.commit()


def _error(error: Exception) -> HTTPException:
    if isinstance(error, RevisionConflictError):
        return HTTPException(409, detail={"code": "revision_conflict"})
    if isinstance(error, CatalogValidationError):
        return HTTPException(409, detail={"code": error.code})
    return HTTPException(409, detail={"code": "catalog_conflict"})


@router.get("/categories", response_model=list[CategoryResponse])
async def categories(
    _: Annotated[Principal, Depends(editor)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> list[CategoryResponse]:
    return [
        CategoryResponse(id=str(x.id), slug=x.slug, name=x.name)
        for x in await CatalogService(session).categories()
    ]


@admin_router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    payload: CategoryCreateRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> CategoryResponse:
    try:
        item = await CatalogService(session).create_category(**payload.model_dump())
        await AuthRepository(session).audit(
            now=datetime.now(UTC),
            actor_user_id=actor.user_id,
            action="category.created",
            object_type="category",
            object_id=item.id,
            request_id=current_request_id(),
            outcome="success",
            details={"key": item.slug},
        )
        await session.commit()
        return CategoryResponse(id=str(item.id), slug=item.slug, name=item.name)
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error


@admin_router.post("/categories/{category_id}/deactivate", status_code=204)
async def deactivate_category(
    category_id: UUID,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> None:
    try:
        await CatalogService(session).deactivate_category(category_id)
        await AuthRepository(session).audit(
            now=datetime.now(UTC),
            actor_user_id=actor.user_id,
            action="category.deactivated",
            object_type="category",
            object_id=category_id,
            request_id=current_request_id(),
            outcome="success",
        )
        await session.commit()
    except CatalogError as error:
        await session.rollback()
        raise _error(error) from error


@router.get("/components", response_model=ComponentListResponse)
async def list_components(
    _: Annotated[Principal, Depends(editor)],
    session: Annotated[AsyncSession, Depends(database_session)],
    component_status: Annotated[ComponentStatus | None, Query(alias="status")] = None,
) -> ComponentListResponse:
    items = [response(x) for x in await CatalogService(session).list_cards(component_status)]
    return ComponentListResponse(items=items, total=len(items))


@router.get("/components/{component_id}", response_model=ComponentResponse)
async def get_component(
    component_id: UUID,
    _: Annotated[Principal, Depends(editor)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    try:
        return response(await CatalogService(session).get_card(component_id))
    except CatalogError as error:
        raise HTTPException(404, detail={"code": "component_not_found"}) from error


@router.post("/components", response_model=ComponentResponse, status_code=status.HTTP_201_CREATED)
async def create_component(
    payload: DraftRequest,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    try:
        card = await CatalogService(session).create(payload.domain(), actor.user_id)
        await _commit(session, "component.created", actor, card)
        return response(card)
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error


@router.put("/components/{component_id}", response_model=ComponentResponse)
async def update_component(
    component_id: UUID,
    payload: UpdateRequest,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    try:
        card = await CatalogService(session).update(
            component_id, payload.revision, payload.domain(), actor.user_id
        )
        await _commit(session, "component.updated", actor, card)
        return response(card)
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error


@router.put("/components/{component_id}/images", response_model=ComponentResponse)
async def update_component_images(
    component_id: UUID,
    payload: ComponentImagesUpdateRequest,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    try:
        card = await CatalogService(session).mutate_images(
            component_id,
            payload.revision,
            tuple(item.domain() for item in payload.images),
            payload.primary_asset_id,
            actor.user_id,
        )
        await _commit(session, "component.images_updated", actor, card)
        return response(card)
    except ComponentMediaNotFoundError as error:
        await session.rollback()
        raise HTTPException(404, detail={"code": "media_not_found"}) from error
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error


async def _transition(
    component_id: UUID,
    payload: LifecycleRequest,
    actor: Principal,
    session: AsyncSession,
    target: ComponentStatus,
) -> ComponentResponse:
    try:
        card = await CatalogService(session).transition(
            component_id, payload.revision, target, actor.user_id
        )
        await _commit(session, f"component.{target.value}", actor, card)
        return response(card)
    except CatalogError as error:
        await session.rollback()
        raise _error(error) from error


@router.post("/components/{component_id}/publish", response_model=ComponentResponse)
async def publish_component(
    component_id: UUID,
    payload: LifecycleRequest,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    return await _transition(component_id, payload, actor, session, ComponentStatus.PUBLISHED)


@router.post("/components/{component_id}/archive", response_model=ComponentResponse)
async def archive_component(
    component_id: UUID,
    payload: LifecycleRequest,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    return await _transition(component_id, payload, actor, session, ComponentStatus.ARCHIVED)
