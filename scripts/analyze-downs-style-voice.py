#!/usr/bin/env python3
"""Derive reproducible, non-verbatim voice metrics from a private post corpus.

The input is the temporary JSON emitted by ``audit-downs-style-archive.py``.
The output deliberately contains aggregate counts only: no article body, sentence,
or excerpt is retained in the tracked analysis artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")

PRONOUN_GROUPS = {
    "first_person_singular": ("i", "me", "my", "mine"),
    "first_person_plural": ("we", "us", "our", "ours"),
    "second_person": ("you", "your", "yours"),
}

LEXICAL_MARKERS = (
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
)

PHRASE_MARKERS = (
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
)


def normalize_word(word: str) -> str:
    return word.lower().replace("’", "'")


def words(text: str) -> list[str]:
    return [normalize_word(word) for word in WORD_PATTERN.findall(text)]


def safe_rate(count: int, total: int) -> float:
    return round((count / total * 1000) if total else 0.0, 2)


def phrase_count(text: str, phrase: str) -> int:
    """Count a normalized phrase without matching prefixes of longer words."""
    pattern = rf"(?<![a-z']){re.escape(phrase)}(?![a-z'])"
    return len(re.findall(pattern, text))


def contains_key(value: Any, key: str) -> bool:
    """Return whether a nested JSON-compatible value contains an exact key."""
    if isinstance(value, dict):
        return key in value or any(contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, key) for item in value)
    return False


def era_for(published_date: str) -> str:
    year = int(published_date[:4])
    if year <= 2018:
        return "2017-2018_foundation"
    if year <= 2020:
        return "2019-2020_reviews"
    if year <= 2023:
        return "2021-2023_expansion"
    if year == 2024:
        return "2024_editorial"
    return "2025_plus"


def summarize(posts: list[dict[str, Any]]) -> dict[str, Any]:
    all_words = [word for post in posts for word in words(post["body"])]
    word_counts = Counter(all_words)
    word_total = len(all_words)
    post_lengths = [len(words(post["body"])) for post in posts]

    sentences: list[str] = []
    paragraphs: list[str] = []
    for post in posts:
        compact = " ".join(post["body"].split())
        sentences.extend(
            sentence
            for sentence in SENTENCE_BOUNDARY.split(compact)
            if len(words(sentence)) >= 3
        )
        paragraphs.extend(
            paragraph.strip()
            for paragraph in post["body"].split("\n\n")
            if paragraph.strip()
        )

    joined = "\n".join(post["body"] for post in posts)
    normalized_text = joined.lower().replace("’", "'")
    sentence_lengths = [len(words(sentence)) for sentence in sentences]
    paragraph_lengths = [len(words(paragraph)) for paragraph in paragraphs]

    pronouns = {
        label: {
            "count": sum(word_counts[word] for word in group),
            "per_1000_words": safe_rate(
                sum(word_counts[word] for word in group), word_total
            ),
        }
        for label, group in PRONOUN_GROUPS.items()
    }
    lexical = {
        marker: {
            "count": word_counts[marker],
            "per_1000_words": safe_rate(word_counts[marker], word_total),
        }
        for marker in LEXICAL_MARKERS
    }
    phrase_counts = {
        marker: phrase_count(normalized_text, marker) for marker in PHRASE_MARKERS
    }
    phrases = {
        marker: {
            "count": count,
            "per_1000_words": safe_rate(count, word_total),
        }
        for marker, count in phrase_counts.items()
    }

    return {
        "posts": len(posts),
        "words": word_total,
        "median_post_words": round(statistics.median(post_lengths), 2) if posts else 0,
        "mean_sentence_words": round(statistics.mean(sentence_lengths), 2)
        if sentence_lengths
        else 0,
        "median_paragraph_words": round(statistics.median(paragraph_lengths), 2)
        if paragraph_lengths
        else 0,
        "pronouns": pronouns,
        "punctuation_per_1000_words": {
            "question_marks": safe_rate(joined.count("?"), word_total),
            "exclamation_marks": safe_rate(joined.count("!"), word_total),
        },
        "structural_post_counts": {
            "first_person_title": sum(
                bool(re.search(r"\b(?:I|My)\b", post["title"])) for post in posts
            ),
            "question_title": sum("?" in post["title"] for post in posts),
            "review_title": sum("review" in post["title"].lower() for post in posts),
            "shop_cue": sum(
                bool(re.search(r"\bshop\b", post["body"], re.IGNORECASE))
                for post in posts
            ),
            "reader_thanks": sum(
                "thanks" in post["body"].lower()
                and "reading" in post["body"].lower()
                for post in posts
            ),
            "numeric_rating": sum(
                bool(re.search(r"\b\d+(?:\.\d+)?\s*/\s*10\b", post["body"]))
                for post in posts
            ),
        },
        "lexical_markers": lexical,
        "phrase_markers": phrases,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--baseline-cutoff",
        type=date.fromisoformat,
        default=date(2024, 12, 31),
        help="Latest publication date included in the causal voice baseline",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus_bytes = args.corpus_json.read_bytes()
    posts = json.loads(corpus_bytes)
    if not isinstance(posts, list) or not all(isinstance(post, dict) for post in posts):
        raise SystemExit("corpus JSON must be a list of post objects")
    required = {"published_date", "category", "title", "url", "body"}
    for index, post in enumerate(posts):
        missing = required - post.keys()
        if missing:
            raise SystemExit(f"post {index} is missing fields: {sorted(missing)}")

    baseline = [
        post
        for post in posts
        if date.fromisoformat(post["published_date"][:10]) <= args.baseline_cutoff
    ]
    excluded = [post for post in posts if post not in baseline]

    by_year = {
        year: summarize(
            [post for post in posts if post["published_date"].startswith(year)]
        )
        for year in sorted({post["published_date"][:4] for post in posts})
    }
    by_category = {
        category: summarize([post for post in posts if post["category"] == category])
        for category in sorted({post["category"] for post in posts})
    }
    by_era = {
        era: summarize(
            [post for post in posts if era_for(post["published_date"]) == era]
        )
        for era in dict.fromkeys(era_for(post["published_date"]) for post in posts)
    }

    output = {
        "schema_version": 1,
        "source": {
            "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
            "public_post_count": len(posts),
            "first_publication_date": min(post["published_date"] for post in posts),
            "last_publication_date": max(post["published_date"] for post in posts),
            "contains_verbatim_article_text": False,
        },
        "baseline": {
            "cutoff": args.baseline_cutoff.isoformat(),
            "rationale": (
                "Causal baseline excludes posts published after the historical corpus "
                "that prompted this voice audit."
            ),
            "included_posts": len(baseline),
            "excluded_posts": len(excluded),
            "excluded_urls": [post["url"] for post in excluded],
            "metrics": summarize(baseline),
        },
        "all_public_posts": summarize(posts),
        "by_era": by_era,
        "by_year": by_year,
        "by_category": by_category,
        "method_notes": [
            "Tokens are alphabetic words with internal apostrophes.",
            "Sentence and paragraph boundaries are heuristic because historic posts mix prose and shopping lists.",
            "Rates are normalized per 1,000 words; phrase counts are case-insensitive and require token boundaries.",
            "Metrics describe the corpus and are evidence for editorial judgment, not a claim of sole authorship.",
        ],
    }
    if contains_key(output, "body"):
        raise AssertionError("derived output must not expose article bodies")
    serialized = json.dumps(output, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding="utf-8")
    print(
        f"analyzed {len(posts)} posts; baseline {len(baseline)}; "
        f"excluded {len(excluded)}; wrote {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
