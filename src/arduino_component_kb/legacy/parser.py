"""Pure, bounded ZIP/OOXML analysis. Never executes or extracts archive members.

The workbook is authoritative. Category ranges are an explicit layout-v1 policy,
not a runtime dependency on the separately supplied review/manifest artifacts.
Contributor columns are deliberately never read into the output model.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import posixpath
import re
import stat
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field

SOURCE_NAME = "Микроконтроллеры, модуля, компоненты и проекты"
PARSER_VERSION = "legacy-layout-v1.2"
MIB = 1024 * 1024
ZIP_LIMIT = 200 * MIB
XLSX_LIMIT = 64 * MIB
CATEGORY_RANGES = (
    (2, 28, "РАДИОКОМПОНЕНТЫ"),
    (29, 40, "МАКЕТНЫЕ ПЛАТЫ И ПИТАНИЕ"),
    (41, 42, "КНОПОЧНЫЕ ПЕРЕКЛЮЧАТЕЛИ И ВЫКЛЮЧАТЕЛИ"),
    (43, 53, "ИНТЕГРАЛЬНЫЕ СХЕМЫ"),
    (54, 59, "РЕЛЕ"),
    (60, 78, "СВЕТОДИОДНЫЕ МОДУЛЯ"),
    (79, 97, "КНОПОЧНЫЕ ПЕРЕКЛЮЧАТЕЛИ И ВЫКЛЮЧАТЕЛИ"),
    (98, 115, "ДВИГАТЕЛИ И СЕРВОПРИВОДЫ"),
    (116, 160, "ДАТЧИКИ"),
    (161, 210, "МОДУЛЯ"),
    (211, 223, "ДИСПЛЕИ"),
    (224, 240, "ПЛАТФОРМЫ РАЗРАБОТКИ"),
    (241, 256, "ПЛАТЫ РАСШИРЕНИЯ"),
)
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
X = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


class LegacyInputError(ValueError):
    """Safe machine-readable error, without document contents or personal data."""


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImageRef(Record):
    origin: str
    path: str
    sha256: str
    size: int
    purpose: str = "photo"


class Specification(Record):
    label: str
    value: str
    unit: str | None = None


class FolderCandidate(Record):
    path: str
    score: int


class Target(Record):
    identity: str
    title: str
    category: str
    rows: list[int]
    images: list[ImageRef] = Field(default_factory=list)
    candidates: list[FolderCandidate] = Field(default_factory=list)
    match: str = "unmatched"
    folder: str | None = None
    description: str = ""
    specifications: list[Specification] = Field(default_factory=list)
    documents: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Analysis(Record):
    source_name: str = SOURCE_NAME
    parser_version: str = PARSER_VERSION
    zip_sha256: str
    xlsx_sha256: str
    targets: list[Target]
    statistics: dict[str, int]
    warnings: list[str]

    def digest(self) -> str:
        return digest(self.model_dump(mode="json"))


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("–", "-").replace("—", "-").replace("\u00a0", " ")
    return " ".join(re.sub(r"[(),;\"«»]", " ", value).split())


def models(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-zа-я0-9]+(?:[-./][a-zа-я0-9]+)*", normalize(value))
        if (token[0].isalpha() or re.fullmatch(r"\d+[a-z]+\d+[a-z0-9]*|\d{4,6}", token))
        and re.search(r"\d", token)
    )


def validate_archive(archive: ZipFile, *, unpacked_limit: int = 1024 * MIB) -> None:
    members = archive.infolist()
    if len(members) > 10000 or sum(m.file_size for m in members) > unpacked_limit:
        raise LegacyInputError("archive_expansion_limit")
    seen: set[str] = set()
    for member in members:
        name = member.filename
        path = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or "\x00" in name
            or path.is_absolute()
            or ".." in path.parts
            or re.match(r"^[A-Za-z]:", name)
            or name in seen
            or stat.S_ISLNK(member.external_attr >> 16)
            or member.flag_bits & 1
        ):
            raise LegacyInputError("unsafe_archive_member")
        seen.add(name)
        if member.file_size > 64 * MIB or member.file_size > max(1, member.compress_size) * 1000:
            raise LegacyInputError("archive_member_limit")


def xml(archive: ZipFile, path: str) -> ET.Element:
    if archive.getinfo(path).file_size > 8 * MIB:
        raise LegacyInputError("xml_size_limit")
    content = archive.read(path).decode("utf-8-sig")
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise LegacyInputError("unsafe_xml")
    # Decode UTF-8 before rejecting DTD/entity declarations: no encoding-detection
    # bypass, external entities or entity expansion can reach ElementTree.
    return ET.fromstring(content)  # noqa: S314  # nosec B314


def relationships(archive: ZipFile, part: str) -> dict[str, str]:
    directory, filename = posixpath.split(part)
    rel_path = posixpath.join(directory, "_rels", filename + ".rels")
    if rel_path not in archive.namelist():
        return {}
    result: dict[str, str] = {}
    for rel in xml(archive, rel_path):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        resolved = posixpath.normpath(posixpath.join(directory, target))
        if target.startswith("/"):
            resolved = target.lstrip("/")
        if resolved.startswith("../") or "\\" in resolved or ":" in resolved:
            raise LegacyInputError("unsafe_relationship")
        result[rel.attrib["Id"]] = resolved
    return result


def image_ref(archive: ZipFile, path: str, origin: str) -> ImageRef:
    member = archive.getinfo(path)
    if member.file_size > 16 * MIB:
        raise LegacyInputError("image_size_limit")
    with archive.open(member) as stream:
        hasher = hashlib.sha256()
        while chunk := stream.read(MIB):
            hasher.update(chunk)
        checksum = hasher.hexdigest()
    name = normalize(PurePosixPath(path).stem)
    purpose = "pinout" if any(s in name for s in ("pinout", "распинов")) else "photo"
    if any(s in name for s in ("схем", "schematic", "circuit", "diagram")):
        purpose = "diagram"
    return ImageRef(
        origin=origin, path=path, sha256=checksum, size=member.file_size, purpose=purpose
    )


def workbook_targets(archive: ZipFile) -> tuple[list[Target], int]:
    workbook = xml(archive, "xl/workbook.xml")
    rels = relationships(archive, "xl/workbook.xml")
    sheets = workbook.findall(f"{S}sheets/{S}sheet")
    sheet = next((s for s in sheets if s.get("name") == "Модуля Ардуино"), None)
    if sheet is None:
        raise LegacyInputError("unsupported_workbook_layout")
    sheet_path = rels[sheet.attrib[f"{R}id"]]
    strings: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        strings = ["".join(s.itertext()) for s in xml(archive, "xl/sharedStrings.xml")]
    titles: dict[int, str] = {}
    root = xml(archive, sheet_path)
    for cell in root.iter(f"{S}c"):
        # The contributor column must never enter any plan, audit or provenance.
        address = cell.get("r", "")
        if not re.fullmatch(r"C\d+", address):
            continue
        row = int(address[1:])
        value = cell.findtext(f"{S}v", "")
        if cell.get("t") == "s":
            value = strings[int(value)]
        elif cell.get("t") == "inlineStr":
            value = "".join(t.text or "" for t in cell.iter(f"{S}t"))
        value = " ".join(value.split())
        if value:
            titles[row] = value
    if normalize(titles.pop(1, "")) != "название" or any(r > 256 for r in titles):
        raise LegacyInputError("unsupported_workbook_layout")
    images: dict[int, list[ImageRef]] = {}
    sheet_rels = relationships(archive, sheet_path)
    for drawing in root.iter(f"{S}drawing"):
        drawing_path = sheet_rels[drawing.attrib[f"{R}id"]]
        drawing_rels = relationships(archive, drawing_path)
        for anchor in xml(archive, drawing_path):
            origin = anchor.find(f"{X}from")
            if origin is None or origin.findtext(f"{X}col") != "1":
                continue
            row = int(origin.findtext(f"{X}row", "-1")) + 1
            for blip in anchor.iter(f"{A}blip"):
                relation = blip.get(f"{R}embed")
                if relation in drawing_rels:
                    path = drawing_rels[relation]
                    images.setdefault(row, []).append(image_ref(archive, path, "xlsx"))
    targets: dict[str, Target] = {}
    for row, title in sorted(titles.items()):
        category = next((c for start, end, c in CATEGORY_RANGES if start <= row <= end), None)
        if category is None or len(title) > 160:
            raise LegacyInputError("unsupported_workbook_row")
        identity = digest([SOURCE_NAME, normalize(category), normalize(title)])
        previous = targets.get(identity)
        refs = (previous.images if previous else []) + images.get(row, [])
        refs = list({r.sha256: r for r in refs}.values())
        targets[identity] = Target(
            identity=identity,
            title=previous.title if previous else title,
            category=category,
            rows=(previous.rows if previous else []) + [row],
            images=refs,
        )
    return list(targets.values()), len(titles)


def folder_index(archive: ZipFile) -> tuple[dict[str, list[str]], int]:
    folders: dict[str, list[str]] = {}
    ignored = 0
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if any(normalize(p) == "проекты" for p in path.parts):
            ignored += int(not member.is_dir())
            continue
        if member.is_dir() or path.suffix.casefold() not in IMAGE_SUFFIXES | {".docx"}:
            continue
        if len(path.parts) < 4 or path.parts[0] != SOURCE_NAME:
            continue
        folders.setdefault(str(path.parent), []).append(member.filename)
    return {k: sorted(v) for k, v in sorted(folders.items())}, ignored


def rank_folders(target: Target, folders: dict[str, list[str]]) -> list[FolderCandidate]:
    ranked: list[FolderCandidate] = []
    wanted = normalize(target.title)
    wanted_models = models(wanted)
    for folder in folders:
        path = PurePosixPath(folder)
        if normalize(path.parts[1]) != normalize(target.category):
            continue
        name = normalize(path.name)
        found_models = models(name)
        if wanted_models and found_models and wanted_models.isdisjoint(found_models):
            continue
        score = round(SequenceMatcher(None, wanted, name).ratio() * 100)
        if wanted == name:
            score = 100
        elif wanted_models and wanted_models == found_models:
            score = max(score, 95)
        elif wanted_models and found_models and wanted_models != found_models:
            score = min(score, 79)
        if score >= 60:
            ranked.append(FolderCandidate(path=folder, score=score))
    return sorted(ranked, key=lambda c: (-c.score, c.path))[:5]


def paragraph(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.iter(f"{W}t")).strip()


def markdown_text(value: str) -> str:
    # Keep source text as inert Markdown, never raw HTML or active links/images.
    return re.sub(r"([\\`*_[\]{}!|])", r"\\\1", html.escape(value, quote=False))


def read_docx(content: bytes) -> tuple[str, list[Specification], list[str]]:
    output: list[str] = []
    specifications: list[Specification] = []
    warnings: list[str] = []
    with ZipFile(io.BytesIO(content)) as archive:
        validate_archive(archive, unpacked_limit=64 * MIB)
        root = xml(archive, "word/document.xml")
        body = root.find(f"{W}body")
        if body is None:
            return "", [], ["empty_document"]
        for element in body:
            if element.tag == f"{W}p":
                value = paragraph(element)
                if value and normalize(value) not in {
                    "название",
                    "описание",
                    "характеристики",
                    "технические характеристики",
                    "назначение",
                    "информация",
                    "изображение",
                    "ссылки",
                }:
                    style = element.find(f"{W}pPr/{W}pStyle")
                    heading = style is not None and "heading" in style.get(f"{W}val", "").lower()
                    output.append(("### " if heading else "") + markdown_text(value))
            elif element.tag == f"{W}tbl":
                rows = [
                    [paragraph(c) for c in r.findall(f"{W}tc")] for r in element.findall(f"{W}tr")
                ]
                simple = bool(rows) and all(len(r) in (2, 3) for r in rows)
                simple = simple and len({len(r) for r in rows}) == 1
                simple = simple and not any(
                    e.tag in {f"{W}gridSpan", f"{W}vMerge"} for e in element.iter()
                )
                header = bool(rows) and normalize(rows[0][0]) in {
                    "параметр",
                    "характеристика",
                    "наименование",
                    "parameter",
                }
                # Comparison tables are not silently interpreted as specifications.
                value_header = header and normalize(rows[0][1]) in {"значение", "value"}
                numeric_rows = (
                    not header
                    and bool(rows)
                    and all(
                        len(r) == 2 and re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?\s*[\w°%/.-]*", r[1])
                        for r in rows
                    )
                )
                simple = simple and (value_header or numeric_rows)
                simple = simple and (
                    len(rows[0]) == 2
                    or (
                        header
                        and normalize(rows[0][2]) in {"единица", "ед. изм.", "единицы", "unit"}
                    )
                )
                if simple:
                    for row in rows[1:] if header else rows:
                        if row[0] and row[1] and len(row[0]) <= 120 and len(row[1]) <= 500:
                            specifications.append(
                                Specification(
                                    label=row[0],
                                    value=row[1],
                                    unit=row[2] or None if len(row) == 3 else None,
                                )
                            )
                # Always preserve all table cells, including unsupported/blank layouts.
                if rows and any(any(row) for row in rows):
                    width = max(map(len, rows))
                    padded = [r + [""] * (width - len(r)) for r in rows]
                    table = ["| " + " | ".join(markdown_text(c) for c in r) + " |" for r in padded]
                    table.insert(1, "| " + " | ".join(["---"] * width) + " |")
                    output.append("\n".join(table))
                    if not simple:
                        warnings.append("complex_table_preserved")
    description = "\n\n".join(output)
    if len(description) > 100000 or len(specifications) > 200:
        raise LegacyInputError("document_content_limit")
    return description, specifications, sorted(set(warnings))


def enrich(target: Target, archive: ZipFile, members: list[str]) -> Target:
    descriptions: list[str] = []
    specifications: list[Specification] = []
    documents: list[dict[str, str]] = []
    warnings = list(target.warnings)
    images = list(target.images)
    for member in members:
        suffix = PurePosixPath(member).suffix.casefold()
        if suffix in IMAGE_SUFFIXES:
            images.append(image_ref(archive, member, "zip"))
        elif suffix == ".docx":
            content = archive.read(member)
            description, specs, notes = read_docx(content)
            documents.append({"path": member, "sha256": hashlib.sha256(content).hexdigest()})
            if description:
                descriptions.append(description)
            specifications.extend(specs)
            warnings.extend(notes)
    unique_images = list({r.sha256: r for r in images}.values())
    if len(unique_images) > 12:
        warnings.append("image_card_limit_review_required")
    if not descriptions:
        warnings.append("description_missing")
    return target.model_copy(
        update={
            "images": unique_images,
            "description": "\n\n".join(descriptions),
            "specifications": specifications,
            "documents": documents,
            "warnings": sorted(set(warnings)),
        }
    )


def analyze(zip_path: Path, xlsx_path: Path) -> Analysis:
    if zip_path.stat().st_size > ZIP_LIMIT or xlsx_path.stat().st_size > XLSX_LIMIT:
        raise LegacyInputError("upload_size_limit")
    try:
        with ZipFile(xlsx_path) as workbook, ZipFile(zip_path) as archive:
            validate_archive(workbook, unpacked_limit=256 * MIB)
            validate_archive(archive)
            targets, row_count = workbook_targets(workbook)
            folders, ignored = folder_index(archive)
            enriched: list[Target] = []
            for target in targets:
                candidates = rank_folders(target, folders)
                automatic = (
                    bool(candidates)
                    and candidates[0].score >= 90
                    and (
                        len(candidates) == 1
                        or candidates[0].score - candidates[1].score >= 10
                        or (candidates[0].score == 100 and candidates[1].score < 100)
                    )
                )
                folder = candidates[0].path if automatic else None
                target = target.model_copy(
                    update={
                        "candidates": candidates,
                        "folder": folder,
                        "match": "auto" if automatic else "review" if candidates else "unmatched",
                        "warnings": ["license_unknown"],
                    }
                )
                enriched.append(enrich(target, archive, folders[folder] if folder else []))
            counts = Counter(t.match for t in enriched)
            return Analysis(
                zip_sha256=file_hash(zip_path),
                xlsx_sha256=file_hash(xlsx_path),
                targets=enriched,
                statistics={
                    "rows": row_count,
                    "targets": len(enriched),
                    "collapsed_rows": row_count - len(enriched),
                    "auto": counts["auto"],
                    "review": counts["review"],
                    "unmatched": counts["unmatched"],
                    "project_files_ignored": ignored,
                    "with_xlsx_images": sum(
                        any(i.origin == "xlsx" for i in t.images) for t in enriched
                    ),
                    "images": sum(len(t.images) for t in enriched),
                    "with_description": sum(bool(t.description) for t in enriched),
                    "with_specifications": sum(bool(t.specifications) for t in enriched),
                    "workbook_images": sum(len(t.images) for t in targets),
                    "docx_scanned": sum(len(t.documents) for t in enriched),
                    "specifications_proposed": sum(len(t.specifications) for t in enriched),
                },
                warnings=["category_mapping_layout_v1", "licenses_require_manual_review"],
            )
    except (BadZipFile, KeyError, ET.ParseError, UnicodeError, IndexError) as error:
        raise LegacyInputError("malformed_legacy_bundle") from error
