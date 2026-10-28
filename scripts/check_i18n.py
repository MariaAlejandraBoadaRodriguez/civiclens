"""Fail if the EN and ES catalogs differ in keys or in placeholders.

Checks both catalog families (ADR-0007):
- web UI strings: apps/web/messages/{en,es}.json
- API domain text: apps/api/app/i18n/{en,es}/*.yaml (needs PyYAML)

Usage: python scripts/check_i18n.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "apps" / "web" / "messages"
API_DIR = ROOT / "apps" / "api" / "app" / "i18n"
LOCALES = ("en", "es")
PLACEHOLDER = re.compile(r"\{(\w+)")


def flatten(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def web_catalogs() -> dict[str, dict[str, str]]:
    return {
        loc: flatten(json.loads((WEB_DIR / f"{loc}.json").read_text(encoding="utf-8")))
        for loc in LOCALES
    }


def api_catalogs() -> dict[str, dict[str, str]]:
    import yaml

    out: dict[str, dict[str, str]] = {}
    for loc in LOCALES:
        entries: dict[str, str] = {}
        for path in sorted((API_DIR / loc).glob("*.yaml")):
            entries.update(
                flatten(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, path.stem)
            )
        out[loc] = entries
    return out


def compare(name: str, catalogs: dict[str, dict[str, str]]) -> list[str]:
    errors = []
    for loc in LOCALES:
        for other in LOCALES:
            if loc != other:
                missing = sorted(set(catalogs[other]) - set(catalogs[loc]))
                errors += [f"{name} [{loc}] missing key: {k}" for k in missing]
    base = catalogs[LOCALES[0]]
    for loc in LOCALES[1:]:
        for key in sorted(set(base) & set(catalogs[loc])):
            a = set(PLACEHOLDER.findall(str(base[key])))
            b = set(PLACEHOLDER.findall(str(catalogs[loc][key])))
            if a != b:
                errors.append(
                    f"{name} [{loc}] placeholders differ for {key}: {sorted(a)} vs {sorted(b)}"
                )
    for loc, entries in catalogs.items():
        errors += [
            f"{name} [{loc}] empty value: {k}" for k, v in entries.items() if not str(v).strip()
        ]
    return errors


def main() -> int:
    web = web_catalogs()
    try:
        api = api_catalogs()
    except ImportError:
        print("PyYAML is required for the API catalogs: pip install pyyaml")
        return 1
    errors = compare("web", web) + compare("api", api)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"i18n OK: web {len(web['en'])} keys, api {len(api['en'])} keys in {', '.join(LOCALES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
