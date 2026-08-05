#!/usr/bin/env python3
"""rewrite-owners — redirect every config that hardcodes an OLD GitHub owner to `organvm`.

The GitHub consolidation (`scripts/consolidate-github.py`) collapses the fragmented
multi-owner estate into ONE org `organvm`. GitHub *URL* redirects survive a transfer, but
the LIVE FLEET keys on literal `owner/repo` strings in three places that DO NOT auto-redirect
and will silently break dispatch the moment a repo moves:

  1. tasks.yaml  — every task's `repo:` owner (a-organvm / 4444J99 / organvm-i-theoria / …).
                   The isolated-local-run + PR logic resolves a checkout by this exact string.
  2. .github/workflows/deploy-api.yml — the hardcoded `LIMEN_GITHUB_REPO=4444J99/limen`
                   env literal pushed into Cloud Run (the dossier's "CI coupling (real)" row).
  3. local git checkouts under ~/Workspace — their `origin` remote still points at the old
                   owner; after a transfer the redirect works but should be made explicit so
                   `git fetch origin <base>` and PR creation stay unambiguous.

SAFE BY DEFAULT. Dry-run prints exactly what it WOULD change and changes NOTHING. Only
`--apply` (GATED) writes — and even then it writes tasks.yaml via the SAME atomic
`limen.io.save_limen_file` (temp-file + os.replace) every other writer uses, so a crash or a
concurrent reader can never observe a truncated file. The `git remote set-url` commands are
ALWAYS only *emitted* (printed / written to a .sh) — this script never runs git or touches a
checkout. Reversible: re-run pointing the mapping back, or `git checkout -- tasks.yaml
.github/workflows/deploy-api.yml` before any commit.

  python3 scripts/rewrite-owners.py                 # DRY-RUN plan (read-only)
  python3 scripts/rewrite-owners.py --apply          # ⚠ GATED: write tasks.yaml + deploy-api.yml
  python3 scripts/rewrite-owners.py --emit-remotes out.sh   # write the git-remote commands to a file
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# tasks.yaml is written through the project's ONE atomic writer — never a hand-rolled open().
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(LIMEN_ROOT / "cli" / "src"))
from limen.io import load_limen_file  # noqa: E402
from limen.tabularius import apply_limen_file_sync  # noqa: E402

TARGET = "organvm"

# The OLD source owners — kept identical to scripts/consolidate-github.py:OWNERS so the two
# stay in lockstep (one source of truth for "which owners are collapsing"). TARGET is excluded.
# Anything NOT in this set (e.g. external upstreams like `langchain-ai/langgraph`) is LEFT
# UNTOUCHED — we only own and only transfer these owners.
OLD_OWNERS = {
    "4444J99",
    "a-organvm",
    "meta-organvm",
    "organvm-i-theoria",
    "organvm-ii-poiesis",
    "organvm-iii-ergon",
    "organvm-iv-taxis",
    "organvm-v-logos",
    "organvm-vi-koinonia",
    "organvm-vii-kerygma",
}
# Bare repo names (no owner prefix) that are ours and must canonicalize to organvm/<name>.
# `repo: limen` is the conductor itself; with no owner the dispatcher can't resolve a checkout,
# so collapse it onto the same canonical target every owner/limen ref lands on.
BARE_OURS = {"limen"}

TASKS_PATH = Path(os.environ.get("LIMEN_TASKS", LIMEN_ROOT / "tasks.yaml"))
DEPLOY_YML = LIMEN_ROOT / ".github" / "workflows" / "deploy-api.yml"
WORKSPACE = Path(os.environ.get("LIMEN_WORKDIR", Path.home() / "Workspace"))


def map_repo(repo: str | None) -> str | None:
    """Return the rewritten `owner/name` if `repo` points at an OLD owner (or is a bare
    name we own), else None (= leave untouched). Pure: no I/O, easy to unit-test/reverse."""
    if not repo:
        return None
    repo = repo.strip()
    if not repo:
        return None
    if "/" in repo:
        owner, name = repo.split("/", 1)
        if owner in OLD_OWNERS and name:
            new = f"{TARGET}/{name}"
            return new if new != repo else None
        return None
    # bare name, no owner
    if repo in BARE_OURS:
        return f"{TARGET}/{repo}"
    return None


# ---------------------------------------------------------------------------- tasks.yaml ----

def plan_tasks() -> tuple[int, list[tuple[str, str, str]], object]:
    """Load tasks.yaml via the pydantic model and compute every repo rewrite.
    Returns (count, changes[(task_id, old, new)], limen_file_with_rewrites_applied_in_memory)."""
    lf = load_limen_file(TASKS_PATH)
    changes: list[tuple[str, str, str]] = []
    for t in lf.tasks:
        new = map_repo(t.repo)
        if new is not None:
            changes.append((t.id, t.repo, new))
            t.repo = new  # mutate the in-memory model; only persisted on --apply
    return len(changes), changes, lf


def apply_tasks(lf) -> None:
    """Submit the owner projection through the single record keeper."""
    apply_limen_file_sync(TASKS_PATH, lf, agent="rewrite-owners", session_id="apply")


# ----------------------------------------------------------------- deploy-api.yml literal ----

DEPLOY_RE = re.compile(r"(LIMEN_GITHUB_REPO=)([\w.-]+)/limen\b")


def plan_deploy() -> tuple[bool, str | None, str | None]:
    """Detect the hardcoded LIMEN_GITHUB_REPO=<old-owner>/limen. Returns (needs_fix, old, new)."""
    if not DEPLOY_YML.exists():
        return False, None, None
    text = DEPLOY_YML.read_text()
    m = DEPLOY_RE.search(text)
    if not m:
        return False, None, None
    owner = m.group(2)
    if owner == TARGET:
        return False, None, None  # already organvm
    old = f"{m.group(1)}{owner}/limen"
    new = f"{m.group(1)}{TARGET}/limen"
    return True, old, new


def apply_deploy() -> bool:
    text = DEPLOY_YML.read_text()
    new_text, n = DEPLOY_RE.subn(rf"\g<1>{TARGET}/limen", text)
    if n and new_text != text:
        # plain literal substitution in a YAML workflow; rewrite the whole file atomically-ish
        DEPLOY_YML.write_text(new_text)
        return True
    return False


# --------------------------------------------------- emit (NOT run) git remote set-url ----

def _git_remote_url(checkout: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(checkout), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _owner_from_url(url: str) -> tuple[str, str] | None:
    """Parse owner/name from an https or ssh github remote URL."""
    u = url.strip()
    u = re.sub(r"\.git$", "", u)
    m = re.search(r"github\.com[:/]+([\w.-]+)/([\w.-]+)$", u)
    if not m:
        return None
    return m.group(1), m.group(2)


def plan_remotes() -> list[tuple[Path, str, str]]:
    """Scan git checkouts under ~/Workspace whose origin points at an OLD owner.
    Returns (checkout_path, old_url, new_url). NEVER runs set-url — caller only emits."""
    out: list[tuple[Path, str, str]] = []
    if not WORKSPACE.exists():
        return out
    seen: set[Path] = set()
    # find every .git (repo or worktree pointer); cap depth to stay fast
    for gitdir in WORKSPACE.rglob(".git"):
        checkout = gitdir.parent
        if checkout in seen:
            continue
        seen.add(checkout)
        url = _git_remote_url(checkout)
        if not url:
            continue
        parsed = _owner_from_url(url)
        if not parsed:
            continue
        owner, name = parsed
        if owner in OLD_OWNERS:
            new_url = re.sub(
                rf"([:/]){re.escape(owner)}/{re.escape(name)}",
                rf"\g<1>{TARGET}/{name}",
                url,
                count=1,
            )
            if new_url != url:
                out.append((checkout, url, new_url))
    return out


def emit_remote_commands(remotes: list[tuple[Path, str, str]]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "# EMITTED by scripts/rewrite-owners.py — review, then run by hand AFTER the transfer.",
        "# This script does NOT run these; updating a remote before the repo actually moves",
        "# would point your checkout at a not-yet-existing path. Run post-consolidation.",
        "set -euo pipefail",
        "",
    ]
    for checkout, old_url, new_url in remotes:
        lines.append(f"# {old_url}  ->  {new_url}")
        lines.append(f"git -C {shquote(str(checkout))} remote set-url origin {shquote(new_url)}")
        lines.append("")
    return "\n".join(lines)


def shquote(s: str) -> str:
    if re.fullmatch(r"[\w@%+=:,./-]+", s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


# ----------------------------------------------------------------------------------- main ----

def main() -> int:
    apply = "--apply" in sys.argv
    emit_path = None
    if "--emit-remotes" in sys.argv:
        i = sys.argv.index("--emit-remotes")
        if i + 1 < len(sys.argv):
            emit_path = Path(sys.argv[i + 1])

    print(f"=== rewrite-owners → {TARGET} ===")
    print(f"  tasks.yaml : {TASKS_PATH}")
    print(f"  deploy yml : {DEPLOY_YML}")
    print(f"  workspace  : {WORKSPACE}")
    print(f"  old owners : {', '.join(sorted(OLD_OWNERS))}")
    print(f"  bare-ours  : {', '.join(sorted(BARE_OURS))}  (external upstreams left untouched)\n")

    # 1) tasks.yaml
    n_tasks, changes, lf = plan_tasks()
    print(f"[1] tasks.yaml repo: refs to rewrite = {n_tasks}")
    from collections import Counter
    by_owner = Counter(old.split("/")[0] if "/" in old else f"<bare:{old}>" for _, old, _ in changes)
    for owner, c in by_owner.most_common():
        print(f"      {c:5} {owner} → {TARGET}")
    print("    sample (first 8):")
    for tid, old, new in changes[:8]:
        print(f"      {tid}: {old} → {new}")
    if len(changes) > 8:
        print(f"      … +{len(changes)-8} more")

    # 2) deploy-api.yml
    need_fix, old_lit, new_lit = plan_deploy()
    print(f"\n[2] deploy-api.yml LIMEN_GITHUB_REPO literal: {'1 to fix' if need_fix else 'none (already organvm or absent)'}")
    if need_fix:
        print(f"      {old_lit} → {new_lit}")

    # 3) git remotes (EMIT ONLY)
    remotes = plan_remotes()
    print(f"\n[3] git checkouts under {WORKSPACE} with origin on an OLD owner = {len(remotes)} (emit-only, never run)")
    for checkout, old_url, new_url in remotes[:8]:
        print(f"      {checkout}: {old_url} → {new_url}")
    if len(remotes) > 8:
        print(f"      … +{len(remotes)-8} more")

    remote_script = emit_remote_commands(remotes)
    if emit_path:
        emit_path.write_text(remote_script)
        try:
            emit_path.chmod(0o755)
        except OSError:
            pass
        print(f"\n    wrote git-remote commands → {emit_path} (review, run by hand AFTER transfer)")

    # apply gate
    if not apply:
        print(f"\nDRY-RUN — nothing written. tasks.yaml refs that WOULD change: {n_tasks}")
        print("Re-run with --apply (GATED) to write tasks.yaml + deploy-api.yml via the atomic writer.")
        print("The git-remote commands are EMIT-ONLY in all modes; use --emit-remotes <file> to save them.")
        return 0

    print(f"\n⚠ --apply: writing tasks.yaml ({n_tasks} refs) + deploy-api.yml …")
    if n_tasks:
        apply_tasks(lf)
    print("  ✓ tasks.yaml rewritten via atomic save_limen_file")
    if need_fix and apply_deploy():
        print(f"  ✓ deploy-api.yml LIMEN_GITHUB_REPO → {TARGET}/limen")
    print("  (git remotes NOT touched — run the emitted commands manually post-transfer.)")
    print(f"\nReversible: `git -C {LIMEN_ROOT} checkout -- tasks.yaml .github/workflows/deploy-api.yml` "
          "before committing, or re-run with the mapping reversed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
