#!/usr/bin/env python3
"""Focused regression tests for the Downs Style archive analysis helpers."""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    voice = runpy.run_path(str(ROOT / "scripts/analyze-downs-style-voice.py"))
    phrase_count = voice["phrase_count"]
    assert phrase_count("i love it; i loved it; i lovely", "i love") == 1
    assert phrase_count("i loved it", "i loved") == 1
    assert voice["contains_key"]({"safe": [{"body": "private"}]}, "body")
    assert not voice["contains_key"]({"body_blocks": 2}, "body")

    bs4 = types.ModuleType("bs4")
    bs4.BeautifulSoup = object
    sys.modules["bs4"] = bs4
    audit = runpy.run_path(str(ROOT / "scripts/audit-downs-style-archive.py"))
    collections = audit["collections_to_audit"](
        ["https://www.downsstyle.com/homepage-only/2026/8/3/example"]
    )
    assert "homepage-only" in collections
    assert set(audit["COLLECTION_LABELS"]) <= set(collections)

    requirements = (
        ROOT / "scripts/requirements-downs-style-archive.txt"
    ).read_text(encoding="utf-8")
    assert "beautifulsoup4" in requirements
    print("downs-style analysis regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
