"""Print the CHANGELOG.md section of one version (used by .github/workflows/release.yml).

Usage: python scripts/release_notes.py 1.0.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(text: str, version: str) -> str:
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if not match:
        raise SystemExit(f"CHANGELOG.md has no '## [{version}]' section")
    return match.group(1).strip() + "\n"


if __name__ == "__main__":
    print(section(CHANGELOG.read_text(encoding="utf-8"), sys.argv[1]), end="")
