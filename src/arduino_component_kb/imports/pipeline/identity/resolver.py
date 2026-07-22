"""Weighted, explainable resolver for names, kinds and category candidates."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import IdentityError
from arduino_component_kb.imports.pipeline.identity.rules import (
    AUTO_RESOLVE_MARGIN,
    AUTO_RESOLVE_SCORE,
    CATEGORY_RULES,
    IDENTITY_RULE_VERSION,
    REVIEW_SCORE,
    CategoryRule,
)
from arduino_component_kb.imports.pipeline.models import (
    CategoryCandidate,
    ComponentIdentity,
    ComponentKind,
    EvidenceFragment,
    ExtractedField,
    IdentifierKind,
    IdentityAlias,
    IdentityConfidence,
    IdentityResolutionStatus,
    IdentityValue,
    KindCandidate,
    NormalizedFacts,
    NormalizedIdentifier,
    ScoreContribution,
)

_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Signal:
    value: str
    evidence: tuple[EvidenceFragment, ...]


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class WeightedIdentityResolver:
    resolver_name = "weighted-identity-v1"
    resolver_version = IDENTITY_RULE_VERSION

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    async def resolve(
        self, context: ImportPipelineContext, facts: NormalizedFacts
    ) -> StageResult[ComponentIdentity]:
        started_at = self.clock.now()
        if context.source_key != facts.artifact.source.source_key:
            raise IdentityError("pipeline_source_mismatch")
        if context.next_stage is not PipelineStage.IDENTITY:
            raise IdentityError("identity_stage_out_of_order")
        identity = self._resolve(facts)
        completed_at = self.clock.now()
        updated = context.advance(
            StageExecution(
                PipelineStage.IDENTITY,
                started_at,
                completed_at,
                identity.warnings,
            )
        )
        return StageResult(PipelineStage.IDENTITY, updated, identity)

    def _resolve(self, facts: NormalizedFacts) -> ComponentIdentity:
        extracted = facts.extracted_facts
        if not extracted.title_candidates:
            raise IdentityError("identity_title_missing")
        canonical_field = extracted.title_candidates[0]
        canonical_name = IdentityValue(
            canonical_field.value,
            "identity.canonical-title.v1",
            canonical_field.evidence,
        )
        manufacturer = (
            IdentityValue(
                facts.manufacturers[0].trace.normalized_value,
                "identity.manufacturer-normalized.v1",
                facts.manufacturers[0].evidence,
            )
            if facts.manufacturers
            else None
        )
        product_identifiers = tuple(
            item for item in facts.identifiers if item.kind is not IdentifierKind.PART_NUMBER
        )
        part_numbers = tuple(
            item for item in facts.identifiers if item.kind is IdentifierKind.PART_NUMBER
        )
        aliases = self._aliases(facts, canonical_name.value)
        category_candidates = self._category_candidates(facts)
        kind_candidates = self._kind_candidates(facts, canonical_field)
        component_kind = kind_candidates[0].kind
        status, confidence = self._resolution(facts, category_candidates, kind_candidates)
        selected_category = (
            category_candidates[0].category_key
            if status is IdentityResolutionStatus.AUTO_RESOLVED
            else None
        )
        warnings = self._warnings(facts, status, category_candidates)
        return ComponentIdentity(
            artifact=facts.artifact,
            normalized_facts_sha256=sha256(facts.to_json().encode()).hexdigest(),
            normalized_facts=facts,
            canonical_name=canonical_name,
            manufacturer=manufacturer,
            product_identifiers=product_identifiers,
            part_numbers=part_numbers,
            primary_ic_candidates=facts.primary_ics,
            aliases=aliases,
            component_kind=component_kind,
            kind_candidates=kind_candidates,
            selected_category=selected_category,
            category_candidates=category_candidates,
            confidence=confidence,
            resolution_status=status,
            warnings=warnings,
        )

    def _aliases(self, facts: NormalizedFacts, canonical_name: str) -> tuple[IdentityAlias, ...]:
        aliases: list[IdentityAlias] = []
        primary_ics = {_normalized(item.trace.normalized_value) for item in facts.primary_ics}
        for field in facts.extracted_facts.title_candidates[1:]:
            if _normalized(field.value) != _normalized(canonical_name):
                aliases.append(
                    IdentityAlias(field.value, "identity.alternate-title.v1", field.evidence)
                )
        for identifier in facts.identifiers:
            value = identifier.trace.normalized_value
            if (
                identifier.kind is IdentifierKind.MODEL
                and _normalized(value) != _normalized(canonical_name)
                and _normalized(value) not in primary_ics
            ):
                aliases.append(IdentityAlias(value, "identity.model-alias.v1", identifier.evidence))
        unique: dict[str, IdentityAlias] = {}
        for alias in aliases:
            unique.setdefault(alias.value.casefold(), alias)
        return tuple(unique.values())

    def _category_candidates(self, facts: NormalizedFacts) -> tuple[CategoryCandidate, ...]:
        title, summary, details = self._signals(facts)
        candidates: list[CategoryCandidate] = []
        for rule in CATEGORY_RULES:
            breakdown: list[ScoreContribution] = []
            self._add_text_contribution(breakdown, rule, "title", 55, title)
            self._add_text_contribution(breakdown, rule, "summary", 20, summary)
            self._add_text_contribution(breakdown, rule, "details", 10, details)
            specification = next(
                (
                    item
                    for item in facts.specifications
                    if any(
                        item.taxonomy_path.startswith(prefix) for prefix in rule.taxonomy_prefixes
                    )
                ),
                None,
            )
            if specification is not None and (rule.category_key != "connectors" or breakdown):
                breakdown.append(
                    ScoreContribution(
                        f"category.{rule.category_key}.taxonomy.v1",
                        specification.taxonomy_path,
                        rule.taxonomy_weight,
                        f"Taxonomy path supports {rule.category_key}.",
                        specification.evidence,
                    )
                )
            if rule.profile is facts.profile:
                breakdown.append(
                    ScoreContribution(
                        f"category.{rule.category_key}.profile.v1",
                        facts.profile.value,
                        15,
                        f"Normalization profile supports {rule.category_key}.",
                        title[0].evidence,
                    )
                )
            if breakdown:
                candidates.append(
                    CategoryCandidate(
                        rule.category_key,
                        min(100, sum(item.weight for item in breakdown)),
                        tuple(breakdown),
                    )
                )
        exact_ic = self._exact_primary_ic(facts, title[0].value)
        if exact_ic is not None:
            candidates.append(
                CategoryCandidate(
                    "integrated-circuits",
                    85,
                    (
                        ScoreContribution(
                            "category.integrated-circuits.exact-primary-identity.v1",
                            exact_ic.trace.normalized_value,
                            85,
                            "The complete title equals an evidenced primary IC part number.",
                            tuple(dict.fromkeys((*title[0].evidence, *exact_ic.evidence))),
                        ),
                    ),
                )
            )
        return tuple(sorted(candidates, key=lambda item: (-item.score, item.category_key)))

    def _kind_candidates(
        self, facts: NormalizedFacts, canonical_field: ExtractedField[str]
    ) -> tuple[KindCandidate, ...]:
        title, summary, details = self._signals(facts)
        candidates: list[KindCandidate] = []
        rules: tuple[tuple[ComponentKind, frozenset[str], int], ...] = (
            (
                ComponentKind.DEVELOPMENT_BOARD,
                frozenset(
                    {"development board", "xiao", "seeeduino", "wio terminal", "arduino board"}
                ),
                70,
            ),
            (
                ComponentKind.CONNECTOR,
                frozenset({"connector", "terminal", "adapter", "socket", "header"}),
                70,
            ),
            (
                ComponentKind.DISCRETE_COMPONENT,
                frozenset(
                    {"resistor", "capacitor", "diode", "transistor", "mosfet", "led", "crystal"}
                ),
                70,
            ),
            (
                ComponentKind.INTEGRATED_CIRCUIT,
                frozenset({"integrated circuit", "microcontroller", "mcu", "controller ic"}),
                70,
            ),
            (
                ComponentKind.MODULE,
                frozenset(
                    {
                        "grove",
                        "module",
                        "shield",
                        "sensor",
                        "display",
                        "driver",
                        "converter",
                        "button",
                        "relay",
                    }
                ),
                35,
            ),
        )
        for kind, tokens, title_weight in rules:
            breakdown: list[ScoreContribution] = []
            matched_title = _first_match(title, tokens)
            if matched_title is not None:
                breakdown.append(
                    ScoreContribution(
                        f"kind.{kind.value}.title.v1",
                        matched_title.value,
                        title_weight,
                        f"Title supports component kind {kind.value}.",
                        matched_title.evidence,
                    )
                )
            body_match = (
                None
                if kind in {ComponentKind.DISCRETE_COMPONENT, ComponentKind.INTEGRATED_CIRCUIT}
                else _first_match((*summary, *details), tokens)
            )
            if body_match is not None:
                breakdown.append(
                    ScoreContribution(
                        f"kind.{kind.value}.body.v1",
                        body_match.value,
                        20,
                        f"Source body supports component kind {kind.value}.",
                        body_match.evidence,
                    )
                )
            if kind is ComponentKind.CONNECTOR:
                connector = next(
                    (
                        item
                        for item in facts.specifications
                        if item.taxonomy_path == "mechanical.connector"
                    ),
                    None,
                )
                if connector is not None and breakdown:
                    breakdown.append(
                        ScoreContribution(
                            "kind.connector.taxonomy.v1",
                            connector.taxonomy_path,
                            10,
                            "Connector taxonomy supports connector kind.",
                            connector.evidence,
                        )
                    )
            if kind is ComponentKind.MODULE:
                breakdown.append(
                    ScoreContribution(
                        "kind.module.registered-seeed-source.v1",
                        facts.artifact.source.source_key,
                        15,
                        "A registered Seeed product page weakly supports module identity.",
                        canonical_field.evidence,
                    )
                )
            if breakdown:
                candidates.append(
                    KindCandidate(
                        kind,
                        min(100, sum(item.weight for item in breakdown)),
                        tuple(breakdown),
                    )
                )
        exact_ic = self._exact_primary_ic(facts, canonical_field.value)
        if exact_ic is not None:
            exact_breakdown = (
                ScoreContribution(
                    "kind.integrated_circuit.exact-primary-identity.v1",
                    exact_ic.trace.normalized_value,
                    85,
                    "The complete title equals an evidenced primary IC part number.",
                    tuple(dict.fromkeys((*canonical_field.evidence, *exact_ic.evidence))),
                ),
            )
            candidates = [
                item for item in candidates if item.kind is not ComponentKind.INTEGRATED_CIRCUIT
            ]
            candidates.append(KindCandidate(ComponentKind.INTEGRATED_CIRCUIT, 85, exact_breakdown))
        if not candidates:
            candidates.append(
                KindCandidate(
                    ComponentKind.GENERIC_UNKNOWN,
                    10,
                    (
                        ScoreContribution(
                            "kind.generic_unknown.fallback.v1",
                            canonical_field.value,
                            10,
                            "No specific component-kind rule matched.",
                            canonical_field.evidence,
                        ),
                    ),
                )
            )
        return tuple(sorted(candidates, key=lambda item: (-item.score, item.kind.value)))

    @staticmethod
    def _signals(
        facts: NormalizedFacts,
    ) -> tuple[tuple[Signal, ...], tuple[Signal, ...], tuple[Signal, ...]]:
        extracted = facts.extracted_facts
        title = tuple(Signal(item.value, item.evidence) for item in extracted.title_candidates)
        summary = tuple(Signal(item.value, item.evidence) for item in extracted.summary_candidates)
        details = (
            *(Signal(item.value.body, item.evidence) for item in extracted.description_sections),
            *(Signal(item.value, item.evidence) for item in extracted.feature_facts),
            *(Signal(item.value, item.evidence) for item in extracted.application_facts),
            *(Signal(item.value.body, item.evidence) for item in extracted.usage_sections),
        )
        return title, summary, details

    @staticmethod
    def _add_text_contribution(
        breakdown: list[ScoreContribution],
        rule: CategoryRule,
        source: str,
        weight: int,
        signals: tuple[Signal, ...],
    ) -> None:
        matched = _first_match(signals, rule.tokens)
        if matched is not None:
            breakdown.append(
                ScoreContribution(
                    f"category.{rule.category_key}.{source}.v1",
                    matched.value,
                    weight,
                    f"{source.capitalize()} terminology supports {rule.category_key}.",
                    matched.evidence,
                )
            )

    @staticmethod
    def _exact_primary_ic(
        facts: NormalizedFacts, canonical_name: str
    ) -> NormalizedIdentifier | None:
        normalized_name = _normalized(canonical_name)
        return next(
            (
                item
                for item in facts.primary_ics
                if _normalized(item.trace.normalized_value) == normalized_name
            ),
            None,
        )

    @staticmethod
    def _resolution(
        facts: NormalizedFacts,
        categories: tuple[CategoryCandidate, ...],
        kinds: tuple[KindCandidate, ...],
    ) -> tuple[IdentityResolutionStatus, IdentityConfidence]:
        if (
            not categories
            or categories[0].score < REVIEW_SCORE
            or kinds[0].kind is ComponentKind.GENERIC_UNKNOWN
        ):
            return IdentityResolutionStatus.UNRESOLVED, IdentityConfidence.LOW
        margin = categories[0].score - (categories[1].score if len(categories) > 1 else 0)
        extraction_ambiguous = any(
            warning.code == "ambiguous_title" for warning in facts.extracted_facts.warnings
        )
        if (
            categories[0].score >= AUTO_RESOLVE_SCORE
            and margin > AUTO_RESOLVE_MARGIN
            and kinds[0].score >= 50
            and not facts.conflicts
            and not extraction_ambiguous
        ):
            return IdentityResolutionStatus.AUTO_RESOLVED, IdentityConfidence.HIGH
        return IdentityResolutionStatus.REVIEW_REQUIRED, IdentityConfidence.MEDIUM

    @staticmethod
    def _warnings(
        facts: NormalizedFacts,
        status: IdentityResolutionStatus,
        categories: tuple[CategoryCandidate, ...],
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if status is IdentityResolutionStatus.UNRESOLVED:
            warnings.append("identity_unresolved")
        elif status is IdentityResolutionStatus.REVIEW_REQUIRED:
            warnings.append("identity_review_required")
        if len(categories) > 1 and categories[0].score - categories[1].score <= AUTO_RESOLVE_MARGIN:
            warnings.append("category_ambiguous")
        if facts.conflicts:
            warnings.append("normalization_conflict_present")
        return tuple(warnings)


def _normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _SPACE.sub(" ", _TOKEN.sub(" ", normalized)).strip()


def _first_match(signals: tuple[Signal, ...], tokens: frozenset[str]) -> Signal | None:
    normalized_tokens = tuple(_normalized(token) for token in tokens)
    return next(
        (
            signal
            for signal in signals
            if any(f" {token} " in f" {_normalized(signal.value)} " for token in normalized_tokens)
        ),
        None,
    )
