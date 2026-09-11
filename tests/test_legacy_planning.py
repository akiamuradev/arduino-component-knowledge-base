"""Pure legacy confirmation and non-destructive merge contracts."""

from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from arduino_component_kb.api.legacy_imports import ApplyInput, BundleInput, LicenseInput
from arduino_component_kb.legacy.parser import Specification, Target
from arduino_component_kb.legacy.planning import draft_data, merge_data


@pytest.mark.parametrize("confirmation", [None, "", "импорт", "IMPORT", "ИМПОРТ "])
def test_apply_requires_exact_confirmation(confirmation: str | None) -> None:
    with pytest.raises(ValidationError):
        ApplyInput.model_validate({"plan_hash": "a" * 64, "confirmation": confirmation})


@pytest.mark.parametrize("sizes", [(0, 1), (1, 0), (201 * 1024**2, 1), (1, 65 * 1024**2)])
def test_bundle_limits(sizes: tuple[int, int]) -> None:
    with pytest.raises(ValidationError):
        BundleInput(zip_size=sizes[0], xlsx_size=sizes[1])


def test_additive_merge_keeps_manual_fields_and_conflicting_specification() -> None:
    target = Target(
        identity="test",
        title="UNO",
        category="ПЛАТФОРМЫ РАЗРАБОТКИ",
        rows=[224],
        specifications=[Specification(label="Напряжение", value="5 В", unit="В")],
    )
    existing = replace(
        draft_data(target, uuid4()),
        slug="uno",
        description="Manual description",
        aliases=("Arduino Uno",),
        summary="Manual summary",
        manual_original=True,
    )
    incoming = replace(
        draft_data(target, uuid4()),
        description="Imported description",
        aliases=("ＡＲＤＵＩＮＯ UNO", "New alias"),
        specifications=(replace(existing.specifications[0], value_text="3.3 В"),),
    )
    merged, warnings = merge_data(existing, incoming)
    assert merged.description == existing.description
    assert merged.summary == existing.summary
    assert merged.primary_category_id == existing.primary_category_id
    assert merged.specifications == existing.specifications
    assert merged.aliases == ("Arduino Uno", "New alias")
    assert merged.manual_original is True
    assert set(warnings) == {"existing_description_preserved", "existing_specification_preserved"}


def test_merge_bounds_aliases_and_specs_without_removing_existing_values() -> None:
    target = Target(
        identity="test",
        title="New title",
        category="ДАТЧИКИ",
        rows=[116],
        specifications=[Specification(label="Extra", value="1")],
    )
    incoming = draft_data(target, uuid4())
    existing = replace(
        incoming,
        title="Original",
        aliases=tuple(f"alias {i}" for i in range(20)),
        specifications=tuple(
            replace(incoming.specifications[0], key=f"key-{i}", label=f"Label {i}", position=i)
            for i in range(50)
        ),
    )
    merged, warnings = merge_data(existing, incoming)
    assert merged.aliases == existing.aliases
    assert merged.specifications == existing.specifications
    assert "alias_limit_preserved_in_plan" in warnings
    assert "specification_limit_preserved_in_plan" in warnings


def test_property_definition_keys_do_not_collide_across_units() -> None:
    target = Target(
        identity="test",
        title="Sensor",
        category="ДАТЧИКИ",
        rows=[116],
        specifications=[Specification(label="Voltage", value="5", unit="V")],
    )
    first = draft_data(target, uuid4())
    second = draft_data(
        target.model_copy(
            update={"specifications": [Specification(label="Voltage", value="5000", unit="mV")]}
        ),
        uuid4(),
    )
    assert first.specifications[0].key != second.specifications[0].key


def test_license_review_cannot_use_whitespace_as_evidence() -> None:
    with pytest.raises(ValidationError):
        LicenseInput(evidence=" " * 40, confirmation="ПРАВА ПРОВЕРЕНЫ")
