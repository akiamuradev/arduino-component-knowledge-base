"""Enrichment providers and reusable external indexes."""

from arduino_component_kb.imports.pipeline.enrichment.kicad_distribution import (
    KICAD_INDEX_ARTIFACT_SCHEMA,
    BuiltKicadIndexArtifact,
    KicadIndexArtifactError,
    KicadIndexArtifactLoader,
    KicadIndexLibraryManifest,
    KicadIndexManifest,
    KicadIndexSourceSnapshot,
    LoadedKicadIndexArtifact,
    build_kicad_index_artifact,
    deserialize_kicad_index_artifact,
    publish_kicad_index_artifact,
    snapshot_from_directory,
)
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
    "BuiltKicadIndexArtifact",
    "KiCadEnrichmentProvider",
    "KICAD_INDEX_ARTIFACT_SCHEMA",
    "KicadIndexArtifactError",
    "KicadIndexArtifactLoader",
    "KicadIndexBuildResult",
    "KicadIndexBuildStats",
    "KicadIndexCache",
    "KicadIndexLibraryManifest",
    "KicadIndexManifest",
    "KicadIndexSourceSnapshot",
    "KicadSymbolIndexer",
    "LoadedKicadIndexArtifact",
    "MATCHER_VERSION",
    "REVIEW_THRESHOLD_BASIS_POINTS",
    "SeeedKicadMatcher",
    "build_kicad_index_artifact",
    "deserialize_kicad_index_artifact",
    "publish_kicad_index_artifact",
    "snapshot_from_directory",
]
