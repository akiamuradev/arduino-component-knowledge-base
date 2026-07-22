"""Pure deterministic value normalization rules; no source parsing or inference."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from arduino_component_kb.imports.pipeline.models import NormalizationConfidence
from arduino_component_kb.imports.pipeline.normalization.registry import ValueKind

NORMALIZATION_RULE_VERSION = "1.0.0"

_SPACE = re.compile(r"\s+")
_NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
_RANGE_SEPARATOR = r"(?:to|[-–—~])"
_DIMENSIONS = re.compile(
    rf"^\s*({_NUMBER})\s*(?:x|×|by)\s*({_NUMBER})(?:\s*(?:x|×|by)\s*({_NUMBER}))?\s*([A-Za-z]+)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ValueNormalization:
    value: str
    unit: str | None
    rule_id: str
    confidence: NormalizationConfidence


_QUANTITY_UNITS: dict[ValueKind, tuple[tuple[str, str], ...]] = {
    ValueKind.VOLTAGE: (
        (r"millivolts?|mv", "mV"),
        (r"kilovolts?|kv", "kV"),
        (r"volts?|v", "V"),
    ),
    ValueKind.CURRENT: (
        (r"microamperes?|microamps?|µa|ua", "µA"),
        (r"milliamperes?|milliamps?|ma", "mA"),
        (r"amperes?|amps?|a", "A"),
    ),
    ValueKind.TEMPERATURE: (
        (r"degrees?\s*celsius|degree\s*c|°c|celsius", "°C"),
        (r"degrees?\s*fahrenheit|degree\s*f|°f|fahrenheit", "°F"),
    ),
    ValueKind.FREQUENCY: (
        (r"gigahertz|ghz", "GHz"),
        (r"megahertz|mhz", "MHz"),
        (r"kilohertz|khz", "kHz"),
        (r"hertz|hz", "Hz"),
    ),
    ValueKind.PERCENT: ((r"percent|%", "%"),),
    ValueKind.PRESSURE: (
        (r"kilopascals?|kpa", "kPa"),
        (r"hectopascals?|hpa", "hPa"),
        (r"pascals?|pa", "Pa"),
    ),
}

_INTERFACES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:i2c|i²c|iic)\b", re.IGNORECASE), "I2C"),
    (re.compile(r"\bspi\b", re.IGNORECASE), "SPI"),
    (re.compile(r"\buart\b", re.IGNORECASE), "UART"),
    (re.compile(r"\banalog(?:ue)?\b", re.IGNORECASE), "analog"),
    (re.compile(r"\bdigital\b", re.IGNORECASE), "digital"),
    (re.compile(r"\bcan(?:\s+bus)?\b", re.IGNORECASE), "CAN"),
    (re.compile(r"\bwi[ -]?fi\b", re.IGNORECASE), "Wi-Fi"),
    (re.compile(r"\bbluetooth\b", re.IGNORECASE), "Bluetooth"),
)

_MANUFACTURERS = {
    "seeed": "Seeed Studio",
    "seeed studio": "Seeed Studio",
    "seeedstudio": "Seeed Studio",
    "seeed technology": "Seeed Studio",
    "seeed technology co ltd": "Seeed Studio",
}


def normalize_value(value: str, kind: ValueKind) -> ValueNormalization:
    cleaned = _clean(value)
    if kind is ValueKind.AUTO:
        for candidate in (
            ValueKind.VOLTAGE,
            ValueKind.CURRENT,
            ValueKind.TEMPERATURE,
            ValueKind.FREQUENCY,
            ValueKind.PERCENT,
            ValueKind.PRESSURE,
        ):
            quantity = _normalize_quantity(cleaned, candidate)
            if quantity is not None:
                return quantity
    if kind in _QUANTITY_UNITS:
        quantity = _normalize_quantity(cleaned, kind)
        if quantity is not None:
            return quantity
    if kind is ValueKind.DIMENSIONS:
        dimensions = _normalize_dimensions(cleaned)
        if dimensions is not None:
            return dimensions
    if kind is ValueKind.INTERFACE:
        interfaces = normalize_interface(cleaned)
        if interfaces:
            return ValueNormalization(
                ", ".join(item.value for item in interfaces),
                None,
                "interface.aliases.v1",
                NormalizationConfidence.HIGH,
            )
    return ValueNormalization(
        cleaned,
        None,
        "text.nfkc-whitespace.v1",
        NormalizationConfidence.LOW,
    )


def normalize_interface(value: str) -> tuple[ValueNormalization, ...]:
    cleaned = _clean(value)
    found = tuple(
        ValueNormalization(
            canonical,
            None,
            "interface.aliases.v1",
            NormalizationConfidence.HIGH,
        )
        for pattern, canonical in _INTERFACES
        if pattern.search(cleaned)
    )
    return tuple(dict.fromkeys(found))


def normalize_manufacturer(value: str) -> ValueNormalization:
    cleaned = _clean(value)
    key = re.sub(r"[^a-z0-9]+", " ", cleaned.casefold()).strip()
    canonical = _MANUFACTURERS.get(key)
    if canonical is not None:
        return ValueNormalization(
            canonical,
            None,
            "manufacturer.aliases.v1",
            NormalizationConfidence.HIGH,
        )
    return ValueNormalization(
        cleaned,
        None,
        "manufacturer.nfkc.v1",
        NormalizationConfidence.LOW,
    )


def normalize_part_number(value: str) -> ValueNormalization:
    cleaned = _clean(value).replace("–", "-").replace("—", "-").replace("−", "-")
    normalized = cleaned.upper() if re.fullmatch(r"[A-Za-z0-9._+ -]+", cleaned) else cleaned
    return ValueNormalization(
        normalized,
        None,
        "part-number.ascii-case.v1",
        NormalizationConfidence.MEDIUM,
    )


def _normalize_quantity(value: str, kind: ValueKind) -> ValueNormalization | None:
    units = _QUANTITY_UNITS[kind]
    unit_pattern = "|".join(f"(?:{pattern})" for pattern, _ in units)
    range_match = re.fullmatch(
        rf"\s*({_NUMBER})\s*({unit_pattern})?\s*{_RANGE_SEPARATOR}\s*({_NUMBER})\s*({unit_pattern})?\s*(.*)",
        value,
        re.IGNORECASE,
    )
    if range_match is not None:
        first, first_unit, second, second_unit, suffix = range_match.groups()
        canonical = _canonical_unit(second_unit or first_unit, units)
        if canonical is not None and (
            first_unit is None or _canonical_unit(first_unit, units) == canonical
        ):
            return ValueNormalization(
                _with_suffix(f"{_number(first)}–{_number(second)} {canonical}", suffix),
                canonical,
                f"quantity.{kind.value}.range.v1",
                NormalizationConfidence.HIGH,
            )
    tolerance_match = re.fullmatch(
        rf"\s*±\s*({_NUMBER})\s*({unit_pattern})\s*(.*)", value, re.IGNORECASE
    )
    if tolerance_match is not None:
        number, unit, suffix = tolerance_match.groups()
        canonical = _canonical_unit(unit, units)
        if canonical is not None:
            return ValueNormalization(
                _with_suffix(f"±{_number(number)} {canonical}", suffix),
                canonical,
                f"quantity.{kind.value}.tolerance.v1",
                NormalizationConfidence.HIGH,
            )
    single_match = re.fullmatch(rf"\s*({_NUMBER})\s*({unit_pattern})\s*(.*)", value, re.IGNORECASE)
    if single_match is None:
        return None
    number, unit, suffix = single_match.groups()
    canonical = _canonical_unit(unit, units)
    if canonical is None:
        return None
    return ValueNormalization(
        _with_suffix(f"{_number(number)} {canonical}", suffix),
        canonical,
        f"quantity.{kind.value}.scalar.v1",
        NormalizationConfidence.HIGH,
    )


def _normalize_dimensions(value: str) -> ValueNormalization | None:
    match = _DIMENSIONS.fullmatch(value)
    if match is None:
        return None
    first, second, third, raw_unit = match.groups()
    units = {
        None: None,
        "mm": "mm",
        "millimeter": "mm",
        "millimeters": "mm",
        "cm": "cm",
        "centimeter": "cm",
        "centimeters": "cm",
        "px": "px",
        "pixel": "px",
        "pixels": "px",
    }
    unit = units.get(raw_unit.casefold() if raw_unit else None)
    if raw_unit is not None and unit is None:
        return None
    values = [_number(first), _number(second)]
    if third is not None:
        values.append(_number(third))
    normalized = " × ".join(values)
    if unit is not None:
        normalized = f"{normalized} {unit}"
    return ValueNormalization(
        normalized,
        unit,
        "dimensions.axes.v1",
        NormalizationConfidence.HIGH,
    )


def _canonical_unit(value: str | None, units: tuple[tuple[str, str], ...]) -> str | None:
    if value is None:
        return None
    return next(
        (canonical for pattern, canonical in units if re.fullmatch(pattern, value, re.IGNORECASE)),
        None,
    )


def _number(value: str) -> str:
    stripped = value.lstrip("+")
    if "." in stripped:
        stripped = stripped.rstrip("0").rstrip(".")
    return "0" if stripped in {"-0", ""} else stripped


def _with_suffix(value: str, suffix: str) -> str:
    cleaned = _clean(suffix)
    return f"{value} {cleaned}" if cleaned else value


def _clean(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    return _SPACE.sub(" ", normalized)
