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
    if not phrase_count("i love it; i loved it; i lovely", "i love") == 1:
        raise AssertionError("validation failed at original line 19")
    if not phrase_count("i loved it", "i loved") == 1:
        raise AssertionError("validation failed at original line 20")
    if not voice["contains_key"]({"safe": [{"body": "private"}]}, "body"):
        raise AssertionError("validation failed at original line 21")
    if not not voice["contains_key"]({"body_blocks": 2}, "body"):
        raise AssertionError("validation failed at original line 22")
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
    if not summarize(posts)["structural_post_counts"]["first_person_title"] == 1:
        raise AssertionError("validation failed at original line 33")
    verifier = runpy.run_path(str(ROOT / "scripts/verify-downs-style-archive.py"))
    normalized_text_sha256 = verifier["normalized_text_sha256"]
    ledger_site_projection = verifier["ledger_site_projection"]
    site_projection_matches = verifier["site_projection_matches"]
    require_exact_keys = verifier["require_exact_keys"]
    try:
        require_exact_keys({"safe": True, "body": "private"}, {"safe"}, "fixture")
    except SystemExit as exc:
        if "fields changed" not in str(exc):
            raise AssertionError("schema allowlist failure was not reported")
    else:
        raise AssertionError("schema allowlist accepted an unexpected body field")
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        lf_path = temporary / "ledger-lf.csv"
        crlf_path = temporary / "ledger-crlf.csv"
        lf_path.write_bytes(b"title,url\nOne,https://example.test\n")
        crlf_path.write_bytes(b"title,url\r\nOne,https://example.test\r\n")
        if not normalized_text_sha256(lf_path) == normalized_text_sha256(crlf_path):
            raise AssertionError("validation failed at original line 45")
    record = {
        "published_date": "2018-01-02T00:00:00Z",
        "category": "Look Book",
        "title": "My title",
        "url": "https://example.test/post",
        "author": "Chas Downs",
        "word_count": "42",
    }
    projection = ledger_site_projection(record)
    if not projection == {
        "publishedDate": "2018-01-02",
        "year": "2018",
        "category": "Look Book",
        "title": "My title",
        "url": "https://example.test/post",
        "author": "Chas Downs",
        "wordCount": 42,
    }:
        raise AssertionError("validation failed at original line 55")
    if not set(projection) == {"publishedDate", "year", "category", "title", "url", "author", "wordCount"}:
        raise AssertionError("validation failed at original line 64")
    if not site_projection_matches([record], [projection]):
        raise AssertionError("validation failed at original line 73")
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
        if not not site_projection_matches([record], [{**projection, field: stale_value}]):
            raise AssertionError("validation failed at original line 84")
    if not not site_projection_matches([record], [{**projection, "extra": True}]):
        raise AssertionError("validation failed at original line 88")
    bs4 = types.ModuleType("bs4")
    bs4.BeautifulSoup = object
    sys.modules["bs4"] = bs4
    audit = runpy.run_path(str(ROOT / "scripts/audit-downs-style-archive.py"))
    if not audit["load_beautiful_soup"]():
        raise AssertionError("controlled BeautifulSoup loading failed")
    try:
        audit["write_corpus"](ROOT / "docs/private-corpus.json", [])
    except SystemExit as exc:
        if "outside the repository worktree" not in str(exc):
            raise AssertionError("unsafe corpus path failure was not reported")
    else:
        raise AssertionError("private corpus path inside the worktree was accepted")
    collections = audit["collections_to_audit"](["https://www.downsstyle.com/homepage-only/2026/8/3/example"])
    if "homepage-only" not in collections:
        raise AssertionError("validation failed at original line 97")
    if not set(audit["COLLECTION_LABELS"]) <= set(collections):
        raise AssertionError("validation failed at original line 98")
    if not audit["extraction_error"](article_found=True, body="") == "article body not extracted":
        raise AssertionError("validation failed at original line 99")
    if not audit["extraction_error"](article_found=True, body="text") == "":
        raise AssertionError("validation failed at original line 102")
    parse_post = audit["parse_post"]
    original_fetch = parse_post.__globals__["fetch"]
    original_soup = parse_post.__globals__["BeautifulSoup"]
    try:
        parse_post.__globals__["fetch"] = lambda *_args, **_kwargs: (
            200,
            "https://www.downsstyle.com/skincare/2026/8/3/replacement",
            "<article>replacement copy must not be parsed</article>",
        )
        parse_post.__globals__["BeautifulSoup"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("redirect body was parsed")
        )
        redirected, redirected_body = parse_post(
            "https://www.downsstyle.com/look-book/2024/7/1/original",
            sources={"sitemap"},
            lastmod="2026-08-03",
            timeout=1,
        )
    finally:
        parse_post.__globals__["fetch"] = original_fetch
        parse_post.__globals__["BeautifulSoup"] = original_soup
    if not redirected.http_status == 200:
        raise AssertionError("validation failed at original line 124")
    if not redirected.final_url.endswith("/replacement"):
        raise AssertionError("validation failed at original line 125")
    if not redirected.error.startswith("unexpected archive redirect:"):
        raise AssertionError("validation failed at original line 126")
    if not redirected.content_sha256 == "":
        raise AssertionError("validation failed at original line 127")
    if not redirected_body == "":
        raise AssertionError("validation failed at original line 128")
    try:
        audit["require_complete_discovery"](["homepage: unavailable"])
    except SystemExit as exc:
        if "archive discovery incomplete" not in str(exc):
            raise AssertionError("validation failed at original line 132")
    else:
        raise AssertionError("failed discovery rail must stop the audit")
    requirements = (ROOT / "scripts/requirements-downs-style-archive.txt").read_text(encoding="utf-8")
    if "beautifulsoup4" not in requirements:
        raise AssertionError("validation failed at original line 139")
    print("downs-style analysis regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
