"""Unit conversion, persisted technical metadata and safe public diagnostics."""

from dataclasses import replace
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException

from arduino_component_kb.api.catalog import DraftRequest, _error
from arduino_component_kb.catalog.domain import CatalogValidationError, TechnicalSpecification
from arduino_component_kb.catalog.models import ComponentProperty, PropertyDefinition, Unit
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.catalog.units import (
    convert_numeric_value,
    fits_numeric_storage,
    normalize_unit_symbol,
    unit_family,
)
from arduino_component_kb.errors import http_exception_handler, safe_validation_details


@pytest.mark.parametrize(
    ("source", "target", "value", "expected"),
    [
        ("MB", "КБ", "4", "4096"),
        ("GB", "Б", "1", "1073741824"),
        ("мВ", "В", "5000", "5"),
        ("MHz", "кГц", "16", "16000"),
        ("µA", "mA", "1000", "1"),
        ("MΩ", "Ом", "1", "1000000"),
        ("pF", "F", "1", "0.000000000001"),
        ("µF", "нФ", "1", "1000"),
        ("ms", "с", "4", "0.004"),
        ("cm", "мм", "1", "10"),
        ("Mbit", "кбит", "1", "1000"),
        ("custom", "custom", "4", "4"),
        (None, None, "4", "4"),
    ],
)
def test_exact_unit_conversion(
    source: str | None, target: str | None, value: str, expected: str
) -> None:
    result = convert_numeric_value(Decimal(value), source, target)
    assert result == Decimal(expected)
    assert result is not None
    assert convert_numeric_value(result, target, source) == Decimal(value)


@pytest.mark.parametrize(
    ("source", "target"), [("Mbit", "MB"), ("мс", "КБ"), ("custom", "CUSTOM"), (None, "В")]
)
def test_units_are_not_guessed(source: str | None, target: str | None) -> None:
    assert convert_numeric_value(Decimal(4), source, target) is None


def test_aliases_and_storage_bounds() -> None:
    assert normalize_unit_symbol(" MiB ") == "МБ"
    assert unit_family("MB") == "data_size_bytes"
    assert unit_family("Mbit") == "data_size_bits"
    assert unit_family("custom") is None
    assert fits_numeric_storage(Decimal("9999999999999999.99999999"))
    assert fits_numeric_storage(Decimal("0.0000000100"))
    for value in ("NaN", "Infinity", "1E16", "1E-9", "1E999999999", "1E-999999999"):
        assert not fits_numeric_storage(Decimal(value))
    assert fits_numeric_storage(Decimal("0E-999999999"))


@pytest.mark.parametrize(
    ("entered", "canonical", "number", "human", "expected"),
    [
        ("МБ", "КБ", "4", "4 МБ", "4096"),
        ("мВ", "В", "5000", " 5000 мВ ", "5"),
        ("custom", "custom", "4", "4 custom", "4"),
    ],
)
async def test_existing_definition_keeps_unit_and_converts_metadata(
    entered: str,
    canonical: str,
    number: str,
    human: str,
    expected: str,
) -> None:
    session = Mock(spec=AsyncSession)
    unit = Unit(id=uuid4(), key="unit", symbol=canonical, name=canonical)
    definition = PropertyDefinition(
        id=uuid4(),
        key="flash",
        label="Flash-память",
        value_type="number",
        unit_id=unit.id,
        is_multivalue=False,
    )
    session.scalar = AsyncMock(return_value=definition)
    session.get = AsyncMock(return_value=unit)
    item = TechnicalSpecification("flash", "Flash-память", human, number, entered, 0)
    draft = DraftRequest(
        slug="test",
        title="Test",
        primary_category_id=uuid4(),
        summary="",
        description="",
        difficulty="beginner",
        manual_original=True,
    ).domain()
    await CatalogService(cast(AsyncSession, session))._replace_technical(
        uuid4(), replace(draft, specifications=(item,))
    )
    stored = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], ComponentProperty)
    ]
    assert len(stored) == 1
    assert stored[0].value_number == Decimal(expected)
    assert stored[0].value_text == human
    assert stored[0].definition_id == definition.id
    assert definition.unit_id == unit.id


@pytest.mark.parametrize(
    ("value_type", "human", "number", "unit", "code"),
    [
        ("number", "4 мс", "4", "мс", "incompatible_unit"),
        ("number", "80 / 160 МГц", None, None, "expected_numeric_value"),
        ("text", "4 КБ", "4", "КБ", "expected_text_value"),
        ("number", "0.00000001 Б", "0.00000001", "Б", "numeric_value_out_of_range"),
    ],
)
async def test_definition_errors_target_value_at_payload_index(
    value_type: str,
    human: str,
    number: str | None,
    unit: str | None,
    code: str,
) -> None:
    session = Mock(spec=AsyncSession)
    canonical = Unit(id=uuid4(), key="kb", symbol="КБ", name="КБ")
    definitions = [
        PropertyDefinition(
            id=uuid4(),
            key="first",
            label="First",
            value_type="text",
            unit_id=None,
            is_multivalue=False,
        ),
        PropertyDefinition(
            id=uuid4(),
            key="flash",
            label="Flash-память",
            value_type=value_type,
            unit_id=canonical.id,
            is_multivalue=False,
        ),
    ]
    session.scalar = AsyncMock(side_effect=definitions)
    session.get = AsyncMock(return_value=canonical)
    draft = DraftRequest(
        slug="test",
        title="Test",
        primary_category_id=uuid4(),
        summary="",
        description="",
        difficulty="beginner",
        manual_original=True,
    ).domain()
    items = (
        TechnicalSpecification("first", "First", "text", None, None, 0),
        TechnicalSpecification("flash", "Flash-память", human, number, unit, 99),
    )
    with pytest.raises(CatalogValidationError) as raised:
        await CatalogService(cast(AsyncSession, session))._replace_technical(
            uuid4(), replace(draft, specifications=items)
        )
    assert raised.value.code == "validation_failed"
    issues = cast(list[dict[str, object]], raised.value.details["issues"])
    assert issues[0]["path"] == ["specifications", 1, "value_text"]
    assert issues[0]["code"] == code
    if code == "incompatible_unit":
        assert issues[0]["meta"] == {
            "label": "Flash-память",
            "entered_unit": "мс",
            "expected_unit": "КБ",
            "expected_family": "data_size_bytes",
        }


def test_public_http_contract_preserves_only_safe_diagnostics() -> None:
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)

    @app.get("/failure")
    async def failure() -> None:
        raise _error(CatalogValidationError.field(["slug"], "slug_already_exists"))

    response = TestClient(app).get("/failure")
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {
        "issues": [{"path": ["slug"], "code": "slug_already_exists", "meta": {}}]
    }
    assert (
        safe_validation_details(
            {
                "issues": [
                    {"code": []},
                    {"code": "incompatible_unit", "path": ["specifications", True, "value_text"]},
                ]
            }
        )
        is None
    )
    assert safe_validation_details(
        {
            "issues": [
                {
                    "path": ["slug"],
                    "code": "slug_already_exists",
                    "meta": {"sql": "private", "label": "x" * 200},
                }
            ]
        }
    ) == {
        "issues": [{"path": ["slug"], "code": "slug_already_exists", "meta": {"label": "x" * 160}}]
    }


def test_duplicate_slug_constraint_and_unknown_integrity_fallback() -> None:
    driver = Exception("private SQL detail")
    driver.constraint_name = "components_slug_key"  # type: ignore[attr-defined]
    wrapped = Exception("wrapped driver")
    wrapped.__cause__ = driver
    error = _error(IntegrityError("private SQL", {}, wrapped))
    assert error.status_code == 422
    detail: object = error.detail
    assert detail == {
        "code": "validation_failed",
        "issues": [{"path": ["slug"], "code": "slug_already_exists", "meta": {}}],
    }
    unknown = _error(IntegrityError("private SQL", {}, Exception("unknown constraint")))
    assert unknown.status_code == 409
    fallback: object = unknown.detail
    assert fallback == {"code": "catalog_conflict"}


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("category_invalid", 422),
        ("category_unavailable", 422),
        ("category_in_use", 409),
        ("component_collection_limit_exceeded", 422),
        ("invalid_compatibility", 422),
        ("invalid_code_example", 422),
        ("merge_target_invalid", 422),
        ("merge_fields_invalid", 422),
        ("publication_source_required", 409),
        ("duplicate_review_required", 409),
    ],
)
def test_known_catalog_rules_keep_specific_public_codes(code: str, status: int) -> None:
    error = _error(CatalogValidationError(code))
    detail: object = error.detail
    assert error.status_code == status
    assert detail == {"code": code}


async def test_invalid_category_has_an_actionable_code() -> None:
    session = Mock(spec=AsyncSession)
    service = CatalogService(cast(AsyncSession, session))
    with pytest.raises(CatalogValidationError, match="category_invalid"):
        await service.create_category("INVALID KEY", "Name", None, None, 0)
    session.get = AsyncMock(return_value=None)
    with pytest.raises(CatalogValidationError, match="category_unavailable"):
        await service.create_category("valid", "Name", uuid4(), None, 0)
