"""File detection, header mapping and data-language detection."""

import io
import json

import pandas as pd
import pytest

from app.core.ingest.detect import (
    FileFormat,
    UnsupportedFormatError,
    detect_delimiter,
    detect_encoding,
    detect_format,
    detect_header_row,
    json_records_path,
)
from app.core.ingest.headers_map import map_headers, normalize_header, score_header
from app.core.ingest.language import detect_text, detect_values, dominant
from app.core.ingest.reader import EmptyFileError, read_any


@pytest.mark.parametrize(
    ("name", "head", "fmt"),
    [
        ("a.csv", b"a;b\n1;2\n", FileFormat.CSV),
        ("a.txt", b"a,b\n1,2\n", FileFormat.CSV),
        ("a.json", b'[{"a": 1}]', FileFormat.JSON),
        ("whatever", b'\xef\xbb\xbf  {"rows": []}', FileFormat.JSON),
        ("a.xlsx", b"PK\x03\x04....xl/workbook.xml", FileFormat.XLSX),
        ("a.parquet", b"PAR1....", FileFormat.PARQUET),
    ],
)
def test_detect_format(name: str, head: bytes, fmt: FileFormat) -> None:
    assert detect_format(name, head) == fmt


@pytest.mark.parametrize(
    ("name", "head"),
    [
        ("a.xls", b"\xd0\xcf\x11\xe0rest"),
        ("a.xlsm", b"PK\x03\x04xl/"),
        ("a.zip", b"PK\x03\x04nope"),
        ("a.bin", b"\x00\x01\x02"),
    ],
)
def test_detect_format_rejects(name: str, head: bytes) -> None:
    with pytest.raises(UnsupportedFormatError):
        detect_format(name, head)


@pytest.mark.parametrize(
    ("data", "encoding"),
    [
        ("año;valor\n".encode(), "utf-8"),
        ("año;valor\n".encode("utf-8-sig"), "utf-8-sig"),
        ("año;valor €\n".encode("cp1252"), "cp1252"),
        (b"plain ascii\n", "utf-8"),
        (bytes([0x81, 0x8D, 0x8F, 0x90, 0x9D]), "latin-1"),  # undefined in cp1252
    ],
)
def test_detect_encoding(data: bytes, encoding: str) -> None:
    assert detect_encoding(data) == encoding


@pytest.mark.parametrize(
    ("sample", "delimiter"),
    [
        ("a;b;c\n1;2;3\n4;5;6\n", ";"),
        ("a,b,c\n1,2,3\n", ","),
        ("a\tb\tc\n1\t2\t3\n", "\t"),
        ("a|b\n1|2\n", "|"),
        ('valor;descripcion\n"1.234,56";"uno, dos"\n"7,5";"tres"\n', ";"),  # commas inside values
    ],
)
def test_detect_delimiter(sample: str, delimiter: str) -> None:
    assert detect_delimiter(sample) == delimiter


def test_detect_header_row_skips_title_rows() -> None:
    rows = [
        ["Contracts report 2024", "", ""],
        ["", "", ""],
        ["id", "supplier", "amount"],
        ["1", "ACME", "10"],
    ]
    assert detect_header_row(rows) == 2
    assert detect_header_row([["id", "name"], ["1", "x"]]) == 0


def test_json_records_path() -> None:
    assert json_records_path([{"a": 1}]) == ""
    assert json_records_path({"meta": {}, "releases": [{"a": 1}], "x": [1, 2]}) == "releases"
    assert json_records_path({"a": 1}) is None


def test_read_csv_latin1_semicolon() -> None:
    data = "fecha_de_firma;valor_del_contrato;ciudad\n12/03/2024;1.234,56;Bogotá\n".encode("cp1252")
    df, info = read_any(data, "x.csv")
    assert info.delimiter == ";" and info.encoding == "cp1252"
    assert df.to_dict("records") == [
        {"fecha_de_firma": "12/03/2024", "valor_del_contrato": "1.234,56", "ciudad": "Bogotá"}
    ]


def test_read_xlsx_with_title_row() -> None:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        pd.DataFrame([["Report title"]]).to_excel(xl, index=False, header=False)
        pd.DataFrame({"Vendor name": ["ACME"], "Contract value": ["10.5"]}).to_excel(
            xl, index=False, startrow=2
        )
    df, info = read_any(buf.getvalue(), "x.xlsx")
    assert info.header_row == 2
    assert list(df.columns) == ["Vendor name", "Contract value"]


def test_read_nested_json() -> None:
    data = json.dumps(
        {"contrats": [{"id": 1, "fournisseur": {"nom": "ABC"}, "tags": ["a"]}]}
    ).encode()
    df, info = read_any(data, "x.json")
    assert info.records_path == "contrats"
    assert df.iloc[0]["fournisseur.nom"] == "ABC"
    assert df.iloc[0]["tags"] == '["a"]'


@pytest.mark.parametrize("data", [b"", b"   \n", b"[]"])
def test_read_empty(data: bytes) -> None:
    with pytest.raises(EmptyFileError):
        read_any(data, "x.json")


@pytest.mark.parametrize(
    ("header", "field"),
    [
        ("fecha_de_firma", "signed_date"),
        ("Fecha de Firma", "signed_date"),
        ("date_signature", "signed_date"),
        ("Contract date / Date du contrat", "signed_date"),
        ("valor_del_contrato", "amount_original"),
        ("Contract value / Valeur du contrat", "amount_original"),
        ("contrat_montant", "amount_original"),
        ("moneda", "currency"),
        ("devise", "currency"),
        ("proveedor_adjudicado", "supplier_name"),
        ("fournisseur.nom", "supplier_name"),
        ("Vendor name / Nom du fournisseur", "supplier_name"),
        ("nombre_entidad", "entity_name"),
        ("acheteur.nom", "entity_name"),
        ("modalidad_de_contratacion", "award_type"),
        ("number_of_bids", "n_bidders"),
    ],
)
def test_header_mapping(header: str, field: str) -> None:
    [match] = map_headers([header])
    assert match.canonical_field == field
    assert match.confidence >= 0.8 and not match.needs_check


def test_header_mapping_is_one_to_one() -> None:
    matches = {
        m.source_header: m.canonical_field
        for m in map_headers(["description_en", "description_fr"])
    }
    assert matches == {"description_en": "description", "description_fr": None}


def test_fuzzy_header_is_flagged_for_check() -> None:
    [match] = map_headers(["valor_contratado"])
    assert match.canonical_field == "amount_original"
    assert match.needs_check
    assert "amount_original" in match.candidates


def test_unknown_header_stays_unmapped() -> None:
    [match] = map_headers(["release_tag"])
    assert match.canonical_field is None
    assert score_header("release_tag")[0][0] < 0.72
    assert map_headers(["monto_adjudicado"])[0].canonical_field == "amount_original"


def test_normalize_header() -> None:
    assert normalize_header("  Fecha de Firma (dd/mm) ") == "fecha_de_firma_dd_mm"
    assert normalize_header("Ministère") == "ministere"


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Prestación de servicios profesionales para el apoyo a la gestión", "es"),
        ("Services professionnels de communications non spécifiés ailleurs", "fr"),
        ("Other professional services not elsewhere specified", "en"),
        ("Contrat de gré à gré pour l'entretien des bâtiments", "fr"),
        ("Suministro de equipos para la adquisición de obra", "es"),
        ("12345", None),
        ("ok", None),
    ],
)
def test_detect_text(text: str, lang) -> None:
    result = detect_text(text)
    assert (result.value if result else None) == lang


def test_detect_values_and_dominant() -> None:
    shares = detect_values(
        ["Servicios de apoyo a la gestión"] * 9 + ["Services for the department"]
    )
    assert shares["es"] == 0.9
    assert dominant(shares) == "es"
    assert dominant({"en": 0.5, "fr": 0.5}) == "mixed"
    assert dominant({}) == "unknown"
    assert detect_values(["123", "456", "2024-01-01"]) == {}
