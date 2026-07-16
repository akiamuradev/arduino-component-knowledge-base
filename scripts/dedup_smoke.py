"""Dependency-isolated smoke test for explainable fuzzy scoring."""

from __future__ import annotations

from arduino_component_kb.deduplication.scoring import (
    ALGORITHM_VERSION,
    HIGH_SCORE_THRESHOLD,
    ComponentSignals,
    score_pair,
    text_hashes,
)


def main() -> int:
    baseline = ComponentSignals(
        title="Joystick module KY-023",
        manufacturer="Keyes",
        model="KY-023",
        specifications=(("voltage", "5 V"),),
        text_hashes=text_hashes("Dual-axis joystick"),
    )
    likely = ComponentSignals(
        title="KY 023 joystick module",
        manufacturer="KEYES",
        model="ky 023",
        specifications=(("voltage", "5 v"),),
        text_hashes=text_hashes("Dual-axis joystick"),
    )
    conflicting = ComponentSignals(
        title="Joystick module KY-023",
        manufacturer="Other",
        model="AB-999",
        specifications=(("voltage", "12 V"),),
        text_hashes=frozenset(),
    )
    likely_result = score_pair(baseline, likely, trigram=0.9)
    conflict_result = score_pair(baseline, conflicting, trigram=0.9)
    assert likely_result.score >= HIGH_SCORE_THRESHOLD
    assert conflict_result.score < likely_result.score
    assert likely_result.evidence["algorithm_version"] == ALGORITHM_VERSION
    assert conflict_result.evidence["penalties"]
    print("Explainable fuzzy deduplication smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
