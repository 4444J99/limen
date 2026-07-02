#!/usr/bin/env python3
"""reap-clones.py — the CLONE-REAP organ (lifecycle rung 4b).

A local clone is a DISPOSABLE CACHE of its GitHub origin. The developer lifecycle every human
runs is  clone → work → push → *delete the clone*  (re-clone on demand). The fleet clones repos
and reaps NONE, so ~/Workspace creeps to full — on 2026-07-01 the data volume hit 411G / 96%
with organvm/ at 14G plus a DUPLICATE a-organvm/ at 3.2G, dormant full clones, and 58 node_modules.
clone-maintenance.sh reaped node_modules but only *printed* reapable clones ("remove only with user
OK"): the last step of the lifecycle was gated on the operator's hand, so the disk crept back every time.

This organ reaps a clone ONLY when it is a PURE PUSHED MIRROR with no live work — the loss-free gate,
identical in spirit to reclaim-worktrees.py:

  • clean working tree AND no untracked files (`git status --porcelain` is EMPTY), AND
  • zero unpushed commits on ANY local branch (`git log --branches --not --remotes` is EMPTY), AND
  • HEAD is reachable from an origin ref, AND
  • no active limen task for the repo's origin slug, AND
  • not a CORE repo, not the live LIMEN_ROOT, not inside a worktree/cartridge root, AND
  • idle >= min-age — UNLESS disk pressure >= high-water, which WAIVES the age gate (still loss-free).

Every gate is loss-free (re-cloneable from GitHub; nothing local unpushed or untracked), so removal
is REVERSIBLE and therefore NOT a human-gated action — it runs autonomically. It NEVER deletes DATA:
a clone with untracked files (possible hand-dropped inputs — the "7 genesis screenshots" rule) or with
unpushed commits is SKIPPED and reported as needs-capture, never removed. capture.sh pushes that work
first; a later beat then finds a pure mirror and reaps it. It only ever touches STANDALONE clones
(`.git` is a directory); registered worktrees (`.git` is a file) are reclaim-worktrees.py's job.

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

HOME = os.environ.get("HOME", str(Path.home()))
WORKSPACE = Path(os.environ.get("LIMEN_WORKSPACE", f"{HOME}/Workspace"))
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", f"{HOME}/Workspace/limen")).resolve()
LOG = LIMEN_ROOT / "logs" / "reap-clones.jsonl"

# CORE repos the operator lives in / the conductor needs local — never reaped even if pushed-clean.
DEFAULT_CORE = "limen session-meta sovereign-systems--elevate-align portfolio portvs universal-mail--automation"
CORE = set(os.environ.get("LIMEN_REAP_CORE", DEFAULT_CORE).split())

# Paths that are somebody else's lifecycle (worktree reaper, cartridge co-tenant, throwaway roots).
EXCLUDE_MARKERS = (".claude/worktrees", ".limen-worktrees", ".home-cartridge", ".worktrees", "/node_modules/")


def _run(args: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=60
        ).stdout.strip()
    except Exception:
        return ""


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
    if any(m in sp + "/" for m in EXCLUDE_MARKERS):
        return Verdict(False, "excluded-root")
    # STANDALONE clone only: a registered worktree has a .git FILE, not a directory — leave those to
    # reclaim-worktrees.py (removing one with rmtree would corrupt the parent's worktree registry).
    if not (repo / ".git").is_dir():
        return Verdict(False, "not-a-clone")
    if repo.name in CORE or origin_slug(repo).split("/")[-1] in CORE:
        return Verdict(False, "core")

    # DATA GUARD (the "7 genesis screenshots" rule): any dirty OR untracked file → never touch it.
    # `git status --porcelain` already omits gitignored files, so a non-empty result means real,
    # unsaved work (tracked edits or hand-dropped untracked inputs). Keep and let capture handle it.
    if _run(["git", "-C", str(repo), "status", "--porcelain"]):
        return Verdict(False, "dirty-or-untracked")

    # PUSH GUARD: commits on any local branch not present on any remote-tracking ref = unpushed work.
    # Loss-free removal requires EVERY local commit already live on origin. (No fetch — stale remote
    # refs only make us more conservative, never less.)
    if _run(["git", "-C", str(repo), "log", "--branches", "--not", "--remotes", "--oneline"]):
        return Verdict(False, "unpushed-commits")
    # HEAD itself must be reachable from a remote ref (covers detached-HEAD-off-a-remote edge cases).
    if not _run(["git", "-C", str(repo), "branch", "-r", "--contains", "HEAD"]):
        return Verdict(False, "head-not-on-remote")

    # No canonical home = we could not re-clone it. Never reap a clone with no origin.
    if not _run(["git", "-C", str(repo), "remote", "get-url", "origin"]):
        return Verdict(False, "no-origin")

    if origin_slug(repo) in active_slugs or repo.name in {s.split("/")[-1] for s in active_slugs}:
        return Verdict(False, "active-task")

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
    """Network belt to the local push gate: the origin must ACTUALLY still hold HEAD.

    classify() proves 're-cloneable' from LOCAL remote-tracking refs, which survive even if the origin
    was deleted or renamed on GitHub — in which case the local clone is the ONLY copy and must never be
    reaped. `git ls-remote` asks the real remote. FAIL-SAFE: any failure (origin gone OR merely offline)
    returns False, so we skip rather than risk loss; a later online beat reaps it. Disable (trust local
    refs) with LIMEN_REAP_VERIFY_REMOTE=0.
    """
    if os.environ.get("LIMEN_REAP_VERIFY_REMOTE", "1").strip().lower() in {"0", "false", "no", "off"}:
        return True
    head = _run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if not head:
        return False
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), "ls-remote", "origin"], capture_output=True, text=True, timeout=30
        )
    except Exception:
        return False
    if res.returncode != 0 or not res.stdout.strip():
        return False
    return head in res.stdout  # HEAD's sha is present on the remote → truly re-cloneable


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

    idle_days = float(os.environ.get("LIMEN_REAP_IDLE_DAYS", "2"))
    high_water = float(os.environ.get("LIMEN_DISK_HIGH_WATER", "85"))
    maxdepth = int(os.environ.get("LIMEN_REAP_MAXDEPTH", "3"))

    pct = disk_pct_used(WORKSPACE)
    pressure = args.pressure if args.pressure is not None else (pct >= high_water)
    active = active_task_slugs(LIMEN_ROOT / "tasks.yaml")
    now = time.time()

    mode = "APPLY" if args.apply else "dry-run"
    print(
        f"[reap-clones] disk {pct:.0f}% used (high-water {high_water:.0f}%) → "
        f"pressure={'ON' if pressure else 'off'}; mode={mode}; idle-gate={'waived' if pressure else f'{idle_days:g}d'}"
    )

    reaped = kept = 0
    freed = 0
    kept_reasons: dict[str, int] = {}
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
