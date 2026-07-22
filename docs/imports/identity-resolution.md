# Identity resolution and weighted classification

Status: stage 5 implementation, resolver `weighted-identity-v1` and rule set `1.0.0`. It runs only
in the parallel pipeline and does not create or persist catalogue cards.

## Result contract

`WeightedIdentityResolver` converts `NormalizedFacts` into immutable `ComponentIdentity`. The
result embeds the complete normalized and extracted inputs, protected by SHA-256, and contains:

- canonical name and optional manufacturer with evidence;
- product/SKU/model identifiers and component part numbers;
- primary IC candidates in a separate field;
- evidenced aliases;
- ranked component-kind candidates;
- ranked category candidates with complete score breakdown;
- resolution status and confidence.

Supported component kinds are `module`, `development_board`, `discrete_component`,
`integrated_circuit`, `connector` and `generic_unknown`. A connector is therefore distinguishable
from a general module even before category persistence is introduced.

## Weighted category scoring

Each category accumulates independent evidence contributions. Only one contribution per signal
family is counted, preventing repeated keywords from inflating a score.

| Signal | Weight | Example rule id |
| --- | ---: | --- |
| title terminology | 55 | `category.sensors.title.v1` |
| summary terminology | 20 | `category.sensors.summary.v1` |
| description/features/applications/usage | 10 | `category.sensors.details.v1` |
| matching semantic taxonomy | normally 20 | `category.sensors.taxonomy.v1` |
| normalization profile | 15 | `category.sensors.profile.v1` |
| complete title equals evidenced primary IC | 85 | `category.integrated-circuits.exact-primary-identity.v1` |

Scores are capped at 100. Candidates are sorted by descending score and then stable category key.
Every contribution stores rule id, weight, matched signal, human-readable reason and source
evidence. Generic interface or connector properties do not independently create communication or
connector candidates.

The rule set covers `sensors`, `displays`, `actuators`, `input`, `power`, `communication`, `boards`,
`connectors`, `semiconductors` and `integrated-circuits`. `connectors` is a target-pipeline candidate
key; the release catalogue taxonomy remains unchanged until the later persistence/switch stages.

## Component-kind scoring

Strong title evidence contributes 70 for development boards, connectors, discrete components and
explicit ICs. Module terminology contributes 35, body terminology 20, and a registered Seeed
source contributes a weak module prior of 15. Connector taxonomy adds 10 only after textual
connector evidence exists.

Discrete and IC kinds require title-level identity evidence. A resistor mentioned in usage text or
an IC mentioned as a module's controller cannot change the component kind.

## Thresholds

Rule set `1.0.0` uses these deterministic thresholds:

- `auto_resolved`: top category score ≥ 65, lead over the second candidate greater than 15, top
  kind score ≥ 50, and no normalization conflict or ambiguous title;
- `review_required`: top category score ≥ 35 but one of the automatic conditions is not met;
- `unresolved`: no category reaches 35, or the component kind remains generic/unknown.

Only `auto_resolved` results receive `selected_category`. Review and unresolved results retain all
candidates without silently choosing one. Confidence is respectively high, medium or low.

## Primary IC promotion guard

Primary IC candidates are never copied into module aliases and never replace a module's canonical
name. An IC kind/category can be proposed only when the complete source title equals an evidenced
primary-IC part number or the title explicitly describes an IC. Thus “Grove OLED Display” remains a
display module with SSD1306 enrichment evidence, not an SSD1306 card.

## Golden score examples

The golden corpus records complete breakdowns for all 15 fixtures; the table below provides more
than the required ten examples.

| Fixture | Kind (score) | Category candidates | Resolution |
| --- | --- | --- | --- |
| `actuator_module.md` | module (70) | actuators 100 | auto-resolved |
| `alternative_headings.mdx` | module (70) | displays 90 | auto-resolved |
| `broken_frontmatter.mdx` | module (70) | actuators 90 | auto-resolved |
| `can_bus_module.md` | module (70) | communication 90 | auto-resolved |
| `communication_module.md` | module (70) | communication 100 | auto-resolved |
| `complete.md` | module (70) | sensors 90 | auto-resolved |
| `connector_module.md` | connector (100) | connectors 85 | auto-resolved |
| `development_board.md` | development board (90) | boards 100, communication 30 | auto-resolved |
| `display_spi.md` | module (70) | displays 100 | auto-resolved |
| `environmental_sensor.md` | module (70) | sensors 100, boards 10 | auto-resolved |
| `minimal_no_summary.md` | module (50) | none | unresolved |
| `motor_shield.md` | module (70) | actuators 100, boards 85 | review-required |
| `power_module.md` | module (70) | power 75 | auto-resolved |
| `unknown_structure.md` | module (70) | sensors 90 | auto-resolved |
| `without_specifications.md` | module (70) | input 55, boards 10 | review-required |

Dedicated false-match tests cover modules containing known ICs, incidental resistor/connector
mentions, an exact IC title, a discrete transistor title and the ambiguous motor-shield case.
