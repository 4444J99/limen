#!/usr/bin/env python3
"""reclaim-worktrees.py — the SPRAWL-RECLAIM organ.

The fleet creates ephemeral worktrees in TWO places and reaps neither; left alone they
accumulate (the dispatch root hit 91 dirs / 3.4 GB; the interactive root leaked ~50 GB /
21 worktrees on 2026-06-26). This organ reaps the ones that are *provably dead* — and ONLY
those:

  • clean working tree (no uncommitted or untracked changes), AND
  • HEAD/content is already merged into the remote default branch, every local patch is equivalent
    to default, or a clean+idle preservation receipt proves the PR is merged with no private patch
    marker, AND
  • idle for >= the root's min-age (so a task/session mid-run is never touched).
  • --apply also requires a matching human acceptance/redaction/archive event in
    docs/worktree-reclaim-acceptance.jsonl immediately before physical removal.

It scans every known creation site (the historical blind spot — see worktree-lifecycle-blind-spot):
  • LIMEN_WORKTREE_ROOT (Scratch-first, or $LIMEN_WORKDIR/.limen-worktrees fallback) — dispatch
    throwaway, min-age 6h.
  • LIMEN_RECLAIM_LEGACY_WORKTREE_ROOTS (default: ~/Workspace/.limen-worktrees) — historical
    dispatch throwaway roots scanned for cleanup after Scratch migration, min-age 6h.
  • LIMEN_ROOT/.claude/worktrees — EnterWorktree / bg-job / interactive cells, min-age 24h.
  • LIMEN_AGY_SCRATCH_ROOT (~/.gemini/antigravity-cli/scratch) — Antigravity/Agy scratch clones,
    min-age LIMEN_AGY_SCRATCH_MIN_IDLE_H.
  • repo-local .worktrees roots discovered under LIMEN_RECLAIM_WORKSPACE_ROOTS.
  • registered git worktrees from LIMEN_RECLAIM_MAIN_REPOS (default: Limen and Portvs).
Set LIMEN_RECLAIM_CLAUDE_WT=0 to disable the interactive sweep.

It is LOSS-FREE by construction (those three gates) and FAILS OPEN: any error on one dir is
logged and skipped, never aborting the rest ("never a silent no"). It NEVER reaps the live
checkout (LIMEN_ROOT) nor the worktree it is itself running from. It removes registered
worktrees via `git worktree remove` (never rm) and standalone clones via rmtree. Bounded per
run (LIMEN_RECLAIM_MAX); if it hits the cap it LOGS the remainder rather than silently dropping.

Dry-run by default; pass --apply to execute. Use --check --json for a structured non-mutating
candidate receipt. Self-throttles to once per
LIMEN_RECLAIM_EVERY_MIN minutes so it is cheap to call every beat.

Env: LIMEN_WORKTREE_ROOT, LIMEN_RECLAIM_MIN_AGE_H (6), LIMEN_RECLAIM_CLAUDE_WT (1),
     LIMEN_RECLAIM_LEGACY_DISPATCH_WT, LIMEN_RECLAIM_LEGACY_WORKTREE_ROOTS,
     LIMEN_RECLAIM_LEGACY_DISPATCH_AGE_H,
     LIMEN_RECLAIM_CLAUDE_AGE_H (24), LIMEN_RECLAIM_REPO_LOCAL_WT, LIMEN_RECLAIM_REPO_LOCAL_AGE_H,
     LIMEN_RECLAIM_AGY_SCRATCH, LIMEN_AGY_SCRATCH_ROOT, LIMEN_AGY_SCRATCH_MIN_IDLE_H,
     LIMEN_RECLAIM_REGISTERED_WT, LIMEN_RECLAIM_REGISTERED_AGE_H, LIMEN_RECLAIM_MAIN_REPOS,
     LIMEN_RECLAIM_WORKSPACE_ROOTS, LIMEN_RECLAIM_MAX (50), LIMEN_RECLAIM_EVERY_MIN (30).
"""

from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT / "cli" / "src"))

from reap_acceptance import (  # noqa: E402
    REQUIRED_ACCEPTANCE_PROOF_FIELDS as SHARED_REQUIRED_ACCEPTANCE_PROOF_FIELDS,
    has_required_acceptance_proof,
)
from limen.worktree_debt import is_generated_log_shell  # noqa: E402
from limen.worktree_roots import iter_worktree_targets  # noqa: E402

HOME = os.environ.get("HOME", "/Users/4jp")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


MAX_REMOVE = _int_env("LIMEN_RECLAIM_MAX", 50)
EVERY_MIN = _float_env("LIMEN_RECLAIM_EVERY_MIN", 30)
GENERATED_RECLAIM_MAX = _int_env("LIMEN_RECLAIM_GENERATED_MAX", 80)
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", f"{HOME}/Workspace/limen"))
AGY_SCRATCH_ROOT = Path(
    os.environ.get("LIMEN_AGY_SCRATCH_ROOT", f"{HOME}/.gemini/antigravity-cli/scratch")
)
LOG = LIMEN_ROOT / "logs" / "reclaim-worktrees.jsonl"
MARKER = LIMEN_ROOT / "logs" / ".reclaim-last"
RECLAIM_ACCEPTANCE = LIMEN_ROOT / "docs" / "worktree-reclaim-acceptance.jsonl"
RECLAIM_ACCEPTANCE_DOC = LIMEN_ROOT / "docs" / "worktree-reclaim-acceptance.md"
CHECK = "--check" in sys.argv
JSON_OUT = "--json" in sys.argv
APPLY = "--apply" in sys.argv and not CHECK
FORCE = "--force" in sys.argv  # ignore the throttle
GENERATED_ONLY = "--generated-only" in sys.argv
HELP = "--help" in sys.argv or "-h" in sys.argv
REMOTE_MERGED_LANES = {"remote-merged"}
REMOTE_MERGED_STATUSES = {"merged_pr_preserved"}
ACCEPTED_ARCHIVE_STATUSES = {
    "verified",
    "remote_merged_receipt_verified",
    "not_required_clean_merged_remote",
    "not_required_generated_residue",
}
ACCEPTED_REDACTION_REVIEWS = {
    "accepted",
    "private_archive_only",
    "not_required_remote_only",
    "not_required_generated_residue",
}
REQUIRED_ACCEPTANCE_PROOF_FIELDS = SHARED_REQUIRED_ACCEPTANCE_PROOF_FIELDS
GENERATED_CLEAN_PATHS = (
    "node_modules",
    ".venv",
    ".next",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".parcel-cache",
    ".turbo",
    "__pycache__",
)

# Never reap the live checkout nor the worktree this process is running from (else we yank
# the rug from under an active session). Resolved once; classify() honors it as a HARD skip.
try:
    _SELF_GUARD = {LIMEN_ROOT.resolve()}
    _cwd = Path.cwd().resolve()
    for _p in (_cwd, *_cwd.parents):
        if (_p / ".git").exists():
            _SELF_GUARD.add(_p)
            break
except Exception:
    _SELF_GUARD = {LIMEN_ROOT}


def git(args, cwd, timeout=30):
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # fail open per-dir
        r = subprocess.CompletedProcess(args, 1, "", str(e))
        return r


def active_async_task_prefixes() -> set[str]:
    runs = LIMEN_ROOT / "logs" / "async-runs"
    prefixes = set()
    for marker in runs.glob("*.running"):
        name = marker.name.split("__", 1)[0].strip().lower()
        if name:
            prefixes.add(name)
    return prefixes


def active_async_root(d: Path, active_prefixes: set[str]) -> bool:
    name = d.name.lower()
    return any(name.startswith(prefix) for prefix in active_prefixes)


def has_generated_payload(d: Path) -> bool:
    return any((d / path).exists() for path in GENERATED_CLEAN_PATHS)


def idle_enough(target, now: float) -> bool:
    min_age_h = getattr(target, "min_age_h", 0)
    try:
        return (now - target.path.stat().st_mtime) / 3600.0 >= float(min_age_h)
    except (OSError, TypeError, ValueError):
        return False


def purge_generated_payloads(d: Path) -> tuple[bool, str]:
    r = git(["clean", "-Xdf", "--", *GENERATED_CLEAN_PATHS], d, timeout=180)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "git clean failed").strip()[:160]
    removed = sum(1 for line in (r.stdout or "").splitlines() if line.strip().startswith("Removing "))
    return True, f"removed:{removed}"


def reclaim_generated_payloads(targets) -> dict[str, object]:
    """Bounded, source-safe cleanup for retained worktrees.

    This removes only ignored generated payload paths from inactive git roots. It does not remove
    source files, untracked non-ignored files, worktree roots, branches, or private artifacts.
    """
    if os.environ.get("LIMEN_RECLAIM_GENERATED", "1") != "1":
        return {"enabled": False, "cleaned": [], "failed": []}
    active_prefixes = active_async_task_prefixes()
    now = time.time()
    cleaned, failed = [], []
    for target in targets:
        d = target.path
        try:
            if d.resolve() in _SELF_GUARD:
                continue
        except Exception:
            continue
        if len(cleaned) >= GENERATED_RECLAIM_MAX:
            break
        if active_async_root(d, active_prefixes):
            continue
        if not idle_enough(target, now):
            continue
        if not has_generated_payload(d):
            continue
        if git(["rev-parse", "--is-inside-work-tree"], d).returncode != 0:
            continue
        ok, detail = purge_generated_payloads(d)
        row = {"root": d.name, "detail": detail}
        if ok:
            cleaned.append(row)
        else:
            failed.append(row)
    return {"enabled": True, "cleaned": cleaned, "failed": failed}


def reachable_from_remote(cwd, head) -> bool:
    r = git(["for-each-ref", f"--contains={head}", "--format=%(refname)", "refs/remotes"], cwd)
    if r.returncode != 0:
        return False
    return bool(r.stdout.strip())


def remote_default_ref(cwd) -> str | None:
    r = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    for ref in ("origin/main", "origin/master"):
        if git(["show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"], cwd).returncode == 0:
            return ref
    return None


def merged_into_default(cwd, head) -> bool:
    ref = remote_default_ref(cwd)
    if not ref:
        return False
    return git(["merge-base", "--is-ancestor", head, ref], cwd).returncode == 0


def patch_equivalent_to_default(cwd) -> bool:
    ref = remote_default_ref(cwd)
    if not ref:
        return False
    r = git(["cherry", ref, "HEAD"], cwd)
    if r.returncode != 0:
        return False
    lines = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("-") for line in lines)


def inside_agy_scratch_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(AGY_SCRATCH_ROOT.expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


def load_preservation_receipts():
    path = LIMEN_ROOT / "docs" / "worktree-preservation-receipts.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    receipts = {}
    for receipt in data.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        root = receipt.get("root")
        if root:
            receipts[str(root)] = receipt
    return receipts


def load_reclaim_acceptance():
    try:
        lines = RECLAIM_ACCEPTANCE.read_text(encoding="utf-8", errors="replace").splitlines()
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


STANDING_ACCEPTANCE = os.environ.get("LIMEN_RECLAIM_STANDING_ACCEPTANCE", "1") != "0"
# PUSHED-REAP ESCAPE HATCH (LIMEN_RECLAIM_PUSHED_OK, declared in parameters.yaml). DEFAULT OFF —
# the standing policy is merge-before-reap: pushed preservation is not closure, so a pushed-but-
# unmerged worktree is KEPT as "not-merged-to-default" (enacted by test_reclaim_keeps_clean_pushed_
# unmerged_branch — the executable predicate wins over any aspirational default). This env is the
# opt-in lever that flips that class to reapable: when set, a clean, idle worktree whose HEAD is
# reachable from any remote ref (reachable_from_remote ⇒ every byte on origin, re-cloneable) is
# reaped as clean+pushed+idle — removing only the disposable LOCAL checkout; the branch and its
# PR/babysitting lifecycle continue on origin. This is how the pushed-but-unmerged backlog (the
# dominant boot-disk pin — hundreds of roots) drains toward the free-space target when the operator
# elects it. The unpushed/dirty/active guardrails are unchanged — unpreserved work is NEVER reaped.
PUSHED_OK = os.environ.get("LIMEN_RECLAIM_PUSHED_OK", "0") != "0"
# Operator standing grant (2026-07-09, docs/removal-acceptance-covenant.md §Standing grant):
# the loss-free class — clean tree + idle past min-age + preserved on the remote (merged into the
# default, patch-equivalent to it, a merged-PR receipt, or pushed-but-unmerged per PUSHED_OK) — is
# pre-accepted for removal without a per-root ledger event.
STANDING_ACCEPTANCE_REASONS = {"clean+merged+idle", "receipt-remote-merged+clean+idle", "clean+pushed+idle"}


def reclaim_accepted(path: Path, action: str, reason: str, acceptance_events) -> tuple[bool, str]:
    if STANDING_ACCEPTANCE and reason in STANDING_ACCEPTANCE_REASONS:
        return True, "standing-grant-2026-07-09"
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)
    for event in reversed(acceptance_events):
        if event.get("root") != path.name:
            continue
        if event.get("accepted") is not True:
            continue
        if event.get("action") and event.get("action") != action:
            continue
        if event.get("reason") and event.get("reason") != reason:
            continue
        if event.get("path") and event.get("path") != resolved:
            continue
        archive_ok = event.get("archive_verified") is True or event.get("archive_status") in ACCEPTED_ARCHIVE_STATUSES
        if not archive_ok:
            continue
        if event.get("redaction_review") not in ACCEPTED_REDACTION_REVIEWS:
            continue
        if not has_required_acceptance_proof(event):
            continue
        return True, "reclaim-accepted"
    return False, "missing-reclaim-acceptance"


def receipt_remote_merged(path: Path, preservation_receipts) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not isinstance(receipt, dict):
        return False
    if receipt.get("private_receipt") or receipt.get("private_patch_sha256"):
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    pr_state = str(receipt.get("pr_state") or "")
    pr_url = str(receipt.get("pr_url") or "")
    return (
        lane in REMOTE_MERGED_LANES
        and status in REMOTE_MERGED_STATUSES
        and pr_state == "MERGED"
        and pr_url.startswith("https://")
    )


def superproject(cwd) -> str | None:
    wl = git(["worktree", "list", "--porcelain"], cwd).stdout.splitlines()
    if wl and wl[0].startswith("worktree "):
        return wl[0].split(" ", 1)[1]
    return None


def classify(d: Path, now: float, min_age_h: float, preservation_receipts=None):
    """Return (action, reason). action in {remove-worktree, remove-clone, remove-residue, skip}."""
    preservation_receipts = preservation_receipts or {}
    try:
        if d.resolve() in _SELF_GUARD:
            return "skip", "self/live-checkout"
    except Exception:
        return "skip", "unresolved"
    if inside_agy_scratch_root(d):
        return "skip", "antigravity-scratch-uses-bridge-acceptance"
    if git(["rev-parse", "--is-inside-work-tree"], d).returncode != 0:
        if is_generated_log_shell(d):
            return "remove-residue", "generated-log-shell"
        return "skip", "not-a-git-dir"
    age_h = (now - d.stat().st_mtime) / 3600.0
    if age_h < min_age_h:
        return "skip", f"active(<{min_age_h:g}h, age={age_h:.1f}h)"
    if git(["status", "--porcelain"], d).stdout.strip():
        return "skip", "dirty"
    is_wt = (d / ".git").is_file()  # gitdir-pointer ⇒ registered worktree
    if receipt_remote_merged(d, preservation_receipts):
        return ("remove-worktree" if is_wt else "remove-clone"), "receipt-remote-merged+clean+idle"
    head = git(["rev-parse", "HEAD"], d).stdout.strip()
    patch_equivalent = patch_equivalent_to_default(d)
    if not head or (not reachable_from_remote(d, head) and not patch_equivalent):
        return "skip", "unpushed-commits"
    if not (merged_into_default(d, head) or patch_equivalent):
        # Reaching here means reachable_from_remote is True (else line above returned
        # unpushed-commits): the HEAD is preserved on origin, just not merged to default. Under the
        # operator's push-first rule this LOCAL checkout is loss-free to remove — the branch stays
        # on origin, resumable. Without PUSHED_OK, keep the conservative merged-only gate.
        if PUSHED_OK:
            return ("remove-worktree" if is_wt else "remove-clone"), "clean+pushed+idle"
        return "skip", "not-merged-to-default"
    return ("remove-worktree" if is_wt else "remove-clone"), "clean+merged+idle"


def persist_apply_receipt(
    *,
    started_ts,
    dirs,
    removed,
    skipped,
    failed,
    deferred,
    generated_reclaim,
):
    """Persist one strict apply receipt with a non-replayable completion timestamp."""
    completed_ts = time.time()
    if (
        isinstance(started_ts, bool)
        or not math.isfinite(float(started_ts))
        or float(started_ts) <= 0
        or not math.isfinite(completed_ts)
        or completed_ts <= 0
        or float(started_ts) > completed_ts
    ):
        raise ValueError("reclaim receipt timestamps must be finite, positive, and ordered")
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(str(completed_ts))
    with LOG.open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": float(started_ts),
                    "completed_ts": completed_ts,
                    "apply": True,
                    "scanned": len(dirs),
                    "removed": [name for name, _ in removed],
                    "skipped": dict(skipped),
                    "failed": dict(failed),
                    "deferred_over_cap": deferred,
                    "generated_reclaim": generated_reclaim,
                }
            )
            + "\n"
        )
    return completed_ts


def main():
    if HELP:
        print(
            "usage: reclaim-worktrees.py [--check] [--json] [--apply] [--force] [--generated-only]\n\n"
            "Dry-run by default. Use --check --json for structured inspection and --apply to remove "
            "accepted clean, idle, remote-preserved worktrees."
        )
        return 0
    # Every known creation site, each with its own idle gate. Missing roots simply disappear
    # from the target list; discovery must never block the heartbeat.
    targets = iter_worktree_targets(LIMEN_ROOT)
    if not targets:
        print("reclaim: no worktree roots present — nothing to do")
        return 0
    # self-throttle (skip silently if run recently, unless --force or dry-run inspection)
    if APPLY and not FORCE and MARKER.exists():
        if (time.time() - MARKER.stat().st_mtime) / 60.0 < EVERY_MIN:
            print(f"reclaim: ran < {EVERY_MIN}min ago — skip (set --force to override)")
            return 0
    now = time.time()
    generated_reclaim = (
        reclaim_generated_payloads(targets) if APPLY else {"enabled": False, "cleaned": [], "failed": []}
    )
    if GENERATED_ONLY:
        cleaned = generated_reclaim.get("cleaned") or []
        gen_failed = generated_reclaim.get("failed") or []
        if JSON_OUT:
            print(
                json.dumps(
                    {
                        "mode": "generated-only-apply" if APPLY else "generated-only-check",
                        "generated_reclaim": generated_reclaim,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        print(f"reclaim [generated-only]: {len(cleaned)} cleaned, {len(gen_failed)} failed")
        for row in cleaned[:20]:
            print(f"  generated-clean {row['detail']:14} {row['root']}")
        return 0
    preservation_receipts = load_preservation_receipts()
    reclaim_acceptance = load_reclaim_acceptance()
    dirs = [(target.path, target.min_age_h) for target in targets]
    removed, skipped, failed, deferred = [], [], [], []
    would_reclaim = []
    for d, min_age_h in dirs:
        action, reason = classify(d, now, min_age_h, preservation_receipts)
        if action == "skip":
            skipped.append((d.name, reason))
            continue
        if len(removed) >= MAX_REMOVE:
            deferred.append(d.name)
            continue  # bounded — but NOT silent (logged below)
        if not APPLY:
            accepted, accept_reason = reclaim_accepted(d, action, reason, reclaim_acceptance)
            if not accepted:
                skipped.append((d.name, accept_reason))
                continue
            removed.append((d.name, f"would-{action}:{reason}"))
            would_reclaim.append({"root": d.name, "path": str(d), "action": action, "reason": reason})
            continue
        accepted, accept_reason = reclaim_accepted(d, action, reason, reclaim_acceptance)
        if not accepted:
            skipped.append((d.name, accept_reason))
            continue
        try:
            if action == "remove-worktree":
                sp = superproject(d)
                base = sp if sp and Path(sp).resolve() != d.resolve() else d
                r = git(["worktree", "remove", "--force", str(d)], base)
                if r.returncode != 0:
                    failed.append((d.name, r.stderr.strip()[:120]))
                    continue
            else:
                shutil.rmtree(d)
            removed.append((d.name, f"{action}:{reason}"))
        except Exception as e:  # fail open
            failed.append((d.name, str(e)[:120]))

    if APPLY:
        try:
            persist_apply_receipt(
                started_ts=now,
                dirs=dirs,
                removed=removed,
                skipped=skipped,
                failed=failed,
                deferred=deferred,
                generated_reclaim=generated_reclaim,
            )
        except Exception:
            pass  # logging must never break the beat

    mode = "APPLY" if APPLY else "check" if CHECK else "dry-run"
    if JSON_OUT:
        print(
            json.dumps(
                {
                    "mode": mode,
                    "apply": APPLY,
                    "scanned": len(dirs),
                    "reclaimed": [{"root": root, "detail": detail} for root, detail in removed] if APPLY else [],
                    "would_reclaim": would_reclaim,
                    "kept_safe": [{"root": root, "reason": reason} for root, reason in skipped],
                    "failed": [{"root": root, "reason": reason} for root, reason in failed],
                    "deferred_over_cap": deferred,
                    "generated_reclaim": generated_reclaim,
                    "reapable_count": len(removed) if not APPLY else 0,
                    "reclaimed_count": len(removed) if APPLY else 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(
        f"reclaim [{mode}]: {len(removed)} reclaimed, {len(skipped)} kept-safe, "
        f"{len(failed)} failed, {len(deferred)} deferred-over-cap (of {len(dirs)})"
    )
    if generated_reclaim.get("enabled"):
        cleaned = generated_reclaim.get("cleaned") or []
        gen_failed = generated_reclaim.get("failed") or []
        print(f"  generated-payloads: {len(cleaned)} cleaned, {len(gen_failed)} failed")
        for row in cleaned[:10]:
            print(f"    generated-clean {row['detail']:14} {row['root']}")
    for n, why in skipped:
        print(f"  keep {why:24} {n}")
    for n, why in removed:
        print(f"  {'reclaimed' if APPLY else 'would'}: {n} ({why})")
    if deferred:
        print(
            f"  NOTE: {len(deferred)} dirs over the {MAX_REMOVE}-cap this run, next run takes them: "
            + ", ".join(deferred[:5])
            + ("…" if len(deferred) > 5 else "")
        )
    for n, why in failed:
        print(f"  FAIL {n}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
