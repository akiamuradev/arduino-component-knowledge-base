"""Catalog validation, RBAC, and optimistic locking tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.catalog import DraftRequest, UpdateRequest, editor
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.catalog.domain import (
    CatalogValidationError,
    ComponentStatus,
    RevisionConflictError,
)
from arduino_component_kb.catalog.models import Category, Component, ComponentRevision
from arduino_component_kb.catalog.service import CatalogService


def principal(role: Role) -> Principal:
    return Principal(uuid4(), "user", "User", frozenset({role}), uuid4(), "hash", datetime.now(UTC))


async def test_workspace_rejects_student_on_backend() -> None:
    with pytest.raises(HTTPException) as error:
        await editor(principal(Role.STUDENT))
    assert error.value.status_code == 403
    assert await editor(principal(Role.TEACHER))


def test_draft_rejects_raw_html() -> None:
    with pytest.raises(ValidationError):
        DraftRequest(
            slug="sensor",
            title="Sensor",
            primary_category_id=uuid4(),
            summary="A sufficiently long summary",
            description="<script>unsafe</script>",
            difficulty="beginner",
            manual_original=True,
        )


def test_update_revision_is_not_part_of_draft_content() -> None:
    payload = UpdateRequest(
        slug="sensor",
        title="Sensor",
        primary_category_id=uuid4(),
        summary="A sufficiently long summary",
        description="Safe Markdown",
        difficulty="beginner",
        manual_original=True,
        revision=7,
        specifications=[
            {
                "key": "supply-voltage",
                "label": "Питание",
                "value_text": "5 В",
                "value_number": "5",
                "unit": "В",
            }
        ],
        compatibility=[{"target_type": "board", "name": "Arduino Uno"}],
    )
    assert payload.domain().slug == "sensor"
    assert payload.domain().specifications[0].position == 0
    assert payload.domain().compatibility[0].name == "Arduino Uno"
    assert payload.revision == 7


def test_code_example_contract_preserves_ordered_hints() -> None:
    payload = DraftRequest(
        slug="sensor",
        title="Sensor",
        primary_category_id=uuid4(),
        summary="A sufficiently long summary",
        description="Safe Markdown",
        difficulty="beginner",
        manual_original=True,
        code_examples=[
            {
                "title": "Read sensor",
                "language": "arduino",
                "practical_task": "Read and print the sensor value.",
                "hints": ["Configure the pin.", "Use Serial.println."],
                "body": "void loop() { Serial.println(analogRead(A0)); }",
                "libraries": ["Arduino core"],
                "explanation": "The loop prints one measurement.",
                "visibility": "student",
            }
        ],
    )
    example = payload.domain().code_examples[0]
    assert example.hints == ("Configure the pin.", "Use Serial.println.")
    assert example.position == 0


async def test_non_finite_numeric_specification_is_rejected_before_database_write() -> None:
    category_id = uuid4()
    payload = DraftRequest(
        slug="sensor",
        title="Sensor",
        primary_category_id=category_id,
        summary="A sufficiently long summary",
        description="Safe Markdown",
        difficulty="beginner",
        manual_original=True,
        specifications=[
            {
                "key": "voltage",
                "label": "Voltage",
                "value_text": "invalid",
                "value_number": "NaN",
            }
        ],
    )
    session = Mock(spec=AsyncSession)
    session.get = AsyncMock(
        return_value=Category(id=category_id, key="sensors", name="Датчики", is_active=True)
    )

    with pytest.raises(CatalogValidationError):
        await CatalogService(cast(AsyncSession, session)).create(payload.domain(), uuid4())


async def test_code_solution_limit_is_measured_in_utf8_bytes() -> None:
    category_id = uuid4()
    payload = DraftRequest(
        slug="sensor",
        title="Sensor",
        primary_category_id=category_id,
        summary="A sufficiently long summary",
        description="Safe Markdown",
        difficulty="beginner",
        manual_original=True,
        code_examples=[
            {
                "title": "Oversized UTF-8",
                "language": "arduino",
                "practical_task": "Demonstrate the byte limit.",
                "body": "я" * 40_000,
            }
        ],
    )
    session = Mock(spec=AsyncSession)
    session.get = AsyncMock(
        return_value=Category(id=category_id, key="sensors", name="Датчики", is_active=True)
    )
    with pytest.raises(CatalogValidationError):
        await CatalogService(cast(AsyncSession, session)).create(payload.domain(), uuid4())


async def test_stale_revision_is_rejected_before_mutation() -> None:
    component = Mock(spec=Component)
    component.revision = 3
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=component)
    service = CatalogService(cast(AsyncSession, session))
    with pytest.raises(RevisionConflictError):
        await service.transition(uuid4(), 2, target=ComponentStatus.PUBLISHED, actor_id=uuid4())


async def test_student_card_uses_published_snapshot_and_hides_teacher_notes() -> None:
    component_id = uuid4()
    category_id = uuid4()
    published_at = datetime.now(UTC)
    component = Component(id=component_id, slug="stable-slug", status="draft")
    snapshot = ComponentRevision(
        id=uuid4(),
        component_id=component_id,
        revision=4,
        status="published",
        content_json={
            "slug": "stable-slug",
            "title": "Published title",
            "aliases": ["Alias"],
            "manufacturer": None,
            "model": None,
            "primary_category_id": str(category_id),
            "tags": ["sensor"],
            "summary": "Published summary with enough content",
            "description": "Published description",
            "purpose": None,
            "usage_notes": None,
            "safety_notes": None,
            "difficulty": "beginner",
            "teacher_notes": "must not leak",
            "manual_original": True,
            "specifications": [
                {
                    "key": "supply-voltage",
                    "label": "Питание",
                    "value_text": "5 В",
                    "value_number": "5",
                    "unit": "В",
                    "position": 0,
                }
            ],
            "compatibility": [
                {
                    "target_type": "board",
                    "name": "Arduino Uno",
                    "version_constraint": None,
                    "notes": "GPIO",
                    "position": 0,
                }
            ],
            "code_examples": [
                {
                    "title": "Student task",
                    "language": "arduino",
                    "practical_task": "Blink the LED.",
                    "hints": ["Use pinMode."],
                    "body": "void setup() {}",
                    "libraries": [],
                    "explanation": "A visible explanation.",
                    "visibility": "student",
                    "position": 0,
                },
                {
                    "title": "Teacher solution",
                    "language": "arduino",
                    "practical_task": "Extended task.",
                    "hints": [],
                    "body": "teacher-only code",
                    "libraries": [],
                    "explanation": None,
                    "visibility": "teacher",
                    "position": 1,
                },
            ],
        },
        actor_id=uuid4(),
        created_at=published_at,
    )
    category = Category(id=category_id, key="sensors", name="Датчики", is_active=True, position=1)
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(side_effect=[component, snapshot])
    session.get = AsyncMock(return_value=category)

    card = await CatalogService(cast(AsyncSession, session)).get_published("stable-slug")

    assert card.data.title == "Published title"
    assert card.data.teacher_notes is None
    assert card.data.specifications[0].label == "Питание"
    assert card.data.compatibility[0].name == "Arduino Uno"
    assert [example.title for example in card.data.code_examples] == ["Student task"]
    assert card.published_at == published_at
