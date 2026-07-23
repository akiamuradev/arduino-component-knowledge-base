# Seeed to KiCad matcher

Status: stage 7 implementation, matcher rules `1.0.0`.

`SeeedKicadMatcher` converts low-level `KicadSearchHit` values into immutable,
explainable `EnrichmentCandidate` decisions. It does not modify normalized facts, compose a card or
write to persistence.

## Relation types

Every `ComponentSymbolRelation` has exactly one explicit relation type:

| Relation | Meaning | Automatic decision |
| --- | --- | --- |
| `exact_component` | The symbol represents the same physical component as the Seeed identity. | Eligible only under the strict policy below. |
| `main_integrated_circuit` | The symbol is the primary IC of a module or development board. | Always review. |
| `onboard_component` | Source evidence explicitly describes the symbol as a component on the board. | Always review. |
| `connector` | The relation is to a physical connector symbol. | Always review. |
| `functional_equivalent` | Only functional/name/alias similarity is proven. | Review or reject; never automatic. |

An arbitrary occurrence of a symbol-like token is not enough for `onboard_component`. The evidence
must include contextual wording such as “based on”, “built around”, “contains”, “uses” or
“onboard”.

## Explainable score

Confidence is stored as deterministic integer basis points from 0 to 1000 and exposed as a decimal
from 0.000 to 1.000. Every contribution contains a versioned rule id, weight, human-readable
reason, source evidence and the corresponding KiCad value.

| Signal | Weight |
| --- | ---: |
| exact part number | +700 |
| exact alias | +520 |
| explicit symbol/alias occurrence in Seeed evidence | +150 |
| exact resolved canonical name | +100 |
| normalized name only | +100 |
| exact/same-identity/same-domain datasheet | +80/+60/+30 |
| manufacturer/package/pin-count agreement | +50 each |
| interface compatibility | +40 |
| description token overlap | +40 |
| manufacturer conflict | -500, blocking |
| package or pin-count conflict | -250, blocking |
| interface conflict | -180 |
| datasheet identity conflict | -120 |
| unsupported match term or weak generic symbol | -1000 |

Numeric package similarity alone is never treated as compatibility: a shared `20` cannot make
`DIP-20` compatible with `PowerSO20`. Positive contributions must retain at least one source
evidence fragment. Manufacturer-only lookup cannot introduce a candidate.

## Decision policy

The configurable auto-accept threshold defaults to 0.950 and cannot be configured below 0.950.
Fractional basis points are rounded upward. Automatic acceptance additionally requires all of:

- relation type `exact_component`;
- an exact part-number search basis;
- a non-generic KiCad symbol;
- no negative evidence;
- at least two distinct source evidence fragments;
- confidence at or above the configured threshold.

Candidates below 0.450 are rejected. Manufacturer, package and pin-count conflicts are blocking
regardless of the remaining score. Other candidates return explicit review or rejection reasons.
The immutable domain model repeats the critical auto-accept invariants, so an invalid serialized
decision cannot bypass matcher policy.

## Pinout boundary

Relations expose KiCad pins only as `symbol_pinout` and serialize `pinout_level=kicad_symbol`.
The module pinout remains inside Seeed `ExtractedFacts`; it is not copied into, compared as, or
relabelled as the IC pinout.

## Calibration

The versioned fixture `tests/fixtures/kicad_matcher/calibration_v1.json` contains 37 pairs covering
all five relation types, exact and alias identity, ambiguous functional matches, generic symbols,
strict thresholds, and positive/negative manufacturer, interface, datasheet, package and pin-count
signals.

Current deterministic baseline:

- decisions: 7 auto-accepted, 19 review-required, 11 rejected;
- relations: 14 exact, 4 main IC, 4 onboard, 2 connector and 13 functional equivalent;
- only exact relations are auto-accepted; all accepted scores are at least 0.950.

The corpus is a regression calibration set, not a claim of production precision. A later shadow
run must measure precision and recall against reviewed real imports before enabling the new
pipeline.
