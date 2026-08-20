#!/usr/bin/env python3
"""estate-repos-refresh — project the remote estate into the skeleton-thin hot cache.

GitHub is the durable authority on BOTH axes of "what does the estate own": the owner
accounts themselves (the authenticated identity + every org it belongs to, derived live
unless LIMEN_OWNERS pins an explicit list) and the repos under each. This effector asks
it and writes the answer to the local cache (limen.estate_repos.v1 at
LIMEN_ESTATE_REPOS_CACHE, default logs/estate-repos.json). The cache is a projection,
never a registry: consumers (limen.estate.load_estate_cache) treat it as evidence with a
TTL, and a stale cache reads as ABSENCE, not emptiness. Transfer/rename aliases probed by
consumers (limen.estate.append_aliases) are carried forward across re-lists — they are
remote-derived facts too, and resolve() re-validates each against the fresh roster.

Inside the TTL this is a cheap due-check (prints `fresh`, exits 0) so a beat can run it
hourly at the cost of nothing; --force re-lists unconditionally.

Fail-closed on partial truth: if owner derivation or ANY owner's listing fails, the old
cache is left untouched and the exit is 1 — writing a half-estate would silently refuse
every repo under the missing owner, which is exactly the shrink this design forbids.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.estate import SCHEMA, load_estate_cache  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
CACHE = Path(os.environ.get("LIMEN_ESTATE_REPOS_CACHE", str(ROOT / "logs" / "estate-repos.json")))
OWNERS_PIN = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "").split(",") if o.strip()]


def _gh_lines(cmd: list[str], timeout: int = 60) -> list[str] | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def derive_owners() -> list[str] | None:
    """The estate's owner accounts, from the remote: viewer login + every org membership."""
    login = _gh_lines(["gh", "api", "user", "--jq", ".login"])
    orgs = _gh_lines(["gh", "api", "user/orgs", "--paginate", "--jq", ".[].login"])
    if not login or orgs is None:
        return None
    seen: dict[str, None] = {}
    for owner in [*login, *orgs]:
        seen.setdefault(owner, None)
    return list(seen)


def list_owner(owner: str) -> list[dict] | None:
    cmd = [
        "gh",
        "repo",
        "list",
        owner,
        "--limit",
        "1000",
        "--json",
        "nameWithOwner,isArchived,isFork",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        rows = json.loads(proc.stdout)
    except ValueError:
        return None
    return rows if isinstance(rows, list) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="refresh even when the cache is inside its TTL")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    ttl_hours = float(os.environ.get("LIMEN_ESTATE_CACHE_TTL_HOURS", "24") or 24)
    if not args.force:
        fresh = load_estate_cache(CACHE, now=now, ttl_hours=ttl_hours)
        if fresh is not None:
            age_hours = (now - fresh.fetched_at).total_seconds() / 3600
            print(
                f"  estate-repos-refresh: fresh — {len(fresh.repos)} repos cached {age_hours:.1f}h ago "
                f"(TTL {ttl_hours:.0f}h); --force to re-list"
            )
            return 0

    owners = OWNERS_PIN or derive_owners()
    if not owners:
        print("  estate-repos-refresh: FAIL — could not derive owner accounts (gh api user/orgs); cache left untouched")
        return 1

    repos: dict[str, dict] = {}
    for owner in owners:
        rows = list_owner(owner)
        if rows is None:
            print(f"  estate-repos-refresh: FAIL — could not list {owner}; cache left untouched")
            return 1
        for row in rows:
            name = str(row.get("nameWithOwner") or "").strip()
            if not name:
                continue
            repos[name] = {"archived": bool(row.get("isArchived")), "fork": bool(row.get("isFork"))}

    aliases: dict[str, str] = {}
    try:
        prior = json.loads(CACHE.read_text(encoding="utf-8"))
        if isinstance(prior, dict) and isinstance(prior.get("aliases"), dict):
            aliases = {str(k): str(v) for k, v in prior["aliases"].items() if isinstance(v, str)}
    except (OSError, ValueError):
        pass

    payload = {
        "schema": SCHEMA,
        "fetched_at": now.isoformat(timespec="seconds"),
        "owners": owners,
        "repos": repos,
        "aliases": aliases,
    }
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archived = sum(1 for entry in repos.values() if entry["archived"])
    print(
        f"  estate-repos-refresh: OK — {len(repos)} repos ({archived} archived) across "
        f"{len(owners)} owners ({'pinned' if OWNERS_PIN else 'derived'}) -> {CACHE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
