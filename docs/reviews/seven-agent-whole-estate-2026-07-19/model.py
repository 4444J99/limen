#!/usr/bin/env python3
"""Pure helpers for the frozen seven-agent estate review.

This module intentionally knows nothing about machine-local store locations.  It
owns the half-open time math, native token deltas, root/child interval handling,
receipt canonicalization, and conservative outcome classification used by the
collector and its synthetic tests.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from collections.abc import Iterable, Mapping
from typing import Any

UTC = dt.timezone.utc

OUTCOMES = (
    "verified_done",
    "verified_partial",
    "durably_homed_open",
    "blocked",
    "superseded",
    "not_done_or_unverified",
    "coverage_unknown",
)

PR_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[0-9]+)"
)


def parse_ts(value: Any) -> dt.datetime | None:
    """Parse ISO, epoch-second, or epoch-millisecond timestamps as UTC."""

    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return dt.datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text or text.startswith("0001-"):
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_z(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclasses.dataclass(frozen=True)
class Window:
    id: str
    label: str
    start: dt.datetime
    end: dt.datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("window timestamps must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("window end must be after start")

    def contains(self, timestamp: dt.datetime | None) -> bool:
        return bool(timestamp is not None and self.start <= timestamp < self.end)

    def intersects(self, start: dt.datetime | None, end: dt.datetime | None) -> bool:
        if start is None and end is None:
            return False
        left = start or end
        right = end or start
        assert left is not None and right is not None
        if right < left:
            left, right = right, left
        if right == left:
            return self.contains(left)
        return left < self.end and right >= self.start

    def clip(
        self, start: dt.datetime | None, end: dt.datetime | None
    ) -> tuple[dt.datetime, dt.datetime] | None:
        if not self.intersects(start, end):
            return None
        left = start or end
        right = end or start
        assert left is not None and right is not None
        if right < left:
            left, right = right, left
        left = max(left, self.start)
        right = min(right, self.end)
        if right < left:
            return None
        return left, right


def interval_seconds(interval: tuple[dt.datetime, dt.datetime] | None) -> float | None:
    if interval is None:
        return None
    return max(0.0, (interval[1] - interval[0]).total_seconds())


def union_seconds(intervals: Iterable[tuple[dt.datetime, dt.datetime]]) -> float:
    """Return concurrency-adjusted wall time for a set of half-open intervals."""

    ordered = sorted((a, b) if a <= b else (b, a) for a, b in intervals)
    if not ordered:
        return 0.0
    total = 0.0
    cur_start, cur_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
            continue
        total += max(0.0, (cur_end - cur_start).total_seconds())
        cur_start, cur_end = start, end
    total += max(0.0, (cur_end - cur_start).total_seconds())
    return total


def int_value(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def codex_usage(raw: Mapping[str, Any] | None) -> dict[str, int]:
    raw = raw or {}
    input_tokens = int_value(raw.get("input_tokens"))
    cached = int_value(raw.get("cached_input_tokens"))
    output = int_value(raw.get("output_tokens"))
    reasoning = int_value(raw.get("reasoning_output_tokens"))
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "uncached_input_tokens": max(0, input_tokens - cached),
        "output_tokens": output,
        "reasoning_output_tokens": reasoning,
    }


def cumulative_delta(
    current: Mapping[str, int], previous: Mapping[str, int] | None
) -> dict[str, int]:
    """Turn a cumulative native meter into a non-negative event delta."""

    if previous is None:
        return {key: int_value(value) for key, value in current.items()}
    return {
        key: max(0, int_value(current.get(key)) - int_value(previous.get(key)))
        for key in current
    }


def sum_components(
    rows: Iterable[Mapping[str, Any]], keys: Iterable[str]
) -> dict[str, int]:
    result = {key: 0 for key in keys}
    for row in rows:
        for key in result:
            result[key] += int_value(row.get(key))
    return result


def extract_pr_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in PR_URL_RE.finditer(text or ""):
        url = (
            f"https://github.com/{match.group('owner')}/"
            f"{match.group('repo')}/pull/{int(match.group('number'))}"
        )
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def parse_pr_url(url: str) -> tuple[str, str, int] | None:
    match = PR_URL_RE.fullmatch((url or "").strip().rstrip("/"))
    if not match:
        return None
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def canonical_receipt_key(receipt: Mapping[str, Any]) -> str:
    """Deduplicate redirects and repeated references by terminal PR identity."""

    canonical_url = str(receipt.get("canonical_url") or receipt.get("url") or "")
    parsed = parse_pr_url(canonical_url)
    if parsed:
        owner, repo, number = parsed
        return f"github:{owner.lower()}/{repo.lower()}#{number}"
    return f"opaque:{canonical_url}"


def checks_pass(checks: Iterable[Mapping[str, Any]]) -> bool:
    rows = list(checks)
    if not rows:
        return False
    accepted = {"SUCCESS", "NEUTRAL", "SKIPPED", "EXPECTED"}
    for row in rows:
        conclusion = str(row.get("conclusion") or row.get("state") or "").upper()
        status = str(row.get("status") or "").upper()
        if status and status not in {"COMPLETED", "SUCCESS"}:
            return False
        if conclusion not in accepted:
            return False
    return True


def classify_receipt(
    receipt: Mapping[str, Any],
    *,
    snapshot_at: dt.datetime,
    predicate_signal: bool = False,
) -> tuple[str, str]:
    """Classify one PR conservatively as it existed at the frozen snapshot."""

    created = parse_ts(receipt.get("created_at"))
    if created is None or created >= snapshot_at:
        return "coverage_unknown", "receipt did not exist before the frozen snapshot"

    commits = [
        row
        for row in (receipt.get("commits") or [])
        if parse_ts(row.get("committed_at")) is not None
    ]
    late_commit = any(
        (parse_ts(row.get("committed_at")) or snapshot_at) >= snapshot_at
        for row in commits
    )
    if late_commit and not parse_ts(receipt.get("merged_at")):
        return "coverage_unknown", "exact head changed after the frozen snapshot"

    merged_at = parse_ts(receipt.get("merged_at"))
    closed_at = parse_ts(receipt.get("closed_at"))
    base = str(receipt.get("base_ref") or "")
    default_branch = str(receipt.get("default_branch") or "")
    on_default = bool(base and default_branch and base == default_branch)
    exact_head_checks = checks_pass(receipt.get("checks") or [])

    if merged_at and merged_at < snapshot_at and on_default:
        if exact_head_checks or predicate_signal:
            return "verified_done", "merged to default with an exact-head passing predicate"
        return "verified_partial", "merged to default, but no executable predicate was captured"

    if closed_at and closed_at < snapshot_at:
        return "not_done_or_unverified", "closed without a default-reachable merge"
    return "durably_homed_open", "open PR at the frozen snapshot"


def outcome_rank(outcome: str) -> int:
    order = {
        "verified_done": 7,
        "verified_partial": 6,
        "durably_homed_open": 5,
        "blocked": 4,
        "superseded": 3,
        "not_done_or_unverified": 2,
        "coverage_unknown": 1,
    }
    return order.get(outcome, 0)


def strongest_outcome(outcomes: Iterable[str]) -> str:
    values = [value for value in outcomes if value in OUTCOMES]
    return max(values, key=outcome_rank) if values else "coverage_unknown"


def sanitize_subject(text: str) -> str:
    """Return a coarse intent label without preserving raw prompt text."""

    lowered = (text or "").lower()
    buckets = (
        ("closeout", ("closeout", "finish everything", "fixed point", "reap")),
        ("audit/review", ("audit", "review", "critique", "report", "assess")),
        ("implementation", ("implement", "build", "add ", "create ", "wire ", "fix ")),
        ("diagnosis", ("debug", "diagnose", "why ", "investigate", "what's going on")),
        ("dispatch/control-plane", ("dispatch", "fleet", "route", "agent", "tasks.yaml")),
        ("research", ("research", "find ", "search", "survey", "study")),
    )
    for label, markers in buckets:
        if any(marker in lowered for marker in markers):
            return label
    return "other"


def redact_session_ids(
    sessions: list[dict[str, Any]], agent: str
) -> dict[str, str]:
    """Create stable report-local labels without exposing provider IDs or hashes."""

    native_ids = sorted(
        {
            str(row.get("native_id") or "")
            for row in sessions
            if row.get("agent") == agent and row.get("native_id")
        }
    )
    return {
        native_id: f"{agent}-{index:04d}"
        for index, native_id in enumerate(native_ids, start=1)
    }
