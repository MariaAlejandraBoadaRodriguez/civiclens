"""Build data/fx_rates.csv: monthly CAD value of one unit of COP, USD and CAD.

Sources
- COP per USD: official TRM (Tasa Representativa del Mercado), Superintendencia
  Financiera de Colombia, published on datos.gov.co (dataset 32sa-8pi3, CC BY-SA 4.0).
  Monthly value = mean of the daily TRM published in that month.
- CAD per USD: Bank of Canada monthly average (series FXMUSDCAD, Valet API). If the
  Valet API is unreachable, ``--boc-csv`` accepts the CSV downloaded by hand from
  https://www.bankofcanada.ca/valet/observations/FXMUSDCAD/csv ; as a last resort the
  script uses APPROX_USDCAD (annual averages, marked ``approximate`` in the source column).

Usage: python scripts/fetch_fx.py [--boc-csv path] [--start 2015-01]
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fx_rates.csv"
TRM_URL = "https://www.datos.gov.co/resource/32sa-8pi3.csv"
BOC_URL = "https://www.bankofcanada.ca/valet/observations/FXMUSDCAD/csv"
TRM_SOURCE = "TRM, Superfinanciera de Colombia (datos.gov.co 32sa-8pi3)"
BOC_SOURCE = "Bank of Canada FXMUSDCAD monthly average"

# Approximate annual averages of CAD per USD — ONLY a fallback; replace with Bank of Canada data.
APPROX_SOURCE = "approximate annual average (replace with Bank of Canada FXMUSDCAD)"
APPROX_USDCAD = {
    2015: 1.279,
    2016: 1.325,
    2017: 1.298,
    2018: 1.296,
    2019: 1.327,
    2020: 1.341,
    2021: 1.254,
    2022: 1.301,
    2023: 1.350,
    2024: 1.370,
    2025: 1.395,
    2026: 1.380,
}


def trm_monthly(start: str) -> dict[str, float]:
    params = {
        "$select": "valor,vigenciadesde",
        "$where": f"vigenciadesde >= '{start}-01'",
        "$limit": 50000,
    }
    r = requests.get(TRM_URL, params=params, timeout=120)
    r.raise_for_status()
    sums: dict[str, list[float]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(r.text)):
        sums[row["vigenciadesde"][:7]].append(float(row["valor"]))
    return {m: round(sum(v) / len(v), 4) for m, v in sorted(sums.items())}


def boc_monthly(text: str) -> dict[str, float]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip('"').startswith("date"))
    out = {}
    for row in csv.DictReader(lines[start:]):
        if row.get("FXMUSDCAD"):
            out[row["date"][:7]] = float(row["FXMUSDCAD"])
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boc-csv", type=Path)
    parser.add_argument("--start", default="2015-01")
    args = parser.parse_args(argv)

    trm = trm_monthly(args.start)
    usdcad: dict[str, float] = {}
    boc_source = BOC_SOURCE
    if args.boc_csv:
        usdcad = boc_monthly(args.boc_csv.read_text(encoding="utf-8"))
    else:
        try:
            r = requests.get(BOC_URL, timeout=60)
            r.raise_for_status()
            usdcad = boc_monthly(r.text)
        except requests.RequestException as exc:
            print(f"Bank of Canada unreachable ({exc.__class__.__name__}); using APPROX_USDCAD")
    if not usdcad:
        boc_source = APPROX_SOURCE

    rows = []
    for month, cop_per_usd in trm.items():
        year = int(month[:4])
        rate = usdcad.get(month) or APPROX_USDCAD.get(year)
        if rate is None:
            continue
        src = boc_source if month in usdcad else APPROX_SOURCE
        rows.append((month, "CAD", 1.0, "identity"))
        rows.append((month, "USD", rate, src))
        rows.append((month, "COP", round(rate / cop_per_usd, 8), f"{TRM_SOURCE} × {src}"))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "currency", "cad_per_unit", "source"])
        w.writerows(rows)
    span = f"{rows[0][0]} … {rows[-1][0]}"
    print(f"wrote {len(rows)} rows ({span}) → {OUT.relative_to(ROOT)} · pulled {date.today()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
