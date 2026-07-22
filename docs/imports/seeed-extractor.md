# Seeed evidence-first extractor

Status: stage 3 implementation, parser `seeed-facts-v2` version `2.0.0`. The extractor is tested in
the parallel import pipeline and is not connected to the release production path.

## Responsibility

`SeeedFactExtractor` converts one immutable Markdown/MDX `SourceArtifact` into `ExtractedFacts`.
It preserves source wording and evidence, but deliberately does not:

- normalize units or specification names;
- infer a catalogue category;
- generate missing summaries or descriptions;
- compose a component card;
- execute code, JSX, imports or exports found in source documents.

Every extracted field has its original text, source revision, path, section or line selector,
extraction method and parser version. Missing optional data and unfamiliar structures produce typed
warnings. A missing title or invalid source/media type produces a typed `ParsingError`.

## Semantic sections

Headings are matched case-insensitively after punctuation and whitespace cleanup.

| Output | Recognized heading families |
| --- | --- |
| description | About, Description, Introduction, Overview, Product Description, What Is It |
| features | Feature, Features, Key Features, Highlights |
| applications | Application(s), Use Cases, Typical Applications |
| specifications | Parameters, Specification(s), Technical Specifications |
| hardware facts | Hardware, Hardware Description/Overview/Structure |
| module pinout | Pin Definition, Pin Map, Pinout, Pins |
| usage | Getting Started, How to Use, Play With Arduino, Usage |
| resources | Documents, Downloads, References, Resource(s) |
| identity | Part List, Product Data, Product Information |

Specification and hardware tables are retained as raw label/value pairs. Key-value feature rows are
also preserved as specifications without deciding whether their labels belong to the canonical
catalogue schema. Module-level pins remain separate from future primary-IC pin enrichment.

Unknown non-empty sections become `UnknownFact` entries and receive `unknown_section` warnings;
they are not silently dropped or forced into a generic catalogue category.

## Safe Markdown/MDX handling

The parser is intentionally non-executing. It decodes bounded source bytes, reads simple scalar
frontmatter and scans headings, paragraphs, lists, tables, links and images. Fenced code,
`import`/`export` statements, JSX tags and JSX expressions are excluded and reported as
`executable_construct_ignored`. Literal identifier punctuation such as the underscore in `DIR_A`
is preserved.

Malformed frontmatter is recoverable when a trustworthy Markdown title still exists. Unsafe or
malformed metadata entries are ignored with warnings rather than interpreted as YAML objects.

## Regression corpus and completeness

The golden corpus contains 15 Seeed fixtures: actuator, connector, display, environmental sensor,
communication modules, development board, motor shield, power, input, malformed MDX, alternate
headings, unknown legacy structure and deliberately incomplete pages.

Across all 15 fixtures the extractor currently retains:

| Fact family | Count |
| --- | ---: |
| raw specifications | 39 |
| module pins | 24 |
| semantic description/feature/application/usage facts | 33 |
| resources | 9 |
| primary IC candidates | 5 |
| identifiers | 4 |
| images | 3 |
| unmapped sections | 3 |

On the eight fixtures shared with the release adapter, the new extractor retains 17 raw
specifications versus 14 normalized specifications, four resources versus none, seven module pins,
12 semantic facts, one image and two unknown sections. This comparison measures structural
retention only; it is not a publication-quality score because normalization and quality evaluation
belong to later stages.

The golden projection also stores a SHA-256 digest of the complete deterministic `ExtractedFacts`
JSON. Any change to values, raw evidence, provenance, warnings or parser metadata therefore requires
an explicit golden review.

## Next boundary

Stage 4 consumes these raw facts through `FactNormalizer`. It may canonicalize units and known
specification labels, but must retain the raw field and evidence links established here. The
extractor must remain independent of catalogue cards and persistence.
