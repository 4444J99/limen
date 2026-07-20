#!/usr/bin/env python3
"""reap-clones.py — the CLONE-REAP organ (lifecycle rung 4b).

A local clone is a DISPOSABLE CACHE of its GitHub origin. The developer lifecycle every human
runs is  clone → work → push → *delete the clone*  (re-clone on demand). The fleet clones repos
and reaps NONE, so ~/Workspace creeps to full — on 2026-07-01 the data volume hit 411G / 96%
with organvm/ at 14G plus a DUPLICATE a-organvm/ at 3.2G, dormant full clones, and 58 node_modules.
clone-maintenance.sh reaped node_modules but only *printed* reapable clones ("remove only with user
OK"): the last step of the lifecycle was gated on the operator's hand, so the disk crept back every time.

This organ reaps a clone ONLY when it is a PURE PUSHED MIRROR with no live work — the loss-free gate.
It is an ALLOWLIST, not a denylist: it deletes only when it can positively prove every local byte is
already on the live remote (a 2026-07-01 adversarial audit reproduced 14 data-loss paths against an
earlier denylist-shaped gate — stash, reflog orphans, local tags, git-notes, gitignored .env/db,
force-push/ahead-of-origin, submodules, LFS, linked worktrees, TOCTOU — all now guarded below):

  • clean working tree AND no untracked files (`git status --porcelain` is EMPTY), AND
  • no un-mirrored gitignored data — every ignored entry is a provably-regenerable dep/build/cache dir
    (a `.env`, local `*.db`, or data/ dir → KEEP), AND
  • NO local-only objects: nothing reachable from any local ref (heads/tags/notes/stash) OR the reflog
    is missing from a remote (catches stash WIP, local tags, notes, hard-reset reflog orphans), AND
  • no skip-worktree / assume-unchanged bit hiding a tracked-file edit, AND
  • not a submodule / LFS / linked-worktree parent (nested contexts outside the parent ref graph), AND
  • HEAD reachable from an origin ref, no active limen task, not CORE / live-root / worktree-root, AND
  • idle >= min-age — UNLESS disk pressure >= high-water, which WAIVES the age gate (still loss-free), AND
  • the NETWORK BELT confirms against a fresh `git fetch --prune` that no local object is un-mirrored
    (catches stale/force-rewound remotes that make refs/heads commits merely LOOK pushed), re-checked
    a final time (porcelain + stash) at the instant before rmtree to close the TOCTOU window.

Every data gate is loss-free (re-cloneable from GitHub; nothing local unpushed or untracked). As of
2026-07-06, --apply still requires a matching human acceptance/redaction/archive event in
docs/clone-reap-acceptance.jsonl before physical removal. It NEVER deletes DATA: a clone with
untracked files (possible hand-dropped inputs — the "7 genesis screenshots" rule) or with unpushed
work is SKIPPED and reported as needs-capture, never removed. capture.sh pushes that work first; a
later beat then finds a pure mirror and proposes it. It only ever touches STANDALONE clones (`.git`
is a directory); registered worktrees (`.git` is a file) are reclaim-worktrees.py's job.

Dry-run by default; --apply removes (rmtree — a clone is not a registered worktree). Disk pressure is
auto-detected via df on the workspace volume, or forced with --pressure / disabled with --no-pressure.
Bounded per run (--max, default 50). Fails OPEN: any error on one clone is logged and skipped.

Env: LIMEN_WORKSPACE (~/Workspace), LIMEN_ROOT, LIMEN_REAP_CORE, LIMEN_REAP_IDLE_DAYS (2),
     LIMEN_DISK_HIGH_WATER (85), LIMEN_REAP_MAX (50), LIMEN_REAP_MAXDEPTH (3).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reap_acceptance import (  # noqa: E402
    REQUIRED_ACCEPTANCE_PROOF_FIELDS as SHARED_REQUIRED_ACCEPTANCE_PROOF_FIELDS,
    has_required_acceptance_proof,
)

HOME = os.environ.get("HOME", str(Path.home()))
WORKSPACE = Path(os.environ.get("LIMEN_WORKSPACE", f"{HOME}/Workspace"))
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", f"{HOME}/Workspace/limen")).resolve()
LOG = LIMEN_ROOT / "logs" / "reap-clones.jsonl"
CLONE_REAP_ACCEPTANCE = LIMEN_ROOT / "docs" / "clone-reap-acceptance.jsonl"
CLONE_REAP_ACCEPTANCE_DOC = LIMEN_ROOT / "docs" / "clone-reap-acceptance.md"

# CORE repos the operator lives in / the conductor needs local — never reaped even if pushed-clean.
DEFAULT_CORE = "limen session-meta sovereign-systems--elevate-align portfolio portvs universal-mail--automation"
CORE = set(os.environ.get("LIMEN_REAP_CORE", DEFAULT_CORE).split())

# Paths that are somebody else's lifecycle (worktree reaper, cartridge co-tenant, throwaway roots).
EXCLUDE_MARKERS = (".claude/worktrees", ".limen-worktrees", ".home-cartridge", ".worktrees", "/node_modules/")

# Gitignored files are normally regenerable (deps, build output, caches) — losing them is loss-free.
# But a gitignored file can also be IRREPLACEABLE local state (a .env secret, a local *.db, a data/
# dir) that lives on NO remote. `git status --porcelain` hides all ignored files, so we enumerate them
# with --ignored and reap only when EVERY ignored entry's top path component is a known-regenerable dir
# (or a regenerable-suffixed top-level file). Anything else → KEEP (the ignored-file data-loss class).
REGENERABLE_DIRS = set(
    "node_modules .venv venv .venv-demucs __pycache__ .pytest_cache .mypy_cache .ruff_cache "
    ".tox dist build .next .nuxt .svelte-kit .astro .turbo .parcel-cache .vercel .wrangler "
    ".gradle coverage .nyc_output .eggs .ipynb_checkpoints".split()
)
REGENERABLE_SUFFIXES = (".pyc", ".pyo")
REGENERABLE_FILES = {".DS_Store"}
_ACTIVE_PROCESS_CWDS: dict[Path, int] = {}

# Non-interactive git: fail (→ fail-safe KEEP) rather than block on a credential/GUI prompt.
_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
ACCEPTED_ARCHIVE_STATUSES = {
    "verified",
    "remote_mirror_verified",
    "not_required_clean_remote_mirror",
}
ACCEPTED_REDACTION_REVIEWS = {
    "accepted",
    "private_archive_only",
    "not_required_remote_only",
}
REQUIRED_ACCEPTANCE_PROOF_FIELDS = SHARED_REQUIRED_ACCEPTANCE_PROOF_FIELDS

# Operator standing grant (2026-07-09) — round two of the removal-acceptance covenant, now for clones.
# The worktree sibling (reclaim-worktrees.py STANDING_ACCEPTANCE) pre-accepts its loss-free class; the
# clone organ was left gated on an unfed ledger AND never beat-wired, so ~/Workspace crept back every
# time (the recurring "why is local storage full" pain). classify() already proves the loss-free gate
# adversarially (14 data-loss paths guarded); its True verdict is "pushed-mirror[-under-pressure]" —
# every local byte is on the live remote, re-cloneable, nothing unpushed/untracked. Pre-accept exactly
# that class, matching the operator's rule "nothing deleted without being pushed; pushed IS enough."
# Default ON; set LIMEN_CLONE_REAP_STANDING_ACCEPTANCE=0 to restore the per-clone ledger gate.
CLONE_REAP_STANDING = os.environ.get("LIMEN_CLONE_REAP_STANDING_ACCEPTANCE", "1") != "0"
CLONE_REAP_STANDING_REASONS = {"pushed-mirror", "pushed-mirror-under-pressure"}


def _run(args: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=60
        ).stdout.strip()
    except Exception:
        return ""


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


def active_process_owner(repo: Path) -> int | None:
    try:
        root = repo.resolve()
    except OSError:
        return -1
    for cwd, pid in _ACTIVE_PROCESS_CWDS.items():
        if pid == -1 or cwd == root or root in cwd.parents:
            return pid
    return None


def load_clone_reap_acceptance() -> list[dict]:
    try:
        lines = CLONE_REAP_ACCEPTANCE.read_text(encoding="utf-8", errors="replace").splitlines()
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


def clone_reap_accepted(repo: Path, slug: str, reason: str, acceptance_events: list[dict]) -> tuple[bool, str]:
    if CLONE_REAP_STANDING and reason in CLONE_REAP_STANDING_REASONS:
        return True, "standing-grant-2026-07-09"
    try:
        resolved = str(repo.resolve())
    except OSError:
        resolved = str(repo)
    names = {repo.name, slug}
    for event in reversed(acceptance_events):
        if event.get("root") not in names and event.get("slug") != slug:
            continue
        if event.get("accepted") is not True:
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
        return True, "clone-reap-accepted"
    return False, "missing-clone-reap-acceptance"


def _ignored_is_all_regenerable(repo: Path) -> bool:
    """True iff every gitignored working-tree entry is provably regenerable (safe to lose on re-clone).

    `git status --porcelain --ignored` collapses an ignored directory to a single `!! dir/` line, so we
    test the TOP path component against the regenerable allowlist. An unknown ignored file (e.g. `.env`,
    `local.db`, `data/`) is treated as irreplaceable → not-all-regenerable → the caller KEEPS the clone.
    A quoted/exotic path never matches the allowlist, so it also fails safe (KEEP).
    """
    out = _run(["git", "-C", str(repo), "status", "--porcelain", "--ignored"])
    for line in out.splitlines():
        if not line.startswith("!! "):
            continue
        path = line[3:].strip().strip('"').rstrip("/")
        if not path:
            return False
        top = path.split("/", 1)[0]
        base = path.rsplit("/", 1)[-1]
        if top in REGENERABLE_DIRS:
            continue
        if "/" not in path and (base in REGENERABLE_FILES or base.endswith(REGENERABLE_SUFFIXES)):
            continue
        return False  # an ignored entry we cannot prove regenerable → not loss-free
    return True


def _nested_context_reason(repo: Path) -> str | None:
    """Reason to KEEP if the clone backs a nested git context whose data lives OUTSIDE its ref graph.

    A submodule (.git/modules/*), git-LFS object store (.git/lfs/objects), or linked worktree
    (.git/worktrees/*) can hold committed-but-unpushed work that NO guard on the parent's refs can see,
    and rmtree of the parent destroys those object stores. We never reap such a clone (conservative).
    """
    gitdir = repo / ".git"
    try:
        wt = gitdir / "worktrees"
        if wt.is_dir() and any(wt.iterdir()):
            return "has-linked-worktrees"
        mod = gitdir / "modules"
        if mod.is_dir() and any(mod.iterdir()):
            return "has-submodule"
        lfs = gitdir / "lfs" / "objects"
        if lfs.is_dir() and any(lfs.iterdir()):
            return "has-lfs-objects"
    except OSError:
        return "nested-context-unreadable"
    return None


def _has_local_only_objects(repo: Path) -> bool:
    """True iff any commit reachable from a LOCAL ref, the reflog, or the stash is NOT on a remote.

    This is the comprehensive replacement for `git log --branches`: it enumerates every local ref
    namespace (refs/heads, refs/tags, refs/notes, refs/stash) plus --reflog, and subtracts --remotes.
    refs/stash, refs/notes, refs/tags and reflog-only (hard-reset) commits live on NO remote, so this
    surfaces them even when remote-tracking refs are stale. (Category C — stale/force-rewound remotes
    that make refs/heads commits *look* pushed — is caught by the belt's post-`fetch --prune` re-run.)
    """
    ns = ["refs/heads", "refs/tags", "refs/notes", "refs/stash"]
    refs = _run(["git", "-C", str(repo), "for-each-ref", "--format=%(refname)", *ns]).split()
    cmd = ["git", "-C", str(repo), "rev-list", "--max-count=1", "--reflog", *refs, "--not", "--remotes"]
    return bool(_run(cmd))


def _pristine_now(repo: Path) -> bool:
    """Last-millisecond TOCTOU belt: re-sample the cheapest data guards immediately before rmtree."""
    if _run(["git", "-C", str(repo), "status", "--porcelain"]):
        return False
    if _run(["git", "-C", str(repo), "stash", "list"]):
        return False
    return True


def origin_slug(repo: Path) -> str:
    """owner/name from the origin URL, or the dir name if there is no origin."""
    url = _run(["git", "-C", str(repo), "remote", "get-url", "origin"])
    if not url:
        return repo.name
    slug = url[:-4] if url.endswith(".git") else url
    parts = slug.replace(":", "/").rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else repo.name


@dataclass(frozen=True)
class Verdict:
    reap: bool
    reason: str  # why reaped, or why kept


def classify(repo: Path, active_slugs: set[str], now: float, idle_days: float, pressure: bool) -> Verdict:
    """The loss-free gate. reap=True ONLY for a pure pushed mirror with no live work.

    Order matters: cheapest / most-protective checks first, and every 'keep' names its reason so a
    dropped clone is never silent. This function performs NO removal — it is a pure predicate and is
    the unit under test (test_reap_clones.py).
    """
    rp = repo.resolve()
    sp = str(rp)
    if rp == LIMEN_ROOT or LIMEN_ROOT == rp:
        return Verdict(False, "live-root")
    owner_pid = active_process_owner(repo)
    if owner_pid is not None:
        return Verdict(False, f"active-process-cwd:{owner_pid}")
    if any(m in sp + "/" for m in EXCLUDE_MARKERS):
        return Verdict(False, "excluded-root")
    # STANDALONE clone only: a registered worktree has a .git FILE, not a directory — leave those to
    # reclaim-worktrees.py (removing one with rmtree would corrupt the parent's worktree registry).
    if not (repo / ".git").is_dir():
        return Verdict(False, "not-a-clone")
    if repo.name in CORE or origin_slug(repo).split("/")[-1] in CORE:
        return Verdict(False, "core")

    # NESTED-CONTEXT GUARD: a submodule, LFS store, or linked worktree holds work outside the parent's
    # ref graph that no other guard can see — never reap it (conservative).
    nested = _nested_context_reason(repo)
    if nested:
        return Verdict(False, nested)

    # DATA GUARD (the "7 genesis screenshots" rule): any dirty OR untracked file → never touch it.
    # `git status --porcelain` omits gitignored files, so a non-empty result means real, unsaved work
    # (tracked edits or hand-dropped untracked inputs). Keep and let capture handle it.
    if _run(["git", "-C", str(repo), "status", "--porcelain"]):
        return Verdict(False, "dirty-or-untracked")
    # IGNORED-DATA GUARD: porcelain hid the ignored files above — a `.env`, a local `*.db`, or a data/
    # dir lives on no remote and re-clone cannot restore it. Reap only if every ignored entry is a
    # provably-regenerable dep/build/cache directory; otherwise KEEP.
    if not _ignored_is_all_regenerable(repo):
        return Verdict(False, "ignored-data")

    # PUSH GUARD: commits on any local branch not present on any remote-tracking ref = unpushed work.
    # (No fetch here — stale remote refs only make classify() more conservative; the belt re-verifies
    # against a fresh fetch --prune.)
    if _run(["git", "-C", str(repo), "log", "--branches", "--not", "--remotes", "--oneline"]):
        return Verdict(False, "unpushed-commits")
    # COMPREHENSIVE OBJECT GUARD: stash, local-only tags, git-notes, and reflog-only (hard-reset)
    # commits live outside refs/heads and are invisible to --branches — but they are un-mirrored work.
    if _has_local_only_objects(repo):
        return Verdict(False, "unpushed-objects")
    # HEAD itself must be reachable from a remote ref (covers detached-HEAD-off-a-remote edge cases).
    if not _run(["git", "-C", str(repo), "branch", "-r", "--contains", "HEAD"]):
        return Verdict(False, "head-not-on-remote")

    # No canonical home = we could not re-clone it. Never reap a clone with no origin.
    if not _run(["git", "-C", str(repo), "remote", "get-url", "origin"]):
        return Verdict(False, "no-origin")

    if origin_slug(repo) in active_slugs or repo.name in {s.split("/")[-1] for s in active_slugs}:
        return Verdict(False, "active-task")

    # HIDDEN-MODIFICATION GUARD (run late — only for a would-be reap): a skip-worktree or assume-unchanged
    # bit hides a LOCAL edit to a tracked file from porcelain. `git ls-files -v` tags those with a
    # lowercase letter (assume-unchanged) or `S` (skip-worktree); any such entry → the porcelain guard
    # may have lied → KEEP.
    for line in _run(["git", "-C", str(repo), "ls-files", "-v"]).splitlines():
        if line[:1].islower() or line.startswith("S "):
            return Verdict(False, "hidden-modifications")

    # Idle gate — waived under disk pressure (a pushed mirror is loss-free at any age; when the disk
    # is full we reclaim NOW rather than wait out the idle window).
    if not pressure:
        try:
            age_days = (now - os.path.getmtime(repo)) / 86400
        except OSError:
            age_days = idle_days  # unknown age → treat as old enough (still fully gated above)
        if age_days < idle_days:
            return Verdict(False, "fresh")

    return Verdict(True, "pushed-mirror" if not pressure else "pushed-mirror-under-pressure")


def confirm_recloneable(repo: Path) -> bool:
    """Network belt: prove against the LIVE remote that every local object is already on origin.

    classify() proves re-cloneability from LOCAL refs, but local remote-tracking refs can be STALE —
    origin may have force-rewound past our HEAD, deleted our branch, or advanced while we moved ahead —
    and a stale tracking ref can make un-mirrored local commits *look* pushed (the Category-C data-loss
    class). So the belt FETCHES the live remote (with --prune, so a branch deleted on origin drops its
    tracking ref) and then re-runs the comprehensive reachability proof against the now-fresh
    refs/remotes/*: if ANY object reachable from a local ref, the reflog, or the stash is NOT reachable
    from a remote-tracking ref, the clone holds work origin does not have → return False (KEEP).

    FAIL-SAFE: any failure (origin gone/renamed → local clone is the only copy, offline, or auth-less)
    returns False, so we skip rather than risk loss; a later online beat reaps it. A pure mirror that is
    merely BEHIND origin still passes — after the fetch its HEAD is an ancestor of the advanced tip, so
    nothing is local-only (this preserves the remote-unreachable=80 behind-origin fix). Disable the
    network belt (trust local refs) with LIMEN_REAP_VERIFY_REMOTE=0.
    """
    if os.environ.get("LIMEN_REAP_VERIFY_REMOTE", "1").strip().lower() in {"0", "false", "no", "off"}:
        return True
    head = _run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if not head:
        return False
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), "ls-remote", "origin"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_GIT_ENV,
        )
    except Exception:
        return False
    if res.returncode != 0 or not res.stdout.strip():
        return False  # origin gone / renamed-away / offline → local clone may be the only copy → keep
    # Refresh remote-tracking refs against the live remote so the reachability proof is trustworthy.
    # --prune expires tracking refs for branches deleted on origin; --no-tags avoids minting local tags.
    try:
        fetch = subprocess.run(
            ["git", "-C", str(repo), "fetch", "--prune", "--no-tags", "--quiet", "origin"],
            capture_output=True,
            text=True,
            timeout=90,
            env=_GIT_ENV,
        )
    except Exception:
        return False
    if fetch.returncode != 0:
        return False  # could not verify against the live remote → fail-safe keep
    # Authoritative proof: after the refresh, nothing reachable from any local ref/reflog/stash is
    # missing from the remote. Catches force-push orphans, ahead-of-origin HEADs, and deleted branches.
    return not _has_local_only_objects(repo)


def active_task_slugs(tasks_path: Path) -> set[str]:
    try:
        import yaml

        data = yaml.safe_load(tasks_path.read_text()) or {}
    except Exception:
        return set()
    live = {"open", "dispatched", "in_progress"}
    return {t["repo"] for t in data.get("tasks", []) if t.get("status") in live and t.get("repo")}


def disk_pct_used(path: Path) -> float:
    try:
        u = shutil.disk_usage(str(path))
        return 100.0 * u.used / u.total if u.total else 0.0
    except Exception:
        return 0.0


def disk_free_gib(path: Path) -> float:
    """Absolute free space (GiB) — the HONEST pressure signal on a large APFS volume. df/statvfs
    counts ~100GB of purgeable-but-reclaimable space (snapshots, caches macOS releases on demand) as
    "used", so `disk_pct_used` can read 95% while the volume has ~120GB effectively free (the
    meter-lie). Emergency reap keys off THIS absolute floor, not the misleading percentage. Fail-open
    to +inf (→ no pressure) so a probe error never triggers an aggressive waived-gate reap."""
    try:
        return shutil.disk_usage(str(path)).free / (1024**3)
    except Exception:
        return float("inf")


def discover_clones(workspace: Path, maxdepth: int) -> list[Path]:
    """Every .git directory under the workspace (standalone clones + the top level), maxdepth-bounded."""
    out: list[Path] = []
    ws = str(workspace)
    try:
        res = subprocess.run(
            ["find", ws, "-maxdepth", str(maxdepth), "-name", ".git"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception:
        return out
    for line in res.stdout.splitlines():
        p = Path(line)
        if p.name == ".git":
            out.append(p.parent)
    return sorted(set(out))


def main() -> int:
    global _ACTIVE_PROCESS_CWDS
    ap = argparse.ArgumentParser(description="Reap pure pushed-mirror clones (loss-free).")
    ap.add_argument("--apply", action="store_true", help="actually remove (default: dry-run)")
    ap.add_argument(
        "--pressure",
        dest="pressure",
        action="store_true",
        default=None,
        help="force disk-pressure mode (waive idle gate)",
    )
    ap.add_argument("--no-pressure", dest="pressure", action="store_false", help="force pressure OFF regardless of df")
    ap.add_argument("--max", type=int, default=int(os.environ.get("LIMEN_REAP_MAX", "50")))
    args = ap.parse_args()
    _ACTIVE_PROCESS_CWDS = active_process_cwds()

    idle_days = float(os.environ.get("LIMEN_REAP_IDLE_DAYS", "2"))
    high_water = float(os.environ.get("LIMEN_DISK_HIGH_WATER", "85"))
    free_floor = float(os.environ.get("LIMEN_DISK_FREE_FLOOR_GIB", "15"))
    maxdepth = int(os.environ.get("LIMEN_REAP_MAXDEPTH", "3"))

    pct = disk_pct_used(WORKSPACE)
    free_gib = disk_free_gib(WORKSPACE)
    # Emergency pressure (age-gate WAIVED → aggressive rmtree every beat) now keys off ABSOLUTE low
    # free space, not the percentage. On a large APFS volume, df/statvfs counts ~100GB of
    # purgeable-but-reclaimable space as "used", so a 95%-by-percent disk can still have ~120GB
    # effectively free — waiving the loss-free age gate on that false 95% made the daemon reap hard
    # every beat for no reason (and slowed the beat). It now fires only when raw free genuinely drops
    # below the floor; the normal idle-gate reap still runs the rest of the time. ([[meter-lie-and-dead-daemon-incident]])
    pressure = args.pressure if args.pressure is not None else (free_gib <= free_floor)
    active = active_task_slugs(LIMEN_ROOT / "tasks.yaml")
    now = time.time()

    mode = "APPLY" if args.apply else "dry-run"
    print(
        f"[reap-clones] disk {pct:.0f}% used, {free_gib:.0f}GiB free (floor {free_floor:.0f}GiB, hw {high_water:.0f}%) → "
        f"pressure={'ON' if pressure else 'off'}; mode={mode}; idle-gate={'waived' if pressure else f'{idle_days:g}d'}"
    )

    reaped = kept = 0
    freed = 0
    kept_reasons: dict[str, int] = {}
    clone_reap_acceptance = load_clone_reap_acceptance()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = LOG.open("a") if args.apply else None
    try:
        for repo in discover_clones(WORKSPACE, maxdepth):
            v = classify(repo, active, now, idle_days, pressure)
            if not v.reap:
                kept += 1
                kept_reasons[v.reason] = kept_reasons.get(v.reason, 0) + 1
                continue
            # Network belt: confirm the origin still holds HEAD before we delete the local copy.
            if not confirm_recloneable(repo):
                kept += 1
                kept_reasons["remote-unreachable"] = kept_reasons.get("remote-unreachable", 0) + 1
                continue
            if reaped >= args.max:
                print(f"[reap-clones] hit --max={args.max}; {repo} and any remainder LEFT for next run")
                kept += 1
                continue
            try:
                sz = sum(f.stat().st_size for f in repo.rglob("*") if f.is_file())
            except Exception:
                sz = 0
            slug = origin_slug(repo)
            # TOCTOU belt: work may have landed between classify() and now — re-verify pristine at the
            # last instant before an irreversible delete.
            if args.apply and not _pristine_now(repo):
                kept += 1
                kept_reasons["raced-dirty"] = kept_reasons.get("raced-dirty", 0) + 1
                continue
            if args.apply:
                accepted, accept_reason = clone_reap_accepted(repo, slug, v.reason, clone_reap_acceptance)
                if not accepted:
                    kept += 1
                    kept_reasons[accept_reason] = kept_reasons.get(accept_reason, 0) + 1
                    continue
            print(f"  {'REAP' if args.apply else 'WOULD reap'}: {repo}  ({slug}, {sz / 1e9:.2f} GB, {v.reason})")
            if args.apply:
                shutil.rmtree(repo, ignore_errors=True)
                if logf:
                    logf.write(json.dumps({"repo": str(repo), "slug": slug, "bytes": sz, "reason": v.reason}) + "\n")
            reaped += 1
            freed += sz
    finally:
        if logf:
            logf.close()

    kr = ", ".join(f"{k}={n}" for k, n in sorted(kept_reasons.items())) or "none"
    print(
        f"[reap-clones] {'reaped' if args.apply else 'would reap'} {reaped} clone(s), "
        f"{freed / 1e9:.2f} GB; kept {kept} ({kr})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
