#!/usr/bin/env python3
"""Verify the tracked Downs Style archive and its bounded presentation data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_CATEGORIES = {
    "Candles": 18,
    "Eat": 12,
    "Gift Inspo": 7,
    "Interior Design": 8,
    "Look Book": 36,
    "Masks": 51,
    "Skincare": 112,
    "Travel": 7,
    "Workouts/Diet": 7,
}
EXPECTED_YEARS = {
    "2017": 16,
    "2018": 78,
    "2019": 22,
    "2020": 54,
    "2021": 22,
    "2022": 5,
    "2023": 36,
    "2024": 24,
    "2026": 1,
}
EXPECTED_ERAS = {
    "2017-2018_foundation",
    "2019-2020_reviews",
    "2021-2023_expansion",
    "2024_editorial",
    "2025_plus",
}
SUMMARY_FIELDS = {
    "posts",
    "words",
    "median_post_words",
    "mean_sentence_words",
    "median_paragraph_words",
    "pronouns",
    "punctuation_per_1000_words",
    "structural_post_counts",
    "lexical_markers",
    "phrase_markers",
}
PRONOUN_FIELDS = {
    "first_person_singular",
    "first_person_plural",
    "second_person",
}
STRUCTURAL_FIELDS = {
    "first_person_title",
    "question_title",
    "review_title",
    "shop_cue",
    "reader_thanks",
    "numeric_rating",
}
LEXICAL_FIELDS = {
    "love",
    "loved",
    "favorite",
    "obsessed",
    "amazing",
    "great",
    "beautiful",
    "cute",
    "luxury",
    "luxurious",
    "glowing",
    "healthy",
    "natural",
    "organic",
    "personally",
    "however",
    "overall",
}
PHRASE_FIELDS = {
    "i love",
    "i loved",
    "i like",
    "i think",
    "i feel",
    "i recommend",
    "i personally",
    "i have to say",
    "my favorite",
    "one of my favorite",
    "for me",
    "of course",
    "so i decided",
    "had to try",
    "fell in love",
    "made my skin feel",
    "left my skin feeling",
    "overall i",
    "thanks so much for reading",
    "shop below",
    "click to shop",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"archive verification failed: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("docs/continuations/charles/downs-style-post-ledger.csv"),
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("docs/continuations/charles/downs-style-voice-metrics.json"),
    )
    parser.add_argument(
        "--site-json",
        type=Path,
        default=Path("docs/continuations/charles/rose-toners-share/data/posts.json"),
    )
    parser.add_argument(
        "--natural-center",
        type=Path,
        default=Path("docs/continuations/charles/downs-style-natural-center.yaml"),
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_exact_keys(value: Any, expected: set[str], label: str) -> None:
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == expected, f"{label} fields changed")


def validate_stat_map(value: Any, fields: set[str], label: str) -> None:
    require_exact_keys(value, fields, label)
    for field, statistic in value.items():
        require_exact_keys(statistic, {"count", "per_1000_words"}, f"{label}.{field}")


def validate_summary(value: Any, label: str) -> None:
    require_exact_keys(value, SUMMARY_FIELDS, label)
    validate_stat_map(value["pronouns"], PRONOUN_FIELDS, f"{label}.pronouns")
    require_exact_keys(
        value["punctuation_per_1000_words"],
        {"question_marks", "exclamation_marks"},
        f"{label}.punctuation_per_1000_words",
    )
    require_exact_keys(
        value["structural_post_counts"],
        STRUCTURAL_FIELDS,
        f"{label}.structural_post_counts",
    )
    validate_stat_map(value["lexical_markers"], LEXICAL_FIELDS, f"{label}.lexical_markers")
    validate_stat_map(value["phrase_markers"], PHRASE_FIELDS, f"{label}.phrase_markers")


def normalized_text_sha256(path: Path) -> str:
    """Hash text after canonicalizing checkout-dependent line endings to LF."""
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def ledger_site_projection(record: dict[str, str]) -> dict[str, Any]:
    """Return the complete body-free projection allowed in the preview archive."""
    return {
        "publishedDate": record["published_date"][:10],
        "year": record["published_date"][:4],
        "category": record["category"],
        "title": record["title"],
        "url": record["url"],
        "author": record["author"],
        "wordCount": int(record["word_count"]),
    }


def site_projection_matches(records: list[dict[str, str]], site_posts: list[Any]) -> bool:
    """Return whether every site row exactly matches its seven ledger fields."""
    projected_by_url = {
        projection["url"]: projection for projection in (ledger_site_projection(record) for record in records)
    }
    return len(site_posts) == len(records) and all(
        isinstance(post, dict) and post == projected_by_url.get(post.get("url")) for post in site_posts
    )


def main() -> int:
    args = parse_args()
    with args.ledger.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))

    require(len(records) == 258, f"expected 258 ledger rows, found {len(records)}")
    urls = [record["url"] for record in records]
    require(len(set(urls)) == 258, "ledger URLs are not unique")
    require(
        all(record["http_status"] == "200" for record in records),
        "not every archived URL returned HTTP 200",
    )
    require(
        all(not record["error"] for record in records),
        "one or more posts have a parse error",
    )
    require(
        {record["author"] for record in records} == {"Chas Downs"},
        "author metadata is not uniformly Chas Downs",
    )
    require(
        len({record["content_sha256"] for record in records}) == 258,
        "content fingerprints are missing or duplicated",
    )
    require(
        Counter(record["category"] for record in records) == EXPECTED_CATEGORIES,
        "category counts changed",
    )
    require(
        Counter(record["published_date"][:4] for record in records) == EXPECTED_YEARS,
        "year counts changed",
    )
    require(records[0]["published_date"][:10] == "2017-12-04", "earliest date changed")
    require(records[-1]["published_date"][:10] == "2026-08-02", "latest date changed")
    require(
        sum(not record["sitemap_lastmod"] for record in records) == 1,
        "expected exactly one post discovered outside the sitemap",
    )

    metrics = load_json(args.metrics)
    require_exact_keys(
        metrics,
        {
            "schema_version",
            "source",
            "baseline",
            "all_public_posts",
            "by_era",
            "by_year",
            "by_category",
            "method_notes",
        },
        "metrics",
    )
    require_exact_keys(
        metrics["source"],
        {
            "corpus_sha256",
            "public_post_count",
            "first_publication_date",
            "last_publication_date",
            "contains_verbatim_article_text",
        },
        "metrics.source",
    )
    require_exact_keys(
        metrics["baseline"],
        {"cutoff", "rationale", "included_posts", "excluded_posts", "excluded_urls", "metrics"},
        "metrics.baseline",
    )
    validate_summary(metrics["baseline"]["metrics"], "metrics.baseline.metrics")
    validate_summary(metrics["all_public_posts"], "metrics.all_public_posts")
    require_exact_keys(metrics["by_era"], EXPECTED_ERAS, "metrics.by_era")
    require_exact_keys(metrics["by_year"], set(EXPECTED_YEARS), "metrics.by_year")
    require_exact_keys(metrics["by_category"], set(EXPECTED_CATEGORIES), "metrics.by_category")
    for group, summaries in (
        ("by_era", metrics["by_era"]),
        ("by_year", metrics["by_year"]),
        ("by_category", metrics["by_category"]),
    ):
        for name, summary in summaries.items():
            validate_summary(summary, f"metrics.{group}.{name}")
    require(
        isinstance(metrics["method_notes"], list) and all(isinstance(note, str) for note in metrics["method_notes"]),
        "metrics method notes must be strings",
    )
    require(metrics.get("schema_version") == 1, "unsupported metrics schema")
    require(metrics["source"]["public_post_count"] == 258, "metrics omit public posts")
    require(
        metrics["source"]["contains_verbatim_article_text"] is False,
        "metrics claim to contain verbatim article text",
    )
    require(metrics["baseline"]["included_posts"] == 257, "baseline must contain 257 posts")
    require(metrics["baseline"]["excluded_posts"] == 1, "baseline must exclude one newer post")
    require(metrics["baseline"]["cutoff"] == "2024-12-31", "baseline cutoff changed")
    baseline_love = metrics["baseline"]["metrics"]["phrase_markers"]["i love"]
    require(
        baseline_love == {"count": 154, "per_1000_words": 2.01},
        "I love metric must use exact token boundaries",
    )
    require(
        metrics["baseline"]["metrics"]["structural_post_counts"]["first_person_title"] == 28,
        "baseline first-person title count must match case-insensitively",
    )
    require(
        metrics["all_public_posts"]["structural_post_counts"]["first_person_title"] == 28,
        "all-public first-person title count must match case-insensitively",
    )

    ledger_sha = normalized_text_sha256(args.ledger)
    metrics_sha = normalized_text_sha256(args.metrics)
    natural_center = args.natural_center.read_text(encoding="utf-8")
    require(
        f"downs-style-post-ledger.csv@sha256:{ledger_sha}" in natural_center,
        "Natural Center ledger digest does not match committed bytes",
    )
    require(
        f"downs-style-voice-metrics.json@sha256:{metrics_sha}" in natural_center,
        "Natural Center metrics digest does not match committed bytes",
    )

    site_posts = load_json(args.site_json)
    require(isinstance(site_posts, list), "site archive must be a JSON list")
    require(len(site_posts) == 258, "site archive must expose all 258 posts")
    require(
        all(isinstance(post, dict) for post in site_posts),
        "site archive rows must be JSON objects",
    )
    require(
        {post.get("url") for post in site_posts} == set(urls),
        "site and ledger URL sets differ",
    )
    require(
        site_projection_matches(records, site_posts),
        "site archive differs from the ledger's seven-field projection",
    )

    print(
        "verified 258 unique Downs Style posts, nine categories, "
        "a 257-post causal voice baseline, and body-free site data"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
