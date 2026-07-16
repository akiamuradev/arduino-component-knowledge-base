"""Explainable fuzzy duplicate scoring tests."""

from __future__ import annotations

from arduino_component_kb.deduplication.scoring import (
    ALGORITHM_VERSION,
    HIGH_SCORE_THRESHOLD,
    ComponentSignals,
    score_pair,
    specification_fingerprint,
    text_hashes,
)


def signals(**changes: object) -> ComponentSignals:
    values: dict[str, object] = {
        "title": "Джойстик модуль KY-023",
        "aliases": ("Analog joystick",),
        "manufacturer": "Keyes",
        "model": "KY-023",
        "specifications": (("voltage", "5 V"), ("axes", "2")),
        "text_hashes": text_hashes("Joystick module", "Two-axis input"),
        "media_sha256": frozenset({"a" * 64}),
        "media_phashes": frozenset({"0f0f0f0f0f0f0f0f"}),
    }
    values.update(changes)
    return ComponentSignals(**values)  # type: ignore[arg-type]


def test_matching_signals_create_high_explainable_score() -> None:
    result = score_pair(signals(), signals(title="KY 023 джойстик модуль"), trigram=0.88)
    assert result.score >= HIGH_SCORE_THRESHOLD
    assert result.evidence["algorithm_version"] == ALGORITHM_VERSION
    assert result.evidence["penalties"] == {}
    signal_evidence = result.evidence["signals"]
    assert isinstance(signal_evidence, dict)
    assert set(signal_evidence) == {
        "title_trigram",
        "token_similarity",
        "identity_similarity",
        "spec_fingerprint",
        "text_hashes",
        "media_sha256",
        "media_phash",
    }


def test_conflicting_identity_and_specs_apply_visible_penalties() -> None:
    different = signals(
        manufacturer="Acme",
        model="AB-999",
        specifications=(("voltage", "12 V"), ("axes", "3")),
        text_hashes=frozenset(),
        media_sha256=frozenset(),
        media_phashes=frozenset(),
    )
    result = score_pair(signals(), different, trigram=0.9)
    assert result.score < HIGH_SCORE_THRESHOLD
    assert result.evidence["penalties"] == {
        "manufacturer_conflict": 0.15,
        "model_conflict": 0.25,
        "spec_conflicts": 0.1,
    }
    assert result.evidence["spec_conflict_count"] == 2


def test_fingerprints_normalize_equivalent_specifications() -> None:
    first = specification_fingerprint((("Supply Voltage", "5 V"),))
    second = specification_fingerprint((("supply  voltage", "５ v"),))
    assert first == second


def test_evidence_does_not_contain_source_text_or_hash_values() -> None:
    result = score_pair(signals(), signals(), trigram=1.0)
    serialized = repr(result.evidence)
    assert "Джойстик" not in serialized
    assert "a" * 64 not in serialized


def test_missing_optional_media_and_specs_do_not_count_as_negative_evidence() -> None:
    left = signals(
        specifications=(),
        media_sha256=frozenset(),
        media_phashes=frozenset(),
    )
    right = signals(
        title="KY-023 джойстик модуль",
        specifications=(),
        media_sha256=frozenset(),
        media_phashes=frozenset(),
    )
    result = score_pair(left, right, trigram=0.9)
    active_weights = result.evidence["active_weights"]
    assert isinstance(active_weights, dict)
    assert "spec_fingerprint" not in active_weights
    assert "media_sha256" not in active_weights
    assert result.score >= HIGH_SCORE_THRESHOLD
