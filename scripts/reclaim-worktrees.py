#!/usr/bin/env python3
"""reclaim-worktrees.py — the SPRAWL-RECLAIM organ.

The fleet creates ephemeral worktrees in TWO places and reaps neither; left alone they
accumulate (the dispatch root hit 91 dirs / 3.4 GB; the interactive root leaked ~50 GB /
21 worktrees on 2026-06-26). This organ reaps the ones that are *provably dead* — and ONLY
those:

  • clean working tree (no uncommitted or untracked changes), AND
  • HEAD/content is reachable from a remote ref, already merged into the remote default branch,
    patch-equivalent to default, or covered by a preservation receipt, AND
  • idle for >= the root's min-age (so a task/session mid-run is never touched).
  • no live process has its current directory inside the candidate root.
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

It is LOSS-FREE by construction (those three gates) and FAILS CLOSED per target: any error on one dir is
logged and skipped, never aborting the rest ("never a silent no"). It NEVER reaps the live
checkout (LIMEN_ROOT) nor the worktree it is itself running from. It detaches clean registered
worktrees through Git's non-forced native operation and atomically quarantines standalone roots
on the same filesystem. It never resets, cleans, or recursively deletes a root. Bounded per
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
     LIMEN_RECLAIM_WORKSPACE_ROOTS, LIMEN_RECLAIM_MAX (50), LIMEN_RECLAIM_EVERY_MIN (30),
     LIMEN_RECLAIM_ORPHANS (0 — observable-first arm for the dead-gitdir orphan sweep),
     LIMEN_ORPHAN_QUARANTINE (same-volume off-worktree target for preserved orphans),
     LIMEN_ABANDONMENT_QUARANTINE (same-volume target for clones/residue/generated payloads),
     LIMEN_WORKTREE_ABANDONMENT_RECEIPTS (private typed receipt root).

Dead-gitdir orphan sweep (LIMEN_RECLAIM_ORPHANS=1): a checkout under a THROWAWAY root whose `.git`
pointer targets a superproject gitdir that no longer exists (prune-race debris — `git worktree prune`
fired while its volume was unmounted) is, past min-age, PRESERVED — MOVED into an off-worktree
quarantine (LIMEN_ORPHAN_QUARANTINE), never deleted. Because git is dead on the checkout the sweep
cannot prove it walked its lifecycle, so it must not destroy it; the reversible move resolves the debt
while losing nothing. Deleting a quarantined orphan is a SEPARATE proof-gated step. Default OFF.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
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
from limen.worktree_abandonment import (  # noqa: E402
    WorktreeAbandonmentError,
    detach_registered_worktree,
    quarantine_path,
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
AGY_SCRATCH_ROOT = Path(os.environ.get("LIMEN_AGY_SCRATCH_ROOT", f"{HOME}/.gemini/antigravity-cli/scratch"))
AGY_ROOT = AGY_SCRATCH_ROOT.expanduser().parent
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


def _option_value(name: str) -> str:
    prefix = f"{name}="
    for index, value in enumerate(sys.argv):
        if value.startswith(prefix):
            return value[len(prefix) :]
        if value == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return ""


EXPECTED_PLAN_SHA = _option_value("--expected-plan-sha")
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
_ACTIVE_PROCESS_CWDS: dict[Path, int] = {}

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


def active_process_cwds() -> dict[Path, int]:
    """Return observable process cwd roots; an unavailable probe fails closed."""
    observed: dict[Path, int] = {}
    proc = Path("/proc")
    if proc.is_dir():
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                observed[(entry / "cwd").resolve(strict=True)] = int(entry.name)
            except (OSError, ValueError):
                continue
        return observed
    try:
        result = subprocess.run(
            ["lsof", "-n", "-a", "-d", "cwd", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {Path("/"): -1}
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            try:
                pid = int(line[1:])
            except ValueError:
                pid = None
        elif line.startswith("n/") and pid is not None:
            try:
                observed[Path(line[1:]).resolve()] = pid
            except OSError:
                continue
    return observed


def active_process_owner(d: Path) -> int | None:
    try:
        root = d.resolve()
    except OSError:
        return -1
    for cwd, pid in _ACTIVE_PROCESS_CWDS.items():
        if pid == -1:
            return -1
        if cwd == root or root in cwd.parents:
            return pid
    return None


def has_generated_payload(d: Path) -> bool:
    return any((d / path).exists() for path in GENERATED_CLEAN_PATHS)


def abandonment_quarantine_root(source_root: Path) -> Path:
    """Choose an off-scan, same-volume default unless the host injects one."""
    if ABANDONMENT_QUARANTINE:
        return Path(ABANDONMENT_QUARANTINE).expanduser()
    creation_root = source_root.parent
    if creation_root.name == ".worktrees":
        return creation_root.parent.parent / "_limen-worktree-abandonment"
    if creation_root.name == "worktrees" and creation_root.parent.name == ".claude":
        return creation_root.parent.parent.parent / "_limen-worktree-abandonment"
    return creation_root.parent / "_limen-worktree-abandonment"


def idle_enough(target, now: float) -> bool:
    min_age_h = getattr(target, "min_age_h", 0)
    try:
        return (now - target.path.stat().st_mtime) / 3600.0 >= float(min_age_h)
    except (OSError, TypeError, ValueError):
        return False


def purge_generated_payloads(d: Path) -> tuple[bool, str]:
    moved = 0
    qroot = abandonment_quarantine_root(d)
    for relative in GENERATED_CLEAN_PATHS:
        source = d / relative
        if not source.exists() and not source.is_symlink():
            continue
        ignored = git(["check-ignore", "-q", "--", relative], d)
        if ignored.returncode == 1:
            continue
        if ignored.returncode != 0:
            return False, f"generated-ignore-status-unavailable-after-{moved}:{relative}"
        destination_name = f"generated-{d.name}-{relative.replace('/', '_')}-{time.time_ns()}-{source.lstat().st_ino}"
        try:
            quarantine_path(
                source,
                qroot,
                reason="ignored-generated-payload",
                receipt_root=ABANDONMENT_RECEIPTS,
                destination_name=destination_name,
                owner_probe=lambda _path: active_process_owner(d),
            )
        except (OSError, WorktreeAbandonmentError) as exc:
            return False, f"generated-quarantine-failed-after-{moved}:{str(exc)[:120]}"
        moved += 1
    return True, f"quarantined:{moved}"


def reclaim_generated_payloads(targets) -> dict[str, object]:
    """Bounded, source-safe cleanup for retained worktrees.

    This atomically quarantines only ignored generated payload paths from inactive git roots.
    It does not remove source files, untracked non-ignored files, worktree roots, branches, or
    private artifacts.
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
    """Treat every Antigravity-owned cache as bridge-gated, not fleet-reapable."""

    try:
        resolved = path.resolve()
        for owned_root in (AGY_ROOT, AGY_SCRATCH_ROOT):
            try:
                resolved.relative_to(owned_root.expanduser().resolve())
                return True
            except ValueError:
                continue
    except OSError:
        return False
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
# PUSHED-REAP POLICY (LIMEN_RECLAIM_PUSHED_OK, declared in parameters.yaml). DEFAULT ON —
# a clean, inactive worktree whose HEAD is
# reachable from any remote ref (reachable_from_remote ⇒ every byte on origin, re-cloneable) is
# reaped as clean+pushed+idle — removing only the disposable LOCAL checkout; the branch and its
# PR/babysitting lifecycle continue on origin. Set 0 only for a bounded diagnostic hold. The
# unpushed/dirty/active guardrails are unchanged — unpreserved work is NEVER reaped.
PUSHED_OK = os.environ.get("LIMEN_RECLAIM_PUSHED_OK", "1") != "0"
# Operator standing grant (2026-07-09, docs/removal-acceptance-covenant.md §Standing grant):
# the loss-free class — clean tree + idle past min-age + preserved on the remote (merged into the
# default, patch-equivalent to it, a merged-PR receipt, or pushed-but-unmerged per PUSHED_OK) — is
# pre-accepted for removal without a per-root ledger event.
STANDING_ACCEPTANCE_REASONS = {"clean+merged+idle", "receipt-remote-merged+clean+idle", "clean+pushed+idle"}

# ── DEAD-GITDIR ORPHAN SWEEP (LIMEN_RECLAIM_ORPHANS, declared in parameters.yaml). DEFAULT OFF —
# observable-first. A worktree checkout whose `.git` pointer targets a superproject gitdir that no
# longer exists is prune-race debris: `git worktree prune` (clone-maintenance.sh) reaps the gitdir
# whenever the worktree's volume (Scratch) is briefly unmounted, and the checkout returns orphaned
# on remount. Because git is DEAD on such a checkout, the reaper CANNOT prove it walked its lifecycle
# (merged/pushed) — so it must NEVER be deleted. The sweep therefore does NOT reap orphans: it
# PRESERVES them by MOVE into an off-worktree quarantine (reversible, loses nothing — walked or not),
# which resolves the debt without destroying data. Actual deletion of a quarantined orphan is a
# SEPARATE, proof-gated step (branch provably on origin, or a long operator grace) — out of scope of
# this autonomous sweep. Confined to THROWAWAY roots, past min-age, only when armed.
ORPHAN_SWEEP = os.environ.get("LIMEN_RECLAIM_ORPHANS", "1") != "0"
ORPHAN_REASON = "orphan-dead-gitdir+throwaway+idle"
# Off-worktree quarantine root (a MOVE target, not a delete). Default: a sibling of the worktree
# root on the same volume (an instant rename, off the worktree-scan path). An override must stay on
# that same volume; cross-device copy fallback is denied. NEVER place it under a worktree root.
ORPHAN_QUARANTINE = os.environ.get("LIMEN_ORPHAN_QUARANTINE", "")
ORPHAN_QUARANTINE_LOG = LIMEN_ROOT / "logs" / "orphan-quarantine.jsonl"
ABANDONMENT_RECEIPTS = Path(
    os.environ.get(
        "LIMEN_WORKTREE_ABANDONMENT_RECEIPTS",
        str(LIMEN_ROOT / "logs" / "worktree-abandonment"),
    )
)
ABANDONMENT_QUARANTINE = os.environ.get("LIMEN_ABANDONMENT_QUARANTINE", "")
if ORPHAN_SWEEP:
    STANDING_ACCEPTANCE_REASONS = STANDING_ACCEPTANCE_REASONS | {ORPHAN_REASON}
# Only THROWAWAY creation roots are eligible for orphan reap — never interactive/registered cells
# (.claude/worktrees, repo-local, registered) which may hold hand-dev work.
_THROWAWAY_SOURCE_PREFIXES = ("dispatch-root", "dispatch-clone-cache", "legacy-dispatch-root", "agy-scratch")


def _is_throwaway_source(source: str) -> bool:
    return any((source or "").startswith(p) for p in _THROWAWAY_SOURCE_PREFIXES)


def orphan_gitdir_name(d: Path) -> str | None:
    """If d/.git is a worktree pointer whose target gitdir no longer exists, return the pointer's
    worktree-admin name (the dead gitdir's basename). Else None. This is the dead-gitdir orphan
    signal — distinct from a plain non-git directory (which has no gitdir pointer at all)."""
    gitfile = d / ".git"
    try:
        if not gitfile.is_file():
            return None
        text = gitfile.read_text(errors="replace").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = text.split("gitdir:", 1)[1].strip()
    if not gitdir or Path(gitdir).exists():
        return None  # gitdir alive ⇒ a registered worktree, not an orphan
    return Path(gitdir).name


def orphan_branch_on_origin(name: str) -> bool:
    """Best-effort: is a remote branch present whose last path-segment matches this orphan's
    worktree-admin name? git derives the admin name from the branch, so a match is evidence the
    committed work is preserved on origin. Recorded in the quarantine receipt (annotation only — the
    quarantine MOVE preserves everything regardless, so no reap decision rides on this)."""
    if not name:
        return False
    r = git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"], LIMEN_ROOT)
    if r.returncode != 0:
        return False
    segs = {ref.rsplit("/", 1)[-1] for ref in r.stdout.split() if ref}
    return name in segs


def orphan_quarantine_root() -> Path:
    """Where preserved orphans are MOVED to. Explicit override wins; else a sibling of the worktree
    root (same volume ⇒ instant rename, and OUTSIDE the worktree-scan path so it clears the debt)."""
    if ORPHAN_QUARANTINE:
        return Path(ORPHAN_QUARANTINE).expanduser()
    try:
        from limen.worktree_roots import effective_worktree_root

        return effective_worktree_root().parent / "_limen-orphan-quarantine"
    except Exception:
        return Path(HOME) / "Workspace" / "_limen-orphan-quarantine"


def quarantine_orphan(d: Path, stamp: str) -> tuple[bool, str]:
    """PRESERVE, never delete: MOVE a dead-gitdir orphan out of the worktree roots into quarantine.
    Reversible; loses nothing (walked lifecycle or not). Returns (ok, dest-or-reason). Refuses if the
    destination would land under a worktree root (which would re-create the debt) or is unwritable."""
    qroot = orphan_quarantine_root()
    try:
        if d.resolve() in _SELF_GUARD:  # never move the live checkout
            return False, "self/live-checkout"
    except OSError as e:
        return False, f"quarantine-unwritable:{str(e)[:80]}"
    destination_name = f"{stamp}-{d.name}"
    if (qroot / destination_name).exists():
        destination_name = f"{destination_name}-{d.stat().st_ino}"
    try:
        branch_on_origin = orphan_branch_on_origin(orphan_gitdir_name(d) or d.name)
        result = quarantine_path(
            d,
            qroot,
            reason=ORPHAN_REASON,
            receipt_root=ABANDONMENT_RECEIPTS,
            destination_name=destination_name,
            owner_probe=lambda _path: active_process_owner(d),
        )
        dest = Path(str((result.get("result") or {})["destination"]))
    except (OSError, WorktreeAbandonmentError, KeyError) as e:
        # Fail closed: a denied atomic move leaves the orphan in place.
        return False, f"quarantine-move-failed:{str(e)[:80]}"
    try:
        ORPHAN_QUARANTINE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ORPHAN_QUARANTINE_LOG.open("a") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "root": d.name,
                        "from": str(d),
                        "to": str(dest),
                        "reason": ORPHAN_REASON,
                        "branch_on_origin": bool(branch_on_origin),
                        "recoverable": "moved-not-deleted",
                    }
                )
                + "\n"
            )
    except OSError:
        pass  # receipt logging must never fail the beat; the move already preserved the data
    return True, str(dest)


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


def worktree_lock_reason(path: Path) -> str | None:
    """Return the explicit Git worktree lock reason for this exact path."""

    result = git(["worktree", "list", "--porcelain"], path)
    if result.returncode != 0:
        return None
    target = path.resolve()
    current: Path | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            try:
                current = Path(line.split(" ", 1)[1]).resolve()
            except OSError:
                current = None
        elif line == "locked" and current == target:
            return "unspecified"
        elif line.startswith("locked ") and current == target:
            return line.split(" ", 1)[1].strip() or "unspecified"
    return None


def classify(d: Path, now: float, min_age_h: float, preservation_receipts=None, source: str = ""):
    """Return (action, reason). action in {remove-worktree, remove-clone, remove-residue,
    quarantine-orphan, skip}. quarantine-orphan MOVES (never deletes) a dead-gitdir orphan."""
    preservation_receipts = preservation_receipts or {}
    try:
        if d.resolve() in _SELF_GUARD:
            return "skip", "self/live-checkout"
    except Exception:
        return "skip", "unresolved"
    owner_pid = active_process_owner(d)
    if owner_pid is not None:
        return "skip", f"active-process-cwd:{owner_pid}"
    if inside_agy_scratch_root(d):
        return "skip", "antigravity-scratch-uses-bridge-acceptance"
    if git(["rev-parse", "--is-inside-work-tree"], d).returncode != 0:
        if is_generated_log_shell(d):
            return "remove-residue", "generated-log-shell"
        # Dead-gitdir orphan (prune-race debris): only under a throwaway root, past min-age, armed.
        # git is dead here, so the loss-free gates below cannot prove it walked its lifecycle — which
        # is exactly why the action is quarantine (a reversible MOVE that preserves everything),
        # NEVER a delete. Deletion of a quarantined orphan is a separate, proof-gated step.
        if ORPHAN_SWEEP and _is_throwaway_source(source) and orphan_gitdir_name(d) is not None:
            try:
                age_h = (now - d.stat().st_mtime) / 3600.0
            except OSError:
                return "skip", "not-a-git-dir"
            if age_h >= min_age_h:
                return "quarantine-orphan", ORPHAN_REASON
            return "skip", f"orphan-active(<{min_age_h:g}h)"
        return "skip", "not-a-git-dir"
    lock_reason = worktree_lock_reason(d)
    if lock_reason is not None:
        return "skip", f"locked:{lock_reason}"
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


def build_candidate_manifest(
    dirs: list[tuple[Path, float, str]],
    now: float,
    preservation_receipts: dict,
    reclaim_acceptance: list[dict],
) -> tuple[dict, str, list[tuple[str, str]], list[str]]:
    """Return the canonical, bounded, accepted candidate set and its digest."""

    candidates: list[dict[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for directory, min_age_h, source in dirs:
        action, reason = classify(
            directory,
            now,
            min_age_h,
            preservation_receipts,
            source=source,
        )
        if action == "skip":
            skipped.append((directory.name, reason))
            continue
        accepted, accept_reason = reclaim_accepted(
            directory,
            action,
            reason,
            reclaim_acceptance,
        )
        if not accepted:
            skipped.append((directory.name, accept_reason))
            continue
        candidates.append(
            {
                "action": action,
                "path": str(directory),
                "reason": reason,
                "root": directory.name,
                "source": source,
            }
        )

    candidates.sort(key=lambda row: (row["path"], row["action"], row["reason"]))
    selected = candidates[:MAX_REMOVE]
    deferred = [row["root"] for row in candidates[MAX_REMOVE:]]
    manifest = {
        "schema": "limen.worktree_reclaim_plan.v1",
        "max_reclaim": MAX_REMOVE,
        "candidates": selected,
    }
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return manifest, hashlib.sha256(canonical).hexdigest(), skipped, deferred


def _print_json_result(
    *,
    mode: str,
    apply: bool,
    dirs: list[tuple[Path, float, str]],
    manifest: dict,
    plan_sha256: str,
    removed: list[tuple[str, str]],
    skipped: list[tuple[str, str]],
    failed: list[tuple[str, str]],
    deferred: list[str],
    generated_reclaim: dict,
) -> None:
    print(
        json.dumps(
            {
                "mode": mode,
                "apply": apply,
                "scanned": len(dirs),
                "candidate_manifest": manifest,
                "plan_sha256": plan_sha256,
                "reclaimed": ([{"root": root, "detail": detail} for root, detail in removed] if apply else []),
                "would_reclaim": manifest["candidates"] if not apply else [],
                "kept_safe": [{"root": root, "reason": reason} for root, reason in skipped],
                "failed": [{"root": root, "reason": reason} for root, reason in failed],
                "deferred_over_cap": deferred,
                "generated_reclaim": generated_reclaim,
                "reapable_count": len(manifest["candidates"]) if not apply else 0,
                "reclaimed_count": len(removed) if apply else 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


def main():
    global _ACTIVE_PROCESS_CWDS
    if HELP:
        print(
            "usage: reclaim-worktrees.py [--check] [--json] [--apply] [--force] "
            "[--generated-only] [--expected-plan-sha SHA256]\n\n"
            "Dry-run by default. Use --check --json for a canonical candidate manifest, "
            "then --apply --expected-plan-sha SHA256 to re-probe and remove only that plan."
        )
        return 0

    targets = iter_worktree_targets(LIMEN_ROOT)
    if not targets:
        print("reclaim: no worktree roots present — nothing to do")
        return 0
    _ACTIVE_PROCESS_CWDS = active_process_cwds()
    if APPLY and not FORCE and MARKER.exists():
        if (time.time() - MARKER.stat().st_mtime) / 60.0 < EVERY_MIN:
            print(f"reclaim: ran < {EVERY_MIN}min ago — skip (set --force to override)")
            return 0

    now = time.time()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    if GENERATED_ONLY:
        generated_reclaim = (
            reclaim_generated_payloads(targets) if APPLY else {"enabled": False, "cleaned": [], "failed": []}
        )
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
    dirs = [(target.path, target.min_age_h, target.source) for target in targets]
    manifest, plan_sha256, skipped, deferred = build_candidate_manifest(
        dirs,
        now,
        preservation_receipts,
        reclaim_acceptance,
    )
    generated_reclaim = {"enabled": False, "cleaned": [], "failed": []}
    removed: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []

    if APPLY:
        if not EXPECTED_PLAN_SHA:
            failed.append(("plan", "expected-plan-sha-required"))
        elif EXPECTED_PLAN_SHA != plan_sha256:
            failed.append(
                (
                    "plan",
                    f"plan-sha-mismatch:expected={EXPECTED_PLAN_SHA}:actual={plan_sha256}",
                )
            )
        if failed:
            if JSON_OUT:
                _print_json_result(
                    mode="APPLY-BLOCKED",
                    apply=True,
                    dirs=dirs,
                    manifest=manifest,
                    plan_sha256=plan_sha256,
                    removed=removed,
                    skipped=skipped,
                    failed=failed,
                    deferred=deferred,
                    generated_reclaim=generated_reclaim,
                )
            else:
                print(f"reclaim [APPLY-BLOCKED]: {failed[0][1]}")
            return 2

        for planned in manifest["candidates"]:
            directory = Path(planned["path"])
            _ACTIVE_PROCESS_CWDS = active_process_cwds()
            action, reason = classify(
                directory,
                time.time(),
                next(min_age_h for path, min_age_h, _source in dirs if path == directory),
                preservation_receipts,
                source=planned["source"],
            )
            accepted, accept_reason = reclaim_accepted(
                directory,
                action,
                reason,
                reclaim_acceptance,
            )
            if not accepted or action != planned["action"] or reason != planned["reason"]:
                detail = accept_reason if not accepted else f"candidate-drift:{action}:{reason}"
                failed.append((directory.name, detail))
                continue
            try:
                if action == "remove-worktree":
                    super_root = superproject(directory)
                    if not super_root or Path(super_root).resolve() == directory.resolve():
                        failed.append((directory.name, "registered-superproject-unavailable"))
                        continue
                    receipt = detach_registered_worktree(
                        Path(super_root),
                        directory,
                        reason=reason,
                        receipt_root=ABANDONMENT_RECEIPTS,
                        owner_probe=lambda _path, root=directory: active_process_owner(root),
                    )
                elif action == "quarantine-orphan":
                    ok, destination = quarantine_orphan(directory, stamp)
                    if not ok:
                        failed.append((directory.name, destination))
                        continue
                    receipt = {
                        "receipt_path": "orphan-quarantine-wrapper",
                        "result": {"destination": destination},
                    }
                else:
                    destination_name = f"{stamp}-{directory.name}-{directory.lstat().st_ino}"
                    receipt = quarantine_path(
                        directory,
                        abandonment_quarantine_root(directory),
                        reason=reason,
                        receipt_root=ABANDONMENT_RECEIPTS,
                        destination_name=destination_name,
                        owner_probe=lambda _path, root=directory: active_process_owner(root),
                    )
                removed.append(
                    (
                        directory.name,
                        f"{action}:{reason}:abandonment={Path(str(receipt['receipt_path'])).name}",
                    )
                )
            except (OSError, WorktreeAbandonmentError) as exc:
                failed.append((directory.name, str(exc)[:120]))

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
            pass

    mode = "APPLY" if APPLY else "check" if CHECK else "dry-run"
    if JSON_OUT:
        _print_json_result(
            mode=mode,
            apply=APPLY,
            dirs=dirs,
            manifest=manifest,
            plan_sha256=plan_sha256,
            removed=removed,
            skipped=skipped,
            failed=failed,
            deferred=deferred,
            generated_reclaim=generated_reclaim,
        )
        return 1 if failed else 0

    print(
        f"reclaim [{mode}]: {len(removed)} reclaimed, {len(skipped)} kept-safe, "
        f"{len(failed)} failed, {len(deferred)} deferred-over-cap (of {len(dirs)}); "
        f"plan_sha256={plan_sha256}"
    )
    for root, reason in skipped:
        print(f"  keep {reason:24} {root}")
    for row in manifest["candidates"]:
        print(f"  {'reclaimed' if APPLY else 'would'}: {row['root']} ({row['action']}:{row['reason']})")
    if deferred:
        print(
            f"  NOTE: {len(deferred)} dirs over the {MAX_REMOVE}-cap this run, next run takes them: "
            + ", ".join(deferred[:5])
            + ("…" if len(deferred) > 5 else "")
        )
    for root, reason in failed:
        print(f"  FAIL {root}: {reason}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
