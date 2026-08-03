#!/usr/bin/env python3
"""Verify the tracked Downs Style archive and its bounded presentation data."""

from __future__ import annotations

import argparse
import csv
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
        default=Path(
            "docs/continuations/charles/rose-toners-share/data/posts.json"
        ),
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    require(metrics.get("schema_version") == 1, "unsupported metrics schema")
    require(metrics["source"]["public_post_count"] == 258, "metrics omit public posts")
    require(
        metrics["source"]["contains_verbatim_article_text"] is False,
        "metrics claim to contain verbatim article text",
    )
    require(metrics["baseline"]["included_posts"] == 257, "baseline must contain 257 posts")
    require(metrics["baseline"]["excluded_posts"] == 1, "baseline must exclude one newer post")
    require(metrics["baseline"]["cutoff"] == "2024-12-31", "baseline cutoff changed")

    site_posts = load_json(args.site_json)
    require(isinstance(site_posts, list), "site archive must be a JSON list")
    require(len(site_posts) == 258, "site archive must expose all 258 posts")
    require(
        {post.get("url") for post in site_posts} == set(urls),
        "site and ledger URL sets differ",
    )
    prohibited = {"body", "content", "html", "tags"}
    require(
        all(not (prohibited & post.keys()) for post in site_posts),
        "site data includes article bodies or noisy raw tags",
    )
    require(
        all(post.get("author") == "Chas Downs" for post in site_posts),
        "site author metadata changed",
    )

    print(
        "verified 258 unique Downs Style posts, nine categories, "
        "a 257-post causal voice baseline, and body-free site data"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
