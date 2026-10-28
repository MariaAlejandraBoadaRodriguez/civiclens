"""Fail if the EN and ES UI catalogs differ in keys or in ICU placeholders.

Usage: python scripts/check_i18n.py
"""

import json
import re
import sys
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent.parent / "apps" / "web" / "messages"
LOCALES = ("en", "es")
PLACEHOLDER = re.compile(r"\{(\w+)")


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
    base = catalogs[LOCALES[0]]
    for loc in LOCALES[1:]:
        for key in sorted(set(base) & set(catalogs[loc])):
            a = set(PLACEHOLDER.findall(str(base[key])))
            b = set(PLACEHOLDER.findall(str(catalogs[loc][key])))
            if a != b:
                errors.append(f"[{loc}] placeholders differ for {key}: {sorted(a)} vs {sorted(b)}")
    for loc, entries in catalogs.items():
        errors += [f"[{loc}] empty value: {k}" for k, v in entries.items() if not str(v).strip()]

    if errors:
        print("\n".join(errors))
        return 1
    print(f"i18n OK: {len(catalogs['en'])} keys in {', '.join(LOCALES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
