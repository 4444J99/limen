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

import fnmatch
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

QUEUE_ACTIVE = "active"
QUEUE_ABSENT = "absent"
QUEUE_UNKNOWN = "unknown"


def enumerate_open_prs(owners, gh_fn, max_total=500, want_url=True, author="@me"):
    """One cheap `gh search prs` call → the FULL open-PR set across `owners`, stably sorted.
    Returns (repo, num, url) tuples when want_url else (repo, num). Empty list on any gh failure
    (fail-open: the caller treats it as 'no PRs this beat'). ``author=None`` is the estate-wide
    census mode; worker loops retain the narrower current-actor default."""
    fields = "number,repository,url" if want_url else "number,repository"
    cmd = ["search", "prs", "--state", "open", "--limit", str(max_total)]
    if author:
        cmd.extend(["--author", str(author)])
    cmd.extend([*sum([["--owner", o] for o in owners], []), "--json", fields])
    r = gh_fn(cmd)
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
        hs = [
            v["headroom_pct"]
            for v in vendors.values()
            if isinstance(v, dict) and isinstance(v.get("headroom_pct"), (int, float))
        ]
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


# ── MERGE-QUEUE CAPABILITY ─────────────────────────────────────────────────────────────────────
# A queue is branch-specific live repository state. Never infer it from mergeStateStatus, local
# configuration, workflow files, or a remembered plan: GitHub's Repository.mergeQueue field is the
# authority. The result is deliberately tri-state so an API/schema/auth failure cannot accidentally
# relax the stale-base guard.

_MERGE_QUEUE_QUERY = """
query($owner:String!,$repo:String!,$branch:String!){
  repository(owner:$owner,name:$repo){
    mergeQueue(branch:$branch){id}
  }
}
""".strip()


@lru_cache(maxsize=64)
def merge_queue_capability(repo, branch, gh_fn):
    """Return ``active``, ``absent``, or ``unknown`` for ``repo``'s target ``branch``.

    ``active`` requires a positive GraphQL MergeQueue object. A clean ``null`` means the queue is
    absent. Transport failures, GraphQL errors, malformed/partial payloads, missing repository
    access, and invalid inputs are ``unknown`` so callers preserve their non-queue safety policy.
    Results are cached only for the current bounded process so a drain beat pays one live probe per
    repository/branch instead of one GraphQL request per pull request.
    """
    if not repo or "/" not in repo or not branch:
        return QUEUE_UNKNOWN
    owner, name = repo.split("/", 1)
    if not owner or not name:
        return QUEUE_UNKNOWN
    try:
        result = gh_fn(
            [
                "api",
                "graphql",
                "-f",
                f"query={_MERGE_QUEUE_QUERY}",
                "-F",
                f"owner={owner}",
                "-F",
                f"repo={name}",
                "-F",
                f"branch={branch}",
            ]
        )
        if getattr(result, "returncode", 1) != 0:
            return QUEUE_UNKNOWN
        payload = json.loads(getattr(result, "stdout", "") or "")
    except Exception:
        return QUEUE_UNKNOWN

    if not isinstance(payload, dict) or payload.get("errors"):
        return QUEUE_UNKNOWN
    data = payload.get("data")
    if not isinstance(data, dict):
        return QUEUE_UNKNOWN
    repository = data.get("repository")
    if not isinstance(repository, dict) or "mergeQueue" not in repository:
        return QUEUE_UNKNOWN
    queue = repository["mergeQueue"]
    if queue is None:
        return QUEUE_ABSENT
    if isinstance(queue, dict) and queue.get("id"):
        return QUEUE_ACTIVE
    return QUEUE_UNKNOWN


def _gh_subprocess(args):
    return subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _main(argv):
    if len(argv) == 4 and argv[1] == "merge-queue-capability":
        print(merge_queue_capability(argv[2], argv[3], _gh_subprocess))
        return 0
    print(
        "usage: _pr_scan.py merge-queue-capability OWNER/REPO BRANCH",
        file=sys.stderr,
    )
    return 2


# ── STALE-BASE GATE ───────────────────────────────────────────────────────────────────────────
# A PR that is mergeable + CI-green can STILL be poison: if it branched from an old base, merging it
# silently REVERTS work that landed on the base since — under an innocent title. That is exactly the
# #111 incident: a "Bhagavad Gita chapters" CONTENT PR, branched weeks back, reverted 23 daemon files
# (model-tiering, proprioception, route/converge/watchdog) the moment it merged. CI was green because
# CI ran on its own stale tree. ([[pr111-daemon-regression-healed]] [[live-checkout-is-chaotic]])
#
# The cure, shared by BOTH organs so they stay "two halves of one verdict": before treating a
# mergeable PR as READY, refuse it if merging would revert work — and route it to a rebase-onto-current
# heal task that KEEPS the PR's genuine changes and DROPS only the reverting hunks. No unique work is
# lost; the branch is absorbed toward current ideal form, then merged. Two tiers:
#   • STALE-CORE — the PR touches the daemon BODY (code/orchestration) AND is not current with base.
#     Core changes must ALWAYS be current before merge; any staleness — or a base we can't verify —
#     is refused. Near-zero false positives (core-touching PRs are rare; a stale one is precisely the
#     danger). This is the surgical #111 guard.
#   • STALE-BASE — a generic PR branched far enough behind base (≥ LIMEN_STALE_BASE_MAX) to risk a
#     silent revert. Repo-agnostic backstop; fails open to "available" so a transient API error never
#     strands a healthy content PR.

# The daemon's BODY — the code/orchestration that IS the organism, vs. content (courses/corpus/
# studium/docs/tasks.yaml). DERIVED default, env-overridable (LIMEN_PROTECTED_PATHS), so a relocation
# or layout change re-tunes it without a hardcode edit ([[derive-never-pin-hardcodes]]).
_DEFAULT_PROTECTED = (
    "cli/src/limen/*",
    "mcp/src/*",
    "web/api/*",
    "scripts/*.py",
    "scripts/*.sh",
    "container/*",
)
STALE_BASE_MAX_DEFAULT = 10


def protected_globs():
    raw = os.environ.get("LIMEN_PROTECTED_PATHS", "")
    return [p.strip() for p in raw.split(",") if p.strip()] or list(_DEFAULT_PROTECTED)


def repo_is_conductor(repo):
    """True for the repo(s) where the protected globs denote the live daemon body. Default: the
    `limen` conductor repo (nameWithOwner endswith /limen); LIMEN_CONDUCTOR_REPOS extends it to
    other code repos sharing the layout. Other repos skip the core gate (no per-repo false positives)."""
    raw = os.environ.get("LIMEN_CONDUCTOR_REPOS", "")
    listed = [r.strip() for r in raw.split(",") if r.strip()]
    if listed:
        return repo in listed
    return repo.split("/")[-1].lower() == "limen"


def touches_protected(repo, paths):
    """Does this PR's changed-file set include any daemon-body path in a conductor repo?"""
    if not repo_is_conductor(repo):
        return False
    globs = protected_globs()
    return any(any(fnmatch.fnmatch(p, g) for g in globs) for p in paths if p)


def pr_behind_by(repo, base, head, gh_fn):
    """Commits the PR's base is AHEAD of its head = how STALE the branch is. One `gh api compare`
    call. Returns an int ≥ 0, or -1 when it can't be determined (missing refs / API error / fork)."""
    if not base or not head:
        return -1
    try:
        r = gh_fn(["api", f"repos/{repo}/compare/{base}...{head}", "--jq", ".behind_by"])
        if getattr(r, "returncode", 1) != 0:
            return -1
        return int((getattr(r, "stdout", "") or "").strip())
    except Exception:
        return -1


def stale_base_verdict(repo, paths, base, head, gh_fn, generic_max=None):
    """Decide whether an otherwise-READY PR must be rebased before it can safely merge.
    Returns "STALE-CORE", "STALE-BASE", or None (safe). Bounded: ONE compare call, only invoked for
    ready candidates. The asymmetry is deliberate — the catastrophic case (reverting the body) is
    fully guarded even when the base is unverifiable; the low-stakes generic case stays available."""
    if generic_max is None:
        try:
            generic_max = int(os.environ.get("LIMEN_STALE_BASE_MAX", STALE_BASE_MAX_DEFAULT))
        except ValueError:
            generic_max = STALE_BASE_MAX_DEFAULT
    behind = pr_behind_by(repo, base, head, gh_fn)
    if touches_protected(repo, paths):
        # core change: must be CURRENT. behind>0 (stale) OR behind<0 (unverifiable) ⇒ rebase first.
        return None if behind == 0 else "STALE-CORE"
    # generic PR: only flag when it branched FAR behind base. Unverifiable (-1) stays available.
    return "STALE-BASE" if behind >= generic_max else None


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
