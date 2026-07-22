"""Evidence-backed identity resolution for the parallel import pipeline."""

from arduino_component_kb.imports.pipeline.identity.resolver import WeightedIdentityResolver
from arduino_component_kb.imports.pipeline.identity.rules import (
    AUTO_RESOLVE_MARGIN,
    AUTO_RESOLVE_SCORE,
    CATEGORY_RULES,
    IDENTITY_RULE_VERSION,
    REVIEW_SCORE,
    CategoryRule,
)

__all__ = [
    "AUTO_RESOLVE_MARGIN",
    "AUTO_RESOLVE_SCORE",
    "CATEGORY_RULES",
    "IDENTITY_RULE_VERSION",
    "REVIEW_SCORE",
    "CategoryRule",
    "WeightedIdentityResolver",
]
