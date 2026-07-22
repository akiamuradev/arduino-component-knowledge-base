"""Semantic normalizer from ExtractedFacts to deterministic NormalizedFacts."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import NormalizationError
from arduino_component_kb.imports.pipeline.models import (
    ExtractedFacts,
    ExtractedField,
    Identifier,
    NormalizationConfidence,
    NormalizationConflict,
    NormalizationProfile,
    NormalizationTrace,
    NormalizedFacts,
    NormalizedIdentifier,
    NormalizedSpecification,
    NormalizedTextFact,
    RawSpecification,
    UnmappedSpecification,
)
from arduino_component_kb.imports.pipeline.normalization.registry import (
    SPECIFICATION_REGISTRY,
    SpecificationRegistry,
    ValueKind,
)
from arduino_component_kb.imports.pipeline.normalization.values import (
    NORMALIZATION_RULE_VERSION,
    ValueNormalization,
    normalize_interface,
    normalize_manufacturer,
    normalize_part_number,
    normalize_value,
)

_PROFILE_TOKENS: tuple[tuple[NormalizationProfile, re.Pattern[str]], ...] = (
    (NormalizationProfile.DISPLAY, re.compile(r"\b(?:display|lcd|oled|screen)\b", re.I)),
    (
        NormalizationProfile.COMMUNICATION,
        re.compile(r"\b(?:can bus|communication|lora|radio|wireless)\b", re.I),
    ),
    (NormalizationProfile.ACTUATOR, re.compile(r"\b(?:actuator|motor|relay|servo)\b", re.I)),
    (
        NormalizationProfile.SENSOR,
        re.compile(r"\b(?:sensor|sensing|temperature|humidity|pressure|ranger)\b", re.I),
    ),
    (NormalizationProfile.BOARD, re.compile(r"\b(?:board|xiao|shield|microcontroller)\b", re.I)),
)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SemanticFactNormalizer:
    normalizer_name = "semantic-facts-v1"
    normalizer_version = "1.0.0"

    def __init__(
        self,
        clock: Clock | None = None,
        registry: SpecificationRegistry = SPECIFICATION_REGISTRY,
    ) -> None:
        self.clock = clock or SystemClock()
        self.registry = registry

    async def normalize(
        self, context: ImportPipelineContext, facts: ExtractedFacts
    ) -> StageResult[NormalizedFacts]:
        started_at = self.clock.now()
        if context.source_key != facts.artifact.source.source_key:
            raise NormalizationError("pipeline_source_mismatch")
        if context.next_stage is not PipelineStage.NORMALIZATION:
            raise NormalizationError("normalization_stage_out_of_order")
        normalized = self._normalize(facts)
        completed_at = self.clock.now()
        updated = context.advance(
            StageExecution(
                stage=PipelineStage.NORMALIZATION,
                started_at=started_at,
                completed_at=completed_at,
                warnings=normalized.warnings,
            )
        )
        return StageResult(PipelineStage.NORMALIZATION, updated, normalized)

    def _normalize(self, facts: ExtractedFacts) -> NormalizedFacts:
        profile = self._profile(facts)
        specifications: list[NormalizedSpecification] = []
        unmapped: list[UnmappedSpecification] = []
        interfaces: list[NormalizedTextFact] = []
        unmapped_interfaces: list[NormalizedTextFact] = []

        for field in facts.specifications:
            definition = self.registry.resolve(field.value.label, profile)
            if definition is None:
                unmapped.append(
                    UnmappedSpecification(
                        field.value.label,
                        field.value.value,
                        field.raw_value,
                        "taxonomy.alias-unmapped.v1",
                        field.evidence,
                    )
                )
                continue
            value = normalize_value(field.value.value, definition.value_kind)
            specifications.append(
                NormalizedSpecification(
                    definition.taxonomy_path,
                    definition.canonical_label,
                    field.value.label,
                    value.unit,
                    self._trace(field, value),
                    field.evidence,
                )
            )
            if definition.value_kind is ValueKind.INTERFACE:
                self._add_interfaces(field, interfaces, unmapped_interfaces)

        for interface_field in facts.interface_facts:
            self._add_interfaces(interface_field, interfaces, unmapped_interfaces)

        normalized_interfaces = self._merge_text_facts(interfaces)
        unknown_interfaces = self._merge_text_facts(unmapped_interfaces)
        manufacturers = self._merge_text_facts(
            [
                NormalizedTextFact(
                    "identity.manufacturer",
                    self._trace(field, normalize_manufacturer(field.value)),
                    field.evidence,
                )
                for field in facts.manufacturer_candidates
            ]
        )
        conflicts = self._conflicts(specifications)
        warnings = tuple(
            code
            for condition, code in (
                (bool(unmapped), "unmapped_specification"),
                (bool(unknown_interfaces), "unmapped_interface"),
                (bool(conflicts), "normalization_conflict"),
            )
            if condition
        )
        return NormalizedFacts(
            artifact=facts.artifact,
            extracted_facts_sha256=sha256(facts.to_json().encode()).hexdigest(),
            extracted_facts=facts,
            profile=profile,
            specifications=tuple(specifications),
            unmapped_specifications=tuple(unmapped),
            interfaces=normalized_interfaces,
            unmapped_interfaces=unknown_interfaces,
            manufacturers=manufacturers,
            identifiers=tuple(self._identifier(field) for field in facts.identifiers),
            primary_ics=tuple(self._identifier(field) for field in facts.primary_ic_candidates),
            conflicts=conflicts,
            warnings=warnings,
        )

    def _add_interfaces(
        self,
        field: ExtractedField[str] | ExtractedField[RawSpecification],
        normalized: list[NormalizedTextFact],
        unmapped: list[NormalizedTextFact],
    ) -> None:
        original = field.value if isinstance(field.value, str) else field.value.value
        matches = normalize_interface(original)
        if not matches:
            fallback = ValueNormalization(
                normalize_value(original, ValueKind.TEXT).value,
                None,
                "interface.unmapped.v1",
                NormalizationConfidence.LOW,
            )
            unmapped.append(
                NormalizedTextFact(
                    "communication.interface_unmapped",
                    self._trace_value(original, field.raw_value, fallback),
                    field.evidence,
                )
            )
            return
        normalized.extend(
            NormalizedTextFact(
                "communication.interface",
                self._trace_value(original, field.raw_value, match),
                field.evidence,
            )
            for match in matches
        )

    def _identifier(self, field: ExtractedField[Identifier]) -> NormalizedIdentifier:
        value = normalize_part_number(field.value.value)
        return NormalizedIdentifier(
            field.value.kind,
            self._trace_value(field.value.value, field.raw_value, value),
            field.evidence,
        )

    @staticmethod
    def _trace(
        field: ExtractedField[str] | ExtractedField[RawSpecification],
        normalized: ValueNormalization,
    ) -> NormalizationTrace:
        original = field.value if isinstance(field.value, str) else field.value.value
        return SemanticFactNormalizer._trace_value(original, field.raw_value, normalized)

    @staticmethod
    def _trace_value(original: str, raw: str, normalized: ValueNormalization) -> NormalizationTrace:
        return NormalizationTrace(
            original,
            raw,
            normalized.value,
            normalized.rule_id,
            NORMALIZATION_RULE_VERSION,
            normalized.confidence,
        )

    @staticmethod
    def _profile(facts: ExtractedFacts) -> NormalizationProfile:
        searchable = " ".join(
            field.value
            for fields in (
                facts.title_candidates,
                facts.summary_candidates,
                facts.feature_facts,
                facts.application_facts,
            )
            for field in fields
        )
        return next(
            (profile for profile, pattern in _PROFILE_TOKENS if pattern.search(searchable)),
            NormalizationProfile.GENERIC,
        )

    @staticmethod
    def _merge_text_facts(facts: list[NormalizedTextFact]) -> tuple[NormalizedTextFact, ...]:
        merged: list[NormalizedTextFact] = []
        for fact in facts:
            index = next(
                (
                    index
                    for index, existing in enumerate(merged)
                    if existing.semantic_path == fact.semantic_path
                    and existing.trace.normalized_value == fact.trace.normalized_value
                ),
                None,
            )
            if index is None:
                merged.append(fact)
                continue
            existing = merged[index]
            merged[index] = NormalizedTextFact(
                existing.semantic_path,
                existing.trace,
                tuple(dict.fromkeys((*existing.evidence, *fact.evidence))),
            )
        return tuple(merged)

    @staticmethod
    def _conflicts(
        specifications: list[NormalizedSpecification],
    ) -> tuple[NormalizationConflict, ...]:
        grouped: dict[str, list[NormalizedSpecification]] = defaultdict(list)
        for specification in specifications:
            grouped[specification.taxonomy_path].append(specification)
        conflicts: list[NormalizationConflict] = []
        for path, candidates in grouped.items():
            values = tuple(dict.fromkeys(item.trace.normalized_value for item in candidates))
            sections = {
                evidence.section
                for candidate in candidates
                for evidence in candidate.evidence
                if evidence.section is not None
            }
            if len(values) < 2 or len(sections) < 2:
                continue
            conflicts.append(
                NormalizationConflict(
                    path,
                    values,
                    tuple(
                        dict.fromkeys(
                            evidence for candidate in candidates for evidence in candidate.evidence
                        )
                    ),
                )
            )
        return tuple(conflicts)
