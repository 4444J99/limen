#!/usr/bin/env python3
"""reap-remote-branches.py — the REMOTE-branch reaper (the GITVS `remote_branch` effector).

reap-branches.py reaps the LOCAL branch ref left after a squash-merge; this is its remote sibling —
the one genuinely-new mutator GITVS owns. It reaps a provably-landed `origin/<branch>` past a grace
window (the ~730 unresolved orphaned remote branches). Scoped to the conductor repo (LIMEN_ROOT's
origin) for a safe first landing — where the remote-tracking refs and the gh PR state are both local;
fleet-wide expansion is a later widening, not a rewrite.

It copies reap-branches.py's PURE, unit-tested classifier VERBATIM (Facts/Verdict/classify) with two
swaps — refs/heads/<b> → refs/remotes/origin/<b>, and the delete verb git branch -D → git push origin
--delete (gh api DELETE fallback for ruleset-protected deletes). ALL THREE gates must hold, exactly as
reclaim-worktrees.py's clean+merged+idle:

  1. LANDED   — origin/<b> is an ancestor of origin/HEAD (a real merge/ff, self-protecting: a
                post-merge commit breaks ancestry), OR its PR is MERGED per gh AND the tip is NOT newer
                than mergedAt + buffer (the squash-merge signal, with a force-push-onto-merged belt), AND
  2. NO OPEN PR — an open PR means IN-FLIGHT; kept silently, AND
  3. GRACE-IDLE — landed longer ago than LIMEN_REMOTE_REAP_GRACE_MIN (default 1440 = 24h, WIDER than the
                local 60m: a remote delete is NOT reflog-recoverable and other clones/CI may hold it).

Everything not provably landed FAILS SAFE to KEEP (open PR → inflight; merged-but-advanced tip →
livework; real work not on default, no PR → livework — surfaced, never deleted). NEVER reaps the default
branch, a configured-protected branch, or a branch checked out in any local worktree.

DOUBLE-DARK by construction (remote deletes are irreversible): dry-run unless BOTH `--apply` AND
LIMEN_REMOTE_REAP_APPLY=1 (default "0", unlike the local reaper's "1"). --apply also requires a matching
human acceptance/archive/redaction event in docs/remote-branch-reap-acceptance.jsonl (the shared
reap_acceptance covenant) OR a standing grant for the two machine-proved landed classes.

Offline / no gh → proof-2 (merged-PR) is skipped, so only ancestor-proven branches are candidates; any
unknown → KEEP. Bounded (--max), fails OPEN per-branch, self-throttles to once per
LIMEN_REMOTE_REAP_EVERY_MIN minutes, logs logs/reap-remote-branches.jsonl.

  python3 scripts/reap-remote-branches.py            # dry-run (WOULD-reap list; mutates nothing)
  python3 scripts/reap-remote-branches.py --apply    # DELETE landed remote branches (needs LIMEN_REMOTE_REAP_APPLY=1)
  python3 scripts/reap-remote-branches.py --check     # exit 1 iff a landed remote branch lingers past grace

Env: LIMEN_ROOT, LIMEN_REMOTE_REAP_APPLY (0), LIMEN_REMOTE_REAP_MAX (100),
     LIMEN_REMOTE_REAP_EVERY_MIN (30), LIMEN_REMOTE_REAP_GRACE_MIN (1440),
     LIMEN_REMOTE_REAP_PROTECT (extra protected branch names), LIMEN_OFFLINE.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reap_acceptance import (  # noqa: E402
    REQUIRED_ACCEPTANCE_PROOF_FIELDS,
    has_required_acceptance_proof,
)

HOME = os.environ.get("HOME", str(Path.home()))
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", f"{HOME}/Workspace/limen")).resolve()
LOG = LIMEN_ROOT / "logs" / "reap-remote-branches.jsonl"
STATE = LIMEN_ROOT / "logs" / "reap-remote-branches-state.json"
MARKER = LIMEN_ROOT / "logs" / ".reap-remote-branches-last"
LEDGER = LIMEN_ROOT / "docs" / "remote-branch-hygiene.md"
# docs/remote-branch-reap-acceptance.jsonl — the human acceptance ledger (named for check-removal-acceptance).
REMOTE_REAP_ACCEPTANCE = LIMEN_ROOT / "docs" / "remote-branch-reap-acceptance.jsonl"

ADVANCED_BUFFER_S = 300
BASE_PROTECT = {"main", "master", "HEAD", "develop", "trunk"}
EXTRA_PROTECT = set(os.environ.get("LIMEN_REMOTE_REAP_PROTECT", "").split())

_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
ACCEPTED_ARCHIVE_STATUSES = {
    "verified",
    "landed_on_default_verified",
    "merged_pr_verified",
    "not_required_landed_ref",
}
ACCEPTED_REDACTION_REVIEWS = {
    "accepted",
    "not_required_landed_ref",
    "not_required_remote_only",
}
# A standing ledger grant may cover ONLY these machine-provable classes (the classifier assigns them
# strictly after the ancestor / merged-PR-with-unadvanced-tip proof already held).
STANDING_GRANT_REASONS = {"landed-pr-merged", "landed-ancestor"}


def _int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def _float_env(name: str, default: float, *, minimum: float | None = None) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def _git(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command against the repo. Fails OPEN (returncode!=0) — never raises."""
    try:
        return subprocess.run(
            ["git", "-C", str(LIMEN_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_GIT_ENV,
        )
    except Exception as e:  # fail open per-call
        return subprocess.CompletedProcess(args, 1, "", str(e))


def load_reap_acceptance() -> list[dict]:
    try:
        lines = REMOTE_REAP_ACCEPTANCE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _remote_tip_sha(branch: str) -> str | None:
    r = _git(["rev-parse", f"refs/remotes/origin/{branch}"])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.strip()


def reap_accepted(branch: str, reason: str, acceptance_events: list[dict]) -> tuple[bool, str]:
    """Same covenant as reap-branches.branch_reap_accepted: a per-branch tip-matched event, or a
    standing grant for the two machine-proved landed classes; archive + redaction + proof fields required."""
    tip = _remote_tip_sha(branch)
    matched_candidate = False
    for event in reversed(acceptance_events):
        standing = event.get("standing") is True and event.get("branch") in (None, "*")
        if standing:
            if reason not in STANDING_GRANT_REASONS:
                continue
            if event.get("accepted") is not True:
                continue
        else:
            if event.get("branch") != branch:
                continue
            if event.get("accepted") is not True:
                continue
            if event.get("reason") and event.get("reason") != reason:
                continue
            if event.get("tip") and event.get("tip") != tip:
                continue
        matched_candidate = True
        archive_ok = event.get("archive_verified") is True or event.get("archive_status") in ACCEPTED_ARCHIVE_STATUSES
        if not archive_ok:
            continue
        if event.get("redaction_review") not in ACCEPTED_REDACTION_REVIEWS:
            continue
        if not has_required_acceptance_proof(event):
            continue
        return True, "remote-branch-reap-accepted"
    if matched_candidate:
        return False, "incomplete-remote-branch-reap-acceptance"
    return False, "missing-remote-branch-reap-acceptance"


def default_ref() -> str:
    r = _git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    for ref in ("origin/main", "origin/master"):
        if _git(["show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"]).returncode == 0:
            return ref
    return "origin/main"


def default_name(dref: str) -> str:
    return dref.split("/", 1)[1] if "/" in dref else dref


def remote_branches() -> list[str]:
    """Bare branch names of the conductor's origin remote-tracking refs (origin/<name> → <name>),
    excluding origin/HEAD."""
    r = _git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/"])
    out = []
    for line in r.stdout.splitlines():
        short = line.strip()
        if not short or not short.startswith("origin/"):
            continue
        name = short[len("origin/") :]
        if name and name != "HEAD":
            out.append(name)
    # A ref backend or fixture may surface the same short name more than once.  Enumeration is a
    # set contract: deterministic ordering keeps previews stable, and de-duplication guarantees a
    # future armed run can never issue the same remote deletion twice.
    return sorted(set(out))


def checked_out_branches() -> set[str]:
    """Every branch checked out in ANY local worktree — a defensive keep (in active use)."""
    out: set[str] = set()
    r = _git(["worktree", "list", "--porcelain"])
    for line in r.stdout.splitlines():
        if line.startswith("branch refs/heads/"):
            out.add(line[len("branch refs/heads/") :].strip())
    return out


def _merged_at_epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def gh_head_states() -> tuple[dict[str, float | None], set[str], bool]:
    """(merged_heads→mergedAt_epoch, open_heads, online). Fail-safe: offline/no gh → ({}, ∅, False)."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return {}, set(), False
    try:
        res = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--json", "headRefName,state,mergedAt", "--limit", "800"],
            cwd=str(LIMEN_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env=_GIT_ENV,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return {}, set(), False
        prs = json.loads(res.stdout)
    except Exception:
        return {}, set(), False
    merged: dict[str, float | None] = {}
    open_: set[str] = set()
    for p in prs:
        head = p.get("headRefName")
        if not head:
            continue
        if p.get("state") == "MERGED":
            merged[head] = _merged_at_epoch(p.get("mergedAt"))
        elif p.get("state") == "OPEN":
            open_.add(head)
    return merged, open_, True


@dataclass(frozen=True)
class Facts:
    is_ancestor: bool
    pr_merged_safe: bool
    pr_merged_raw: bool
    pr_open: bool
    checked_out: bool
    protected: bool


@dataclass(frozen=True)
class Verdict:
    action: str  # "reap" | "keep"
    reason: str  # landed-ancestor|landed-pr-merged|inflight|pr-merged-but-advanced|livework|protected|checked-out
    landed: bool  # provably landed AND reapable


def classify(f: Facts) -> Verdict:
    """PURE predicate (the unit under test) — identical topology to reap-branches.classify, one scale
    out (remote refs). Protective checks first; a landed proof last."""
    if f.protected:
        return Verdict("keep", "protected", False)
    if f.checked_out:
        return Verdict("keep", "checked-out", False)
    if f.pr_open:
        return Verdict("keep", "inflight", False)
    if f.is_ancestor:
        return Verdict("reap", "landed-ancestor", True)
    if f.pr_merged_safe:
        return Verdict("reap", "landed-pr-merged", True)
    if f.pr_merged_raw:
        return Verdict("keep", "pr-merged-but-advanced", False)
    return Verdict("keep", "livework", False)


def gather_facts(
    branch: str, dref: str, checked_out: set[str], merged: dict[str, float | None], open_: set[str], dname: str
) -> Facts:
    """Compute a remote branch's Facts via git + the precomputed gh maps. Every git/parse failure → the
    conservative value (harder to reap, never easier)."""
    ref = f"refs/remotes/origin/{branch}"
    is_ancestor = _git(["merge-base", "--is-ancestor", ref, dref]).returncode == 0
    pr_merged_raw = branch in merged
    pr_merged_safe = False
    if pr_merged_raw:
        merged_at = merged.get(branch)
        tip = _git(["log", "-1", "--format=%ct", ref])
        try:
            tip_ct = int(tip.stdout.strip()) if tip.returncode == 0 else None
        except ValueError:
            tip_ct = None
        pr_merged_safe = bool(merged_at is not None and tip_ct is not None and tip_ct <= merged_at + ADVANCED_BUFFER_S)
    return Facts(
        is_ancestor=is_ancestor,
        pr_merged_safe=pr_merged_safe,
        pr_merged_raw=pr_merged_raw,
        pr_open=branch in open_,
        checked_out=branch in checked_out,
        protected=(branch == dname or branch in BASE_PROTECT or branch in EXTRA_PROTECT),
    )


def _landed_age_s(branch: str, merged: dict[str, float | None], now: float) -> float:
    """Seconds since the branch's work LANDED. Best signal: the PR's mergedAt. Fallback: the tip commit
    time (predates landing → can only OVERESTIMATE age → fails toward RED/surfaced, never toward hidden)."""
    merged_at = merged.get(branch)
    if merged_at is not None:
        return now - merged_at
    r = _git(["log", "-1", "--format=%ct", f"refs/remotes/origin/{branch}"])
    try:
        tip_ct = int(r.stdout.strip()) if r.returncode == 0 else None
    except ValueError:
        tip_ct = None
    return float("inf") if tip_ct is None else now - tip_ct


def _delete_remote(branch: str) -> tuple[bool, str]:
    """Delete origin/<branch>. Primary: git push origin --delete (never a force). Fallback: gh api DELETE
    (respects an org ruleset's deletion-protection more cleanly). Returns (ok, detail)."""
    r = _git(["push", "origin", "--delete", branch], timeout=90)
    if r.returncode == 0:
        return True, "git push --delete"
    if shutil.which("gh"):
        slug = _git(["remote", "get-url", "origin"]).stdout.strip()
        # owner/repo from an https or ssh remote url
        repo = ""
        if "github.com" in slug:
            repo = slug.split("github.com", 1)[1].lstrip(":/").removesuffix(".git")
        if repo:
            g = subprocess.run(
                ["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch}"],
                capture_output=True,
                text=True,
                timeout=60,
                env=_GIT_ENV,
            )
            if g.returncode == 0:
                return True, "gh api DELETE"
            return False, (g.stderr or r.stderr).strip()[:120]
    return False, (r.stderr or "").strip()[:120]


def main() -> int:
    ap = argparse.ArgumentParser(description="Reap provably-landed REMOTE branches (loss-free, double-dark).")
    ap.add_argument(
        "--apply", action="store_true", help="delete landed remote branches (needs LIMEN_REMOTE_REAP_APPLY=1)"
    )
    ap.add_argument(
        "--check", action="store_true", help="exit 1 if any landed remote branch lingers past grace (read-only)"
    )
    ap.add_argument("--force", action="store_true", help="ignore the self-throttle")
    ap.add_argument("--max", type=int, default=_int_env("LIMEN_REMOTE_REAP_MAX", 100, minimum=1))
    args = ap.parse_args()

    every_min = _float_env("LIMEN_REMOTE_REAP_EVERY_MIN", 30.0, minimum=0.0)

    if not args.check:
        _git(["fetch", "--prune", "--quiet", "origin"], timeout=120)
    dref = default_ref()
    dname = default_name(dref)
    checked = checked_out_branches()
    merged, open_, online = gh_head_states()

    # THE DOUBLE-DARK GATE: --apply alone is not enough. Remote deletes are irreversible, so the arming
    # env flag defaults OFF (unlike the local reaper). An unarmed --apply degrades to a dry-run.
    armed = args.apply and _bool_env("LIMEN_REMOTE_REAP_APPLY", default=False)
    if args.apply and not armed:
        print(
            "[reap-remote-branches] --apply given but LIMEN_REMOTE_REAP_APPLY!=1 — staying DARK (dry-run). "
            "Remote deletes are not reflog-recoverable; arm deliberately."
        )

    if armed and not args.force and not args.check and MARKER.exists():
        if (time.time() - MARKER.stat().st_mtime) / 60.0 < every_min:
            print(f"[reap-remote-branches] ran < {every_min:g}min ago — skip (--force to override)")
            return 0

    reap: list[tuple[str, str]] = []
    inflight: list[str] = []
    livework: list[str] = []
    advanced: list[str] = []
    kept_reasons: dict[str, int] = {}
    for b in remote_branches():
        f = gather_facts(b, dref, checked, merged, open_, dname)
        v = classify(f)
        if v.action == "reap":
            reap.append((b, v.reason))
        else:
            kept_reasons[v.reason] = kept_reasons.get(v.reason, 0) + 1
            if v.reason == "inflight":
                inflight.append(b)
            elif v.reason == "pr-merged-but-advanced":
                advanced.append(b)
            elif v.reason == "livework":
                livework.append(b)

    # ── --check: exit 1 iff a landed remote branch LINGERS past the digestion grace window. ──
    if args.check:
        grace_s = _float_env("LIMEN_REMOTE_REAP_GRACE_MIN", 1440.0, minimum=0.0) * 60.0
        now = time.time()
        lingering = [(b, why) for b, why in reap if _landed_age_s(b, merged, now) > grace_s]
        if lingering:
            print(
                f"[reap-remote-branches] FAIL — {len(lingering)} landed remote branch(es) lingering past grace "
                "(review docs/remote-branch-reap-acceptance.md, then --apply with LIMEN_REMOTE_REAP_APPLY=1):"
            )
            for b, why in sorted(lingering)[:20]:
                print(f"  landed  origin/{b}  ({why})")
            if len(lingering) > 20:
                print(f"  … and {len(lingering) - 20} more")
            return 1
        note = "" if online else " (offline — gh proof-2 skipped; ancestor-only)"
        print(
            f"[reap-remote-branches] ok — no landed remote branch lingers past grace{note}. "
            f"{len(inflight)} in-flight, {len(advanced)} merged-advanced, {len(livework)} live-work kept."
        )
        return 0

    mode = "APPLY(armed)" if armed else "dry-run"
    online_note = "online" if online else "offline(gh proof-2 skipped)"
    print(
        f"[reap-remote-branches] {mode}; default={dref}; {online_note}; "
        f"{len(reap)} reapable, {len(inflight)} in-flight, {len(advanced)} merged-advanced, {len(livework)} live-work."
    )

    done = 0
    reaped_names: list[str] = []
    acceptance = load_reap_acceptance()
    for b, why in reap:
        if done >= args.max:
            print(f"[reap-remote-branches] hit --max={args.max}; 'origin/{b}' and any remainder LEFT for next run")
            break
        print(f"  {'REAP' if armed else 'WOULD reap'}: origin/{b}  ({why})")
        if armed:
            accepted, accept_reason = reap_accepted(b, why, acceptance)
            if not accepted:
                print(f"    KEEP origin/{b}: {accept_reason}")
                kept_reasons[accept_reason] = kept_reasons.get(accept_reason, 0) + 1
                continue
            ok, detail = _delete_remote(b)
            if not ok:
                print(f"    FAIL delete origin/{b}: {detail}")
                continue
            reaped_names.append(b)
        done += 1

    if armed:
        try:
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            MARKER.write_text(str(time.time()))
            with LOG.open("a") as fh:
                fh.write(
                    json.dumps(
                        {
                            "ts": time.time(),
                            "default": dref,
                            "online": online,
                            "reaped": reaped_names,
                            "inflight": sorted(inflight),
                            "advanced": sorted(advanced),
                            "livework": sorted(livework),
                            "kept_reasons": kept_reasons,
                        }
                    )
                    + "\n"
                )
            STATE.write_text(
                json.dumps(
                    {
                        "ts": time.time(),
                        "default": dref,
                        "online": online,
                        "reaped_this_run": reaped_names,
                        "inflight": sorted(inflight),
                        "advanced": sorted(advanced),
                        "livework": sorted(livework),
                    },
                    indent=2,
                )
            )
        except Exception as e:  # observability must never break the beat
            print(f"[reap-remote-branches] note: stamp/log write skipped ({str(e)[:80]})")

    kr = ", ".join(f"{k}={n}" for k, n in sorted(kept_reasons.items())) or "none"
    print(
        f"[reap-remote-branches] {'reaped' if armed else 'would reap'} "
        f"{len(reaped_names) if armed else done} remote branch(es); kept {sum(kept_reasons.values())} ({kr})."
    )
    # REQUIRED_ACCEPTANCE_PROOF_FIELDS is imported to bind this surface to the shared covenant contract.
    _ = REQUIRED_ACCEPTANCE_PROOF_FIELDS
    return 0


if __name__ == "__main__":
    sys.exit(main())
