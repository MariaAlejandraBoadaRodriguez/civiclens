"""Write the deterministic "dirty" demo versions of the seed datasets.

The API builds the same files on first use (app/core/seed/dirty.py); this CLI is for
inspecting them or using them as upload test files.

Usage (from the repo root, API dependencies installed):
    python scripts/make_dirty.py [--out data/demo] [secop_co contracts_ca contracts_qc]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

import pandas as pd  # noqa: E402
from app.core.seed.dirty import DIRTY_BUILDERS, SEED  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "demo")
    parser.add_argument("slugs", nargs="*", default=sorted(DIRTY_BUILDERS))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    manifests = {}
    for slug in args.slugs:
        result = DIRTY_BUILDERS[slug](pd.read_parquet(ROOT / "data" / "seed" / f"{slug}.parquet"))
        (args.out / result.filename).write_bytes(result.data)
        manifests[slug] = {"file": result.filename, "seed": SEED, "issues": result.manifest}
        print(f"{slug}: {result.filename} ({len(result.data) / 1e6:.1f} MB) {result.manifest}")
    (args.out / "manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
