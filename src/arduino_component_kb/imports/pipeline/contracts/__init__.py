"""Public stage interfaces for the future import pipeline."""

from arduino_component_kb.imports.pipeline.contracts.acquisition import SourceAcquirer
from arduino_component_kb.imports.pipeline.contracts.composition import CardComposer
from arduino_component_kb.imports.pipeline.contracts.enrichment import EnrichmentProvider
from arduino_component_kb.imports.pipeline.contracts.evaluation import QualityEvaluator
from arduino_component_kb.imports.pipeline.contracts.extraction import FactExtractor
from arduino_component_kb.imports.pipeline.contracts.identity import IdentityResolver
from arduino_component_kb.imports.pipeline.contracts.normalization import FactNormalizer
from arduino_component_kb.imports.pipeline.contracts.persistence import ImportPersistenceGateway

__all__ = [
    "CardComposer",
    "EnrichmentProvider",
    "FactExtractor",
    "FactNormalizer",
    "IdentityResolver",
    "ImportPersistenceGateway",
    "QualityEvaluator",
    "SourceAcquirer",
]
