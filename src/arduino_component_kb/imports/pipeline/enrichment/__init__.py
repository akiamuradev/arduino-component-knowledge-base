"""Enrichment providers and reusable external indexes."""

from arduino_component_kb.imports.pipeline.enrichment.kicad_index import (
    DEFAULT_KICAD_LIBRARY_ALLOWLIST,
    KicadIndexBuildResult,
    KicadIndexBuildStats,
    KicadIndexCache,
    KicadSymbolIndexer,
)
from arduino_component_kb.imports.pipeline.enrichment.kicad_provider import (
    KiCadEnrichmentProvider,
)
from arduino_component_kb.imports.pipeline.enrichment.matcher import (
    DEFAULT_AUTO_ACCEPT_THRESHOLD,
    MATCHER_VERSION,
    REVIEW_THRESHOLD_BASIS_POINTS,
    SeeedKicadMatcher,
)

__all__ = [
    "DEFAULT_KICAD_LIBRARY_ALLOWLIST",
    "DEFAULT_AUTO_ACCEPT_THRESHOLD",
    "KiCadEnrichmentProvider",
    "KicadIndexBuildResult",
    "KicadIndexBuildStats",
    "KicadIndexCache",
    "KicadSymbolIndexer",
    "MATCHER_VERSION",
    "REVIEW_THRESHOLD_BASIS_POINTS",
    "SeeedKicadMatcher",
]
