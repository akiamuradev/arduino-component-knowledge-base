# Pre-composition quality evaluation

Status: stage 8 implementation, evaluator `1.0.0`, report schema `quality-report/v1`.

`DeterministicQualityEvaluator` assesses an immutable `QualityEvaluationInput` after enrichment and
before card composition. It creates only scores, issues and a route. It never repairs extracted
facts, invents prose, changes identity, accepts an enrichment or writes a catalogue card.

The implementation remains in the parallel pipeline and is not connected to release HTTP routes,
workers or persistence. A later composition stage must accept only `ready_to_compose`; review and
reject routes cannot silently become publishable cards.

## Dimensions and weights

Scores are integers from 0 to 1000. The overall score is the weighted integer mean, which makes a
report deterministic across machines and JSON round trips.

| Dimension | Weight | Independent signals |
| --- | ---: | --- |
| identity confidence | 150 | resolver status and evidenced canonical identity |
| description completeness | 120 | summary and detailed description availability |
| specification coverage | 150 | profile-specific required facts and unmapped specifications |
| module pinout presence | 80 | Seeed module-level pinout only; KiCad symbol pins never satisfy it |
| source provenance completeness | 150 | immutable source revision and consistent evidence fragments |
| conflicts | 120 | normalization conflicts, extraction/identity warnings and enrichment conflicts |
| enrichment confidence | 80 | accepted, review-only or objectively expected missing relation |
| educational usefulness | 80 | description, features, applications, usage and resources |
| publication readiness | 70 | identity/content/specification/provenance baseline minus open blockers and warnings |

The profile layer evaluates expectations separately:

- display: communication interface and resolution;
- sensor: measured quantity and measurement range;
- development board: MCU, power and interfaces;
- actuator: power and control interface;
- communication: interface and frequency/band.

Generic profiles use available structured specifications without pretending that an unrelated
profile requirement applies.

## Issues and missing-data causes

Every issue has a stable code, dimension and one severity:

- `blocking` makes the route `reject`;
- `warning` requires `manual_review`;
- `suggestion` records an improvement without claiming parser failure.

Missing data has an explicit cause. `extraction_missing` means retained source evidence contains a
matching signal but the structured fact is absent; it is a warning and a parser/taxonomy review
candidate. `source_missing` means no matching evidence exists in the available source; it receives
a milder score and usually a suggestion. This prevents objectively absent source fields from being
reported as extraction defects. `conflict` and `policy` cover contradictory evidence and review
rules respectively.

## Routing policy

The default reject threshold is 0.500 and the ready threshold is 0.800. Configuration is bounded:
reject must stay within 0.300–0.700, ready within 0.700–0.950, and reject must remain below ready.
Fractional basis points round upward.

Routing is deterministic and severity-aware:

| Condition | Route |
| --- | --- |
| any blocking issue, or score below reject threshold | `reject` |
| any warning, or score below ready threshold | `manual_review` |
| no blocker/warning and score at or above ready threshold | `ready_to_compose` |

The immutable `QualityReport` validates all nine dimensions in canonical order, weights totaling
1000, the recomputed overall score, unique ordered issues and the route implied by scores and
severities. Serialized reports include an input hash and reject unknown schema versions.

## Fixture benchmark

The versioned benchmark at `tests/fixtures/quality/benchmark_v1.json` evaluates all 15 Seeed
fixtures after normalization, identity resolution and KiCad matching. The regression test compares
profile, every dimension score, overall score, route, issue counts and ordered issue codes.

Current baseline:

- routes: 1 reject, 14 manual review, 0 ready-to-compose;
- issues: 1 blocking, 48 warnings and 23 suggestions;
- causes: 37 extraction-missing, 24 source-missing and 11 policy;
- overall score: minimum 0.559, median 0.878, mean 0.842 and maximum 0.966;
- profiles: 4 generic, 3 actuator, 3 sensor, 2 display, 2 communication and 1 board.

The source corpus intentionally contains malformed, sparse and ambiguous pages, so this route
distribution is a guardrail baseline rather than a desired production acceptance rate. A separate
test proves that a complete warning-free input reaches `ready_to_compose`. Thresholds must be
calibrated later against human-reviewed shadow-import outcomes; this fixture set alone cannot
estimate production precision or recall.

Reproduce the report contract with:

```bash
pytest -q tests/test_quality_evaluation.py
```
