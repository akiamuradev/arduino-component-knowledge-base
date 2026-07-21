"""Controlled normalization for specifications extracted from untrusted repositories."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class CanonicalSpecification:
    key: str
    label: str
    value: str


_DEFINITIONS: dict[str, tuple[str, frozenset[str]]] = {
    "supply-voltage": (
        "Supply voltage",
        frozenset(
            {
                "supply",
                "supply voltage",
                "input voltage",
                "working voltage",
                "rated voltage",
                "voltage",
            }
        ),
    ),
    "operating-voltage": (
        "Operating voltage",
        frozenset({"operating voltage", "operation voltage", "operational voltage"}),
    ),
    "operating-current": (
        "Operating current",
        frozenset(
            {
                "current",
                "current consumption",
                "operating current",
                "operation current",
                "working current",
            }
        ),
    ),
    "power-consumption": (
        "Power consumption",
        frozenset({"power consumption", "rated power", "max power", "maximum power"}),
    ),
    "operating-temperature": (
        "Operating temperature",
        frozenset(
            {
                "operating temperature",
                "operating temperature range",
                "operation temperature",
                "working temperature",
                "temperature range",
            }
        ),
    ),
    "measurement-range": (
        "Measurement range",
        frozenset(
            {
                "detection range",
                "measuring range",
                "measurement range",
                "operating range",
                "range",
                "sensing range",
            }
        ),
    ),
    "accuracy": ("Accuracy", frozenset({"accuracy", "measurement accuracy"})),
    "resolution": ("Resolution", frozenset({"resolution"})),
    "frequency": (
        "Frequency",
        frozenset({"frequency", "operating frequency", "sampling frequency"}),
    ),
    "dimensions": (
        "Dimensions",
        frozenset({"dimensions", "dimension", "product size", "size"}),
    ),
    "weight": ("Weight", frozenset({"net weight", "weight"})),
    "interface": (
        "Interface",
        frozenset({"bus", "communication interface", "interface", "protocol"}),
    ),
    "connector": ("Connector", frozenset({"connector", "connector type"})),
    "electrical-life": (
        "Electrical life",
        frozenset({"electrical life", "mechanical life"}),
    ),
    "actuation-force": (
        "Actuation force",
        frozenset({"actuation force", "operation force", "operating force"}),
    ),
}

_ALIASES = {
    alias: (key, label)
    for key, (label, aliases) in _DEFINITIONS.items()
    for alias in aliases | {key.replace("-", " ")}
}


def canonical_specification(label: str, value: str) -> CanonicalSpecification | None:
    """Return an application-controlled specification or reject an unknown upstream field."""

    normalized_label = _normalize_label(label)
    definition = _ALIASES.get(normalized_label)
    normalized_value = _SPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()
    if definition is None or not normalized_value:
        return None
    key, canonical_label = definition
    return CanonicalSpecification(key, canonical_label, normalized_value[:2_000])


def canonical_specification_keys() -> frozenset[str]:
    return frozenset(_DEFINITIONS)


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return _SPACE.sub(" ", _PUNCTUATION.sub(" ", normalized)).strip()
