"""estate — the remote-first enumeration of every repo the estate owns.

The durable authority is GitHub itself: the estate is whatever `gh repo list` reports
for the owner accounts, live. The local cache file (schema ``limen.estate_repos.v1``,
written by ``scripts/estate-repos-refresh.py``) is a skeleton-thin hot projection of
that answer — a TTL'd cache, never an independent registry. Consumers MUST treat a
missing, unparseable, or stale cache as ABSENCE OF EVIDENCE (``None``), never as an
empty estate: "I read nothing" and "there is nothing" are different facts, and the
work-loan underwriter refusing 300 repos because a cache file went stale would be the
silent-shrink failure mode this module exists to prevent.

Pure functions over a payload/path — no gh, no writes — so staleness and membership
are exhaustively testable. The refresher effector owns the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "limen.estate_repos.v1"


@dataclass(frozen=True)
class EstateRepo:
    archived: bool
    fork: bool


@dataclass(frozen=True)
class EstateCache:
    fetched_at: datetime
    repos: dict[str, EstateRepo]
    aliases: dict[str, str]

    def live_members(self) -> set[str]:
        """Repos loans may be underwritten against: present on GitHub and not archived."""
        return {name for name, repo in self.repos.items() if not repo.archived}

    def resolve(self, repo: str) -> str | None:
        """Canonical estate name for ``repo``, following transfer/rename aliases.

        The board records the repo path a task was FILED under; GitHub transfers and
        renames leave those rows pointing at redirect stubs. An alias entry (probed
        remotely, cached beside the roster) maps the old path to the canonical one.
        None ⟺ the name reaches no estate repo either directly or via alias.
        """
        if repo in self.repos:
            return repo
        target = self.aliases.get(repo)
        if target is not None and target in self.repos:
            return target
        return None


def parse_estate_payload(payload: Any) -> EstateCache | None:
    """Payload -> cache, or None when the shape is not a v1 estate projection."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    try:
        fetched_at = datetime.fromisoformat(str(payload.get("fetched_at")))
    except (TypeError, ValueError):
        return None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    raw = payload.get("repos")
    if not isinstance(raw, dict):
        return None
    repos: dict[str, EstateRepo] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            return None
        repos[str(name)] = EstateRepo(
            archived=bool(entry.get("archived")),
            fork=bool(entry.get("fork")),
        )
    raw_aliases = payload.get("aliases")
    aliases = (
        {str(k): str(v) for k, v in raw_aliases.items() if isinstance(v, str)} if isinstance(raw_aliases, dict) else {}
    )
    return EstateCache(fetched_at=fetched_at, repos=repos, aliases=aliases)


def load_estate_cache(path: Path, *, now: datetime, ttl_hours: float) -> EstateCache | None:
    """Read the hot cache; None when missing, unparseable, or older than the TTL."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cache = parse_estate_payload(payload)
    if cache is None:
        return None
    if now - cache.fetched_at > timedelta(hours=ttl_hours):
        return None
    return cache


def append_aliases(path: Path, aliases: dict[str, str]) -> bool:
    """Fold newly-probed transfer/rename aliases into the cache file in place.

    Aliases are remote-derived facts (GitHub redirect answers), so they belong in the
    same projection as the roster. The fold is a targeted merge — roster and stamp are
    left untouched, so appending aliases never extends the cache's TTL. False on any
    read/shape/write problem: alias persistence is an optimization, never worth a crash.
    """
    if not aliases:
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return False
    raw_aliases = payload.get("aliases")
    merged: dict[str, Any] = dict(raw_aliases) if isinstance(raw_aliases, dict) else {}
    merged.update(aliases)
    payload["aliases"] = merged
    try:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True
