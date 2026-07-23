# Target import architecture

Status: stage 10 persistence and enrichment lifecycle implementation. The package described here
exists in parallel with the release `0.21.0` import flow and is not connected to HTTP endpoints,
Dramatiq jobs or current production import orchestration.

The current implementation and compatibility surface are documented in
[`current-state.md`](current-state.md).

## Architectural decision

The target flow is:

```text
acquisition
→ extraction
→ semantic normalization
→ identity resolution
→ enrichment
→ quality evaluation
→ card composition
→ persistence
```

Seeed Wiki is the primary source for a component card. KiCad is an enrichment provider for an
identity extracted from Seeed; it is not a bulk card source. Composition is the first stage allowed
to shape publication-facing fields.

Stages 1–5 establish the boundaries, raw fact model, Seeed extractor, semantic normalizer and
weighted identity resolution. Stage 6 adds the reusable KiCad index and low-level enrichment
candidates. Stage 7 adds explicit relation types, calibrated confidence and review decisions.
Stage 8 adds immutable quality reports and reject/review/compose routing. Stage 9 adds deterministic
review drafts and an explicit legacy compatibility mapper. Stage 10 adds idempotent PostgreSQL
snapshots, reviewer audit and revision-aware KiCad enrichment lifecycle without rewriting the source
draft or legacy catalogue schema.

## Package tree

```text
src/arduino_component_kb/imports/pipeline/
├── __init__.py
├── context.py
├── errors.py
├── orchestration.py
├── contracts/
│   ├── __init__.py
│   ├── acquisition.py
│   ├── extraction.py
│   ├── normalization.py
│   ├── identity.py
│   ├── enrichment.py
│   ├── evaluation.py
│   ├── composition.py
│   └── persistence.py
├── extractors/
│   ├── __init__.py
│   ├── markdown.py
│   └── seeed.py
├── normalization/
│   ├── __init__.py
│   ├── registry.py
│   ├── semantic.py
│   └── values.py
├── identity/
│   ├── __init__.py
│   ├── resolver.py
│   └── rules.py
├── enrichment/
│   ├── __init__.py
│   ├── kicad_index.py
│   ├── kicad_provider.py
│   └── matcher.py
├── evaluation/
│   ├── __init__.py
│   └── quality.py
├── composition/
│   ├── __init__.py
│   ├── composer.py
│   └── legacy.py
└── models/
    ├── __init__.py
    ├── artifact.py
    ├── component_identity.py
    ├── composition.py
    ├── enrichment.py
    ├── extracted_facts.py
    ├── kicad.py
    ├── normalized_facts.py
    ├── quality.py
    └── provenance.py
```

The extra `pipeline` namespace is intentional. The existing package already contains
`imports/acquisition.py`, adapters, processor and repository modules used by production. Reusing
those paths for the new domain would create accidental coupling and change existing imports before
the explicit switch stage.

## Dependency direction

```mermaid
flowchart TB
    API[Future API / jobs / CLI adapters] --> ORCH[Pipeline orchestrator]
    ORCH --> CONTRACTS[Stage Protocols]
    ORCH --> DOMAIN[Context and stage domain models]
    INFRA[Future HTTP, Git, KiCad index and ORM adapters] --> CONTRACTS
    CONTRACTS --> DOMAIN
    ERRORS[Typed pipeline errors] --> DOMAIN
```

Allowed dependencies:

- domain context depends only on the Python standard library;
- stage contracts depend only on domain context/result types;
- orchestration depends only on context and abstract steps;
- future infrastructure implements contracts and may depend on HTTP, filesystem, cache or ORM;
- API/jobs depend on orchestration through an adapter introduced during the feature-flag stage.

Forbidden dependencies:

- the domain package must not import FastAPI, SQLAlchemy, Redis, Dramatiq, `httpx2` or catalogue ORM
  classes;
- extractors must not invoke persistence or create catalogue cards;
- providers and evaluators must not mutate prior-stage values;
- legacy production modules must not import `imports.pipeline` until the planned wiring stage.

The unit suite includes a static guard for the last rule.

## Stage contracts

All interfaces are structural `Protocol` contracts. Their input and output values are generic so
later stages can introduce concrete immutable domain types without weakening the contracts with
`Any` or dictionaries.

| Stage | Protocol | Method | Responsibility boundary |
| --- | --- | --- | --- |
| acquisition | `SourceAcquirer[Request, Artifact]` | `acquire` | Obtain a bounded source artifact; do not interpret component meaning. |
| extraction | `FactExtractor[Artifact, Facts]` | `extract` | Convert source syntax into evidenced raw facts. |
| normalization | `FactNormalizer[Facts, Normalized]` | `normalize` | Apply deterministic semantic rules while retaining raw values. |
| identity | `IdentityResolver[Normalized, Identity]` | `resolve` | Produce explainable component and category candidates. |
| enrichment | `EnrichmentProvider[Input, Enrichment]` | `enrich` | Propose external facts/relations without changing a card. |
| evaluation | `QualityEvaluator[Input, Quality]` | `evaluate` | Report readiness and issues; never repair or generate data. |
| composition | `CardComposer[Input, Draft]` | `compose` | Build a deterministic review draft from accepted inputs. |
| persistence | `ImportPersistenceGateway[Draft, Persisted]` | `persist` | Persist through an infrastructure adapter with idempotency. |

Composite inputs required by enrichment, evaluation and composition will be explicit dataclasses,
not variadic parameters or untyped mappings.

## Pipeline context and results

`ImportPipelineContext` is immutable and contains only cross-stage execution identity:

- `run_id`;
- registered `source_key` and bounded `source_locator`;
- `pipeline_version`;
- timezone-aware start time;
- ordered immutable `StageExecution` records.

It deliberately does not contain source payloads or facts. Each contract receives its typed input
and returns `StageResult[T]`, which couples a typed value to the advanced context and completed
stage. This prevents the context from becoming an untyped property bag.

Context validation guarantees:

- stages form an exact prefix of the canonical order;
- stages do not overlap and cannot precede the run;
- a result identifies the same stage as the last context execution;
- source/run identity cannot be replaced by an orchestration step;
- JSON serialization is deterministic and round-trippable.

The current `PipelineOrchestrator` is a sequencing stub. It validates that all eight stages are
present exactly once and that each abstract step advances the same context by one stage. It carries
no component payload and is intentionally not production-ready; the real typed data flow arrives
after the stage models exist.

## Error taxonomy

All new failures inherit `ImportPipelineError`, carry a bounded machine-readable `code`, declare
whether retry is safe, and serialize without raw exception text.

| Error | Category | Stage |
| --- | --- | --- |
| `AcquisitionError` | `acquisition` | acquisition |
| `ParsingError` | `parsing` | extraction |
| `NormalizationError` | `normalization` | normalization |
| `IdentityError` | `identity` | identity |
| `EnrichmentError` | `enrichment` | enrichment |
| `QualityError` | `quality` | evaluation |
| `CompositionError` | `composition` | composition |
| `PersistenceError` | `persistence` | persistence |

Retryability is explicit per error instance. A future orchestrator may retry only acquisition or
other proven-idempotent operations; it must not infer retryability from an arbitrary exception.

## Compatibility and rollout

During stages 1–10:

- the current Seeed and KiCad adapters continue returning `ParsedRepositoryComponent`;
- current endpoints, frontend contracts, worker and `ImportRepository` remain the source of truth;
- current golden fixtures remain the regression oracle;
- new domain models and implementations are exercised only by unit/golden/dry-run tests.

Stage 11 may connect the new orchestrator behind a disabled feature flag and run it in shadow mode.
Only the explicit switch stage may make the new flow authoritative. Existing models and adapters
are removed only after acceptance metrics and rollback requirements are satisfied.

## Stage 2 implementation

Stage 2 defines `ExtractedFacts` and evidence/provenance models as the concrete future output of
`FactExtractor`. The model preserves raw and unmapped data, contains no UI/card fields and remains
unwired from production. Its complete contract is documented in
[`extracted-facts.md`](extracted-facts.md).

## Stage 3 implementation

Stage 3 provides the non-executing `SeeedFactExtractor`, safe source-retaining Markdown/MDX
primitives and a 15-profile golden corpus. The extractor separates summaries, description sections,
features, applications, usage, raw specifications, module pinout, identity candidates, resources,
images and unmapped facts. Its behavior and completeness baseline are documented in
[`seeed-extractor.md`](seeed-extractor.md).

## Stage 4 implementation

Stage 4 provides immutable `NormalizedFacts`, a versioned hierarchical specification registry,
deterministic quantity/interface/identity rules, profile-aware alias disambiguation, unmapped
retention and explicit conflict records. The complete raw extraction result remains embedded and
hash-protected. Rules and corpus metrics are documented in
[`normalization.md`](normalization.md).

## Stage 5 implementation

Stage 5 provides immutable `ComponentIdentity`, separate module/discrete/board/IC/connector kind
candidates, weighted category candidates, explicit auto/review/unresolved thresholds and a guard
against promoting a module's primary IC into the module identity. Every score contribution contains
a rule id, reason and evidence. The scoring model and 15 worked examples are documented in
[`identity-resolution.md`](identity-resolution.md).

## Stage 6 implementation

Stage 6 provides a reusable, content-hash-aware KiCad symbol index and an
`EnrichmentProvider` implementation. KiCad candidates retain exact/alias/name/description and
manufacturer match bases but deliberately contain no relation score and no card fields. Generic
symbols require exact identity evidence. The deprecated KiCad-to-card workflow remains available
only through `ACKB_LEGACY_KICAD_CARD_IMPORT_ENABLED`; see
[`kicad-enrichment.md`](kicad-enrichment.md).

## Stage 7 implementation

Stage 7 provides immutable enrichment candidates, all five Seeed↔KiCad relation types,
versioned positive and negative score contributions and strict decision policy. Only non-generic
`exact_component` relations with an exact part number, no conflicts, at least two source evidence
fragments and confidence of at least 0.950 may be accepted automatically. Main IC, onboard,
connector and functional-equivalent relations remain review-first. The 37-pair calibration corpus,
weights, penalties and pinout boundary are documented in
[`kicad-matcher.md`](kicad-matcher.md).

## Stage 8 implementation

Stage 8 provides immutable `QualityEvaluationInput`, `QualityReport`, nine independently weighted
dimensions, explicit blocking/warning/suggestion issues and deterministic reject/manual-review/
ready-to-compose routes. Profile expectations cover displays, sensors, boards, actuators and
communication modules. Missing source content is distinguished from missed extraction so absent
upstream facts are not mislabeled as parser defects. The complete scoring policy, thresholds and
15-fixture benchmark are documented in [`quality-evaluation.md`](quality-evaluation.md).

## Stage 9 implementation

Stage 9 provides immutable `CompositionInput` and `ReviewDraft`, deterministic section composition,
field-level review metadata, separate module/KiCad pinout structures and explicit accepted/proposed
enrichment state. Rejected quality cannot be composed and rejected KiCad candidates never enter a
draft. An adapter maps review drafts to the existing `ParsedRepositoryComponent` contract without
wiring the new flow into production. The contract, compatibility boundary, 14-draft golden corpus
and representative old/new comparisons are documented in
[`card-composition.md`](card-composition.md).

## Stage 10 implementation

Stage 10 provides `PipelinePersistenceInput`, deterministic aggregate identifiers,
`PostgresImportPersistenceGateway` and `EnrichmentLifecycleRepository`. Six reversible tables retain
source artifacts, identity candidates, evaluations, review drafts, KiCad enrichments and append-only
review decisions. Normalization registry versions are stored with artifacts, repeated writes are
idempotent, and a KiCad source revision change marks only enrichment records stale. The schema and
rollback contract are documented in [`persistence.md`](persistence.md).
