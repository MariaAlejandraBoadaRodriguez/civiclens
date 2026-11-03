"""Deterministically inject documented data-quality issues into the seed samples.

The demo ("Try with sample data") files are the seed Parquet files passed through these
functions and written in each jurisdiction's original format (CSV, XLSX, JSON), so the
ingest path is exercised exactly like an upload and the Cleaning Studio always shows the
same issues. Same seed Parquet + same ``SEED`` → byte-identical output.

Every injected issue is counted in the returned manifest (shown in data/seed/README.md).
Synthetic personal data uses reserved example domains / fictitious numbers only.
"""

from __future__ import annotations

import io
import json
import random
import re
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from app.core.ingest.locale_parse import strip_accents

SEED = 20261028
Manifest = dict[str, int]


@dataclass
class DirtyResult:
    data: bytes
    filename: str
    manifest: Manifest = field(default_factory=dict)


def _pick(
    rng: random.Random, n_rows: int, share: float, exclude: set[int] | None = None
) -> list[int]:
    pool = [i for i in range(n_rows) if not exclude or i not in exclude]
    k = min(len(pool), round(n_rows * share))
    return sorted(rng.sample(pool, k))


def _fmt_es(x: float) -> str:  # 1.234.567,89
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt_en(x: float) -> str:  # 1,234,567.89
    return f"{x:,.2f}"


def _fmt_fr(x: float) -> str:  # 1 234 567,89 (narrow no-break space)
    return f"{x:,.2f}".replace(",", "\u202f").replace(".", ",")


def _variant(rng: random.Random, name: str) -> str:
    """Case / accent / spacing variant of an entity or supplier name."""
    choice = rng.randrange(4)
    if choice == 0:
        return name.upper()
    if choice == 1:
        return strip_accents(name)
    if choice == 2:
        return f" {name}  "
    return name.title()


def _to_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _duplicates(
    df: pd.DataFrame,
    rng: random.Random,
    exact: float,
    near: float,
    tweak: Callable[[pd.DataFrame], pd.DataFrame],
    m: Counter,
) -> pd.DataFrame:
    exact_rows = df.iloc[_pick(rng, len(df), exact)]
    near_rows = tweak(df.iloc[_pick(rng, len(df), near)].copy())
    m["duplicates_exact"] += len(exact_rows)
    m["duplicates_near"] += len(near_rows)
    out = pd.concat([df, exact_rows, near_rows], ignore_index=True)
    order = list(range(len(out)))
    rng.shuffle(order)
    return out.iloc[order].reset_index(drop=True)


# --------------------------------------------------------------------------- Colombia


def dirty_secop(seed: pd.DataFrame) -> DirtyResult:
    """CSV, ';' delimiter, Windows-1252, Spanish number notation."""
    rng = random.Random(SEED)
    m: Counter = Counter()
    df = seed.copy().astype(object)
    n = len(df)
    amount = df["valor_del_contrato"].map(_to_float)

    # Mixed currencies: a few contracts reported in USD / CAD (amount converted back).
    currency = ["COP"] * n
    usd = _pick(rng, n, 0.0165)
    cad = _pick(rng, n, 0.0035, exclude=set(usd))
    for i in usd:
        currency[i] = "USD"
        amount.iat[i] = round((amount.iat[i] or 0) / 4000, 2)
    for i in cad:
        currency[i] = "CAD"
        amount.iat[i] = round((amount.iat[i] or 0) / 2950, 2)
    df.insert(df.columns.get_loc("valor_del_contrato") + 1, "moneda", currency)
    m["currency_usd"], m["currency_cad"] = len(usd), len(cad)

    # Outliers: amount × 1000 (typo of thousands separator).
    for i in _pick(rng, n, 0.0006):
        amount.iat[i] = (amount.iat[i] or 0) * 1000
        m["outliers"] += 1

    # Number notation: Spanish for most, English for some.
    en_rows = set(_pick(rng, n, 0.12))
    m["number_locale_en"] = len(en_rows)
    df["valor_del_contrato"] = [
        None if a is None else (_fmt_en(a) if i in en_rows else _fmt_es(a))
        for i, a in enumerate(amount)
    ]

    # Date formats on fecha_de_firma: ISO (as published), dd/mm/yyyy and mm/dd/yyyy.
    signed = pd.to_datetime(df["fecha_de_firma"], errors="coerce")
    dmy = set(_pick(rng, n, 0.30))
    mdy = set(_pick(rng, n, 0.06, exclude=dmy))
    out = []
    for i, (raw, ts) in enumerate(zip(df["fecha_de_firma"], signed, strict=True)):
        if pd.isna(ts):
            out.append(raw)
        elif i in dmy:
            out.append(ts.strftime("%d/%m/%Y"))
        elif i in mdy:
            out.append(ts.strftime("%m/%d/%Y"))
        else:
            out.append(raw)
    df["fecha_de_firma"] = out
    m["date_format_dmy"], m["date_format_mdy"] = len(dmy), len(mdy)

    # Coded nulls.
    tokens = ["N/A", "-", "sin dato", "No Definido", ""]
    for col in ("ciudad", "destino_gasto", "origen_de_los_recursos"):
        for i in _pick(rng, n, 0.03):
            df.at[i, col] = tokens[rng.randrange(len(tokens))]
            m["null_tokens"] += 1

    # Entity / supplier name variants.
    for col in ("nombre_entidad", "proveedor_adjudicado"):
        for i in _pick(rng, n, 0.04):
            df.at[i, col] = _variant(rng, str(df.at[i, col]))
            m["name_variants"] += 1

    # Synthetic contact data (PII demo) — reserved example domain, fictitious numbers.
    email = [None] * n
    phone = [None] * n
    for i in _pick(rng, n, 0.35):
        email[i] = f"contacto{i:05d}@example.org"
        phone[i] = f"+57 300 555 {i % 10000:04d}"
    df["email_contacto"] = email
    df["telefono_contacto"] = phone
    m["pii_synthetic_columns"] = 2

    def tweak(rows: pd.DataFrame) -> pd.DataFrame:
        rows["proveedor_adjudicado"] = rows["proveedor_adjudicado"].map(lambda s: str(s).upper())
        return rows

    df = _duplicates(df, rng, 0.012, 0.004, tweak, m)
    # A header as it comes out of a portal export: matched only fuzzily → "check" in the UI.
    df = df.rename(columns={"modalidad_de_contratacion": "Modalidad de Contratación (SECOP)"})
    m["fuzzy_headers"] = 1
    buf = io.StringIO()
    df.to_csv(buf, sep=";", index=False)
    return DirtyResult(buf.getvalue().encode("cp1252", errors="replace"), "secop_co.csv", dict(m))


# --------------------------------------------------------------------------- Canada

CA_ROWS = 10_000
CA_BILINGUAL = {
    "vendor_name": "Vendor name / Nom du fournisseur",
    "contract_date": "Contract date / Date du contrat",
    "contract_value": "Contract value / Valeur du contrat",
    "owner_org_title": "Department / Ministère",
}


def dirty_canada(seed: pd.DataFrame) -> DirtyResult:
    """XLSX with a title row, bilingual headers, mixed notations. 10k rows (XLSX is slow)."""
    rng = random.Random(SEED + 1)
    m: Counter = Counter()
    df = (
        seed.iloc[sorted(rng.sample(range(len(seed)), min(CA_ROWS, len(seed))))]
        .copy()
        .astype(object)
    )
    df = df.reset_index(drop=True)
    n = len(df)
    amount = df["contract_value"].map(_to_float)

    currency = ["CAD"] * n
    usd = _pick(rng, n, 0.02)
    for i in usd:
        currency[i] = "USD"
        amount.iat[i] = round((amount.iat[i] or 0) / 1.37, 2)
    df.insert(df.columns.get_loc("contract_value") + 1, "currency", currency)
    m["currency_usd"] = len(usd)

    fr_rows = set(_pick(rng, n, 0.15))
    df["contract_value"] = [
        None if a is None else (_fmt_fr(a) if i in fr_rows else f"{a:.2f}")
        for i, a in enumerate(amount)
    ]
    m["number_locale_fr"] = len(fr_rows)

    dates = pd.to_datetime(df["contract_date"], errors="coerce")
    slashed = set(_pick(rng, n, 0.10))
    df["contract_date"] = [
        ts.strftime("%m/%d/%Y") if i in slashed and not pd.isna(ts) else raw
        for i, (raw, ts) in enumerate(zip(df["contract_date"], dates, strict=True))
    ]
    m["date_format_mdy"] = len(slashed)

    for i in _pick(rng, n, 0.04):
        df.at[i, "number_of_bids"] = ["N/A", "non disponible", "-"][rng.randrange(3)]
        m["null_tokens"] += 1
    for i in _pick(rng, n, 0.03):
        df.at[i, "vendor_name"] = _variant(rng, str(df.at[i, "vendor_name"]))
        m["name_variants"] += 1

    df = _duplicates(df, rng, 0.01, 0.003, lambda r: r, m)
    df = df.rename(columns=CA_BILINGUAL)
    m["bilingual_headers"] = len(CA_BILINGUAL)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        pd.DataFrame(
            [["Proactive Publication - Contracts / Publication proactive - Contrats"]]
        ).to_excel(xl, sheet_name="contracts", index=False, header=False)
        df.to_excel(xl, sheet_name="contracts", index=False, startrow=2)
    m["title_rows"] = 2
    return DirtyResult(_freeze_zip(buf.getvalue()), "contracts_ca.xlsx", dict(m))


_FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def _freeze_zip(data: bytes) -> bytes:
    """Rewrite an XLSX (zip) with fixed timestamps so the output is byte-identical."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            payload = src.read(item.filename)
            if item.filename == "docProps/core.xml":
                payload = re.sub(
                    rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", b"2026-01-01T00:00:00Z", payload
                )
            info = zipfile.ZipInfo(item.filename, date_time=_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, payload)
    return out.getvalue()


# --------------------------------------------------------------------------- Québec

QC_ROWS = 20_000
_BUYER = ("acheteur_nom", "acheteur_id", "acheteur_ville", "acheteur_region")
_SUPPLIER = (
    "fournisseur_nom",
    "fournisseur_id",
    "fournisseur_neq",
    "fournisseur_ville",
    "fournisseur_region",
    "fournisseur_pays",
)


def dirty_quebec(seed: pd.DataFrame) -> DirtyResult:
    """Nested JSON records (acheteur.*, fournisseur.*), French notations, coded nulls."""
    rng = random.Random(SEED + 2)
    m: Counter = Counter()
    df = (
        seed.iloc[sorted(rng.sample(range(len(seed)), min(QC_ROWS, len(seed))))]
        .copy()
        .astype(object)
    )
    df = df.reset_index(drop=True)
    n = len(df)

    fr_rows = set(_pick(rng, n, 0.30))
    df["contrat_montant"] = [
        None if (a := _to_float(v)) is None else (_fmt_fr(a) if i in fr_rows else a)
        for i, v in enumerate(df["contrat_montant"])
    ]
    m["number_locale_fr"] = len(fr_rows)

    dates = pd.to_datetime(df["date_signature"], errors="coerce", utc=True)
    dmy = set(_pick(rng, n, 0.15))
    df["date_signature"] = [
        ts.strftime("%d/%m/%Y") if i in dmy and not pd.isna(ts) else raw
        for i, (raw, ts) in enumerate(zip(df["date_signature"], dates, strict=True))
    ]
    m["date_format_dmy"] = len(dmy)
    m["time_zone_offsets"] = int(
        df["date_signature"].astype(str).str.contains(r"[+-]\d\d:\d\d$").sum()
    )

    for i in _pick(rng, n, 0.03):
        df.at[i, "fournisseur_ville"] = ["non disponible", "N/D", "-"][rng.randrange(3)]
        m["null_tokens"] += 1
    for i in _pick(rng, n, 0.04):
        df.at[i, "acheteur_nom"] = _variant(rng, str(df.at[i, "acheteur_nom"]))
        m["name_variants"] += 1
    for i in _pick(rng, n, 0.0005):
        if isinstance(df.at[i, "contrat_montant"], float):
            df.at[i, "contrat_montant"] *= 1000
            m["outliers"] += 1

    df = _duplicates(df, rng, 0.01, 0.0, lambda r: r, m)

    def record(row: dict) -> dict:
        rec = {k: v for k, v in row.items() if k not in _BUYER + _SUPPLIER}
        rec["acheteur"] = {k.split("_", 1)[1]: row[k] for k in _BUYER}
        rec["fournisseur"] = {k.split("_", 1)[1]: row[k] for k in _SUPPLIER}
        return rec

    records = [record(r) for r in df.where(df.notna(), None).to_dict(orient="records")]
    payload = {
        "source": "SEAO (sample, CivicLens demo)",
        "license": "CC BY 4.0",
        "contrats": records,
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    m["nested_objects"] = 2
    return DirtyResult(data, "contracts_qc.json", dict(m))


DIRTY_BUILDERS: dict[str, Callable[[pd.DataFrame], DirtyResult]] = {
    "secop_co": dirty_secop,
    "contracts_ca": dirty_canada,
    "contracts_qc": dirty_quebec,
}
