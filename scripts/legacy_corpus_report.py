"""Read-only local corpus analysis; optional references never affect the parser's plan."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from arduino_component_kb.legacy.parser import SOURCE_NAME, analyze, models, normalize


def relative_folder(value: str | None) -> str | None:
    if value is None:
        return None
    return value.removeprefix(SOURCE_NAME + "/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--reference-manifest", type=Path)
    parser.add_argument("--reference-review", type=Path)
    args = parser.parse_args()
    result = analyze(args.archive, args.workbook)
    report: dict[str, object] = {
        "analysis_only": True,
        "parser_version": result.parser_version,
        "statistics": result.statistics,
        "analysis_hash": result.digest(),
    }
    if args.reference_manifest:
        with args.reference_manifest.open(encoding="utf-8-sig") as stream:
            reference = json.load(stream)
        targets = {(normalize(t.title), t.category): t for t in result.targets}
        transitions: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        examples: list[dict[str, object]] = []
        for source in reference["components"]:
            target = targets.get((normalize(source["title"]), source["category"]))
            if target is None:
                reasons["reference_target_absent"] += 1
                continue
            match = source["archive_match"]
            old = match["status"]
            old_path = relative_folder(match.get("path") or match.get("candidate_path"))
            transitions[f"{old}->{target.match}"] += 1
            current_path = relative_folder(target.folder)
            if old_path == current_path or (old == "unmatched" and target.match == "unmatched"):
                continue
            reason = "conservative_similarity_or_margin"
            if old_path:
                parts = Path(old_path).parts
                if len(parts) > 1 and normalize(parts[0]) != normalize(target.category):
                    reason = "reference_cross_category"
                elif (
                    models(target.title)
                    and models(parts[-1])
                    and models(target.title).isdisjoint(models(parts[-1]))
                ):
                    reason = "reference_model_conflict"
            reasons[reason] += 1
            if len(examples) < 20:
                examples.append(
                    {
                        "title": target.title,
                        "reference_status": old,
                        "current_status": target.match,
                        "reference_folder": old_path,
                        "current_folder": target.folder,
                        "reason": reason,
                    }
                )
        report.update(
            reference_counts=reference["stats"],
            transitions=dict(transitions),
            changed_reasons=dict(reasons),
            examples=examples,
        )
    if args.reference_review:
        with args.reference_review.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        report["review_rows"] = len(rows)
        report["review_statuses"] = dict(Counter(row["Статус сопоставления папки"] for row in rows))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
