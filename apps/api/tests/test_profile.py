"""Profiler, quality score, PII scan and the deterministic dirty demo data."""

import pandas as pd
import pytest

from app.config import settings
from app.core.ingest.reader import read_any
from app.core.profile.pii import PiiKind, detect_pii, mask_value
from app.core.profile.profiler import profile_frame
from app.core.seed.dirty import DIRTY_BUILDERS


def frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols, dtype=object)


def test_profile_detects_types_and_notations() -> None:
    df = frame(
        fecha_de_firma=["12/03/2024", "2024-03-13", "25/03/2024", "N/A"],
        valor_del_contrato=["1.234,56", "2.000,00", "1,500.00", "3.000,00"],
        moneda=["COP", "COP", "USD", "XXX"],
        proveedor=["ACME S.A.S.", "acme s.a.s.", "Beta", "ACME S.A.S."],
    )
    p = profile_frame(df)
    cols = {c["source_header"]: c for c in p["columns_profile"]}
    assert cols["fecha_de_firma"]["canonical_field"] == "signed_date"
    assert cols["fecha_de_firma"]["inferred_type"] == "date"
    assert cols["fecha_de_firma"]["null_ratio"] == 0.25
    assert cols["fecha_de_firma"]["null_tokens"] == {"N/A": 1}
    assert cols["valor_del_contrato"]["inferred_type"] == "number"
    assert cols["valor_del_contrato"]["notations"] == {"comma": 3, "point": 1}
    assert cols["valor_del_contrato"]["consistency"] == 0.75
    assert cols["moneda"]["validity"] == 0.75  # XXX is not an ISO code we know
    assert cols["proveedor"]["consistency"] == 0.75  # "acme s.a.s." is a case variant
    q = p["quality"]
    assert set(q) == {"score", "completeness", "uniqueness", "validity", "consistency"}
    assert q["score"] == round(
        (q["completeness"] + q["uniqueness"] + q["validity"] + q["consistency"]) / 4
    )
    assert q["consistency"] < 100 and q["validity"] < 100


def test_profile_counts_duplicates() -> None:
    df = frame(id_contrato=["1", "1", "2"], proveedor=["A", "A", "B"])
    p = profile_frame(df)
    assert p["duplicate_rows"] == 1
    assert p["quality"]["uniqueness"] == 67


def test_profile_is_deterministic() -> None:
    df = frame(a=["x", "y", "x"], fecha=["01/02/2024", "2024-02-01", "N/A"])
    assert profile_frame(df) == profile_frame(df.copy())


@pytest.mark.parametrize(
    ("header", "values", "kind"),
    [
        ("contacto", ["ana@example.org", "luis@example.com", None], PiiKind.EMAIL),
        ("telefono", ["+57 300 555 0101", "(613) 555-0199"], PiiKind.PHONE),
        ("cedula", ["1020304050", "52123456"], PiiKind.NATIONAL_ID),
        ("nombre_representante_legal", ["Ana Pérez"], PiiKind.PERSON_NAME),
        ("fecha", ["2024-03-12", "2024-03-13"], None),  # dates are not phones
        ("release_id", ["20260930214050", "20260930214051"], None),  # bare digit runs are ids
        ("proveedor", ["ACME"], None),
    ],
)
def test_detect_pii(header: str, values: list, kind) -> None:
    assert detect_pii(header, values) == kind


def test_mask_value_is_stable_and_irreversible() -> None:
    assert mask_value("ana@example.org") == mask_value("ana@example.org")
    assert mask_value("ana@example.org") != mask_value("luis@example.org")
    assert "ana" not in mask_value("ana@example.org")
    assert mask_value(None) is None


@pytest.mark.parametrize("slug", sorted(DIRTY_BUILDERS))
def test_dirty_builders_are_deterministic_and_readable(slug: str) -> None:
    seed = pd.read_parquet(settings.seed_dir / f"{slug}.parquet").head(1500)
    first, second = DIRTY_BUILDERS[slug](seed), DIRTY_BUILDERS[slug](seed)
    assert first.data == second.data
    assert first.manifest == second.manifest and first.manifest
    df, info = read_any(first.data, first.filename)
    assert info.format == first.filename.rsplit(".", 1)[1]
    p = profile_frame(df)
    mapped = {c["canonical_field"] for c in p["columns_profile"]}
    assert {"signed_date", "amount_original", "supplier_name", "entity_name"} <= mapped
    assert p["quality"]["consistency"] < 100  # issues were injected
