"""Build the acceptance fixtures in data/fixtures from the downloaded public files.

Usage: python scripts/build_fixtures.py <folder with the downloads> data/fixtures
The download URLs, licenses and transformations are listed in data/fixtures/README.md.
Deterministic (fixed seeds), so the fixtures can be rebuilt byte for byte.
"""
import json
import random
import sys
from pathlib import Path

import pandas as pd

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
rng = random.Random(7)

lines = (SRC / "bank-additional-full.csv").read_text(encoding="utf-8").splitlines()
body = rng.sample(lines[1:], 5000)
(OUT / "bank_marketing.csv").write_text("\n".join([lines[0], *body]) + "\n", encoding="utf-8")

(OUT / "german_credit.csv").write_bytes((SRC / "gc.csv").read_bytes())

air = pd.read_csv(SRC / "air.csv", dtype=str)
air = air[air["med_fecha_inicio"] < "2021-04-01"]
air.to_csv(OUT / "air_quality_bucaramanga.csv", index=False)

el = pd.read_csv(SRC / "elections.csv", dtype=str)
el = el[el["stage"] == "general"]
keep = ["cycle", "state_abbrev", "state", "office_name", "party", "candidate_name", "ballot_party", "votes", "percent", "winner"]
el[keep].sample(n=min(3000, len(el)), random_state=7).sort_values(["cycle", "state"]).to_csv(OUT / "us_presidential_results.csv", index=False)

(OUT / "budget_colombia_pgn.csv").write_bytes((SRC / "budget.csv").read_bytes())

x = pd.ExcelFile(SRC / "aw.xlsx")
sales = x.parse("Sales_data")
dates = x.parse("Date_data")[["DateKey", "Date"]].rename(columns={"DateKey": "OrderDateKey", "Date": "Order Date"})
prod = x.parse("Product_data")[["ProductKey", "Product", "Category", "Subcategory", "Color"]]
terr = x.parse("Sales Territory_data")[["SalesTerritoryKey", "Region", "Country"]]
order = x.parse("Sales Order_data")[["SalesOrderLineKey", "Channel", "Sales Order"]]
flat = sales.merge(dates, on="OrderDateKey").merge(prod, on="ProductKey").merge(terr, on="SalesTerritoryKey").merge(order, on="SalesOrderLineKey")
print("sales columns", list(flat.columns))
cols = ["Sales Order", "Order Date", "Channel", "Region", "Country", "Category", "Subcategory", "Product", "Color", "Order Quantity", "Unit Price", "Unit Price Discount Pct", "Sales Amount", "Total Product Cost"]
cols = [c for c in cols if c in flat.columns]
flat = flat[cols].sample(n=3000, random_state=7).sort_values("Order Date")
flat.to_excel(OUT / "sales_adventureworks.xlsx", index=False, sheet_name="Sales")

sp = pd.read_csv(SRC / "sp500.csv", dtype=str)
(OUT / "sp500_companies.json").write_text(json.dumps(sp.to_dict(orient="records"), ensure_ascii=False, indent=1), encoding="utf-8")
for f in sorted(OUT.iterdir()):
    print(f.name, f.stat().st_size)
