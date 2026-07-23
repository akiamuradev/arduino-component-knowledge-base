"""Stage 7 relation inference, confidence and calibration tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest
from import_pipeline_helpers import kicad_snapshot, resolved

from arduino_component_kb.imports.pipeline import (
    ComponentIdentity,
    ComponentSymbolRelationType,
    EnrichmentCandidate,
    EnrichmentDecision,
    ExtractedField,
    IdentifierKind,
    IdentityAlias,
    IdentityValue,
    KicadCandidateSet,
    KiCadEnrichmentProvider,
    KicadMatchBasis,
    KicadMatchedTerm,
    KicadSearchHit,
    KicadSymbolIndexer,
    KicadSymbolRecord,
    NormalizationConfidence,
    NormalizationTrace,
    NormalizedIdentifier,
    RawSpecification,
    SeeedKicadMatcher,
)

CALIBRATION = Path(__file__).parent / "fixtures" / "kicad_matcher" / "calibration_v1.json"


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    case_id: str
    seeed: str
    symbol: str
    mode: str
    relation: ComponentSymbolRelationType
    decision: EnrichmentDecision


def calibration_cases() -> tuple[CalibrationCase, ...]:
    decoded: object = json.loads(CALIBRATION.read_text("utf-8"))
    if not isinstance(decoded, list):
        raise ValueError("calibration_payload_invalid")
    result: list[CalibrationCase] = []
    for item in decoded:
        if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
            raise ValueError("calibration_case_invalid")
        values = {key: item.get(key) for key in ("id", "seeed", "symbol", "mode")}
        if not all(isinstance(value, str) for value in values.values()):
            raise ValueError("calibration_case_string_invalid")
        relation = item.get("relation")
        decision = item.get("decision")
        if not isinstance(relation, str) or not isinstance(decision, str):
            raise ValueError("calibration_case_expectation_invalid")
        result.append(
            CalibrationCase(
                case_id=str(values["id"]),
                seeed=str(values["seeed"]),
                symbol=str(values["symbol"]),
                mode=str(values["mode"]),
                relation=ComponentSymbolRelationType(relation),
                decision=EnrichmentDecision(decision),
            )
        )
    return tuple(result)


def _exact_identity(identity: ComponentIdentity, symbol: str) -> ComponentIdentity:
    if not identity.primary_ic_candidates:
        raise ValueError("calibration_primary_ic_missing")
    identifier = replace(
        identity.primary_ic_candidates[0],
        trace=replace(identity.primary_ic_candidates[0].trace, normalized_value=symbol),
    )
    return replace(
        identity,
        canonical_name=replace(identity.canonical_name, value=symbol),
        part_numbers=(identifier,),
        primary_ic_candidates=(),
    )


def _connector_identity(identity: ComponentIdentity, symbol: str) -> ComponentIdentity:
    evidence = (replace(identity.canonical_name.evidence[0], raw_text=f"Part number: {symbol}"),)
    identifier = NormalizedIdentifier(
        IdentifierKind.PART_NUMBER,
        NormalizationTrace(
            symbol,
            symbol,
            symbol,
            "part-number.calibration.v1",
            "1.0.0",
            NormalizationConfidence.HIGH,
        ),
        evidence,
    )
    return replace(identity, part_numbers=(identifier,), primary_ic_candidates=())


def _with_specification(identity: ComponentIdentity, label: str, value: str) -> ComponentIdentity:
    evidence = (
        replace(
            identity.canonical_name.evidence[0],
            raw_text=f"{label}: {value}",
        ),
    )
    field = ExtractedField(
        RawSpecification(label, value),
        f"{label}: {value}",
        evidence,
    )
    extracted = replace(
        identity.normalized_facts.extracted_facts,
        specifications=(*identity.normalized_facts.extracted_facts.specifications, field),
    )
    facts = replace(
        identity.normalized_facts,
        extracted_facts=extracted,
        extracted_facts_sha256=sha256(extracted.to_json().encode()).hexdigest(),
    )
    return replace(
        identity,
        normalized_facts=facts,
        normalized_facts_sha256=sha256(facts.to_json().encode()).hexdigest(),
    )


def _hit(
    record: KicadSymbolRecord,
    basis: KicadMatchBasis,
    query: str,
    matched_value: str,
) -> KicadSearchHit:
    return KicadSearchHit(record, (KicadMatchedTerm(basis, query, matched_value),))


async def _evaluate(case: CalibrationCase) -> EnrichmentCandidate:
    _, identity = await resolved(case.seeed)
    index = KicadSymbolIndexer().build(kicad_snapshot()).index
    record = next(item for item in index.records if item.symbol_name == case.symbol)
    provider = KiCadEnrichmentProvider(index)
    matcher = SeeedKicadMatcher(
        auto_accept_threshold=1.0 if case.mode == "strict_threshold" else 0.95
    )

    if case.mode in {
        "exact_component",
        "manufacturer_conflict",
        "interface_conflict",
        "datasheet_conflict",
        "package_conflict",
        "pin_conflict",
        "strict_threshold",
        "manufacturer_match",
        "package_match",
        "pin_match",
    }:
        identity = _exact_identity(identity, case.symbol)
    if case.mode == "manufacturer_conflict":
        identity = replace(
            identity,
            manufacturer=IdentityValue(
                "Wrong Semiconductor Corp",
                "identity.manufacturer-calibration.v1",
                identity.canonical_name.evidence,
            ),
        )
    if case.mode == "manufacturer_match":
        identity = replace(
            identity,
            manufacturer=IdentityValue(
                "Texas Instruments",
                "identity.manufacturer-calibration.v1",
                identity.canonical_name.evidence,
            ),
        )
    if case.mode == "package_conflict":
        identity = _with_specification(identity, "Package", "DIP-40")
    if case.mode == "package_match":
        identity = _with_specification(identity, "Package", "VSSOP-10")
    if case.mode == "pin_conflict":
        identity = _with_specification(identity, "Pin Count", "99")
    if case.mode == "pin_match":
        identity = _with_specification(identity, "Pin Count", "4")

    if case.mode == "natural":
        hit = next(
            item
            for item in provider.find_candidates(identity, identity.normalized_facts)
            if item.record.symbol_name == case.symbol
        )
    elif case.mode in {
        "exact_component",
        "manufacturer_conflict",
        "interface_conflict",
        "datasheet_conflict",
        "package_conflict",
        "pin_conflict",
        "strict_threshold",
        "manufacturer_match",
        "package_match",
        "pin_match",
    }:
        hit = next(
            item
            for item in provider.find_candidates(identity, identity.normalized_facts)
            if item.record.symbol_name == case.symbol
        )
        if case.mode == "interface_conflict":
            hit = replace(
                hit,
                record=replace(hit.record, description="SPI-only peripheral", keywords=("SPI",)),
            )
        elif case.mode == "datasheet_conflict":
            hit = replace(
                hit,
                record=replace(
                    hit.record,
                    datasheet="https://example.com/datasheets/other9999.pdf",
                ),
            )
    elif case.mode == "description":
        hit = _hit(
            record,
            KicadMatchBasis.DESCRIPTION,
            identity.canonical_name.value,
            record.description or " ".join(record.keywords),
        )
    elif case.mode in {"functional_alias", "onboard_alias"}:
        alias = f"CAL-{case.symbol}"
        record = replace(record, aliases=(*record.aliases, alias))
        evidence = (
            replace(
                identity.canonical_name.evidence[0],
                raw_text=(
                    f"Onboard component: {case.symbol}"
                    if case.mode == "onboard_alias"
                    else f"Functional equivalent identifier: {alias}"
                ),
            ),
        )
        identity = replace(
            identity,
            aliases=(
                *identity.aliases,
                IdentityAlias(alias, "identity.calibration-alias.v1", evidence),
            ),
        )
        hit = _hit(record, KicadMatchBasis.ALIAS, alias, alias)
    elif case.mode == "connector_exact":
        identity = _connector_identity(identity, case.symbol)
        hit = _hit(
            record,
            KicadMatchBasis.EXACT_PART_NUMBER,
            case.symbol,
            case.symbol,
        )
    elif case.mode == "generic_weak":
        hit = _hit(
            record,
            KicadMatchBasis.NORMALIZED_NAME,
            "Connector",
            case.symbol,
        )
    elif case.mode == "alias_component":
        alias = record.aliases[0]
        identity = _exact_identity(identity, alias)
        hit = _hit(record, KicadMatchBasis.ALIAS, alias, alias)
    else:
        raise ValueError(f"unknown_calibration_mode:{case.mode}")
    return matcher.score_hit(identity, identity.normalized_facts, hit)


@pytest.mark.asyncio
async def test_calibration_corpus_has_thirty_explainable_pairs() -> None:
    cases = calibration_cases()
    assert len(cases) >= 30
    assert len({case.case_id for case in cases}) == len(cases)

    for case in cases:
        candidate = await _evaluate(case)
        assert candidate.relation.relation_type is case.relation, case.case_id
        assert candidate.decision is case.decision, case.case_id
        assert candidate.relation.score_breakdown, case.case_id
        assert all(
            item.reason and item.kicad_evidence for item in candidate.relation.score_breakdown
        )


@pytest.mark.asyncio
async def test_exact_component_is_the_only_auto_accept_relation() -> None:
    candidates = [await _evaluate(case) for case in calibration_cases()]
    accepted = [item for item in candidates if item.decision is EnrichmentDecision.AUTO_ACCEPTED]
    assert accepted
    assert all(
        item.relation.relation_type is ComponentSymbolRelationType.EXACT_COMPONENT
        for item in accepted
    )
    assert all(item.relation.confidence >= 0.95 for item in accepted)
    assert all(not item.relation.negative_evidence for item in accepted)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "rule_id"),
    [
        ("match-manufacturer", "matcher.manufacturer-match.v1"),
        ("match-package", "matcher.package-compatible.v1"),
        ("match-pin-count", "matcher.pin-count-compatible.v1"),
        ("conflict-manufacturer", "matcher.manufacturer-conflict.v1"),
        ("conflict-interface", "matcher.interface-conflict.v1"),
        ("conflict-datasheet", "matcher.datasheet-conflict.v1"),
        ("conflict-package", "matcher.package-conflict.v1"),
        ("conflict-pin-count", "matcher.pin-count-conflict.v1"),
        ("connector-generic-weak", "matcher.generic-without-explicit-id.v1"),
    ],
)
async def test_calibration_exercises_positive_and_negative_rules(
    case_id: str, rule_id: str
) -> None:
    case = next(item for item in calibration_cases() if item.case_id == case_id)
    candidate = await _evaluate(case)

    assert rule_id in {item.rule_id for item in candidate.relation.score_breakdown}


@pytest.mark.asyncio
async def test_candidate_round_trip_keeps_symbol_pinout_separate() -> None:
    case = next(item for item in calibration_cases() if item.case_id == "main-drv8830")
    candidate = await _evaluate(case)
    payload = candidate.as_dict()
    relation_payload = payload.get("relation")

    assert isinstance(relation_payload, dict)
    assert relation_payload["pinout_level"] == "kicad_symbol"
    assert "module_pinout" not in relation_payload
    assert candidate.relation.symbol_pinout == candidate.relation.symbol.pins
    assert EnrichmentCandidate.from_json(candidate.to_json()) == candidate


@pytest.mark.asyncio
async def test_domain_model_rejects_forged_auto_accept_decisions() -> None:
    accepted = await _evaluate(
        next(item for item in calibration_cases() if item.case_id == "exact-drv8830")
    )
    alias_match = await _evaluate(
        next(item for item in calibration_cases() if item.case_id == "alias-exact-component")
    )
    main_ic = await _evaluate(
        next(item for item in calibration_cases() if item.case_id == "main-drv8830")
    )

    with pytest.raises(ValueError, match="auto_accept_confidence_invalid"):
        replace(alias_match, decision=EnrichmentDecision.AUTO_ACCEPTED, review_reasons=())
    with pytest.raises(ValueError, match="auto_accept_relation_invalid"):
        replace(main_ic, decision=EnrichmentDecision.AUTO_ACCEPTED, review_reasons=())
    with pytest.raises(ValueError, match="generic_auto_accept_forbidden"):
        replace(
            accepted,
            relation=replace(
                accepted.relation,
                symbol=replace(accepted.relation.symbol, is_generic=True),
            ),
        )
    alias_term = replace(
        accepted.relation.matched_terms[0],
        basis=KicadMatchBasis.ALIAS,
    )
    with pytest.raises(ValueError, match="auto_accept_exact_match_missing"):
        replace(
            accepted,
            relation=replace(accepted.relation, matched_terms=(alias_term,)),
        )
    single_evidence = accepted.relation.score_breakdown[0].source_evidence[0]
    collapsed_breakdown = tuple(
        replace(item, source_evidence=(single_evidence,)) if item.weight_basis_points > 0 else item
        for item in accepted.relation.score_breakdown
    )
    with pytest.raises(ValueError, match="auto_accept_evidence_insufficient"):
        replace(
            accepted,
            relation=replace(accepted.relation, score_breakdown=collapsed_breakdown),
        )
    penalty = replace(
        accepted.relation.score_breakdown[0],
        rule_id="matcher.synthetic-negative.v1",
        weight_basis_points=-40,
        reason="Synthetic conflict for invariant validation.",
    )
    penalized_relation = replace(
        accepted.relation,
        score_breakdown=(*accepted.relation.score_breakdown, penalty),
    )
    with pytest.raises(ValueError, match="auto_accept_negative_evidence"):
        replace(accepted, relation=penalized_relation)


@pytest.mark.asyncio
async def test_match_validates_candidate_identity_and_orders_decisions() -> None:
    _, identity = await resolved("actuator_module.md")
    index = KicadSymbolIndexer().build(kicad_snapshot()).index
    hits = KiCadEnrichmentProvider(index).find_candidates(identity, identity.normalized_facts)
    identity_sha256 = sha256(identity.to_json().encode()).hexdigest()
    candidate_set = KicadCandidateSet(
        identity_sha256,
        index.index_sha256,
        index.source_revision,
        hits,
    )

    results = SeeedKicadMatcher().match(identity, identity.normalized_facts, candidate_set)

    assert results[0].decision is EnrichmentDecision.REVIEW_REQUIRED
    assert all(item.decision is EnrichmentDecision.REJECTED for item in results[1:])
    with pytest.raises(ValueError, match="matcher_candidate_identity_mismatch"):
        SeeedKicadMatcher().match(
            identity,
            identity.normalized_facts,
            replace(candidate_set, identity_sha256="0" * 64),
        )


@pytest.mark.parametrize("threshold", [0.0, 0.949, 1.001, float("nan"), float("inf")])
def test_auto_accept_threshold_is_configurable_but_strict(threshold: float) -> None:
    with pytest.raises(ValueError, match="matcher_auto_accept_threshold_invalid"):
        SeeedKicadMatcher(auto_accept_threshold=threshold)


def test_fractional_threshold_rounds_up_to_next_basis_point() -> None:
    matcher = SeeedKicadMatcher(auto_accept_threshold=0.9501)
    assert matcher.auto_accept_threshold_basis_points == 951
