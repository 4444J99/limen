#!/usr/bin/env python3
"""moat-audit.py — the standing predicate for the estate's lure + moat boundary.

Two questions, one exit code, across every value-tier repo:

  1. MOAT LEAK (hard fail): does a PUBLIC repo's tree contain the concrete
     private-VALUE signatures declared in `moat-guard.json` — the calibration,
     the curated dictionaries, the discovery source-map a competitor would
     steal? The interfaces/architecture stay public (the lure); only the tuned
     values are guarded. A leak in a public repo is exit-nonzero.

  2. LURE GAP (warn by default, fail under --strict): is a repo magnet-ready
     but dark — public with no positioning page, or authored-but-private
     (awaiting_publish), or missing a seed? A dark lure pulls zero inbound.

This is the sibling to generate-positioning.py's no-price guard: the boundary
is enforced by a runnable check, not remembered. Registry-owned — add a repo's
crown jewels to moat-guard.json, not to this script.

Exit 0 ⟺ no moat leaks (and, under --strict, no lure gaps).

Usage:
  scripts/moat-audit.py                 # audit all value-tier repos
  scripts/moat-audit.py --repo organvm/public-record-data-scrapper
  scripts/moat-audit.py --json          # machine-readable
  scripts/moat-audit.py --strict        # also fail on lure gaps
  scripts/moat-audit.py --no-visibility # skip gh api (offline; leak scan only)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Registries are CO-LOCATED with this script (same repo/worktree), so resolve
# script-relative — NOT via LIMEN_ROOT, which points at the live board root and
# would read a different (or missing) tree, making the audit fail OPEN. Each
# path is individually env-overridable so the predicate is hermetically testable.
ROOT = Path(__file__).resolve().parent.parent
MOAT_GUARD = Path(os.environ.get("LIMEN_MOAT_GUARD", ROOT / "moat-guard.json"))
VALUE_REPOS = Path(os.environ.get("LIMEN_VALUE_REPOS", ROOT / "value-repos.json"))
# One knob per fact: the same ACCESS registry gitvs parity/class-N and Rule #7 read.
ACCESS = Path(os.environ.get("LIMEN_GITVS_ACCESS", ROOT / "institutio" / "github" / "access.yaml"))
POSITIONING_SEEDS = Path(os.environ.get("LIMEN_POSITIONING_SEEDS", ROOT / "positioning-seeds.json"))
POSITIONING_DIR = Path(os.environ.get("LIMEN_POSITIONING_DIR", ROOT / "docs" / "positioning"))


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:  # a malformed registry must fail loud
        print(f"FATAL: {path.name} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)


def _slug(repo: str) -> str:
    """owner/name -> name (the positioning-page slug convention)."""
    return repo.split("/", 1)[-1]


def _granted_repos() -> set[str]:
    """Repos carrying partner grant rows in the ACCESS registry. A partner's eyes make the
    tree exposed, so these are audited regardless of visibility. Absent/unreadable → empty
    (the gitvs parity gate owns registry integrity, not this audit)."""
    try:
        import yaml
        grants = (yaml.safe_load(ACCESS.read_text(encoding="utf-8")) or {}).get("grants") or {}
        return {str(r) for r in grants}
    except Exception:
        return set()


def repo_secret_posture(repo: str) -> str | None:
    """Zero-policy probe: does the repo carry ANY Actions secrets. On a partner-granted repo
    any push collaborator can exfiltrate a repo secret via a workflow edit, so the policy is
    ZERO — re-home to org secrets with selected-repo scoping. Returns a posture literal only
    ('clean' / 'exposed'); no secret value, name, or count ever leaves this function."""
    res = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/secrets", "--jq", ".total_count"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        return None
    try:
        return "clean" if int(res.stdout.strip()) == 0 else "exposed"
    except ValueError:
        return None


def repo_visibility(repo: str) -> str:
    """'public' | 'private' | 'unknown' via gh api (best-effort, never raises)."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}", "--jq", ".private"],
            capture_output=True, text=True, timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    if out.returncode != 0:
        return "unknown"
    val = out.stdout.strip()
    if val == "true":
        return "private"
    if val == "false":
        return "public"
    return "unknown"


def clone_path(repo: str, clone_root: Path) -> Path | None:
    """Local clone at <clone_root>/<owner>/<name>, if present."""
    owner, name = repo.split("/", 1)
    candidate = clone_root / owner / name
    return candidate if (candidate / ".git").exists() else None


def scan_leaks(repo: str, guard: dict, clone_root: Path) -> dict:
    """git grep the clone's origin/main for each declared leak pattern.

    Scanning origin/main (not the working tree) audits exactly what is PUBLIC,
    independent of whatever branch the clone is parked on.
    """
    patterns = guard.get("leak_patterns", [])
    if not patterns:
        return {"status": "no_patterns", "hits": []}

    clone = clone_path(repo, clone_root)
    if clone is None:
        return {"status": "no_clone", "hits": []}

    # Prefer origin/main; fall back to main, then working tree.
    ref = None
    for candidate in ("origin/main", "main"):
        probe = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "--verify", "--quiet", candidate],
            capture_output=True, text=True,
        )
        if probe.returncode == 0:
            ref = candidate
            break

    scan_paths = guard.get("scan_paths", [])
    hits = []
    for pat in patterns:
        cmd = ["git", "-C", str(clone), "grep", "-lE", pat["regex"]]
        if ref:
            cmd.append(ref)
        else:
            cmd.append("--")  # working tree
        if scan_paths:
            if ref:
                cmd.append("--")
            cmd.extend(scan_paths)
        res = subprocess.run(cmd, capture_output=True, text=True)
        # git grep: 0 = match found (LEAK), 1 = clean, >1 = error
        if res.returncode == 0:
            files = [ln.split(":", 1)[-1] if ref else ln
                     for ln in res.stdout.strip().splitlines()]
            hits.append({"name": pat["name"], "why": pat["why"], "files": files})
    return {"status": "scanned", "ref": ref or "worktree", "hits": hits}


def lure_readiness(repo: str, visibility: str, seeded: bool, awaiting: bool) -> tuple[str, str]:
    """(verdict, detail) — is this repo pulling inbound, or dark?

    A private repo is 'dark' (no public lure). Otherwise the gap is the missing
    positioning surface — which is observable WITHOUT a visibility probe, so the
    predicate stays useful offline.
    """
    page = POSITIONING_DIR / f"{_slug(repo)}.md"
    has_page = page.exists()
    if visibility == "private":
        if awaiting:
            return "dark", "authored but private (awaiting_publish) — one flip from live"
        return "dark", "private repo — pulls zero inbound (no public lure)"
    # public OR unknown: the page absence is the gap either way.
    if not seeded:
        return "gap", "no positioning seed — un-positioned lure"
    if not has_page:
        return "gap", "seeded but no published positioning page"
    return "ready", "seeded + positioning page present"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="audit a single owner/name repo")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="also fail on lure gaps")
    ap.add_argument("--no-visibility", action="store_true", help="skip gh api probes (visibility + secrets)")
    ap.add_argument("--require-guard", action="store_true",
                    help="fail if an audited repo has no moat-guard entry (the evict-then-guard done-predicate)")
    args = ap.parse_args()

    # Fail LOUD if the boundary registry is absent — a moat audit that silently
    # finds no patterns would report "clean" while looking at nothing.
    if not MOAT_GUARD.exists():
        print(f"FATAL: moat-guard.json not found at {MOAT_GUARD} — the audit would "
              f"fail open. Set LIMEN_MOAT_GUARD or run from the repo.", file=sys.stderr)
        return 2

    guard_reg = _load(MOAT_GUARD)
    value_reg = _load(VALUE_REPOS)
    seeds = _load(POSITIONING_SEEDS).get("repos", {})

    clone_root = Path(os.path.expanduser(guard_reg.get("clone_root", "~/Workspace")))
    guard_repos = guard_reg.get("repos", {})

    granted = _granted_repos()
    if args.repo:
        repos = [args.repo]
    else:
        # Union of value-tier repos, any repo with a guard entry, and any partner-granted repo.
        repos = list(dict.fromkeys(value_reg.get("repos", []) + list(guard_repos.keys()) + sorted(granted)))

    results = []
    for repo in repos:
        visibility = "unknown" if args.no_visibility else repo_visibility(repo)
        guard = guard_repos.get(repo, {})
        seed = seeds.get(repo, {})
        # A partner's eyes make a private tree exposed — granted repos are always scanned.
        exposed = visibility != "private" or repo in granted
        leaks = scan_leaks(repo, guard, clone_root) if exposed else {"status": "private_skip", "hits": []}
        verdict, detail = lure_readiness(
            repo, visibility, seeded=bool(seed), awaiting=bool(seed.get("awaiting_publish")),
        )
        results.append({
            "repo": repo, "visibility": visibility,
            "granted": repo in granted,
            "guard_owed": repo in granted and not guard,
            "repo_secrets": (repo_secret_posture(repo) if repo in granted and not args.no_visibility else None),
            "leak_status": leaks["status"], "leaks": leaks["hits"],
            "leak_ref": leaks.get("ref"),
            "lure": verdict, "lure_detail": detail,
        })

    leaking = [r for r in results if r["leaks"]]
    lure_gaps = [r for r in results if r["lure"] in ("gap", "dark")]
    guard_owed = [r for r in results if r["guard_owed"]]
    secrets_exposed = [r for r in results if r["repo_secrets"] == "exposed"]
    guard_missing = [r for r in results if args.require_guard and not guard_repos.get(r["repo"])]

    if args.json:
        print(json.dumps({
            "results": results,
            "moat_leaks": len(leaking),
            "lure_gaps": len(lure_gaps),
            "guard_owed": [r["repo"] for r in guard_owed],
            "secrets_exposed": [r["repo"] for r in secrets_exposed],
        }, indent=2))
    else:
        print("MOAT + LURE AUDIT")
        print("=" * 68)
        for r in results:
            leak_mark = f"LEAK x{len(r['leaks'])}" if r["leaks"] else "clean"
            granted_mark = "  granted=partner" if r["granted"] else ""
            print(f"  {r['repo']}")
            print(f"      visibility={r['visibility']}  moat={leak_mark}  lure={r['lure']}{granted_mark}")
            if r["leaks"]:
                for h in r["leaks"]:
                    print(f"        ! {h['name']}: {h['files']}")
                    print(f"          {h['why']}")
            elif r["lure"] in ("gap", "dark"):
                print(f"        · {r['lure_detail']}")
            if r["guard_owed"]:
                print("        · granted repo without a moat-guard entry — evict-then-guard owed (CONST-*-MOAT)")
            if r["repo_secrets"] == "exposed":
                print("        ! Actions secrets present on a partner-granted repo — a push "
                      "collaborator can exfiltrate via a workflow edit; re-home to org secrets with "
                      "selected-repo scoping (L-PARTNER-GRANTS)")
        print("-" * 68)
        print(f"moat leaks: {len(leaking)}   lure gaps: {len(lure_gaps)}   "
              f"guard owed: {len(guard_owed)}   secrets exposed: {len(secrets_exposed)}")

    if leaking:
        if not args.json:
            print(f"\nFAIL — {len(leaking)} exposed repo(s) leak declared private values.", file=sys.stderr)
        return 1
    if secrets_exposed:
        if not args.json:
            print(f"\nFAIL — {len(secrets_exposed)} partner-granted repo(s) carry Actions secrets "
                  f"(zero-policy; re-home is L-PARTNER-GRANTS work).", file=sys.stderr)
        return 1
    if guard_missing:
        if not args.json:
            print(f"\nFAIL (--require-guard) — {len(guard_missing)} repo(s) without a moat-guard entry.",
                  file=sys.stderr)
        return 1
    if args.strict and lure_gaps:
        if not args.json:
            print(f"\nFAIL (--strict) — {len(lure_gaps)} lure gap(s).", file=sys.stderr)
        return 1
    if not args.json:
        print("\nPASS — no moat leaks" + (" and no lure gaps" if args.strict else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
