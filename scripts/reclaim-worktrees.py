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
  • workspace checkout roots themselves only when LIMEN_RECLAIM_WORKSPACE_CHECKOUTS=1.
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
     LIMEN_RECLAIM_WORKSPACE_ROOTS, LIMEN_RECLAIM_WORKSPACE_CHECKOUTS,
     LIMEN_RECLAIM_WORKSPACE_CHECKOUT_AGE_H, LIMEN_RECLAIM_MAX (50), LIMEN_RECLAIM_EVERY_MIN (30),
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
from collections.abc import Callable
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT / "cli" / "src"))

from limen.estate_audit_custody import (
    EstateAuditCustodyError,
    verify_failed_checkout_state,
)
from limen.estate_audit_custody import (
    discover_plan as discover_estate_custody_plan,
)
from limen.estate_audit_custody import (
    verify_receipt as verify_estate_custody_receipt,
)
from limen.worktree_abandonment import (
    CustodyPathIdentity,
    WorktreeAbandonmentError,
    detach_registered_worktree,
    purge_custody_proven_path,
    purge_remote_proven_path,
    quarantine_path,
)
from limen.worktree_debt import is_generated_log_shell
from limen.worktree_roots import iter_worktree_targets
from reap_acceptance import (
    REQUIRED_ACCEPTANCE_PROOF_FIELDS as SHARED_REQUIRED_ACCEPTANCE_PROOF_FIELDS,
)
from reap_acceptance import (
    has_required_acceptance_proof,
)

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
ESTATE_CUSTODY_ROOT = _option_value("--estate-custody-root")
ESTATE_CUSTODY_PLAN_SHA = _option_value("--estate-custody-plan-sha")
REMOTE_MERGED_LANES = {"remote-merged"}
REMOTE_MERGED_STATUSES = {"merged_pr_preserved"}
CUSTODY_RESTORED_REASON = "custody-restored+idle"
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
# A planning pass may inspect dozens of registered worktrees backed by one repository. Querying the
# same origin separately for every sibling made the canonical check exceed the heartbeat's bound.
# ``main`` enables this cache only while building one manifest; apply reclassification runs with it
# disabled so each accepted removal still gets a fresh remote proof immediately before detach.
_REMOTE_ADVERTISEMENT_CACHE: dict[Path, tuple[tuple[str, str], ...] | None] | None = None

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


# The probe and its containment rule live in _worktree_liveness (shared with the stream
# launcher's live/dormant classification — one probe, two consumers with opposite decisions:
# reclaim must not DELETE a live worktree, the launcher must not REOPEN one). Extracted verbatim;
# this organ keeps its own refresh cycle (it re-scans mid-apply on purpose), so it consumes
# `active_process_cwds` + `owner_in` directly rather than the helper's memoized `process_owner`.
from _worktree_liveness import active_process_cwds, owner_in  # noqa: E402


def active_process_owner(d: Path) -> int | None:
    return owner_in(_ACTIVE_PROCESS_CWDS, d)


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
    if os.environ.get("LIMEN_RECLAIM_GENERATED", "0") != "1":
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
    return bool(remote_refs_containing_head(cwd, head))


def _git_common_dir(cwd: Path) -> Path:
    """Resolve the repository identity shared by linked worktrees without another Git process."""
    checkout = Path(cwd)
    dot_git = checkout / ".git"
    try:
        if dot_git.is_dir():
            return dot_git.resolve()
        marker = dot_git.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        prefix = "gitdir: "
        if not marker.startswith(prefix):
            return checkout.resolve()
        git_dir = Path(marker[len(prefix) :])
        if not git_dir.is_absolute():
            git_dir = dot_git.parent / git_dir
        git_dir = git_dir.resolve()
        common_marker = git_dir / "commondir"
        if common_marker.is_file():
            common = Path(common_marker.read_text(encoding="utf-8", errors="replace").strip())
            if not common.is_absolute():
                common = git_dir / common
            return common.resolve()
        return git_dir
    except (IndexError, OSError):
        try:
            return checkout.resolve()
        except OSError:
            return checkout


def _advertised_remote_refs(cwd: Path) -> tuple[tuple[str, str], ...] | None:
    cache_key = _git_common_dir(cwd)
    if _REMOTE_ADVERTISEMENT_CACHE is not None and cache_key in _REMOTE_ADVERTISEMENT_CACHE:
        return _REMOTE_ADVERTISEMENT_CACHE[cache_key]

    advertised = git(["ls-remote", "--refs", "origin"], cwd, timeout=120)
    parsed: tuple[tuple[str, str], ...] | None = None
    if advertised.returncode == 0:
        rows: list[tuple[str, str]] = []
        valid = True
        for line in advertised.stdout.splitlines():
            try:
                remote_object, remote_ref = line.split("\t", 1)
            except ValueError:
                valid = False
                break
            if not remote_object or not remote_ref.startswith("refs/"):
                valid = False
                break
            rows.append((remote_ref, remote_object))
        if valid:
            parsed = tuple(rows)

    if _REMOTE_ADVERTISEMENT_CACHE is not None:
        _REMOTE_ADVERTISEMENT_CACHE[cache_key] = parsed
    return parsed


def remote_refs_containing_head(cwd: Path, head: str) -> tuple[str, ...]:
    """Return only provider-advertised refs that currently preserve ``head``.

    Local ``refs/remotes/*`` are caches and can outlive a deleted server
    branch. Reclaim proof therefore queries the live remote on every planning
    and apply pass. One planning manifest shares the resulting advertisement
    across linked worktrees from the same repository.
    """

    if not head:
        return ()
    advertised = _advertised_remote_refs(cwd)
    if advertised is None:
        return ()
    exact = sorted(remote_ref for remote_ref, remote_object in advertised if remote_object == head)
    if exact:
        return tuple(exact)

    # The dominant merged-worktree case needs no all-ref walk. Prove that the locally fetched
    # default tip is byte-for-byte the tip currently advertised by origin, then ask Git whether it
    # contains HEAD. A stale origin/main cannot pass the object-ID equality check.
    default_ref = remote_default_ref(cwd)
    if default_ref and default_ref.startswith("origin/"):
        advertised_default = f"refs/heads/{default_ref.removeprefix('origin/')}"
        advertised_object = dict(advertised).get(advertised_default)
        if advertised_object:
            local_default = git(["rev-parse", default_ref], cwd)
            if (
                local_default.returncode == 0
                and local_default.stdout.strip() == advertised_object
                and git(["merge-base", "--is-ancestor", head, default_ref], cwd).returncode == 0
            ):
                return (advertised_default,)

    # GitHub can advertise thousands of refs. Spawning one ``merge-base`` process per ref made a
    # single Limen planning pass exceed five minutes. Ask Git once for locally known refs containing
    # HEAD, then accept only entries whose ref name *and object ID* still match the live advertisement.
    # A stale or unfetched remote-tracking ref cannot pass that intersection, so this is a conservative
    # fail-closed replacement for the per-ref process storm.
    local = git(
        [
            "for-each-ref",
            f"--contains={head}",
            "--format=%(refname)%00%(objectname)",
            "refs/remotes/origin",
            "refs/tags",
        ],
        cwd,
        timeout=60,
    )
    if local.returncode != 0:
        return ()
    local_containing: dict[str, str] = {}
    remote_prefix = "refs/remotes/origin/"
    for line in local.stdout.splitlines():
        parts = line.split("\0")
        if len(parts) != 2:
            return ()
        local_ref, object_id = parts
        if local_ref.startswith(remote_prefix):
            suffix = local_ref[len(remote_prefix) :]
            if suffix != "HEAD":
                local_containing[f"refs/heads/{suffix}"] = object_id
        elif local_ref.startswith("refs/tags/"):
            local_containing[local_ref] = object_id

    containing: list[str] = []
    for remote_ref, remote_object in advertised:
        if local_containing.get(remote_ref) == remote_object:
            containing.append(remote_ref)
    return tuple(sorted(containing))


def all_local_refs_remote_proof(cwd: Path) -> tuple[dict[str, object], ...] | None:
    """Prove every local ref's object is recoverable from the live origin.

    HEAD-only proof loses local branches, tags, notes, and stashes. This queries
    the provider-native advertised refs and then proves each local object is
    either advertised exactly or is an ancestor of an advertised commit that is
    already present locally. Unknown object type or reachability fails closed.
    """

    local = git(
        [
            "for-each-ref",
            "--format=%(refname)%00%(objectname)%00%(*objectname)",
            "refs/heads",
            "refs/tags",
            "refs/notes",
            "refs/stash",
        ],
        cwd,
        timeout=60,
    )
    advertised = _advertised_remote_refs(cwd)
    if local.returncode != 0 or advertised is None:
        return None
    remote = list(advertised)
    if not remote:
        return None
    proof: list[dict[str, object]] = []
    for line in local.stdout.splitlines():
        parts = line.split("\0")
        if len(parts) != 3:
            return None
        local_ref, object_id, peeled = parts
        containing: list[str] = [remote_ref for remote_ref, remote_object in remote if object_id == remote_object]
        object_type = git(["cat-file", "-t", object_id], cwd)
        if object_type.returncode != 0:
            return None
        if object_type.stdout.strip() == "commit":
            for remote_ref, remote_object in remote:
                if remote_ref in containing:
                    continue
                if git(["merge-base", "--is-ancestor", object_id, remote_object], cwd).returncode == 0:
                    containing.append(remote_ref)
        if not containing:
            return None
        proof.append(
            {
                "local_ref": local_ref,
                "object": object_id,
                "peeled_object": peeled or None,
                "remote_refs": sorted(containing),
            }
        )
    return tuple(sorted(proof, key=lambda value: str(value["local_ref"])))


def estate_checkout_content_probe(
    root_record: dict[str, object],
    state: dict[str, object],
) -> Callable[[Path], None]:
    def probe(_path: Path) -> None:
        verify_failed_checkout_state(root_record, state, max_seconds=900)

    return probe


def remote_clone_content_probe(
    expected_head: str,
    expected_refs: tuple[str, ...],
    expected_local_refs: tuple[dict[str, object], ...],
) -> Callable[[Path], None]:
    def probe(current: Path) -> None:
        status = git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], current)
        if status.returncode != 0 or status.stdout:
            raise RuntimeError("remote-purge-working-tree-drift")
        observed_head = git(["rev-parse", "HEAD"], current).stdout.strip()
        observed_refs = remote_refs_containing_head(current, observed_head)
        observed_local_refs = all_local_refs_remote_proof(current)
        if (
            observed_head,
            observed_refs,
            observed_local_refs,
        ) != (
            expected_head,
            expected_refs,
            expected_local_refs,
        ):
            raise RuntimeError("remote-purge-all-ref-proof-drift")

    return probe


def path_identity(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    current = resolved.lstat()
    return {
        "path": str(resolved),
        "path_sha256": hashlib.sha256(str(resolved).encode("utf-8", errors="surrogateescape")).hexdigest(),
        "device": int(current.st_dev),
        "inode": int(current.st_ino),
        "mtime_ns": int(current.st_mtime_ns),
    }


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


def load_estate_custody_context() -> dict[str, object] | None:
    """Verify one exact external custody plan and expose only its public reclaim proof.

    The custody override is deliberately limited to failed-checkout roots whose
    working payloads are present in the fully restored receipt. Indexed roots
    continue through the ordinary clean/remote lifecycle gates.
    """

    if not ESTATE_CUSTODY_ROOT and not ESTATE_CUSTODY_PLAN_SHA:
        return None
    if not ESTATE_CUSTODY_ROOT or not ESTATE_CUSTODY_PLAN_SHA:
        raise EstateAuditCustodyError("custody-arguments-incomplete")
    if len(ESTATE_CUSTODY_PLAN_SHA) != 64 or any(
        character not in "0123456789abcdef" for character in ESTATE_CUSTODY_PLAN_SHA
    ):
        raise EstateAuditCustodyError("invalid-custody-plan-sha")

    receipt = verify_estate_custody_receipt(
        Path(ESTATE_CUSTODY_ROOT),
        ESTATE_CUSTODY_PLAN_SHA,
        full_restore=True,
        max_seconds=900,
    )
    current = discover_estate_custody_plan(LIMEN_ROOT)
    if current.plan_sha256 != ESTATE_CUSTODY_PLAN_SHA:
        raise EstateAuditCustodyError("custody-current-plan-mismatch")
    if receipt.get("roots") != current.private_payload()["roots"]:
        raise EstateAuditCustodyError("custody-current-roots-mismatch")

    restored_paths: set[Path] = set()
    restored_identities: dict[str, dict[str, object]] = {}
    private_content_states: dict[str, dict[str, object]] = {}
    states_by_path_sha = {
        str(state.get("path_sha256") or ""): state
        for state in receipt.get("failed_checkout_states") or []
        if isinstance(state, dict)
    }
    for root in receipt.get("roots") or []:
        if not isinstance(root, dict) or int(root.get("index_entry_count", -1)) != 0:
            continue
        try:
            restored = Path(str(root["path"])).resolve(strict=True)
            restored_paths.add(restored)
            restored_identities[str(restored)] = {
                "path": str(restored),
                "path_sha256": str(root["path_sha256"]),
                "device": int(root["device"]),
                "inode": int(root["inode"]),
                "mtime_ns": int(root["mtime_ns"]),
            }
            state = states_by_path_sha.get(str(root["path_sha256"]))
            if not isinstance(state, dict):
                raise EstateAuditCustodyError("custody-content-state-missing")
            private_content_states[str(restored)] = {
                "root_record": root,
                "state": state,
            }
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise EstateAuditCustodyError("custody-root-unavailable") from exc
    failed_checkout_count = int(receipt.get("failed_checkout_root_count", -1))
    if not restored_paths or failed_checkout_count != len(restored_paths):
        raise EstateAuditCustodyError("custody-failed-checkout-coverage-mismatch")

    return {
        "paths": frozenset(restored_paths),
        "identities": restored_identities,
        "content_states": private_content_states,
        "proof": {
            "schema": "limen.worktree_reclaim_estate_custody.v1",
            "plan_sha256": ESTATE_CUSTODY_PLAN_SHA,
            "content_sha256": str(receipt.get("content_sha256") or ""),
            "root_count": int(receipt.get("root_count") or 0),
            "failed_checkout_root_count": failed_checkout_count,
            "restoration_passed": receipt.get("restoration_passed") is True,
        },
    }


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


def reclaim_accepted(
    path: Path,
    action: str,
    reason: str,
    acceptance_events,
    estate_custody_proof: dict[str, object] | None = None,
) -> tuple[bool, str]:
    if STANDING_ACCEPTANCE and reason in STANDING_ACCEPTANCE_REASONS:
        return True, "standing-grant-2026-07-09"
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)
    for event in reversed(acceptance_events):
        root = event.get("root")
        wildcard_custody = root == "*" and reason == CUSTODY_RESTORED_REASON
        if root != path.name and not wildcard_custody:
            continue
        if reason == CUSTODY_RESTORED_REASON:
            if not estate_custody_proof:
                continue
            if event.get("custody_plan_sha256") != estate_custody_proof.get("plan_sha256"):
                continue
            if event.get("custody_content_sha256") != estate_custody_proof.get("content_sha256"):
                continue
        elif root == "*":
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


def registered_sibling_worktrees(path: Path) -> tuple[Path, ...]:
    """Return live sibling worktrees whose admin state is owned by this clone."""

    listed = git(["worktree", "list", "--porcelain"], path)
    if listed.returncode != 0:
        raise RuntimeError("registered-worktree-state-unavailable")
    try:
        current = path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("registered-worktree-owner-unavailable") from exc
    siblings: list[Path] = []
    for line in listed.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        try:
            candidate = Path(line.split(" ", 1)[1]).resolve(strict=True)
        except OSError as exc:
            raise RuntimeError("registered-sibling-worktree-unavailable") from exc
        if candidate != current:
            siblings.append(candidate)
    return tuple(siblings)


def classify(
    d: Path,
    now: float,
    min_age_h: float,
    preservation_receipts=None,
    source: str = "",
    estate_custody_paths: frozenset[Path] | set[Path] | None = None,
):
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
    status = git(["status", "--porcelain"], d)
    if status.returncode != 0:
        return "skip", "status-unavailable"
    if status.stdout.strip():
        try:
            custody_restored = d.resolve() in (estate_custody_paths or set())
        except OSError:
            custody_restored = False
        if custody_restored:
            is_wt = (d / ".git").is_file()
            return ("remove-worktree" if is_wt else "remove-clone"), CUSTODY_RESTORED_REASON
        return "skip", "dirty"
    is_wt = (d / ".git").is_file()  # gitdir-pointer ⇒ registered worktree
    if source == "workspace-checkout" and is_wt:
        return "skip", "workspace-checkout-source-contract-violation"
    if not is_wt:
        try:
            if registered_sibling_worktrees(d):
                return "skip", "registered-worktree-owner"
        except RuntimeError as exc:
            return "skip", str(exc)
    if receipt_remote_merged(d, preservation_receipts):
        if not is_wt and all_local_refs_remote_proof(d) is None:
            return "skip", "unpreserved-local-refs"
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
            # Removing one linked worktree leaves the common repository and every local ref intact.
            # A standalone clone purge deletes that ref store, so only the clone needs all-ref proof.
            if not is_wt and all_local_refs_remote_proof(d) is None:
                return "skip", "unpreserved-local-refs"
            return ("remove-worktree" if is_wt else "remove-clone"), "clean+pushed+idle"
        return "skip", "not-merged-to-default"
    if not is_wt and all_local_refs_remote_proof(d) is None:
        return "skip", "unpreserved-local-refs"
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
    estate_custody_context: dict[str, object] | None = None,
) -> tuple[dict, str, list[tuple[str, str]], list[str]]:
    """Return the canonical, bounded, accepted candidate set and its digest."""

    custody_paths = estate_custody_context.get("paths", frozenset()) if estate_custody_context else frozenset()
    custody_proof = estate_custody_context.get("proof") if estate_custody_context else None
    custody_identities = estate_custody_context.get("identities", {}) if estate_custody_context else {}
    candidates: list[dict[str, object]] = []
    skipped: list[tuple[str, str]] = []
    for directory, min_age_h, source in dirs:
        action, reason = classify(
            directory,
            now,
            min_age_h,
            preservation_receipts,
            source=source,
            estate_custody_paths=custody_paths,
        )
        if action == "skip":
            skipped.append((directory.name, reason))
            continue
        accepted, accept_reason = reclaim_accepted(
            directory,
            action,
            reason,
            reclaim_acceptance,
            estate_custody_proof=custody_proof,
        )
        if not accepted:
            skipped.append((directory.name, accept_reason))
            continue
        candidate: dict[str, object] = {
            "action": action,
            "path": str(directory),
            "reason": reason,
            "root": directory.name,
            "source": source,
        }
        if reason == CUSTODY_RESTORED_REASON:
            try:
                identity = custody_identities[str(directory.resolve(strict=True))]
            except (KeyError, OSError) as exc:
                raise EstateAuditCustodyError("custody-root-identity-missing") from exc
            if not isinstance(identity, dict):
                raise EstateAuditCustodyError("custody-root-identity-invalid")
            candidate["custody_identity"] = identity
        elif action == "remove-clone":
            head = git(["rev-parse", "HEAD"], directory).stdout.strip()
            remote_refs = remote_refs_containing_head(directory, head)
            local_ref_proof = all_local_refs_remote_proof(directory)
            if not head or not remote_refs or local_ref_proof is None:
                skipped.append((directory.name, "remote-clone-proof-drift"))
                continue
            candidate["path_identity"] = path_identity(directory)
            candidate["remote_proof"] = {
                "head": head,
                "remote_refs": list(remote_refs),
                "local_refs": list(local_ref_proof),
            }
        candidates.append(candidate)

    candidates.sort(key=lambda row: (row["path"], row["action"], row["reason"]))
    selected = candidates[:MAX_REMOVE]
    deferred = [row["root"] for row in candidates[MAX_REMOVE:]]
    manifest = {
        "schema": "limen.worktree_reclaim_plan.v1",
        "max_reclaim": MAX_REMOVE,
        "candidates": selected,
    }
    if custody_proof:
        manifest["estate_custody"] = custody_proof
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
    global _ACTIVE_PROCESS_CWDS, _REMOTE_ADVERTISEMENT_CACHE
    if HELP:
        print(
            "usage: reclaim-worktrees.py [--check] [--json] [--apply] [--force] "
            "[--generated-only] [--expected-plan-sha SHA256] "
            "[--estate-custody-root PATH --estate-custody-plan-sha SHA256]\n\n"
            "Dry-run by default. Use --check --json for a canonical candidate manifest, "
            "then --apply --expected-plan-sha SHA256 to re-probe and remove only that plan. "
            "The estate-custody pair admits only exact fully restored failed-checkout roots."
        )
        return 0

    try:
        estate_custody_context = load_estate_custody_context()
    except EstateAuditCustodyError as exc:
        if JSON_OUT:
            print(
                json.dumps(
                    {
                        "mode": "CUSTODY-BLOCKED",
                        "apply": APPLY,
                        "failed": [{"root": "estate-custody", "reason": exc.code}],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"reclaim [CUSTODY-BLOCKED]: {exc.code}")
        return 2

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
    previous_advertisement_cache = _REMOTE_ADVERTISEMENT_CACHE
    _REMOTE_ADVERTISEMENT_CACHE = {}
    try:
        manifest, plan_sha256, skipped, deferred = build_candidate_manifest(
            dirs,
            now,
            preservation_receipts,
            reclaim_acceptance,
            estate_custody_context,
        )
    finally:
        # The exact manifest gets one coherent remote advertisement per repository. Disable the
        # cache before apply's candidate reclassification so remote deletion/drift still blocks.
        _REMOTE_ADVERTISEMENT_CACHE = previous_advertisement_cache
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
        if not failed and estate_custody_context:
            try:
                refreshed_custody = load_estate_custody_context()
            except EstateAuditCustodyError as exc:
                failed.append(("estate-custody", exc.code))
            else:
                if refreshed_custody != estate_custody_context:
                    failed.append(("estate-custody", "custody-proof-drift"))
                estate_custody_context = refreshed_custody
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
            custody_paths = estate_custody_context.get("paths", frozenset()) if estate_custody_context else frozenset()
            custody_proof = estate_custody_context.get("proof") if estate_custody_context else None
            action, reason = classify(
                directory,
                time.time(),
                next(min_age_h for path, min_age_h, _source in dirs if path == directory),
                preservation_receipts,
                source=planned["source"],
                estate_custody_paths=custody_paths,
            )
            accepted, accept_reason = reclaim_accepted(
                directory,
                action,
                reason,
                reclaim_acceptance,
                estate_custody_proof=custody_proof,
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
                elif action == "remove-clone" and reason == CUSTODY_RESTORED_REASON:
                    identity = planned.get("custody_identity")
                    if not isinstance(identity, dict) or not isinstance(custody_proof, dict):
                        failed.append((directory.name, "custody-purge-proof-missing"))
                        continue
                    try:
                        expected_identity = CustodyPathIdentity(
                            path=str(identity["path"]),
                            path_sha256=str(identity["path_sha256"]),
                            device=int(identity["device"]),
                            inode=int(identity["inode"]),
                            mtime_ns=int(identity["mtime_ns"]),
                        )
                    except (KeyError, TypeError, ValueError):
                        failed.append((directory.name, "custody-purge-identity-invalid"))
                        continue
                    content_states = estate_custody_context.get("content_states", {}) if estate_custody_context else {}
                    content_state = (
                        content_states.get(str(directory.resolve(strict=True)))
                        if isinstance(content_states, dict)
                        else None
                    )
                    if not isinstance(content_state, dict):
                        failed.append((directory.name, "custody-content-state-missing"))
                        continue

                    rehash_estate_checkout = estate_checkout_content_probe(
                        dict(content_state["root_record"]),
                        dict(content_state["state"]),
                    )

                    receipt = purge_custody_proven_path(
                        directory,
                        expected_identity,
                        reason=reason,
                        custody_plan_sha256=str(custody_proof.get("plan_sha256") or ""),
                        custody_content_sha256=str(custody_proof.get("content_sha256") or ""),
                        receipt_root=ABANDONMENT_RECEIPTS,
                        owner_probe=lambda _path, root=directory: active_process_owner(root),
                        content_probe=rehash_estate_checkout,
                    )
                elif action == "remove-clone":
                    identity = planned.get("path_identity")
                    remote_proof = planned.get("remote_proof")
                    if not isinstance(identity, dict) or not isinstance(remote_proof, dict):
                        failed.append((directory.name, "remote-purge-proof-missing"))
                        continue
                    try:
                        expected_identity = CustodyPathIdentity(
                            path=str(identity["path"]),
                            path_sha256=str(identity["path_sha256"]),
                            device=int(identity["device"]),
                            inode=int(identity["inode"]),
                            mtime_ns=int(identity["mtime_ns"]),
                        )
                        planned_head = str(remote_proof["head"])
                        planned_refs = tuple(str(value) for value in remote_proof["remote_refs"])
                        planned_local_refs = tuple(remote_proof["local_refs"])
                    except (KeyError, TypeError, ValueError):
                        failed.append((directory.name, "remote-purge-proof-invalid"))
                        continue
                    current_head = git(["rev-parse", "HEAD"], directory).stdout.strip()
                    current_refs = remote_refs_containing_head(directory, current_head)
                    current_local_refs = all_local_refs_remote_proof(directory)
                    if (
                        current_head,
                        current_refs,
                        current_local_refs,
                    ) != (
                        planned_head,
                        planned_refs,
                        planned_local_refs,
                    ):
                        failed.append((directory.name, "remote-purge-proof-drift"))
                        continue

                    rehash_remote_clone = remote_clone_content_probe(
                        planned_head,
                        planned_refs,
                        planned_local_refs,
                    )

                    receipt = purge_remote_proven_path(
                        directory,
                        expected_identity,
                        reason=reason,
                        head=current_head,
                        remote_refs=current_refs,
                        local_ref_proof=current_local_refs,
                        receipt_root=ABANDONMENT_RECEIPTS,
                        owner_probe=lambda _path, root=directory: active_process_owner(root),
                        content_probe=rehash_remote_clone,
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
