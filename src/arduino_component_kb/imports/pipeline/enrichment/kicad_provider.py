"""KiCad candidate lookup for an already resolved component identity."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import EnrichmentError
from arduino_component_kb.imports.pipeline.models import (
    ComponentIdentity,
    KicadCandidateSet,
    KicadEnrichmentRequest,
    KicadMatchBasis,
    KicadMatchedTerm,
    KicadSearchHit,
    KicadSymbolIndex,
    KicadSymbolRecord,
    NormalizedFacts,
)

_BASIS_ORDER = {
    KicadMatchBasis.EXACT_PART_NUMBER: 0,
    KicadMatchBasis.ALIAS: 1,
    KicadMatchBasis.NORMALIZED_NAME: 2,
    KicadMatchBasis.DESCRIPTION: 3,
    KicadMatchBasis.MANUFACTURER_HINT: 4,
}


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class KiCadEnrichmentProvider:
    """Return low-level KiCad matches without composing or persisting a card."""

    provider_name = "kicad-symbol-enrichment-v1"
    provider_version = "1.0.0"

    def __init__(
        self,
        index: KicadSymbolIndex,
        clock: Clock | None = None,
        *,
        candidate_limit: int = 100,
    ) -> None:
        if not 1 <= candidate_limit <= 200:
            raise ValueError("kicad_candidate_limit_invalid")
        self.index = index
        self.clock = clock or SystemClock()
        self.candidate_limit = candidate_limit

    async def enrich(
        self,
        context: ImportPipelineContext,
        value: KicadEnrichmentRequest,
    ) -> StageResult[KicadCandidateSet]:
        started_at = self.clock.now()
        if context.next_stage is not PipelineStage.ENRICHMENT:
            raise EnrichmentError("enrichment_stage_out_of_order")
        if context.source_key != value.identity.artifact.source.source_key:
            raise EnrichmentError("pipeline_source_mismatch")
        hits = self.find_candidates(value.identity, value.facts)
        warnings = () if hits else ("kicad_candidates_missing",)
        candidates = KicadCandidateSet(
            identity_sha256=sha256(value.identity.to_json().encode()).hexdigest(),
            index_sha256=self.index.index_sha256,
            index_revision=self.index.source_revision,
            hits=hits,
            warnings=warnings,
        )
        completed_at = self.clock.now()
        updated = context.advance(
            StageExecution(
                PipelineStage.ENRICHMENT,
                started_at,
                completed_at,
                warnings,
            )
        )
        return StageResult(PipelineStage.ENRICHMENT, updated, candidates)

    def find_candidates(
        self,
        identity: ComponentIdentity,
        facts: NormalizedFacts,
    ) -> tuple[KicadSearchHit, ...]:
        if identity.normalized_facts != facts:
            raise ValueError("kicad_enrichment_facts_mismatch")
        matches: dict[str, tuple[KicadSymbolRecord, list[KicadMatchedTerm]]] = {}

        explicit_terms = _unique(
            item.trace.normalized_value
            for item in (*identity.part_numbers, *identity.primary_ic_candidates)
        )
        for query in explicit_terms:
            self._add_matches(
                matches,
                self.index.exact_part_number(query),
                KicadMatchBasis.EXACT_PART_NUMBER,
                query,
            )
            self._add_matches(
                matches,
                self.index.alias(query),
                KicadMatchBasis.ALIAS,
                query,
            )

        alias_terms = _unique(
            (
                *(item.trace.normalized_value for item in identity.product_identifiers),
                *(item.value for item in identity.aliases),
            )
        )
        for query in alias_terms:
            self._add_matches(
                matches,
                self.index.alias(query),
                KicadMatchBasis.ALIAS,
                query,
            )

        name_terms = _unique((identity.canonical_name.value, *alias_terms))
        for query in name_terms:
            self._add_matches(
                matches,
                self.index.normalized_name(query),
                KicadMatchBasis.NORMALIZED_NAME,
                query,
            )

        self._add_matches(
            matches,
            self.index.description(identity.canonical_name.value, self.candidate_limit),
            KicadMatchBasis.DESCRIPTION,
            identity.canonical_name.value,
        )

        if identity.manufacturer is not None:
            manufacturer = identity.manufacturer.value
            manufacturer_ids = {
                item.record_id for item in self.index.manufacturer_hint(manufacturer)
            }
            for record_id, (record, terms) in matches.items():
                if record_id in manufacturer_ids:
                    terms.append(
                        KicadMatchedTerm(
                            KicadMatchBasis.MANUFACTURER_HINT,
                            manufacturer,
                            record.manufacturer_hints[0],
                        )
                    )

        hits: list[KicadSearchHit] = []
        for record, terms in matches.values():
            stable_terms = tuple(
                dict.fromkeys(
                    sorted(
                        terms,
                        key=lambda item: (
                            _BASIS_ORDER[item.basis],
                            item.query.casefold(),
                            item.matched_value.casefold(),
                        ),
                    )
                )
            )
            has_explicit_identity = any(
                item.basis is KicadMatchBasis.EXACT_PART_NUMBER for item in stable_terms
            )
            if record.is_generic and not has_explicit_identity:
                continue
            hits.append(KicadSearchHit(record, stable_terms))
        return tuple(
            sorted(
                hits,
                key=lambda item: (
                    min(_BASIS_ORDER[term.basis] for term in item.matched_terms),
                    item.record.record_id,
                ),
            )[: self.candidate_limit]
        )

    @staticmethod
    def _add_matches(
        matches: dict[str, tuple[KicadSymbolRecord, list[KicadMatchedTerm]]],
        records: tuple[KicadSymbolRecord, ...],
        basis: KicadMatchBasis,
        query: str,
    ) -> None:
        for record in records:
            existing = matches.setdefault(record.record_id, (record, []))
            matched_value = {
                KicadMatchBasis.EXACT_PART_NUMBER: record.symbol_name,
                KicadMatchBasis.ALIAS: _matching_alias(record, query),
                KicadMatchBasis.NORMALIZED_NAME: record.symbol_name,
                KicadMatchBasis.DESCRIPTION: record.description or " ".join(record.keywords),
                KicadMatchBasis.MANUFACTURER_HINT: query,
            }[basis]
            existing[1].append(KicadMatchedTerm(basis, query, matched_value))


def _matching_alias(record: KicadSymbolRecord, query: str) -> str:
    return next(
        (value for value in record.aliases if value.casefold() == query.casefold()),
        record.symbol_name,
    )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value.strip()))
