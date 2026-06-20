#!/usr/bin/env python3
"""jules-land.py — LAND completed jules work as PRs (the missing jules→PR step).

The gap this fills: jules produces a diff per completed session, but `limen harvest` only
marks the task done + stores the diff text — it never APPLIES the diff or opens a PR, so the
work never lands in the repo. Local lanes go worktree→apply→commit→push→PR; jules had no
equivalent. This is that equivalent: for each COMPLETED jules session matched to a task,
resolve the repo, make an isolated worktree off origin/<base>, `jules remote pull --apply`
the session patch into it, then commit→push→PR and mark the task done. Same isolation
keystone as local dispatch (throwaway worktree, never the live tree).

Dry-run by default (prints the plan); --apply does real worktree→PR. --limit N bounds it.
Idempotent-ish: skips sessions whose task is already done and empty-diff sessions (no PR).
"""
import argparse
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.dispatch import _resolve_repo_dir, _git, _default_branch  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry, Task  # noqa: E402
import datetime  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
WT_ROOT = Path(os.environ.get("LIMEN_WORKTREES", Path.home() / "Workspace" / ".limen-worktrees"))
JULES = os.environ.get("LIMEN_JULES_BIN", "jules")
_TASK_ID_RE = re.compile(r"Complete task (\S+?):")


def completed_sessions():
    """(sid, task_id) for every COMPLETED jules session (task_id from the description)."""
    r = subprocess.run([JULES, "remote", "list", "--session"],
                       capture_output=True, text=True, timeout=90)
    out = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        if "completed" not in line.lower():
            continue
        m = _TASK_ID_RE.search(line)
        out.append((parts[0], m.group(1) if m else ""))
    return out


def land_one(task: Task, sid: str, apply: bool) -> str:
    repo_dir = _resolve_repo_dir(task)
    if repo_dir is None:
        return f"SKIP {task.id}: no local checkout of {task.repo}"
    base = _default_branch(repo_dir)
    if not apply:
        return f"would land {task.id} <- jules session {sid} into {task.repo} (base {base})"
    _git(["fetch", "origin", base], repo_dir, timeout=300)
    branch = f"limen/jules-{task.id.lower()}-{secrets.token_hex(2)}"
    wt = WT_ROOT / branch.replace("/", "_")
    WT_ROOT.mkdir(parents=True, exist_ok=True)
    add = _git(["worktree", "add", "-b", branch, str(wt), f"origin/{base}"], repo_dir, timeout=120)
    if add.returncode != 0:
        return f"FAIL {task.id}: worktree add ({add.stderr.strip()[:120]})"
    try:
        # apply the jules session patch directly into the isolated worktree
        pull = subprocess.run([JULES, "remote", "pull", "--session", sid, "--apply"],
                              cwd=str(wt), capture_output=True, text=True, timeout=180)
        _git(["add", "-A"], wt)
        if _git(["diff", "--cached", "--quiet"], wt).returncode == 0:
            return f"no-op {task.id}: jules session {sid} produced no diff"
        msg = f"{task.title}\n\nlimen task {task.id} (jules session {sid})"
        c = _git(["-c", f"user.name={os.environ.get('LIMEN_COMMIT_NAME', '4444J99')}",
                  "-c", f"user.email={os.environ.get('LIMEN_COMMIT_EMAIL', '4444J99@users.noreply.github.com')}",
                  "commit", "-m", msg], wt)
        if c.returncode != 0:
            return f"FAIL {task.id}: commit ({c.stderr.strip()[:120]})"
        p = _git(["push", "-u", "origin", branch], wt, timeout=300)
        if p.returncode != 0:
            return f"FAIL {task.id}: push ({p.stderr.strip()[:120]})"
        pr = subprocess.run(["gh", "pr", "create", "--repo", task.repo, "--head", branch,
                             "--base", base, "--title", f"[limen jules {task.id}] {task.title}"[:100],
                             "--body", f"Lands completed jules session {sid}.\n\nlimen task {task.id}"],
                            capture_output=True, text=True, timeout=120)
        if pr.returncode != 0:
            return f"FAIL {task.id}: pr create ({pr.stderr.strip()[:120]})"
        return f"LANDED {task.id} -> {pr.stdout.strip()}"
    finally:
        _git(["worktree", "remove", "--force", str(wt)], repo_dir)
        _git(["branch", "-D", branch], repo_dir)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--recover", action="store_true",
                    help="also re-land jules tasks marked done that NEVER got a PR (the "
                         "harvest gap: harvest closed them without applying the diff)")
    args = ap.parse_args()

    lf = load_limen_file(TASKS)
    by_id = {t.id: t for t in lf.tasks}
    now = datetime.datetime.now(datetime.timezone.utc)

    def ever_pr(t) -> bool:
        return any("/pull/" in str(e.session_id or "") for e in (t.dispatch_log or []))

    done = 0
    for sid, tid in completed_sessions():
        if done >= args.limit:
            break
        t = by_id.get(tid)
        if t is None:
            continue
        if t.status == "done":
            # only recover done tasks whose work never actually landed as a PR
            if not args.recover or ever_pr(t):
                continue
        msg = land_one(t, sid, args.apply)
        print(f"  {msg}")
        if args.apply and msg.startswith("LANDED"):
            # record the PR URL in session_id so ever_pr() sees it → never re-land (no dupes)
            pr_url = msg.split("-> ", 1)[1].strip() if "-> " in msg else sid
            t.status = "done"
            t.updated = now
            t.dispatch_log.append(DispatchLogEntry(
                timestamp=now, agent="jules", session_id=pr_url, status="done",
                output=f"jules-land: landed session {sid} as PR"))
            save_limen_file(TASKS, lf)  # persist per-PR so a mid-run stop can't cause dupes
            done += 1
    if args.apply and done:
        save_limen_file(TASKS, lf)
        print(f"  APPLIED -> {done} jules session(s) landed + marked done")
    elif not args.apply:
        print("  dry-run (pass --apply to land for real)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
