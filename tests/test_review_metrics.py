"""Stage 13.2 human-labelled metrics contracts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest

from arduino_component_kb.imports.review_metrics import (
    ReviewMetricAction,
    ReviewMetricCandidate,
    build_human_labelled_report,
    report_json,
)


def _action(number: int, action: str, revision: int = 2) -> ReviewMetricAction:
    return ReviewMetricAction(f"action-{number:03d}", action, revision)


def _candidate(
    number: int,
    *,
    decision: str,
    initial_relation: str,
    final_relation: str | None = None,
    lifecycle: str,
    actions: Sequence[ReviewMetricAction] = (),
    review_state: str | None = "confirmed",
    matcher_version: str = "matcher-1.0.0",
    index_revision: str = "a" * 40,
    rule_ids: tuple[str, ...] = ("matcher.part-number-exact.v1",),
) -> ReviewMetricCandidate:
    return ReviewMetricCandidate(
        enrichment_id=f"enrichment-{number:03d}",
        review_state_status=review_state,
        lifecycle_status=lifecycle,
        matcher_decision=decision,
        initial_relation_type=initial_relation,
        final_relation_type=final_relation or initial_relation,
        matcher_version=matcher_version,
        index_revision=index_revision,
        rule_ids=rule_ids,
        actions=tuple(actions),
    )


def _corpus() -> tuple[ReviewMetricCandidate, ...]:
    return (
        _candidate(
            1,
            decision="auto_accepted",
            initial_relation="exact_component",
            lifecycle="accepted",
            actions=(_action(1, "enrichment_accepted"),),
        ),
        _candidate(
            2,
            decision="auto_accepted",
            initial_relation="exact_component",
            lifecycle="rejected",
            actions=(_action(2, "enrichment_rejected"),),
        ),
        _candidate(
            3,
            decision="review_required",
            initial_relation="main_integrated_circuit",
            final_relation="onboard_component",
            lifecycle="accepted",
            actions=(
                _action(3, "enrichment_relation_changed"),
                _action(4, "enrichment_accepted", 3),
            ),
        ),
        _candidate(
            4,
            decision="rejected",
            initial_relation="onboard_component",
            lifecycle="accepted",
            actions=(_action(5, "enrichment_accepted"),),
        ),
        _candidate(
            5,
            decision="rejected",
            initial_relation="exact_component",
            lifecycle="rejected",
            actions=(_action(6, "enrichment_rejected"),),
        ),
        _candidate(
            6,
            decision="review_required",
            initial_relation="connector",
            lifecycle="accepted",
            actions=(_action(7, "enrichment_accepted"),),
            review_state="pending",
        ),
        _candidate(
            7,
            decision="review_required",
            initial_relation="connector",
            lifecycle="stale",
            actions=(_action(8, "enrichment_accepted"),),
        ),
        _candidate(
            8,
            decision="review_required",
            initial_relation="connector",
            lifecycle="conflict",
            actions=(_action(9, "enrichment_rejected"),),
        ),
        _candidate(
            9,
            decision="review_required",
            initial_relation="connector",
            lifecycle="suggested",
        ),
        _candidate(
            10,
            decision="auto_accepted",
            initial_relation="exact_component",
            lifecycle="accepted",
        ),
        _candidate(
            11,
            decision="auto_accepted",
            initial_relation="exact_component",
            lifecycle="accepted",
            actions=(_action(10, "enrichment_rejected"),),
        ),
    )


def test_report_uses_only_final_human_labels_and_tracks_exclusions() -> None:
    report = build_human_labelled_report(_corpus(), minimum_reviewed_sample=5)

    assert report["schema_version"] == "human-labelled-enrichment-metrics/v1"
    assert report["summary"] == {
        "total_candidates": 11,
        "reviewed_sample_size": 5,
        "minimum_reviewed_sample": 5,
        "sample_gate": "met",
        "excluded": {
            "pending_or_missing_confirmation": 1,
            "stale": 1,
            "conflict": 1,
            "unresolved": 1,
            "unreviewed": 1,
            "lifecycle_mismatch": 1,
        },
    }
    overall = report["overall"]
    assert isinstance(overall, dict)
    assert overall["binary_confusion"] == {
        "true_positive": 2,
        "false_positive": 1,
        "false_negative": 1,
        "true_negative": 1,
    }
    assert overall["precision"] == {
        "numerator": 2,
        "denominator": 3,
        "estimate_basis_points": 667,
        "confidence_interval_95_basis_points": {"lower": 208, "upper": 939},
    }
    assert overall["recall"] == overall["precision"]


def test_report_separates_matcher_decisions_and_relation_changes() -> None:
    report = build_human_labelled_report(_corpus(), minimum_reviewed_sample=100)
    outcome_items = cast(
        list[dict[str, object]],
        report["review_outcomes_by_matcher_decision"],
    )
    outcomes = {cast(str, item["matcher_decision"]): item for item in outcome_items}

    assert outcomes["auto_accepted"] == {
        "matcher_decision": "auto_accepted",
        "sample_size": 2,
        "reviewer_accepted": 1,
        "reviewer_rejected": 1,
        "relation_changed": 0,
    }
    assert outcomes["review_required"]["relation_changed"] == 1
    assert outcomes["rejected"]["reviewer_accepted"] == 1
    summary = cast(dict[str, object], report["summary"])
    assert summary["sample_gate"] == "insufficient"

    matrix = cast(dict[str, dict[str, int]], report["confusion_matrix"])
    assert matrix["exact_component"]["exact_component"] == 1
    assert matrix["exact_component"]["no_match"] == 1
    assert matrix["main_integrated_circuit"]["onboard_component"] == 1
    assert matrix["no_match"]["onboard_component"] == 1
    assert matrix["no_match"]["no_match"] == 1


def test_report_is_byte_identical_and_contains_no_review_content() -> None:
    corpus = _corpus()
    first = report_json(
        build_human_labelled_report(corpus, minimum_reviewed_sample=5),
        indent=None,
    )
    second = report_json(
        build_human_labelled_report(tuple(reversed(corpus)), minimum_reviewed_sample=5),
        indent=None,
    )

    assert first == second
    assert "action-001" in first
    for forbidden in (
        "reviewer",
        "actor_id",
        "reason",
        "note",
        "evidence",
        "source_text",
        "proxy_unreviewed",
    ):
        assert f'"{forbidden}"' not in first


def test_version_slices_include_rule_and_index_versions() -> None:
    report = build_human_labelled_report(_corpus()[:5], minimum_reviewed_sample=1)
    slices = cast(list[dict[str, object]], report["version_slices"])

    assert len(slices) == 1
    assert slices[0]["matcher_version"] == "matcher-1.0.0"
    assert slices[0]["index_revision"] == "a" * 40
    assert slices[0]["rule_ids"] == ["matcher.part-number-exact.v1"]
    rule_set_sha256 = cast(str, slices[0]["rule_set_sha256"])
    assert len(rule_set_sha256) == 64
    assert slices[0]["sample_size"] == 5


@pytest.mark.parametrize("minimum", [0, 1_000_001])
def test_minimum_reviewed_sample_is_bounded(minimum: int) -> None:
    with pytest.raises(ValueError, match="review_metrics_minimum_sample_invalid"):
        build_human_labelled_report((), minimum_reviewed_sample=minimum)
