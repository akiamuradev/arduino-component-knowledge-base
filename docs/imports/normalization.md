# Semantic normalization

Status: stage 4 implementation, normalizer `semantic-facts-v1` version `1.0.0`. It runs only in
the parallel import pipeline and is not connected to production endpoints, jobs or persistence.

## Boundary

`SemanticFactNormalizer` receives immutable `ExtractedFacts` and produces immutable
`NormalizedFacts`. The result is not a catalogue card: it contains no chosen name, category,
publication status or generated description. Identity resolution and card composition remain later
stages.

The complete input `ExtractedFacts` is embedded unchanged in the result and protected by SHA-256.
Every normalized fact additionally records:

- the original extracted value and exact raw source text;
- the normalized value and canonical taxonomy path;
- rule id and rule-set version;
- confidence and original evidence fragments.

No LLM, locale-dependent parser, network service or mutable registry participates in normalization.

## Taxonomy and aliases

Specification paths form a hierarchy such as `electrical.voltage.supply`,
`sensor.temperature.measurement_range` and `communication.frequency.carrier`. The registry version
is `1.0.0`; aliases are normalized with NFKC, case folding and punctuation/whitespace cleanup.

An alias may have a generic definition plus non-overlapping profile-specific definitions. The
normalization profile is a deterministic disambiguation hint, not the component category produced
by Stage 5.

| Profile | Example profile-aware mapping |
| --- | --- |
| sensor | `Temperature range` → `sensor.temperature.measurement_range` |
| display | `Resolution` → `display.resolution` |
| actuator | `Maximum current` → `actuator.current.maximum_output` |
| board | `Processor` → `board.processor` |
| communication | `Frequency` → `communication.frequency.carrier` |
| generic | falls back to generic taxonomy definitions only |

Unknown specification labels become `UnmappedSpecification` with their original label, value,
raw text, evidence and reason `taxonomy.alias-unmapped.v1`. Existing unknown source sections remain
available through the embedded extraction result.

## Value rules

All rules use rule-set version `1.0.0`.

| Rule family | Example input | Normalized value | Confidence |
| --- | --- | --- | --- |
| `quantity.voltage.range.v1` | `3.3 to 5 volts` | `3.3–5 V` | high |
| `quantity.current.scalar.v1` | `20 milliamps` | `20 mA` | high |
| `quantity.temperature.range.v1` | `-40 to 85 degrees celsius` | `-40–85 °C` | high |
| `quantity.temperature.tolerance.v1` | `±0.5 degrees celsius` | `±0.5 °C` | high |
| `quantity.frequency.scalar.v1` | `16MHz` | `16 MHz` | high |
| `quantity.pressure.range.v1` | `300 to 1100 hPa` | `300–1100 hPa` | high |
| `quantity.percent.range.v1` | `0 to 100 percent` | `0–100 %` | high |
| `dimensions.axes.v1` | `21 x 17.8 millimeters` | `21 × 17.8 mm` | high |
| `interface.aliases.v1` | `I²C`, `SPI / UART` | `I2C`, `SPI`, `UART` | high |
| `manufacturer.aliases.v1` | `Seeed Technology Co. Ltd.` | `Seeed Studio` | high |
| `part-number.ascii-case.v1` | `esp32–c3` | `ESP32-C3` | medium |
| `text.nfkc-whitespace.v1` | known textual specification | normalized Unicode/spacing | low |

Interface aliases cover I2C/I²C/IIC, SPI, UART, analog, digital, CAN, Wi-Fi and Bluetooth.
Unrecognized interface values are retained separately with `interface.unmapped.v1`.

## Conflicts

Two or more distinct normalized values for the same taxonomy path are reported as an
`incompatible_values` conflict when their evidence comes from different source sections. Values
are not silently selected or merged. The normalization stage adds `normalization_conflict` to its
execution warnings so later quality and review stages can block automatic publication.

## Corpus result

The 15-profile Seeed golden corpus produces 36 mapped specifications, three unmapped
specifications and seven normalized interfaces. The corpus exercises sensor, display, actuator,
board, communication and generic mappings. No conflict is expected in the normal corpus; a
dedicated fixture-level test injects incompatible supply voltages from separate sections.

Property-based tests generate voltage aliases, whitespace variations and signed current ranges,
then verify canonical output and idempotence. The golden projection fixes profiles, taxonomy paths,
values, units, rules, confidence, unmapped values, warnings and the SHA-256 of the complete result.
