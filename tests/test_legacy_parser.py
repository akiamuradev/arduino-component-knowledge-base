"""Synthetic fixtures only: no redistribution of the supplied private corpus."""

from __future__ import annotations

import io
import stat
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from arduino_component_kb.legacy.parser import (
    SOURCE_NAME,
    LegacyInputError,
    Target,
    digest,
    folder_index,
    models,
    normalize,
    rank_folders,
    read_docx,
    validate_archive,
    workbook_targets,
    xml,
)


def package(files: dict[str, str | bytes]) -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


@pytest.mark.parametrize("name", ["../bad", "/etc/passwd", "C:/bad", "a\\bad"])
def test_archive_rejects_unsafe_paths(name: str) -> None:
    with ZipFile(io.BytesIO(package({name: "bad"}))) as archive:
        with pytest.raises(LegacyInputError, match="unsafe_archive_member"):
            validate_archive(archive)


def test_archive_rejects_links_and_bombs() -> None:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        info = ZipInfo("link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")
    with ZipFile(buffer) as archive, pytest.raises(LegacyInputError):
        validate_archive(archive)
    with ZipFile(io.BytesIO(package({"bomb": b"a" * 2000000}))) as archive:
        with pytest.raises(LegacyInputError, match="archive_member_limit"):
            validate_archive(archive)


def test_xml_rejects_entities() -> None:
    content = '<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>'
    with ZipFile(io.BytesIO(package({"x.xml": content}))) as archive:
        with pytest.raises(LegacyInputError, match="unsafe_xml"):
            xml(archive, "x.xml")


def test_identity_preserves_model_numbers() -> None:
    assert normalize("  ＤＨＴ１１ (датчик) ") == "dht11 датчик"
    assert normalize("DHT11") != normalize("DHT22")
    assert models("Барометр BMP180") == {"bmp180"}
    assert digest(["a", "b"]) != digest(["ab"])


def test_matching_excludes_other_categories_and_conflicting_models() -> None:
    target = Target(identity="x", title="Датчик DHT11", category="ДАТЧИКИ", rows=[116])
    folders = {
        f"{SOURCE_NAME}/ДАТЧИКИ/Влажность DHT11": [],
        f"{SOURCE_NAME}/ДАТЧИКИ/Датчик DHT22": [],
        f"{SOURCE_NAME}/МОДУЛЯ/Датчик DHT11": [],
    }
    candidates = rank_folders(target, folders)
    assert len(candidates) == 1 and candidates[0].score == 95


def test_projects_and_code_are_not_indexed() -> None:
    files = {
        f"{SOURCE_NAME}/ПРОЕКТЫ/DHT11/Информация.docx": "ignored",
        f"{SOURCE_NAME}/ДАТЧИКИ/DHT11/main.ino": "ignored",
        f"{SOURCE_NAME}/ДАТЧИКИ/DHT11/photo.png": b"bytes",
    }
    with ZipFile(io.BytesIO(package(files))) as archive:
        folders, ignored = folder_index(archive)
    assert ignored == 1
    assert list(folders.values()) == [[f"{SOURCE_NAME}/ДАТЧИКИ/DHT11/photo.png"]]


def test_docx_preserves_paragraphs_tables_and_escapes_html() -> None:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    content = f'''<w:document xmlns:w="{ns}"><w:body>
    <w:p><w:r><w:t>&lt;script&gt;hello&lt;/script&gt;</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Напряжение</w:t></w:r></w:p></w:tc>
    <w:tc><w:p><w:r><w:t>5 В</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''
    description, specs, warnings = read_docx(package({"word/document.xml": content}))
    assert "&lt;script&gt;" in description and "<script>" not in description
    assert specs[0].value == "5 В"
    assert "Напряжение" in description
    assert not warnings


def test_workbook_group_anchors_collapse_rows_and_omit_contributors() -> None:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    draw = "http://schemas.openxmlformats.org/drawingml/2006"
    files = {
        "xl/workbook.xml": f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'
        '<sheet name="Модуля Ардуино" r:id="s"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="s" '
        'Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{ns}" xmlns:r="{rel}">'
        '<sheetData><row><c r="C1" t="inlineStr"><is><t>Название</t></is></c></row>'
        '<row><c r="C2" t="inlineStr"><is><t>DHT11</t></is></c>'
        '<c r="D2" t="inlineStr"><is><t>PRIVATE PERSON</t></is></c></row>'
        '<row><c r="C3" t="inlineStr"><is><t> DHT11 </t></is></c></row>'
        '</sheetData><drawing r:id="d"/></worksheet>',
        "xl/worksheets/_rels/sheet1.xml.rels": '<Relationships><Relationship Id="d" '
        'Target="../drawings/drawing1.xml"/></Relationships>',
        "xl/drawings/drawing1.xml": f'<x:wsDr xmlns:x="{draw}/spreadsheetDrawing" '
        f'xmlns:a="{draw}/main" xmlns:r="{rel}"><x:oneCellAnchor><x:from>'
        "<x:col>1</x:col><x:row>1</x:row></x:from><x:grpSp><x:pic>"
        '<a:blip r:embed="i"/></x:pic></x:grpSp></x:oneCellAnchor></x:wsDr>',
        "xl/drawings/_rels/drawing1.xml.rels": '<Relationships><Relationship Id="i" '
        'Target="../media/image1.png"/></Relationships>',
        "xl/media/image1.png": b"image bytes",
    }
    with ZipFile(io.BytesIO(package(files))) as archive:
        targets, rows = workbook_targets(archive)
    assert rows == 2 and len(targets) == 1
    assert targets[0].rows == [2, 3]
    assert targets[0].images[0].path == "xl/media/image1.png"
    assert "PRIVATE" not in targets[0].model_dump_json()
