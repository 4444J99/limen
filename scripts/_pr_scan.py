#!/usr/bin/env python3
"""_pr_scan.py — shared open-PR enumeration + rotating-window coverage for the HEAL and MERGE organs.

Both self-heal.py and merge-drain.py used to call `gh search prs --limit 30` and only ever
assessed the first 30 open PRs — so a backlog larger than 30 left its tail (100+ CI-red PRs)
permanently UNSEEN: never healed, never merged even once they turned mergeable. The open-PR floor
could not fall. This module closes that blind spot for BOTH organs with one implementation:

  • enumerate_open_prs() does ONE cheap `gh search prs` call (lightweight number/repo[/url] fields
    only, so a high --limit is fine and stays a single round-trip) and returns the FULL open-PR
    set, sorted by (repo, number) so the ordering is STABLE beat-to-beat — a given slot is the same
    PR until it merges, regardless of gh's search-relevance reshuffling.
  • rotating_window() returns the next `window` PRs starting at a persisted integer cursor and
    advances it (wrapping). The expensive per-PR `gh pr view` classification each organ runs stays
    bounded at `window` per beat (no rate-limit blowup), while EVERY open PR is assessed within one
    full rotation. Each organ keeps its OWN cursor file so the two rotate independently.

Pure + dependency-injected (the caller passes its own `gh`), so it carries no limen import and is
trivially unit-testable. Every filesystem touch is atomic and FAIL-OPEN: a cursor read/write error
degrades to "start at 0", never raising into the heartbeat. ([[no-never-happens-again]])
"""
import json
import os
import tempfile
from pathlib import Path


def enumerate_open_prs(owners, gh_fn, max_total=500, want_url=True):
    """One cheap `gh search prs` call → the FULL open-PR set across `owners`, stably sorted.
    Returns (repo, num, url) tuples when want_url else (repo, num). Empty list on any gh failure
    (fail-open: the caller treats it as 'no PRs this beat')."""
    fields = "number,repository,url" if want_url else "number,repository"
    r = gh_fn(["search", "prs", "--author", "@me", "--state", "open", "--limit", str(max_total),
               *sum([["--owner", o] for o in owners], []), "--json", fields])
    if getattr(r, "returncode", 1) != 0:
        return []
    try:
        rows = json.loads(r.stdout or "[]")
    except Exception:
        return []
    out = []
    for p in rows:
        try:
            repo = p["repository"]["nameWithOwner"]
            num = p["number"]
        except (KeyError, TypeError):
            continue
        out.append((repo, num, p.get("url", "")) if want_url else (repo, num))
    # STABLE order so the rotating cursor visits the same slot beat-to-beat regardless of gh's
    # search-relevance ranking (which reshuffles between calls).
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def _read_cursor(path):
    try:
        return max(0, int(Path(path).read_text().strip()))
    except Exception:
        return 0  # fail-open: unreadable/absent cursor ⇒ start at 0


def _write_cursor(path, value):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".cursor.")
        with os.fdopen(fd, "w") as f:
            f.write(str(int(value)))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)  # atomic
    except Exception:
        pass  # fail-open: a cursor write failure must never break the beat


def rotating_window(items, window, cursor_path, persist=True):
    """Return up to `window` items starting at the persisted cursor (wrapping), and advance the
    cursor by how many were taken. persist=False (dry-run) PEEKS at the current window without
    advancing or writing — so a preview makes zero writes."""
    n = len(items)
    if n <= 0:
        return []
    start = _read_cursor(cursor_path) % n
    take = min(window, n)
    sel = [items[(start + i) % n] for i in range(take)]
    if persist:
        _write_cursor(cursor_path, (start + take) % n)
    return sel


def avg_headroom_pct(root):
    """Average live per-vendor headroom (0–100) from logs/usage.json, or None if unreadable.
    Mirrors the accelerator input generate-backlog.py uses (kept in sync deliberately): a full tank
    means idle vendor capacity, so the per-run cap can lift without flooding."""
    try:
        fpath = Path(root) / "logs" / "usage.json"
        vendors = (json.loads(fpath.read_text()) or {}).get("vendors", {})
        hs = [v["headroom_pct"] for v in vendors.values()
              if isinstance(v, dict) and isinstance(v.get("headroom_pct"), (int, float))]
        return sum(hs) / len(hs) if hs else None
    except Exception:
        return None


def scaled_limit(base, root, lo=50.0, span=25.0, max_mult=3.0):
    """Scale a per-run cap up to max_mult× as average headroom climbs from `lo`→100 (full tank ⇒
    burst more heal tasks). Below `lo`, or with no readable usage, returns `base` unchanged.
    Symmetric with generate-backlog.py's floor accelerator (50%→1× … 100%→3×)."""
    hr = avg_headroom_pct(root)
    if hr is None or hr < lo:
        return base
    mult = 1.0 + min(max_mult - 1.0, (hr - lo) / span)
    return int(round(base * mult))
