"""Versioned hierarchical specification taxonomy and label aliases."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from arduino_component_kb.imports.pipeline.models import NormalizationProfile

_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_TAXONOMY_PATH = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")


class ValueKind(StrEnum):
    AUTO = "auto"
    VOLTAGE = "voltage"
    CURRENT = "current"
    TEMPERATURE = "temperature"
    FREQUENCY = "frequency"
    DIMENSIONS = "dimensions"
    PERCENT = "percent"
    PRESSURE = "pressure"
    INTERFACE = "interface"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class SpecificationDefinition:
    taxonomy_path: str
    canonical_label: str
    aliases: frozenset[str]
    value_kind: ValueKind
    profiles: frozenset[NormalizationProfile] = frozenset()

    def __post_init__(self) -> None:
        if _TAXONOMY_PATH.fullmatch(self.taxonomy_path) is None:
            raise ValueError("specification_taxonomy_path_invalid")
        if not self.canonical_label.strip() or len(self.canonical_label) > 500:
            raise ValueError("specification_canonical_label_invalid")
        normalized_aliases = frozenset(normalize_label(item) for item in self.aliases)
        if not normalized_aliases or "" in normalized_aliases:
            raise ValueError("specification_aliases_invalid")
        object.__setattr__(self, "aliases", normalized_aliases)


class SpecificationRegistry:
    version = "1.0.0"

    def __init__(self, definitions: tuple[SpecificationDefinition, ...]) -> None:
        if not definitions:
            raise ValueError("specification_registry_empty")
        paths = [item.taxonomy_path for item in definitions]
        if len(paths) != len(set(paths)):
            raise ValueError("specification_taxonomy_path_duplicate")
        self.definitions = definitions
        self._aliases: dict[str, list[SpecificationDefinition]] = {}
        for definition in definitions:
            for alias in definition.aliases:
                existing = self._aliases.setdefault(alias, [])
                if any(
                    (not item.profiles and not definition.profiles)
                    or (
                        bool(item.profiles)
                        and bool(definition.profiles)
                        and bool(item.profiles.intersection(definition.profiles))
                    )
                    for item in existing
                ):
                    raise ValueError("specification_alias_profile_overlap")
                existing.append(definition)

    def resolve(self, label: str, profile: NormalizationProfile) -> SpecificationDefinition | None:
        definitions = self._aliases.get(normalize_label(label), [])
        return next(
            (item for item in definitions if profile in item.profiles),
            next((item for item in definitions if not item.profiles), None),
        )

    def taxonomy_paths(self) -> frozenset[str]:
        return frozenset(item.taxonomy_path for item in self.definitions)

    def taxonomy_branches(self) -> frozenset[str]:
        return frozenset(
            ".".join(parts[:index])
            for definition in self.definitions
            for parts in (definition.taxonomy_path.split("."),)
            for index in range(1, len(parts))
        )


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return _SPACE.sub(" ", _PUNCTUATION.sub(" ", normalized)).strip()


def _definition(
    path: str,
    label: str,
    aliases: tuple[str, ...],
    kind: ValueKind,
    *profiles: NormalizationProfile,
) -> SpecificationDefinition:
    return SpecificationDefinition(path, label, frozenset(aliases), kind, frozenset(profiles))


SPECIFICATION_REGISTRY = SpecificationRegistry(
    (
        _definition(
            "sensor.temperature.measurement_range",
            "Temperature measurement range",
            ("temperature range",),
            ValueKind.TEMPERATURE,
            NormalizationProfile.SENSOR,
        ),
        _definition(
            "environment.temperature.operating_range",
            "Operating temperature",
            (
                "operating temperature",
                "operating temperature range",
                "operation temperature",
                "temperature range",
                "working temperature",
            ),
            ValueKind.TEMPERATURE,
        ),
        _definition(
            "sensor.humidity.measurement_range",
            "Humidity measurement range",
            ("humidity range",),
            ValueKind.PERCENT,
            NormalizationProfile.SENSOR,
        ),
        _definition(
            "sensor.pressure.measurement_range",
            "Pressure measurement range",
            ("pressure range",),
            ValueKind.PRESSURE,
            NormalizationProfile.SENSOR,
        ),
        _definition(
            "display.resolution",
            "Display resolution",
            ("resolution",),
            ValueKind.DIMENSIONS,
            NormalizationProfile.DISPLAY,
        ),
        _definition(
            "measurement.resolution",
            "Resolution",
            ("resolution",),
            ValueKind.TEXT,
        ),
        _definition(
            "communication.frequency.carrier",
            "Carrier frequency",
            ("frequency", "operating frequency"),
            ValueKind.FREQUENCY,
            NormalizationProfile.COMMUNICATION,
        ),
        _definition(
            "signal.frequency",
            "Frequency",
            ("frequency", "operating frequency", "sampling frequency"),
            ValueKind.FREQUENCY,
        ),
        _definition(
            "actuator.current.maximum_output",
            "Maximum output current",
            ("maximum current", "max current"),
            ValueKind.CURRENT,
            NormalizationProfile.ACTUATOR,
        ),
        _definition(
            "electrical.current.maximum",
            "Maximum current",
            ("maximum current", "max current"),
            ValueKind.CURRENT,
        ),
        _definition(
            "electrical.voltage.supply",
            "Supply voltage",
            (
                "input voltage",
                "rated voltage",
                "supply",
                "supply voltage",
                "voltage",
                "working voltage",
            ),
            ValueKind.VOLTAGE,
        ),
        _definition(
            "electrical.voltage.operating",
            "Operating voltage",
            ("operating voltage", "operation voltage", "operational voltage"),
            ValueKind.VOLTAGE,
        ),
        _definition(
            "electrical.current.operating",
            "Operating current",
            (
                "current",
                "current consumption",
                "operating current",
                "operation current",
                "working current",
            ),
            ValueKind.CURRENT,
        ),
        _definition(
            "electrical.efficiency",
            "Efficiency",
            ("efficiency",),
            ValueKind.PERCENT,
        ),
        _definition(
            "measurement.range",
            "Measurement range",
            (
                "detection range",
                "measuring range",
                "measurement range",
                "operating range",
                "range",
                "sensing range",
            ),
            ValueKind.AUTO,
        ),
        _definition(
            "measurement.accuracy",
            "Accuracy",
            ("accuracy", "measurement accuracy"),
            ValueKind.AUTO,
        ),
        _definition(
            "physical.dimensions",
            "Dimensions",
            ("dimension", "dimensions", "product size", "size"),
            ValueKind.DIMENSIONS,
        ),
        _definition(
            "communication.interface",
            "Interface",
            ("bus", "communication interface", "interface", "interfaces", "protocol"),
            ValueKind.INTERFACE,
        ),
        _definition(
            "mechanical.connector",
            "Connector",
            ("connector", "connector type"),
            ValueKind.TEXT,
        ),
        _definition(
            "identity.primary_ic",
            "Primary IC",
            ("chip", "controller", "main chip", "main ic", "mcu", "primary ic", "sensor ic"),
            ValueKind.TEXT,
        ),
        _definition(
            "display.color",
            "Display color",
            ("display color", "colour", "color"),
            ValueKind.TEXT,
            NormalizationProfile.DISPLAY,
        ),
        _definition(
            "communication.link_budget",
            "Link budget",
            ("link budget",),
            ValueKind.TEXT,
            NormalizationProfile.COMMUNICATION,
        ),
        _definition(
            "board.processor",
            "Processor",
            ("processor", "cpu"),
            ValueKind.TEXT,
            NormalizationProfile.BOARD,
        ),
    )
)
