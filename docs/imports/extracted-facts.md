# Extracted facts contract

Status: stage 2 domain model. `ExtractedFacts` is available to future extractors but remains
disconnected from the release `0.21.0` production import flow.

## Purpose

`ExtractedFacts` is the evidence-preserving boundary between source-specific parsing and semantic
normalization. It records what a source actually says, where it says it and how the parser found it.
It is not a catalogue card, a normalized specification set or an identity decision.

The implementation is in
`src/arduino_component_kb/imports/pipeline/models/` and uses immutable standard-library
dataclasses. It does not import ORM, HTTP, FastAPI, Redis, Dramatiq or catalogue types.

## Core models

| Model | Responsibility |
| --- | --- |
| `SourceReference` | Registered source key plus source URL and/or path and optional immutable revision. |
| `SourceArtifactMetadata` | Media type, SHA-256, byte length and timezone-aware acquisition time for the parsed artifact. |
| `EvidenceFragment` | Source, selector/section, exact raw text, extraction method and parser version. |
| `ExtractedField[T]` | Structurally extracted value, its raw representation and one or more evidence fragments. |
| `RawSpecification` | Source label and source value without taxonomy mapping or unit normalization. |
| `ExtractionWarning` | Safe warning code/message with optional source evidence. |
| `ExtractedFacts` | Immutable collection of all candidates and facts extracted from one artifact. |

Supporting value types are `DescriptionSection`, `Identifier`, `ModulePin`, `ResourceReference`,
`ImageReference` and `UnknownFact`.

## Fact groups

`ExtractedFacts` stores:

- `title_candidates` and `summary_candidates`;
- `description_sections`, `feature_facts`, `application_facts` and `usage_sections`;
- product/SKU/model/part-number `identifiers`;
- `manufacturer_candidates` and `brand_candidates`;
- `interface_facts`;
- module-level `module_pinout`;
- `primary_ic_candidates` without promoting them to the component identity;
- all `specifications` as raw label/value pairs;
- `resources` and `images`;
- `unmapped_facts` for source material without a known semantic type;
- extraction `warnings`.

There is deliberately no category, publication status, catalogue ID, UI section, normalized value,
accepted identity or KiCad relation in this model.

## Provenance invariants

Every `ExtractedField` must have at least one `EvidenceFragment`. Evidence always includes:

- source URL and/or source path through `SourceReference`;
- a selector, section, or both;
- exact `raw_text`;
- versioned `extraction_method`;
- `parser_version`.

All fact and warning evidence must reference the same `SourceReference` as the artifact. Mixed-source
facts are rejected. Cross-source comparison belongs to enrichment, not extraction.

The distinction between values is:

| Layer | Example | Owner |
| --- | --- | --- |
| Evidence raw text | `| Supply Voltage | 3.3V to 5V |` | extractor |
| Structurally extracted value | `{label: "Supply Voltage", value: "3.3V to 5V"}` | extractor |
| Normalized value | range `3.3–5 V`, rule ID and confidence | future normalizer |

An extractor may decode syntax and split a table row, but it must not apply specification aliases,
convert units, select a category or generate missing prose.

## Unknown data retention

Unknown specification rows remain ordinary `RawSpecification` values. They do not need to be known
to the future taxonomy. Other unknown source structures are stored as `UnknownFact` in
`unmapped_facts`. Both retain raw values and evidence and survive JSON round trips.

This replaces the legacy behavior that reduces an unknown specification to
`untrusted_specification_ignored` and discards its label and value.

## Stable serialization

The wire/storage representation has schema version `extracted-facts/v1`.

- `ExtractedFacts.to_json()` emits deterministic UTF-8 JSON with sorted keys.
- `ExtractedFacts.from_json()` validates and recreates equal immutable models.
- Unknown schema versions are rejected rather than interpreted heuristically.
- All tuples serialize as JSON arrays and recover as tuples.
- Raw values and evidence are part of the serialized contract.

Schema changes require a new schema version and explicit compatibility handling. Adding silent
defaults that lose source facts is not allowed.

## Example: Seeed temperature module

The following shortened example shows the contract shape. A real extraction contains the remaining
fact-group arrays as well.

```json
{
  "schema_version": "extracted-facts/v1",
  "artifact": {
    "source": {
      "source_key": "seeed_wiki",
      "source_url": "https://github.com/Seeed-Studio/wiki-documents",
      "source_path": "sites/en/docs/Sensor/Grove-Temperature-Sensor.md",
      "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    "media_type": "text/markdown",
    "content_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "byte_length": 4096,
    "acquired_at": "2026-07-23T10:00:00+00:00"
  },
  "title_candidates": [
    {
      "value": "Grove - Temperature Sensor",
      "raw_value": "title: Grove - Temperature Sensor",
      "evidence": [
        {
          "source": {
            "source_key": "seeed_wiki",
            "source_url": "https://github.com/Seeed-Studio/wiki-documents",
            "source_path": "sites/en/docs/Sensor/Grove-Temperature-Sensor.md",
            "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
          },
          "selector": "frontmatter.title",
          "section": "frontmatter",
          "raw_text": "title: Grove - Temperature Sensor",
          "extraction_method": "markdown.section-v1",
          "parser_version": "2.0.0-dev1"
        }
      ]
    }
  ],
  "specifications": [
    {
      "value": {
        "label": "Signal settling profile",
        "value": "fast/typical"
      },
      "raw_value": "| Signal settling profile | fast/typical |",
      "evidence": [
        {
          "source": {
            "source_key": "seeed_wiki",
            "source_url": "https://github.com/Seeed-Studio/wiki-documents",
            "source_path": "sites/en/docs/Sensor/Grove-Temperature-Sensor.md",
            "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
          },
          "selector": "table[1] row[2]",
          "section": "Specifications",
          "raw_text": "| Signal settling profile | fast/typical |",
          "extraction_method": "markdown.section-v1",
          "parser_version": "2.0.0-dev1"
        }
      ]
    }
  ],
  "unmapped_facts": [
    {
      "value": {"label": "Calibration matrix", "value": "A1,B2,C3"},
      "raw_value": "Calibration matrix: A1,B2,C3",
      "evidence": [
        {
          "source": {
            "source_key": "seeed_wiki",
            "source_url": "https://github.com/Seeed-Studio/wiki-documents",
            "source_path": "sites/en/docs/Sensor/Grove-Temperature-Sensor.md",
            "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
          },
          "selector": null,
          "section": "Factory Notes",
          "raw_text": "Calibration matrix: A1,B2,C3",
          "extraction_method": "markdown.section-v1",
          "parser_version": "2.0.0-dev1"
        }
      ]
    }
  ]
}
```

## Verification

Focused contract checks:

```shell
uv run pytest -q tests/test_extracted_facts.py
uv run mypy src/arduino_component_kb/imports/pipeline tests/test_extracted_facts.py
```

The tests cover deterministic round-trip equality, schema validation, source consistency, required
evidence, timezone/digest validation and preservation of unknown specifications/unmapped facts.

## Stage 3 hand-off

The new Seeed extractor will implement `FactExtractor[SourceArtifact, ExtractedFacts]` using these
models and the stage 0 fixtures. It must not modify this contract to imitate the legacy catalogue
draft shape, and it remains outside production flow until the shadow-mode stage.
