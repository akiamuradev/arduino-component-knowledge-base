"""Deterministic, privacy-safe metrics from final human enrichment reviews."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.imports.persistence_models import (
    ComponentEnrichmentRecord,
    ImportReviewActionRecord,
    ImportReviewStateRecord,
)
from arduino_component_kb.imports.pipeline.models.enrichment import (
    ComponentSymbolRelationType,
    EnrichmentDecision,
)
from arduino_component_kb.imports.pipeline.models.persistence import EnrichmentLifecycleStatus

SCHEMA_VERSION: Final = "human-labelled-enrichment-metrics/v1"
NO_MATCH: Final = "no_match"
_DECISION_ACTIONS: Final = frozenset({"enrichment_accepted", "enrichment_rejected"})
_METRIC_ACTIONS: Final = frozenset({*_DECISION_ACTIONS, "enrichment_relation_changed"})
_RELATION_LABELS: Final = tuple(item.value for item in ComponentSymbolRelationType)
_ALL_LABELS: Final = (NO_MATCH, *_RELATION_LABELS)
_Z_95: Final = 1.959963984540054


class ReviewMetricsDataError(ValueError):
    """Persisted data cannot be interpreted without guessing."""


@dataclass(frozen=True, slots=True)
class ReviewMetricAction:
    action_id: str
    action: str
    review_revision: int

    def __post_init__(self) -> None:
        if not self.action_id or self.action not in _METRIC_ACTIONS:
            raise ReviewMetricsDataError("review_metrics_action_invalid")
        if self.review_revision < 2:
            raise ReviewMetricsDataError("review_metrics_action_revision_invalid")


@dataclass(frozen=True, slots=True)
class ReviewMetricCandidate:
    """Safe projection of one persisted enrichment and its reviewer actions."""

    enrichment_id: str
    review_state_status: str | None
    lifecycle_status: str
    matcher_decision: str
    initial_relation_type: str
    final_relation_type: str
    matcher_version: str
    index_revision: str
    rule_ids: tuple[str, ...]
    actions: tuple[ReviewMetricAction, ...]

    def __post_init__(self) -> None:
        if not self.enrichment_id:
            raise ReviewMetricsDataError("review_metrics_enrichment_id_missing")
        if self.review_state_status not in {None, "pending", "confirmed"}:
            raise ReviewMetricsDataError("review_metrics_review_state_invalid")
        if self.lifecycle_status not in {item.value for item in EnrichmentLifecycleStatus}:
            raise ReviewMetricsDataError("review_metrics_lifecycle_invalid")
        if self.matcher_decision not in {item.value for item in EnrichmentDecision}:
            raise ReviewMetricsDataError("review_metrics_matcher_decision_invalid")
        for relation in (self.initial_relation_type, self.final_relation_type):
            if relation not in _RELATION_LABELS:
                raise ReviewMetricsDataError("review_metrics_relation_type_invalid")
        if not self.matcher_version or not self.index_revision:
            raise ReviewMetricsDataError("review_metrics_version_missing")
        if tuple(sorted(set(self.rule_ids))) != self.rule_ids or not self.rule_ids:
            raise ReviewMetricsDataError("review_metrics_rule_ids_invalid")
        expected_actions = tuple(
            sorted(self.actions, key=lambda item: (item.review_revision, item.action_id))
        )
        if self.actions != expected_actions:
            raise ReviewMetricsDataError("review_metrics_actions_not_sorted")


@dataclass(frozen=True, slots=True)
class HumanLabelledSample:
    enrichment_id: str
    review_action_ids: tuple[str, ...]
    matcher_decision: str
    predicted_label: str
    reviewer_outcome: str
    actual_label: str
    relation_changed: bool
    matcher_version: str
    index_revision: str
    rule_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "enrichment_id": self.enrichment_id,
            "review_action_ids": list(self.review_action_ids),
            "matcher_decision": self.matcher_decision,
            "predicted_label": self.predicted_label,
            "reviewer_outcome": self.reviewer_outcome,
            "actual_label": self.actual_label,
            "relation_changed": self.relation_changed,
            "matcher_version": self.matcher_version,
            "index_revision": self.index_revision,
            "rule_ids": list(self.rule_ids),
        }


class ReviewMetricsRepository:
    """Read only the persisted fields required for reproducible metrics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(self) -> tuple[ReviewMetricCandidate, ...]:
        action_rows = (
            await self.session.execute(
                select(
                    ImportReviewActionRecord.id,
                    ImportReviewActionRecord.target_key,
                    ImportReviewActionRecord.action,
                    ImportReviewActionRecord.review_revision,
                )
                .where(ImportReviewActionRecord.action.in_(_METRIC_ACTIONS))
                .order_by(
                    ImportReviewActionRecord.target_key,
                    ImportReviewActionRecord.review_revision,
                    ImportReviewActionRecord.id,
                )
            )
        ).all()
        actions_by_target: dict[str, list[ReviewMetricAction]] = defaultdict(list)
        for action_id, target_key, action, review_revision in action_rows:
            actions_by_target[target_key].append(
                ReviewMetricAction(str(action_id), action, review_revision)
            )

        rows = (
            await self.session.execute(
                select(
                    ComponentEnrichmentRecord.id,
                    ImportReviewStateRecord.status,
                    ComponentEnrichmentRecord.status,
                    ComponentEnrichmentRecord.payload["decision"].as_string(),
                    ComponentEnrichmentRecord.payload["relation"]["relation_type"].as_string(),
                    ComponentEnrichmentRecord.relation_type,
                    ComponentEnrichmentRecord.parser_version,
                    ComponentEnrichmentRecord.source_revision,
                    func.jsonb_path_query_array(
                        ComponentEnrichmentRecord.payload,
                        cast("$.relation.score_breakdown[*].rule_id", JSONPATH),
                    ),
                )
                .outerjoin(
                    ImportReviewStateRecord,
                    ImportReviewStateRecord.review_draft_id
                    == ComponentEnrichmentRecord.review_draft_id,
                )
                .order_by(ComponentEnrichmentRecord.id)
            )
        ).all()
        candidates: list[ReviewMetricCandidate] = []
        for (
            enrichment_id,
            review_state_status,
            lifecycle_status,
            matcher_decision,
            initial_relation_type,
            final_relation_type,
            matcher_version,
            index_revision,
            score_rule_ids,
        ) in rows:
            rule_ids = tuple(
                sorted(set(_string_sequence(score_rule_ids, "review_metrics_rule_ids_invalid")))
            )
            candidates.append(
                ReviewMetricCandidate(
                    enrichment_id=str(enrichment_id),
                    review_state_status=review_state_status,
                    lifecycle_status=lifecycle_status,
                    matcher_decision=matcher_decision,
                    initial_relation_type=initial_relation_type,
                    final_relation_type=final_relation_type,
                    matcher_version=matcher_version,
                    index_revision=index_revision,
                    rule_ids=rule_ids,
                    actions=tuple(actions_by_target.get(str(enrichment_id), ())),
                )
            )
        return tuple(candidates)


def build_human_labelled_report(
    candidates: Sequence[ReviewMetricCandidate],
    *,
    minimum_reviewed_sample: int,
) -> dict[str, object]:
    """Build a byte-stable report without source evidence or reviewer metadata."""
    if not 1 <= minimum_reviewed_sample <= 1_000_000:
        raise ValueError("review_metrics_minimum_sample_invalid")

    excluded = {
        "pending_or_missing_confirmation": 0,
        "stale": 0,
        "conflict": 0,
        "unresolved": 0,
        "unreviewed": 0,
        "lifecycle_mismatch": 0,
    }
    ordered_candidates = sorted(candidates, key=lambda item: item.enrichment_id)
    if len({item.enrichment_id for item in ordered_candidates}) != len(ordered_candidates):
        raise ReviewMetricsDataError("review_metrics_enrichment_duplicate")
    samples: list[HumanLabelledSample] = []
    for candidate in ordered_candidates:
        if candidate.review_state_status != "confirmed":
            excluded["pending_or_missing_confirmation"] += 1
            continue
        if candidate.lifecycle_status == EnrichmentLifecycleStatus.STALE.value:
            excluded["stale"] += 1
            continue
        if candidate.lifecycle_status == EnrichmentLifecycleStatus.CONFLICT.value:
            excluded["conflict"] += 1
            continue
        if candidate.lifecycle_status not in {
            EnrichmentLifecycleStatus.ACCEPTED.value,
            EnrichmentLifecycleStatus.REJECTED.value,
        }:
            excluded["unresolved"] += 1
            continue
        decisions = tuple(item for item in candidate.actions if item.action in _DECISION_ACTIONS)
        if not decisions:
            excluded["unreviewed"] += 1
            continue
        final_decision = decisions[-1]
        reviewer_outcome = (
            EnrichmentLifecycleStatus.ACCEPTED.value
            if final_decision.action == "enrichment_accepted"
            else EnrichmentLifecycleStatus.REJECTED.value
        )
        if candidate.lifecycle_status != reviewer_outcome:
            excluded["lifecycle_mismatch"] += 1
            continue
        predicted_label = (
            NO_MATCH
            if candidate.matcher_decision == EnrichmentDecision.REJECTED.value
            else candidate.initial_relation_type
        )
        actual_label = (
            candidate.final_relation_type
            if reviewer_outcome == EnrichmentLifecycleStatus.ACCEPTED.value
            else NO_MATCH
        )
        samples.append(
            HumanLabelledSample(
                enrichment_id=candidate.enrichment_id,
                review_action_ids=tuple(item.action_id for item in candidate.actions),
                matcher_decision=candidate.matcher_decision,
                predicted_label=predicted_label,
                reviewer_outcome=reviewer_outcome,
                actual_label=actual_label,
                relation_changed=(
                    any(item.action == "enrichment_relation_changed" for item in candidate.actions)
                    or candidate.initial_relation_type != candidate.final_relation_type
                ),
                matcher_version=candidate.matcher_version,
                index_revision=candidate.index_revision,
                rule_ids=candidate.rule_ids,
            )
        )

    samples.sort(
        key=lambda item: (
            item.matcher_version,
            item.index_revision,
            item.enrichment_id,
        )
    )
    sample_dicts = [item.as_dict() for item in samples]
    snapshot_material = [
        {
            "enrichment_id": item.enrichment_id,
            "review_state_status": item.review_state_status,
            "lifecycle_status": item.lifecycle_status,
            "matcher_decision": item.matcher_decision,
            "initial_relation_type": item.initial_relation_type,
            "final_relation_type": item.final_relation_type,
            "matcher_version": item.matcher_version,
            "index_revision": item.index_revision,
            "rule_ids": list(item.rule_ids),
            "actions": [
                {
                    "action_id": action.action_id,
                    "action": action.action,
                    "review_revision": action.review_revision,
                }
                for action in item.actions
            ],
        }
        for item in ordered_candidates
    ]
    snapshot_sha256 = sha256(_canonical_json(snapshot_material).encode()).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_sha256": snapshot_sha256,
        "summary": {
            "total_candidates": len(candidates),
            "reviewed_sample_size": len(samples),
            "minimum_reviewed_sample": minimum_reviewed_sample,
            "sample_gate": ("met" if len(samples) >= minimum_reviewed_sample else "insufficient"),
            "excluded": excluded,
        },
        "review_outcomes_by_matcher_decision": _decision_outcomes(samples),
        "overall": _metric_block(samples),
        "confusion_matrix": _confusion_matrix(samples),
        "relations": [
            {
                "relation_type": relation,
                **_metric_block(samples, positive_label=relation),
            }
            for relation in _RELATION_LABELS
        ],
        "version_slices": _version_slices(samples),
        "samples": sample_dicts,
    }


def report_json(report: Mapping[str, object], *, indent: int | None = 2) -> str:
    return json.dumps(
        report,
        ensure_ascii=False,
        indent=indent,
        separators=None if indent is not None else (",", ":"),
        sort_keys=True,
    )


def _decision_outcomes(samples: Sequence[HumanLabelledSample]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for decision in EnrichmentDecision:
        selected = [item for item in samples if item.matcher_decision == decision.value]
        result.append(
            {
                "matcher_decision": decision.value,
                "sample_size": len(selected),
                "reviewer_accepted": sum(
                    item.reviewer_outcome == EnrichmentLifecycleStatus.ACCEPTED.value
                    for item in selected
                ),
                "reviewer_rejected": sum(
                    item.reviewer_outcome == EnrichmentLifecycleStatus.REJECTED.value
                    for item in selected
                ),
                "relation_changed": sum(item.relation_changed for item in selected),
            }
        )
    return result


def _metric_block(
    samples: Sequence[HumanLabelledSample],
    *,
    positive_label: str | None = None,
) -> dict[str, object]:
    if positive_label is None:
        predicted = [item.predicted_label != NO_MATCH for item in samples]
        actual = [item.actual_label != NO_MATCH for item in samples]
    else:
        predicted = [item.predicted_label == positive_label for item in samples]
        actual = [item.actual_label == positive_label for item in samples]
    true_positive = sum(left and right for left, right in zip(predicted, actual, strict=True))
    false_positive = sum(left and not right for left, right in zip(predicted, actual, strict=True))
    false_negative = sum(not left and right for left, right in zip(predicted, actual, strict=True))
    true_negative = sum(
        not left and not right for left, right in zip(predicted, actual, strict=True)
    )
    correct = true_positive + true_negative
    return {
        "sample_size": len(samples),
        "binary_confusion": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_negative": true_negative,
        },
        "precision": _rate(true_positive, true_positive + false_positive),
        "recall": _rate(true_positive, true_positive + false_negative),
        "accuracy": _rate(correct, len(samples)),
    }


def _confusion_matrix(samples: Sequence[HumanLabelledSample]) -> dict[str, dict[str, int]]:
    result = {predicted: {actual: 0 for actual in _ALL_LABELS} for predicted in _ALL_LABELS}
    for item in samples:
        result[item.predicted_label][item.actual_label] += 1
    return result


def _version_slices(samples: Sequence[HumanLabelledSample]) -> list[dict[str, object]]:
    groups: dict[
        tuple[str, str, tuple[str, ...]],
        list[HumanLabelledSample],
    ] = defaultdict(list)
    for item in samples:
        groups[(item.matcher_version, item.index_revision, item.rule_ids)].append(item)
    result: list[dict[str, object]] = []
    for (matcher_version, index_revision, rule_ids), selected in sorted(groups.items()):
        rule_set_sha256 = sha256("\n".join(rule_ids).encode()).hexdigest()
        result.append(
            {
                "matcher_version": matcher_version,
                "index_revision": index_revision,
                "rule_ids": list(rule_ids),
                "rule_set_sha256": rule_set_sha256,
                **_metric_block(selected),
                "confusion_matrix": _confusion_matrix(selected),
            }
        )
    return result


def _rate(numerator: int, denominator: int) -> dict[str, object]:
    if denominator == 0:
        return {
            "numerator": numerator,
            "denominator": denominator,
            "estimate_basis_points": None,
            "confidence_interval_95_basis_points": None,
        }
    estimate = numerator / denominator
    z_squared = _Z_95 * _Z_95
    adjusted = 1 + z_squared / denominator
    center = (estimate + z_squared / (2 * denominator)) / adjusted
    margin = (
        _Z_95
        * math.sqrt(
            estimate * (1 - estimate) / denominator + z_squared / (4 * denominator * denominator)
        )
        / adjusted
    )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "estimate_basis_points": round(estimate * 1_000),
        "confidence_interval_95_basis_points": {
            "lower": round(max(0.0, center - margin) * 1_000),
            "upper": round(min(1.0, center + margin) * 1_000),
        },
    }


def _string_sequence(value: object, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReviewMetricsDataError(code)
    return tuple(value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


async def generate_database_report(
    settings: Settings,
    *,
    minimum_reviewed_sample: int,
) -> dict[str, object]:
    database = Database(settings)
    try:
        async with database.sessions() as session:
            snapshot = await ReviewMetricsRepository(session).snapshot()
        return build_human_labelled_report(
            snapshot,
            minimum_reviewed_sample=minimum_reviewed_sample,
        )
    finally:
        await database.dispose()


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description=(
            "Export deterministic, privacy-safe metrics from final human enrichment reviews."
        )
    )
    command.add_argument(
        "--minimum-reviewed-sample",
        type=int,
        default=None,
        help="Override ACKB_IMPORT_REVIEW_METRICS_MIN_SAMPLE for this decision report.",
    )
    return command


def main() -> None:
    args = parser().parse_args()
    settings = Settings()
    minimum = (
        settings.import_review_metrics_min_sample
        if args.minimum_reviewed_sample is None
        else args.minimum_reviewed_sample
    )
    try:
        report = asyncio.run(
            generate_database_report(
                settings,
                minimum_reviewed_sample=minimum,
            )
        )
    except (ReviewMetricsDataError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(report_json(report))


if __name__ == "__main__":
    main()
