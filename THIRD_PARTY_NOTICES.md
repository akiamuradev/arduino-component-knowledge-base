# Third-party notices / Уведомления о сторонних материалах

This file records external data sources supported by Arduino Component Knowledge Base (ACKB).
It does not change the [PolyForm Noncommercial License 1.0.0](LICENCE) that applies to ACKB code,
and it does not relicense third-party material.

Этот файл перечисляет внешние источники данных, поддерживаемые ACKB. Он не изменяет лицензию
кода ACKB и не перелицензирует сторонние материалы.

## Seeed Studio Wiki

- Upstream: <https://github.com/Seeed-Studio/wiki-documents>
- Project site: <https://wiki.seeedstudio.com/>
- Recorded data license: GNU General Public License v3.0 only (`GPL-3.0-only`)
- License reference: <https://www.gnu.org/licenses/gpl-3.0.html>
- ACKB use: bounded retrieval of selected documentation files, followed by extraction and
  normalization into an educational component draft.
- Attribution: the exact upstream repository, resolved commit, source file, original page,
  parser version and attribution text are retained in the component source snapshot.
- Modifications: formatting, headings and technical facts may be selected, normalized or mapped
  to ACKB fields; the snapshot records the applicable modifications notice.

## Official KiCad Symbols

- Upstream: <https://gitlab.com/kicad/libraries/kicad-symbols>
- Project site: <https://www.kicad.org/>
- Recorded data license: Creative Commons Attribution-ShareAlike 4.0 International
  (`CC-BY-SA-4.0`)
- License reference: <https://creativecommons.org/licenses/by-sa/4.0/>
- ACKB use: bounded retrieval of a selected `.kicad_sym` library and extraction of one selected
  symbol into an educational component draft. KiCad footprints are not imported by this adapter.
- Attribution: the exact upstream repository, resolved commit/tag, library file, symbol name,
  parser version and attribution text are retained in the component source snapshot.
- Modifications: symbol properties and pins are parsed and normalized into ACKB fields; the
  snapshot records the applicable modifications notice.

## Historical disabled sources

Arduino-Tex and Portal-PK remain inactive registry records for audit transparency. AlexGyver is
disabled with reason `owner_denied_usage`: use of materials was denied by the source owner. These
sources cannot be selected in the repository import UI or launched by the repository import API.

Names and trademarks belong to their respective owners. ACKB is not affiliated with Arduino,
Seeed Studio or KiCad. This notice documents implementation metadata and is not legal advice.
