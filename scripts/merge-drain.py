#!/usr/bin/env python3
"""merge-drain.py — the MISSING merge organ of the heartbeat.

The loop lands PRs every beat (dispatch + jules-land) but nothing ever MERGED them, so
open PRs piled up until a human ran a manual drain. This makes merge autonomic: every
drain beat it merges the PRs that are genuinely READY (mergeable + CI-green), surfaces
the blocked ones, and NEVER force-merges. Bounded per run so it never dominates a beat.
Idempotent and concurrency-safe: if another agent already merged a PR, gh reports it and
we count it, no error. Touches only GitHub — not tasks.yaml ownership or agent worktrees —
so it cannot race the dispatcher.

  --scan N    max open PRs to assess this run (default 30)
  --limit N   max PRs to merge this run   (default 10)
  --dry-run   assess + report only
"""
import argparse, json, subprocess, sys, datetime, concurrent.futures as cf
from pathlib import Path

OWNERS = ["organvm", "4444J99"]
LOG = Path(__file__).resolve().parent.parent / "logs" / "merge-drain.log"

def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)

def open_prs(scan):
    r = gh(["search", "prs", "--author", "@me", "--state", "open", "--limit", str(scan),
            *sum([["--owner", o] for o in OWNERS], []),
            "--json", "number,repository"])
    if r.returncode != 0:
        return []
    return [(p["repository"]["nameWithOwner"], p["number"]) for p in json.loads(r.stdout or "[]")]

def _is_trivial(repo, num):
    """True if the PR diff is a no-op / pure reformat (whitespace or line-ending only) or empty — the
    'green-checkmark noise' class (e.g. a CIFIX that only normalized CRLF->LF, showing 436/436 lines).
    A VALUE gate ON TOP of the CI gate: refuse to auto-merge these. Conservative + fail-open: any real
    content change, or any error fetching the diff, -> NOT trivial (defer to the existing CI gate)."""
    r = gh(["pr", "diff", str(num), "-R", repo], timeout=60)
    if r.returncode != 0:
        return False
    added, removed = [], []
    for ln in r.stdout.splitlines():
        if ln.startswith(("+++", "---", "diff ", "index ", "@@", "old mode", "new mode",
                          "similarity", "rename", "deleted file", "new file", "Binary")):
            continue
        if ln.startswith("+"):
            added.append(ln[1:].strip())
        elif ln.startswith("-"):
            removed.append(ln[1:].strip())
    if not added and not removed:
        return True  # empty diff
    # added==removed after stripping whitespace/EOL -> no net content change -> pure reformat no-op
    return sorted(x for x in added if x) == sorted(x for x in removed if x)

def assess(rn):
    repo, num = rn
    try:
        r = gh(["pr", "view", str(num), "-R", repo, "--json",
                "mergeable,mergeStateStatus,state,statusCheckRollup,isDraft"], timeout=40)
        if r.returncode != 0:
            return (repo, num, "ERR")
        d = json.loads(r.stdout)
        if d.get("state") != "OPEN" or d.get("isDraft"):
            return (repo, num, "SKIP")
        states = [(c.get("conclusion") or c.get("state") or "") for c in (d.get("statusCheckRollup") or [])]
        if any(s in ("FAILURE","ERROR","CANCELLED","TIMED_OUT","ACTION_REQUIRED") for s in states):
            return (repo, num, "CI-RED")
        if any(s in ("PENDING","IN_PROGRESS","QUEUED","EXPECTED","") for s in states):
            return (repo, num, "CI-PENDING")
        if d.get("mergeable") == "CONFLICTING":
            return (repo, num, "CONFLICT")
        if d.get("mergeable") == "MERGEABLE":
            if _is_trivial(repo, num):
                return (repo, num, "TRIVIAL")  # CI-green but no-op/reformat — value gate refuses it
            return (repo, num, "READY")
        return (repo, num, "BLOCKED")
    except Exception:
        return (repo, num, "ERR")

def merge(repo, num):
    for m in ("--squash", "--merge", "--rebase"):
        r = gh(["pr", "merge", str(num), "-R", repo, m, "--delete-branch"], timeout=90)
        out = (r.stdout + r.stderr).lower()
        if r.returncode == 0 or "merged" in out:
            return True
        if "not allowed" in out or "not enabled" in out:
            continue
        return False
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", type=int, default=30)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    prs = open_prs(a.scan)
    if not prs:
        print("[merge-drain] no open PRs (or gh unavailable)"); return
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(assess, prs))
    import collections
    b = collections.Counter(r[2] for r in rows)
    ready = [(r[0], r[1]) for r in rows if r[2] == "READY"][:a.limit]
    merged = []
    if not a.dry_run:
        for repo, num in ready:
            if merge(repo, num):
                merged.append(f"{repo}#{num}")
    ts = datetime.datetime.now().strftime("%F %T")
    summary = (f"[merge-drain] {ts} scanned={len(prs)} ready={b['READY']} "
               f"merged={len(merged)} trivial-skipped={b['TRIVIAL']} | blocked: conflict={b['CONFLICT']} "
               f"ci-red={b['CI-RED']} ci-pending={b['CI-PENDING']}")
    print(summary)
    try:
        with open(LOG, "a") as f:
            f.write(summary + (("  " + " ".join(merged)) if merged else "") + "\n")
    except Exception:
        pass

if __name__ == "__main__":
    main()
