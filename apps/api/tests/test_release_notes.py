"""scripts/release_notes.py: the GitHub Release body is exactly one CHANGELOG section."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "scripts" / "release_notes.py"
)
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)


def test_extracts_one_version_section() -> None:
    text = (
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [1.0.0] — 2026-11-03\nfirst\n### Added\n- a\n\n## [0.9.0]\nold\n"
    )
    assert release_notes.section(text, "1.0.0") == "first\n### Added\n- a\n"
    with pytest.raises(SystemExit, match=r"no '## \[2.0.0\]'"):
        release_notes.section(text, "2.0.0")


def test_the_real_changelog_has_v1() -> None:
    notes = release_notes.section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), "1.0.0")
    assert "First public release" in notes and "## [" not in notes
