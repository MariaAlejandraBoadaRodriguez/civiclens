"""Build data/fx_rates.csv: monthly CAD value of one unit of COP, USD and CAD.

Sources
- COP per USD: official TRM (Tasa Representativa del Mercado), Superintendencia
  Financiera de Colombia, published on datos.gov.co (dataset 32sa-8pi3, CC BY-SA 4.0).
  Monthly value = mean of the daily TRM published in that month.
- CAD per USD, in this order:
  1. Bank of Canada monthly average (series FXMUSDCAD, Valet API), or ``--boc-csv`` with the
     CSV downloaded by hand from https://www.bankofcanada.ca/valet/observations/FXMUSDCAD/csv ;
  2. Federal Reserve monthly average (H.10, FRED series EXCAUS, public domain), read from
     the Open Knowledge "datasets/exchange-rates" mirror (country = Canada).
  There is no approximate fallback: the script fails rather than write invented rates.

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

FRED_URL = "https://raw.githubusercontent.com/datasets/exchange-rates/main/data/monthly.csv"
FRED_SOURCE = "Federal Reserve H.10 monthly average (FRED EXCAUS)"


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


def fred_monthly(text: str) -> dict[str, float]:
    """CAD per USD by month from the datasets/exchange-rates mirror of FRED (EXCAUS)."""
    return {
        row["Date"][:7]: float(row["Exchange rate"])
        for row in csv.DictReader(io.StringIO(text))
        if row["Country"] == "Canada" and row["Exchange rate"]
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boc-csv", type=Path)
    parser.add_argument("--start", default="2015-01")
    args = parser.parse_args(argv)

    trm = trm_monthly(args.start)
    usdcad: dict[str, float] = {}
    source = BOC_SOURCE
    if args.boc_csv:
        usdcad = boc_monthly(args.boc_csv.read_text(encoding="utf-8"))
    else:
        try:
            r = requests.get(BOC_URL, timeout=60)
            r.raise_for_status()
            usdcad = boc_monthly(r.text)
        except requests.RequestException as exc:
            print(f"Bank of Canada unreachable ({exc.__class__.__name__}); trying FRED")
    if not usdcad:
        r = requests.get(FRED_URL, timeout=120)
        r.raise_for_status()
        usdcad, source = fred_monthly(r.text), FRED_SOURCE

    rows = []
    missing = []
    for month, cop_per_usd in trm.items():
        rate = usdcad.get(month)
        if rate is None:
            missing.append(month)
            continue
        rows.append((month, "CAD", 1.0, "identity"))
        rows.append((month, "USD", rate, source))
        rows.append((month, "COP", round(rate / cop_per_usd, 8), f"{TRM_SOURCE} × {source}"))
    if missing:  # e.g. the current month, not yet published as a monthly average
        print(f"no USD/CAD monthly average yet for {', '.join(missing)}: left out")
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "currency", "cad_per_unit", "source"])
        w.writerows(rows)
    span = f"{rows[0][0]} … {rows[-1][0]}"
    print(f"wrote {len(rows)} rows ({span}) → {OUT.relative_to(ROOT)} · pulled {date.today()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
