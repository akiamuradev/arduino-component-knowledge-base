"""Explainable Seeed-to-symbol relation and matcher decision models."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from arduino_component_kb.imports.pipeline.models.kicad import (
    KicadMatchBasis,
    KicadMatchedTerm,
    KicadPin,
    KicadSymbolRecord,
)
from arduino_component_kb.imports.pipeline.models.provenance import EvidenceFragment

_RULE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(code)
    return value


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ValueError(f"{key}_must_be_string")
    return item


def _required_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key}_must_be_integer")
    return item


def _object_list(value: Mapping[str, object], key: str) -> list[object]:
    items = value.get(key, [])
    if not isinstance(items, list):
        raise ValueError(f"{key}_must_be_array")
    return list(items)


def _string_list(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    items = value.get(key, [])
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise ValueError(f"{key}_must_be_string_array")
    return tuple(items)


def _bounded(value: str, code: str, maximum: int = 2_000) -> None:
    if not value.strip() or "\x00" in value or len(value) > maximum:
        raise ValueError(code)


class ComponentSymbolRelationType(StrEnum):
    EXACT_COMPONENT = "exact_component"
    MAIN_INTEGRATED_CIRCUIT = "main_integrated_circuit"
    ONBOARD_COMPONENT = "onboard_component"
    CONNECTOR = "connector"
    FUNCTIONAL_EQUIVALENT = "functional_equivalent"


class EnrichmentDecision(StrEnum):
    AUTO_ACCEPTED = "auto_accepted"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class EvidencePolarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class EnrichmentScoreContribution:
    rule_id: str
    signal: str
    weight_basis_points: int
    reason: str
    source_evidence: tuple[EvidenceFragment, ...]
    kicad_evidence: str

    def __post_init__(self) -> None:
        if _RULE_ID.fullmatch(self.rule_id) is None:
            raise ValueError("enrichment_score_rule_id_invalid")
        _bounded(self.signal, "enrichment_score_signal_invalid", 1_000)
        _bounded(self.reason, "enrichment_score_reason_invalid", 1_000)
        _bounded(self.kicad_evidence, "enrichment_score_kicad_evidence_invalid", 4_000)
        if self.weight_basis_points == 0 or not -1_000 <= self.weight_basis_points <= 1_000:
            raise ValueError("enrichment_score_weight_invalid")
        if self.weight_basis_points > 0 and not self.source_evidence:
            raise ValueError("enrichment_score_positive_evidence_missing")

    @property
    def polarity(self) -> EvidencePolarity:
        return (
            EvidencePolarity.POSITIVE if self.weight_basis_points > 0 else EvidencePolarity.NEGATIVE
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "signal": self.signal,
            "weight_basis_points": self.weight_basis_points,
            "polarity": self.polarity.value,
            "reason": self.reason,
            "source_evidence": [item.as_dict() for item in self.source_evidence],
            "kicad_evidence": self.kicad_evidence,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> EnrichmentScoreContribution:
        polarity = EvidencePolarity(_required_string(value, "polarity"))
        result = cls(
            rule_id=_required_string(value, "rule_id"),
            signal=_required_string(value, "signal"),
            weight_basis_points=_required_int(value, "weight_basis_points"),
            reason=_required_string(value, "reason"),
            source_evidence=tuple(
                EvidenceFragment.from_dict(_mapping(item, "enrichment_score_evidence_invalid"))
                for item in _object_list(value, "source_evidence")
            ),
            kicad_evidence=_required_string(value, "kicad_evidence"),
        )
        if result.polarity is not polarity:
            raise ValueError("enrichment_score_polarity_mismatch")
        return result


@dataclass(frozen=True, slots=True)
class ComponentSymbolRelation:
    identity_sha256: str
    relation_type: ComponentSymbolRelationType
    symbol: KicadSymbolRecord
    matched_terms: tuple[KicadMatchedTerm, ...]
    confidence_basis_points: int
    score_breakdown: tuple[EnrichmentScoreContribution, ...]
    matcher_version: str

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.identity_sha256) is None:
            raise ValueError("component_symbol_relation_identity_sha256_invalid")
        if not self.matched_terms:
            raise ValueError("component_symbol_relation_terms_missing")
        if len(set(self.matched_terms)) != len(self.matched_terms):
            raise ValueError("component_symbol_relation_terms_duplicate")
        if not self.score_breakdown:
            raise ValueError("component_symbol_relation_breakdown_missing")
        score_keys = [(item.rule_id, item.signal) for item in self.score_breakdown]
        if len(score_keys) != len(set(score_keys)):
            raise ValueError("component_symbol_relation_breakdown_duplicate")
        expected = max(
            0,
            min(1_000, sum(item.weight_basis_points for item in self.score_breakdown)),
        )
        if self.confidence_basis_points != expected:
            raise ValueError("component_symbol_relation_confidence_mismatch")
        if _VERSION.fullmatch(self.matcher_version) is None:
            raise ValueError("component_symbol_relation_matcher_version_invalid")

    @property
    def confidence(self) -> float:
        return self.confidence_basis_points / 1_000

    @property
    def symbol_pinout(self) -> tuple[KicadPin, ...]:
        """Expose only KiCad symbol pins; module pins remain in NormalizedFacts."""
        return self.symbol.pins

    @property
    def negative_evidence(self) -> tuple[EnrichmentScoreContribution, ...]:
        return tuple(
            item for item in self.score_breakdown if item.polarity is EvidencePolarity.NEGATIVE
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "identity_sha256": self.identity_sha256,
            "relation_type": self.relation_type.value,
            "symbol": self.symbol.as_dict(),
            "matched_terms": [item.as_dict() for item in self.matched_terms],
            "confidence": self.confidence,
            "confidence_basis_points": self.confidence_basis_points,
            "score_breakdown": [item.as_dict() for item in self.score_breakdown],
            "matcher_version": self.matcher_version,
            "pinout_level": "kicad_symbol",
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ComponentSymbolRelation:
        if value.get("pinout_level") != "kicad_symbol":
            raise ValueError("component_symbol_relation_pinout_level_invalid")
        confidence = value.get("confidence")
        if not isinstance(confidence, int | float) or isinstance(confidence, bool):
            raise ValueError("component_symbol_relation_confidence_invalid")
        result = cls(
            identity_sha256=_required_string(value, "identity_sha256"),
            relation_type=ComponentSymbolRelationType(_required_string(value, "relation_type")),
            symbol=KicadSymbolRecord.from_dict(
                _mapping(value.get("symbol"), "component_symbol_relation_symbol_invalid")
            ),
            matched_terms=tuple(
                KicadMatchedTerm.from_dict(_mapping(item, "component_symbol_term_invalid"))
                for item in _object_list(value, "matched_terms")
            ),
            confidence_basis_points=_required_int(value, "confidence_basis_points"),
            score_breakdown=tuple(
                EnrichmentScoreContribution.from_dict(
                    _mapping(item, "enrichment_score_contribution_invalid")
                )
                for item in _object_list(value, "score_breakdown")
            ),
            matcher_version=_required_string(value, "matcher_version"),
        )
        if abs(result.confidence - float(confidence)) > 0.000_001:
            raise ValueError("component_symbol_relation_confidence_mismatch")
        return result


@dataclass(frozen=True, slots=True)
class EnrichmentCandidate:
    relation: ComponentSymbolRelation
    decision: EnrichmentDecision
    review_reasons: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for reasons in (self.review_reasons, self.rejection_reasons):
            if any(not item.strip() or len(item) > 300 for item in reasons):
                raise ValueError("enrichment_candidate_reason_invalid")
            if len(set(reasons)) != len(reasons):
                raise ValueError("enrichment_candidate_reasons_duplicate")
        if self.decision is EnrichmentDecision.AUTO_ACCEPTED:
            if self.relation.relation_type is not ComponentSymbolRelationType.EXACT_COMPONENT:
                raise ValueError("enrichment_candidate_auto_accept_relation_invalid")
            if self.relation.symbol.is_generic:
                raise ValueError("enrichment_candidate_generic_auto_accept_forbidden")
            if self.relation.confidence_basis_points < 950:
                raise ValueError("enrichment_candidate_auto_accept_confidence_invalid")
            if self.relation.negative_evidence:
                raise ValueError("enrichment_candidate_auto_accept_negative_evidence")
            if not any(
                item.basis is KicadMatchBasis.EXACT_PART_NUMBER
                for item in self.relation.matched_terms
            ):
                raise ValueError("enrichment_candidate_auto_accept_exact_match_missing")
            source_evidence = {
                evidence
                for contribution in self.relation.score_breakdown
                if contribution.weight_basis_points > 0
                for evidence in contribution.source_evidence
            }
            if len(source_evidence) < 2:
                raise ValueError("enrichment_candidate_auto_accept_evidence_insufficient")
            if self.review_reasons or self.rejection_reasons:
                raise ValueError("enrichment_candidate_auto_accept_reasons_forbidden")
        elif self.decision is EnrichmentDecision.REVIEW_REQUIRED:
            if not self.review_reasons or self.rejection_reasons:
                raise ValueError("enrichment_candidate_review_reasons_invalid")
        elif not self.rejection_reasons or self.review_reasons:
            raise ValueError("enrichment_candidate_rejection_reasons_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "relation": self.relation.as_dict(),
            "decision": self.decision.value,
            "review_reasons": list(self.review_reasons),
            "rejection_reasons": list(self.rejection_reasons),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> EnrichmentCandidate:
        return cls(
            relation=ComponentSymbolRelation.from_dict(
                _mapping(value.get("relation"), "enrichment_candidate_relation_invalid")
            ),
            decision=EnrichmentDecision(_required_string(value, "decision")),
            review_reasons=_string_list(value, "review_reasons"),
            rejection_reasons=_string_list(value, "rejection_reasons"),
        )

    @classmethod
    def from_json(cls, value: str) -> EnrichmentCandidate:
        decoded: object = json.loads(value)
        return cls.from_dict(_mapping(decoded, "enrichment_candidate_payload_invalid"))
