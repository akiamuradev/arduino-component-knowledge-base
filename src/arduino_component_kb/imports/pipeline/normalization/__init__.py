"""Deterministic semantic normalization for the parallel import pipeline."""

from arduino_component_kb.imports.pipeline.normalization.registry import (
    SPECIFICATION_REGISTRY,
    SpecificationDefinition,
    SpecificationRegistry,
    ValueKind,
)
from arduino_component_kb.imports.pipeline.normalization.semantic import SemanticFactNormalizer
from arduino_component_kb.imports.pipeline.normalization.values import (
    NORMALIZATION_RULE_VERSION,
    ValueNormalization,
    normalize_interface,
    normalize_manufacturer,
    normalize_part_number,
    normalize_value,
)

__all__ = [
    "NORMALIZATION_RULE_VERSION",
    "SPECIFICATION_REGISTRY",
    "SemanticFactNormalizer",
    "SpecificationDefinition",
    "SpecificationRegistry",
    "ValueKind",
    "ValueNormalization",
    "normalize_interface",
    "normalize_manufacturer",
    "normalize_part_number",
    "normalize_value",
]
