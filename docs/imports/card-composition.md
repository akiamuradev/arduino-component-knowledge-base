# Card composition and review draft

Status: stage 9 implementation, composer `1.0.0`, draft schema `review-draft/v1`.

`DeterministicCardComposer` is the first pipeline stage allowed to shape publication-facing
sections. It accepts exactly one `CompositionInput`: normalized facts, resolved identity, evaluated
KiCad candidates and the matching `QualityReport`. The report input hash must match those exact
objects. A `reject` route raises `composition_quality_rejected`; only manual-review or
ready-to-compose input can produce a draft.

The implementation remains parallel to the release `0.21.0` import flow. It does not call ORM,
catalogue services, HTTP, workers or persistence.

## Review draft sections

`ReviewDraft` is immutable and contains separate typed sections for:

- title, aliases, manufacturer and selected category from resolved identity;
- source summary and detailed description sections;
- features and applications;
- normalized and unmapped module specifications;
- connection instructions and the module-level pinout;
- internal electronic component relations;
- KiCad symbols, symbol pins, footprint filters and provider source metadata;
- resources, complete primary-source evidence and quality review warnings.

Every textual fact is copied from the input model. The composer neither fills absent sections nor
creates fallback prose. Normalized specification values come from the normalizer trace and retain
the raw value and evidence. Unmapped specifications remain visible and carry
`composition.unmapped_specification` review metadata.

Low-confidence normalized fields carry review metadata alongside the field. Identity review state
is attached to identity fields. These codes and reasons are never appended to summary,
description, specification values or other public text.

## Enrichment boundary

Only matcher decisions `auto_accepted` and `review_required` enter a draft. Rejected candidates are
excluded. Their presentation status is explicit:

| Matcher decision | Draft status | Public interpretation |
| --- | --- | --- |
| `auto_accepted` | `accepted` | confirmed enrichment data |
| `review_required` | `proposed` | reviewer proposal, never an accepted fact |
| `rejected` | absent | not composable |

Internal/onboard/connector/functional relations appear in the internal-components section and
reference the corresponding KiCad record. Full provider data remains in the separate
`kicad_symbols` section. Exact-component relations may supply symbol data without being relabelled
as an internal component.

The module pinout is `DraftModuleConnection.pins`; KiCad pins are
`DraftKicadSymbol.pins` and serialize with `pinout_level=kicad_symbol`. Neither structure can
satisfy or replace the other.

## Provenance and determinism

Primary-source facts retain their exact `EvidenceFragment` tuples. The draft also contains a
deduplicated primary provenance set. KiCad entries retain library, source path, immutable revision,
content digest and parser version, while Seeed evidence explains why the relation was proposed or
accepted.

The composition input hash includes the quality-report digest. Reports and drafts use sorted,
compact JSON; fixed input and clock values produce byte-identical output. Model validation rejects
unknown schemas, rejected draft routes, missing primary provenance and internal-component records
without a corresponding KiCad symbol.

## Current draft compatibility

`LegacyRepositoryDraftMapper` converts a `ReviewDraft` into the existing
`ParsedRepositoryComponent` contract. License snapshot, original public URL and modifications
notice remain explicit adapter-supplied metadata because they are not component facts and must not
be guessed by the composer.

The mapper:

- keeps the current `draft`-only lifecycle;
- supplies provenance for every mapped field;
- preserves proposed/accepted status inside KiCad and internal-component payloads;
- keeps module pins and KiCad pins under different keys;
- passes review issue codes through legacy warnings;
- does not synthesize missing summary or description.

This mapper is a compatibility seam for the later orchestrator switch. Stage 9 does not wire it to
current jobs or persistence.

## Golden corpus and old/new comparison

`tests/golden/imports/review_drafts_v1.json` pins 14 composable Seeed fixtures, exceeding the
required ten drafts. Each case fixes the complete payload hash plus quality route, section counts,
review fields, enrichment state and warnings. The fifteenth sparse fixture has blocking identity
quality and is tested as non-composable.

Representative comparison against the legacy Seeed parser:

| Fixture | Legacy result | New review draft |
| --- | --- | --- |
| `complete.md` | 5 specs, no module pin section, no extractor warnings | 5 specs, 1 module pin, 2 resources, 3 explicit review issues |
| `display_spi.md` | 3 specs and one flat warning | 4 specs, 2 module pins, proposed SSD1306 internal relation and separate KiCad pinout |
| `motor_shield.md` | 1 spec, selected flat category, 2 warnings | 3 specs, unresolved category marked for review, proposed L298P relation, separate 2-pin module connection |
| `broken_frontmatter.mdx` | shallow parsed draft with 2 warnings | source-only sparse sections and 10 detailed quality issues; no generated description/specs/pins |

The higher issue count is intentional: the new draft carries evaluator diagnostics instead of
hiding missing source content, extraction gaps or ambiguous identity.

Focused verification:

```bash
pytest -q tests/test_card_composition.py
```
