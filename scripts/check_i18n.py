"""Fail if the EN and ES UI catalogs do not have exactly the same keys.

Usage: python scripts/check_i18n.py
"""

import json
import sys
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent.parent / "apps" / "web" / "messages"
LOCALES = ("en", "es")


def flatten(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def main() -> int:
    catalogs = {
        loc: flatten(json.loads((CATALOG_DIR / f"{loc}.json").read_text(encoding="utf-8")))
        for loc in LOCALES
    }
    errors = []
    for loc in LOCALES:
        for other in LOCALES:
            if loc == other:
                continue
            missing = sorted(set(catalogs[other]) - set(catalogs[loc]))
            errors += [f"[{loc}] missing key: {k}" for k in missing]
    for loc, entries in catalogs.items():
        errors += [f"[{loc}] empty value: {k}" for k, v in entries.items() if not str(v).strip()]

    if errors:
        print("\n".join(errors))
        return 1
    print(f"i18n OK: {len(catalogs['en'])} keys in {', '.join(LOCALES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
