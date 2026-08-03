#!/usr/bin/env python3
"""Focused regression tests for the Downs Style archive analysis helpers."""

from __future__ import annotations

import runpy
import sys
import tempfile
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
    summarize = voice["summarize"]
    posts = [
        {
            "published_date": "2018-01-01",
            "category": "Look Book",
            "title": "The 5 next outfits for my next vacation",
            "url": "https://example.test/post",
            "body": "I love it.",
        }
    ]
    assert summarize(posts)["structural_post_counts"]["first_person_title"] == 1

    verifier = runpy.run_path(str(ROOT / "scripts/verify-downs-style-archive.py"))
    normalized_text_sha256 = verifier["normalized_text_sha256"]
    ledger_site_projection = verifier["ledger_site_projection"]
    site_projection_matches = verifier["site_projection_matches"]
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        lf_path = temporary / "ledger-lf.csv"
        crlf_path = temporary / "ledger-crlf.csv"
        lf_path.write_bytes(b"title,url\nOne,https://example.test\n")
        crlf_path.write_bytes(b"title,url\r\nOne,https://example.test\r\n")
        assert normalized_text_sha256(lf_path) == normalized_text_sha256(crlf_path)
    record = {
        "published_date": "2018-01-02T00:00:00Z",
        "category": "Look Book",
        "title": "My title",
        "url": "https://example.test/post",
        "author": "Chas Downs",
        "word_count": "42",
    }
    projection = ledger_site_projection(record)
    assert projection == {
        "publishedDate": "2018-01-02",
        "year": "2018",
        "category": "Look Book",
        "title": "My title",
        "url": "https://example.test/post",
        "author": "Chas Downs",
        "wordCount": 42,
    }
    assert set(projection) == {
        "publishedDate",
        "year",
        "category",
        "title",
        "url",
        "author",
        "wordCount",
    }
    assert site_projection_matches([record], [projection])
    stale_values = {
        "publishedDate": "2018-01-03",
        "year": "2019",
        "category": "Skincare",
        "title": "Stale title",
        "url": "https://example.test/stale",
        "author": "Someone Else",
        "wordCount": 41,
    }
    for field, stale_value in stale_values.items():
        assert not site_projection_matches(
            [record],
            [{**projection, field: stale_value}],
        )
    assert not site_projection_matches([record], [{**projection, "extra": True}])

    bs4 = types.ModuleType("bs4")
    bs4.BeautifulSoup = object
    sys.modules["bs4"] = bs4
    audit = runpy.run_path(str(ROOT / "scripts/audit-downs-style-archive.py"))
    collections = audit["collections_to_audit"](
        ["https://www.downsstyle.com/homepage-only/2026/8/3/example"]
    )
    assert "homepage-only" in collections
    assert set(audit["COLLECTION_LABELS"]) <= set(collections)
    assert audit["extraction_error"](article_found=True, body="") == (
        "article body not extracted"
    )
    assert audit["extraction_error"](article_found=True, body="text") == ""
    try:
        audit["require_complete_discovery"](["homepage: unavailable"])
    except SystemExit as exc:
        assert "archive discovery incomplete" in str(exc)
    else:
        raise AssertionError("failed discovery rail must stop the audit")

    requirements = (
        ROOT / "scripts/requirements-downs-style-archive.txt"
    ).read_text(encoding="utf-8")
    assert "beautifulsoup4" in requirements
    print("downs-style analysis regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
