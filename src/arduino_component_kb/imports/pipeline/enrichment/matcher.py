"""Deterministic, explainable Seeed-to-KiCad relation matcher."""

from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from hashlib import sha256
from urllib.parse import urlsplit

from arduino_component_kb.imports.pipeline.models import (
    ComponentIdentity,
    ComponentKind,
    ComponentSymbolRelation,
    ComponentSymbolRelationType,
    EnrichmentCandidate,
    EnrichmentDecision,
    EnrichmentScoreContribution,
    EvidenceFragment,
    KicadCandidateSet,
    KicadMatchBasis,
    KicadSearchHit,
    NormalizedFacts,
    ResourceKind,
)

MATCHER_VERSION = "1.0.0"
DEFAULT_AUTO_ACCEPT_THRESHOLD = Decimal("0.950")
REVIEW_THRESHOLD_BASIS_POINTS = 450

_BASIS_WEIGHT = {
    KicadMatchBasis.EXACT_PART_NUMBER: (
        "matcher.part-number-exact.v1",
        700,
        "Exact part-number equality is a strong identity signal.",
    ),
    KicadMatchBasis.ALIAS: (
        "matcher.alias-exact.v1",
        520,
        "An exact KiCad alias matches an evidenced Seeed identifier.",
    ),
    KicadMatchBasis.NORMALIZED_NAME: (
        "matcher.name-normalized.v1",
        100,
        "Only the normalized component name matches.",
    ),
    KicadMatchBasis.DESCRIPTION: (
        "matcher.description-token.v1",
        40,
        "Description tokens overlap; this is a weak functional signal.",
    ),
}
_BASIS_PRIORITY = {
    KicadMatchBasis.EXACT_PART_NUMBER: 0,
    KicadMatchBasis.ALIAS: 1,
    KicadMatchBasis.NORMALIZED_NAME: 2,
    KicadMatchBasis.DESCRIPTION: 3,
    KicadMatchBasis.MANUFACTURER_HINT: 4,
}
_SEVERE_CONFLICT_RULES = frozenset(
    {
        "matcher.manufacturer-conflict.v1",
        "matcher.package-conflict.v1",
        "matcher.pin-count-conflict.v1",
    }
)
_PIN_COUNT_LABEL = re.compile(r"^(?:number of )?pins?(?: count)?$", re.IGNORECASE)


class SeeedKicadMatcher:
    matcher_version = MATCHER_VERSION

    def __init__(self, *, auto_accept_threshold: float | Decimal = 0.95) -> None:
        try:
            threshold = Decimal(str(auto_accept_threshold))
        except InvalidOperation as error:
            raise ValueError("matcher_auto_accept_threshold_invalid") from error
        if not threshold.is_finite() or not DEFAULT_AUTO_ACCEPT_THRESHOLD <= threshold <= Decimal(
            "1"
        ):
            raise ValueError("matcher_auto_accept_threshold_invalid")
        self.auto_accept_threshold_basis_points = int(
            (threshold * 1_000).to_integral_value(rounding=ROUND_CEILING)
        )

    @property
    def auto_accept_threshold(self) -> float:
        return self.auto_accept_threshold_basis_points / 1_000

    def match(
        self,
        identity: ComponentIdentity,
        facts: NormalizedFacts,
        candidates: KicadCandidateSet,
    ) -> tuple[EnrichmentCandidate, ...]:
        if identity.normalized_facts != facts:
            raise ValueError("matcher_facts_mismatch")
        identity_sha256 = sha256(identity.to_json().encode()).hexdigest()
        if candidates.identity_sha256 != identity_sha256:
            raise ValueError("matcher_candidate_identity_mismatch")
        if any(hit.record.source_revision != candidates.index_revision for hit in candidates.hits):
            raise ValueError("matcher_candidate_revision_mismatch")
        matched = tuple(self.score_hit(identity, facts, hit) for hit in candidates.hits)
        decision_order = {
            EnrichmentDecision.AUTO_ACCEPTED: 0,
            EnrichmentDecision.REVIEW_REQUIRED: 1,
            EnrichmentDecision.REJECTED: 2,
        }
        return tuple(
            sorted(
                matched,
                key=lambda item: (
                    decision_order[item.decision],
                    -item.relation.confidence_basis_points,
                    item.relation.symbol.record_id,
                ),
            )
        )

    def score_hit(
        self,
        identity: ComponentIdentity,
        facts: NormalizedFacts,
        hit: KicadSearchHit,
    ) -> EnrichmentCandidate:
        if identity.normalized_facts != facts:
            raise ValueError("matcher_facts_mismatch")
        relation_type = self._relation_type(identity, facts, hit)
        breakdown = self._score(identity, facts, hit)
        confidence = max(0, min(1_000, sum(item.weight_basis_points for item in breakdown)))
        relation = ComponentSymbolRelation(
            identity_sha256=sha256(identity.to_json().encode()).hexdigest(),
            relation_type=relation_type,
            symbol=hit.record,
            matched_terms=hit.matched_terms,
            confidence_basis_points=confidence,
            score_breakdown=breakdown,
            matcher_version=self.matcher_version,
        )
        decision, review_reasons, rejection_reasons = self._decision(relation)
        return EnrichmentCandidate(
            relation,
            decision,
            review_reasons,
            rejection_reasons,
        )

    def _score(
        self,
        identity: ComponentIdentity,
        facts: NormalizedFacts,
        hit: KicadSearchHit,
    ) -> tuple[EnrichmentScoreContribution, ...]:
        contributions: list[EnrichmentScoreContribution] = []
        primary_term = min(hit.matched_terms, key=lambda item: _BASIS_PRIORITY[item.basis])
        if primary_term.basis is not KicadMatchBasis.MANUFACTURER_HINT:
            rule_id, weight, reason = _BASIS_WEIGHT[primary_term.basis]
            term_evidence = _identity_term_evidence(identity, primary_term.query)
            if term_evidence:
                contributions.append(
                    self._contribution(
                        rule_id,
                        primary_term.query,
                        weight,
                        reason,
                        term_evidence,
                        primary_term.matched_value,
                    )
                )
            else:
                contributions.append(
                    self._contribution(
                        "matcher.match-term-unproven.v1",
                        primary_term.query,
                        -1_000,
                        "The search term is not backed by the resolved Seeed identity.",
                        (),
                        primary_term.matched_value,
                    )
                )

        explicit_evidence = _record_mention_evidence(identity, facts, hit)
        if explicit_evidence:
            contributions.append(
                self._contribution(
                    "matcher.source-explicit-mention.v1",
                    hit.record.symbol_name,
                    150,
                    "The KiCad symbol or alias appears explicitly in Seeed evidence.",
                    explicit_evidence,
                    hit.record.symbol_name,
                )
            )

        if _compact(identity.canonical_name.value) in _record_keys(hit):
            contributions.append(
                self._contribution(
                    "matcher.canonical-name-exact.v1",
                    identity.canonical_name.value,
                    100,
                    "The resolved component name exactly identifies the KiCad symbol.",
                    identity.canonical_name.evidence,
                    hit.record.symbol_name,
                )
            )

        manufacturer = self._manufacturer_contribution(identity, hit)
        if manufacturer is not None:
            contributions.append(manufacturer)
        datasheet = self._datasheet_contribution(facts, hit)
        if datasheet is not None:
            contributions.append(datasheet)
        interface = self._interface_contribution(facts, hit)
        if interface is not None:
            contributions.append(interface)
        package = self._package_contribution(facts, hit)
        if package is not None:
            contributions.append(package)
        pin_count = self._pin_count_contribution(facts, hit)
        if pin_count is not None:
            contributions.append(pin_count)

        if hit.record.is_generic and not any(
            term.basis is KicadMatchBasis.EXACT_PART_NUMBER for term in hit.matched_terms
        ):
            contributions.append(
                self._contribution(
                    "matcher.generic-without-explicit-id.v1",
                    hit.record.symbol_name,
                    -1_000,
                    "A generic symbol cannot be linked without an exact evidenced identifier.",
                    explicit_evidence,
                    hit.record.record_id,
                )
            )
        return tuple(contributions)

    @staticmethod
    def _relation_type(
        identity: ComponentIdentity,
        facts: NormalizedFacts,
        hit: KicadSearchHit,
    ) -> ComponentSymbolRelationType:
        record_keys = _record_keys(hit)
        part_keys = {_compact(item.trace.normalized_value) for item in identity.part_numbers}
        primary_keys = {
            _compact(item.trace.normalized_value) for item in identity.primary_ic_candidates
        }
        canonical_key = _compact(identity.canonical_name.value)
        if identity.component_kind is ComponentKind.CONNECTOR and _is_connector(hit):
            return ComponentSymbolRelationType.CONNECTOR
        if record_keys.intersection(part_keys):
            return ComponentSymbolRelationType.EXACT_COMPONENT
        if record_keys.intersection(primary_keys):
            if identity.component_kind in {ComponentKind.MODULE, ComponentKind.DEVELOPMENT_BOARD}:
                return ComponentSymbolRelationType.MAIN_INTEGRATED_CIRCUIT
            return ComponentSymbolRelationType.EXACT_COMPONENT
        if canonical_key in record_keys and identity.component_kind in {
            ComponentKind.DISCRETE_COMPONENT,
            ComponentKind.INTEGRATED_CIRCUIT,
        }:
            return ComponentSymbolRelationType.EXACT_COMPONENT
        if _is_connector(hit) and _record_mention_evidence(identity, facts, hit):
            return ComponentSymbolRelationType.CONNECTOR
        if _onboard_mention_evidence(identity, facts, hit):
            return ComponentSymbolRelationType.ONBOARD_COMPONENT
        return ComponentSymbolRelationType.FUNCTIONAL_EQUIVALENT

    def _manufacturer_contribution(
        self, identity: ComponentIdentity, hit: KicadSearchHit
    ) -> EnrichmentScoreContribution | None:
        if identity.manufacturer is None or not hit.record.manufacturer_hints:
            return None
        source = _compact(identity.manufacturer.value)
        record_values = {_compact(value) for value in hit.record.manufacturer_hints}
        if source in record_values:
            return self._contribution(
                "matcher.manufacturer-match.v1",
                identity.manufacturer.value,
                50,
                "Seeed and KiCad manufacturer identities agree.",
                identity.manufacturer.evidence,
                ", ".join(hit.record.manufacturer_hints),
            )
        return self._contribution(
            "matcher.manufacturer-conflict.v1",
            identity.manufacturer.value,
            -500,
            "Seeed and KiCad identify different manufacturers.",
            identity.manufacturer.evidence,
            ", ".join(hit.record.manufacturer_hints),
        )

    def _datasheet_contribution(
        self, facts: NormalizedFacts, hit: KicadSearchHit
    ) -> EnrichmentScoreContribution | None:
        if hit.record.datasheet is None:
            return None
        datasheets = tuple(
            field
            for field in facts.extracted_facts.resources
            if field.value.kind is ResourceKind.DATASHEET
        )
        if not datasheets:
            return None
        target = _normalized_url(hit.record.datasheet)
        exact = next(
            (field for field in datasheets if _normalized_url(field.value.locator) == target), None
        )
        if exact is not None:
            return self._contribution(
                "matcher.datasheet-exact.v1",
                exact.value.locator,
                80,
                "Seeed and KiCad reference the same datasheet URL.",
                exact.evidence,
                hit.record.datasheet,
            )
        target_tokens = _datasheet_tokens(hit.record.datasheet)
        filename = next(
            (
                field
                for field in datasheets
                if target_tokens.intersection(_datasheet_tokens(field.value.locator))
            ),
            None,
        )
        if filename is not None:
            return self._contribution(
                "matcher.datasheet-identity.v1",
                filename.value.locator,
                60,
                "Datasheet filenames contain the same component identity.",
                filename.evidence,
                hit.record.datasheet,
            )
        same_domain = next(
            (
                field
                for field in datasheets
                if urlsplit(field.value.locator).hostname == urlsplit(hit.record.datasheet).hostname
            ),
            None,
        )
        if same_domain is not None:
            return self._contribution(
                "matcher.datasheet-domain.v1",
                same_domain.value.locator,
                30,
                "Seeed and KiCad datasheets share a source domain.",
                same_domain.evidence,
                hit.record.datasheet,
            )
        source_tokens = set().union(
            *(_datasheet_tokens(field.value.locator) for field in datasheets)
        )
        if target_tokens and source_tokens:
            field = datasheets[0]
            return self._contribution(
                "matcher.datasheet-conflict.v1",
                field.value.locator,
                -120,
                "Datasheet identities disagree and require manual validation.",
                field.evidence,
                hit.record.datasheet,
            )
        return None

    def _interface_contribution(
        self, facts: NormalizedFacts, hit: KicadSearchHit
    ) -> EnrichmentScoreContribution | None:
        source_interfaces = {
            interface
            for item in facts.interfaces
            for interface in _interfaces(item.trace.normalized_value)
        }
        record_interfaces = _interfaces(
            " ".join(
                (
                    hit.record.description or "",
                    *hit.record.keywords,
                    *(pin.name for pin in hit.record.pins),
                )
            )
        )
        if not source_interfaces or not record_interfaces:
            return None
        evidence = tuple(dict.fromkeys(item for fact in facts.interfaces for item in fact.evidence))
        shared = source_interfaces.intersection(record_interfaces)
        if shared:
            return self._contribution(
                "matcher.interface-compatible.v1",
                ", ".join(sorted(source_interfaces)),
                40,
                "Seeed and KiCad expose at least one compatible interface.",
                evidence,
                ", ".join(sorted(record_interfaces)),
            )
        return self._contribution(
            "matcher.interface-conflict.v1",
            ", ".join(sorted(source_interfaces)),
            -180,
            "Seeed and KiCad state incompatible interface sets.",
            evidence,
            ", ".join(sorted(record_interfaces)),
        )

    def _package_contribution(
        self, facts: NormalizedFacts, hit: KicadSearchHit
    ) -> EnrichmentScoreContribution | None:
        package = next(
            (
                field
                for field in facts.extracted_facts.specifications
                if _compact(field.value.label) in {"package", "footprint", "packagecase"}
            ),
            None,
        )
        if package is None or not hit.record.footprint_filters:
            return None
        source_tokens = _comparison_tokens(package.value.value)
        target_tokens = _comparison_tokens(" ".join(hit.record.footprint_filters))
        if source_tokens.intersection(target_tokens):
            return self._contribution(
                "matcher.package-compatible.v1",
                package.value.value,
                50,
                "The explicit Seeed package is compatible with a KiCad footprint filter.",
                package.evidence,
                ", ".join(hit.record.footprint_filters),
            )
        return self._contribution(
            "matcher.package-conflict.v1",
            package.value.value,
            -250,
            "The explicit Seeed package conflicts with KiCad footprint filters.",
            package.evidence,
            ", ".join(hit.record.footprint_filters),
        )

    def _pin_count_contribution(
        self, facts: NormalizedFacts, hit: KicadSearchHit
    ) -> EnrichmentScoreContribution | None:
        pin_field = None
        expected = None
        for field in facts.extracted_facts.specifications:
            if _PIN_COUNT_LABEL.fullmatch(field.value.label.strip()) is None:
                continue
            match = re.search(r"\d+", field.value.value)
            if match is not None:
                pin_field = field
                expected = int(match.group())
                break
        if pin_field is None or expected is None or not hit.record.pins:
            return None
        actual = len({pin.number for pin in hit.record.pins})
        if expected == actual:
            return self._contribution(
                "matcher.pin-count-compatible.v1",
                str(expected),
                50,
                "An explicit component pin count agrees with the KiCad symbol.",
                pin_field.evidence,
                str(actual),
            )
        return self._contribution(
            "matcher.pin-count-conflict.v1",
            str(expected),
            -250,
            "An explicit component pin count conflicts with the KiCad symbol.",
            pin_field.evidence,
            str(actual),
        )

    def _decision(
        self, relation: ComponentSymbolRelation
    ) -> tuple[EnrichmentDecision, tuple[str, ...], tuple[str, ...]]:
        negative_rules = {item.rule_id for item in relation.negative_evidence}
        severe = sorted(negative_rules.intersection(_SEVERE_CONFLICT_RULES))
        if severe:
            blocking_reasons = tuple(
                f"Rejected because {rule_id} is a blocking identity conflict." for rule_id in severe
            )
            return EnrichmentDecision.REJECTED, (), blocking_reasons
        exact = any(
            term.basis is KicadMatchBasis.EXACT_PART_NUMBER for term in relation.matched_terms
        )
        if (
            relation.relation_type is ComponentSymbolRelationType.EXACT_COMPONENT
            and exact
            and not relation.negative_evidence
            and not relation.symbol.is_generic
            and len(_positive_source_evidence(relation)) >= 2
            and relation.confidence_basis_points >= self.auto_accept_threshold_basis_points
        ):
            return EnrichmentDecision.AUTO_ACCEPTED, (), ()
        if relation.confidence_basis_points < REVIEW_THRESHOLD_BASIS_POINTS:
            rejection_reasons = [
                f"Confidence {relation.confidence:.3f} is below the review threshold 0.450."
            ]
            rejection_reasons.extend(
                f"Negative evidence: {item.reason}" for item in relation.negative_evidence
            )
            return EnrichmentDecision.REJECTED, (), tuple(dict.fromkeys(rejection_reasons))

        review_reasons: list[str] = []
        if relation.relation_type in {
            ComponentSymbolRelationType.MAIN_INTEGRATED_CIRCUIT,
            ComponentSymbolRelationType.ONBOARD_COMPONENT,
        }:
            review_reasons.append("Internal component relations require human review by policy.")
        if relation.relation_type is ComponentSymbolRelationType.FUNCTIONAL_EQUIVALENT:
            review_reasons.append("Functional equivalents are never accepted automatically.")
        if relation.relation_type is ComponentSymbolRelationType.CONNECTOR:
            review_reasons.append(
                "Connector relations require confirmation of the physical connector."
            )
        if relation.symbol.is_generic:
            review_reasons.append("Generic symbols require explicit human confirmation.")
        if not exact:
            review_reasons.append("The candidate lacks an exact part-number match.")
        if relation.negative_evidence:
            review_reasons.extend(
                f"Negative evidence requires review: {item.reason}"
                for item in relation.negative_evidence
            )
        if relation.confidence_basis_points < self.auto_accept_threshold_basis_points:
            review_reasons.append(
                f"Confidence {relation.confidence:.3f} is below auto-accept threshold "
                f"{self.auto_accept_threshold:.3f}."
            )
        if relation.relation_type is ComponentSymbolRelationType.EXACT_COMPONENT and exact:
            if len(_positive_source_evidence(relation)) < 2:
                review_reasons.append(
                    "Auto-accept requires at least two independent source evidence fragments."
                )
        return EnrichmentDecision.REVIEW_REQUIRED, tuple(dict.fromkeys(review_reasons)), ()

    @staticmethod
    def _contribution(
        rule_id: str,
        signal: str,
        weight: int,
        reason: str,
        evidence: tuple[EvidenceFragment, ...],
        kicad_evidence: str,
    ) -> EnrichmentScoreContribution:
        return EnrichmentScoreContribution(
            rule_id,
            signal,
            weight,
            reason,
            evidence,
            kicad_evidence,
        )


def _record_keys(hit: KicadSearchHit) -> set[str]:
    return {
        _compact(value)
        for value in (hit.record.symbol_name, *hit.record.aliases)
        if _compact(value)
    }


def _identity_term_evidence(
    identity: ComponentIdentity, query: str
) -> tuple[EvidenceFragment, ...]:
    key = _compact(query)
    groups = [
        *(
            item.evidence
            for item in identity.part_numbers
            if _compact(item.trace.normalized_value) == key
        ),
        *(
            item.evidence
            for item in identity.primary_ic_candidates
            if _compact(item.trace.normalized_value) == key
        ),
        *(
            item.evidence
            for item in identity.product_identifiers
            if _compact(item.trace.normalized_value) == key
        ),
        *(item.evidence for item in identity.aliases if _compact(item.value) == key),
    ]
    if _compact(identity.canonical_name.value) == key:
        groups.append(identity.canonical_name.evidence)
    return tuple(dict.fromkeys(evidence for group in groups for evidence in group))


def _record_mention_evidence(
    identity: ComponentIdentity,
    facts: NormalizedFacts,
    hit: KicadSearchHit,
) -> tuple[EvidenceFragment, ...]:
    keys = _record_keys(hit)
    return tuple(
        evidence
        for evidence in _all_source_evidence(identity, facts)
        if any(key and key in _identifier_keys(evidence.raw_text) for key in keys)
    )


def _onboard_mention_evidence(
    identity: ComponentIdentity,
    facts: NormalizedFacts,
    hit: KicadSearchHit,
) -> tuple[EvidenceFragment, ...]:
    context = re.compile(
        r"\b(?:based on|built around|contains|equipped with|main ic|onboard|on-board|uses)\b",
        re.IGNORECASE,
    )
    return tuple(
        evidence
        for evidence in _record_mention_evidence(identity, facts, hit)
        if context.search(evidence.raw_text) is not None
    )


def _all_source_evidence(
    identity: ComponentIdentity, facts: NormalizedFacts
) -> tuple[EvidenceFragment, ...]:
    result = list(identity.evidence)
    extracted = facts.extracted_facts
    for fields in (
        extracted.summary_candidates,
        extracted.description_sections,
        extracted.feature_facts,
        extracted.application_facts,
        extracted.usage_sections,
        extracted.module_pinout,
        extracted.specifications,
        extracted.resources,
        extracted.unmapped_facts,
    ):
        for field in fields:
            result.extend(field.evidence)
    return tuple(dict.fromkeys(result))


def _is_connector(hit: KicadSearchHit) -> bool:
    return "connector" in _words(f"{hit.record.library} {hit.record.symbol_name}")


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _identifier_keys(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return {
        key
        for token in re.findall(r"[a-z0-9]+(?:[-_./][a-z0-9]+)*", normalized)
        if (key := _compact(token))
    }


def _positive_source_evidence(
    relation: ComponentSymbolRelation,
) -> tuple[EvidenceFragment, ...]:
    return tuple(
        dict.fromkeys(
            evidence
            for contribution in relation.score_breakdown
            if contribution.weight_basis_points > 0
            for evidence in contribution.source_evidence
        )
    )


def _words(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return set(re.findall(r"[a-z0-9]+", normalized))


def _normalized_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    return f"{(parsed.hostname or '').casefold()}{parsed.path.rstrip('/').casefold()}"


def _datasheet_tokens(value: str) -> set[str]:
    path = urlsplit(value).path.casefold()
    return {
        token
        for token in re.findall(r"[a-z]*\d+[a-z0-9]*", path)
        if len(token) >= 4 and token not in {"ds002"}
    }


def _interfaces(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    aliases = {
        "i2c": (r"\bi2c\b", r"\bi²c\b", r"\btwi\b"),
        "spi": (r"\bspi\b",),
        "uart": (r"\buart\b", r"\bserial\b"),
        "can": (r"\bcan(?: bus)?\b",),
        "usb": (r"\busb\b",),
        "analog": (r"\banalog\b",),
        "digital": (r"\bdigital\b",),
        "wifi": (r"\bwi[ -]?fi\b",),
        "bluetooth": (r"\bbluetooth\b",),
    }
    return {
        interface
        for interface, patterns in aliases.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    }


def _comparison_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z]+", value.casefold())
        if len(token) >= 2 and token not in {"filter", "footprint", "package"}
    }
