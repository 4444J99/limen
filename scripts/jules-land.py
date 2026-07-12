#!/usr/bin/env python3
"""jules-land.py — LAND completed jules work as PRs (the missing jules→PR step).

The gap this fills: jules produces a diff per completed session, but `limen harvest` only
marks the task done + stores the diff text — it never APPLIES the diff or opens a PR, so the
work never lands in the repo. Local lanes go worktree→apply→commit→push→PR; jules had no
equivalent. This is that equivalent: for each COMPLETED jules session matched to a task,
resolve the repo, make an isolated worktree off origin/<base>, `jules remote pull --apply`
the session patch into it, then commit→push→PR and mark the task done. Same isolation
keystone as local dispatch (isolated worktree, never the live tree). Physical local cleanup is
delegated to the receipt-backed reclaim/reap organs after archive and redaction proof; this script
never force-removes the isolated root or branch itself.

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
from limen.jules_remote import JulesRemoteSnapshot, probe_jules_remote_sessions  # noqa: E402
from limen.models import DispatchLogEntry, Task  # noqa: E402
from limen.worktree_roots import default_worktrees_root  # noqa: E402
import datetime  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
WT_ROOT = Path(os.environ.get("LIMEN_WORKTREES") or default_worktrees_root())
JULES = os.environ.get("LIMEN_JULES_BIN", "jules")
_TASK_ID_RE = re.compile(r"Complete task (\S+?):")
_GENERATED_CLEAN_PATHS = (
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


def purge_generated_payloads(wt: Path) -> str:
    if not wt.exists():
        return "missing"
    clean = _git(["clean", "-Xdf", "--", *_GENERATED_CLEAN_PATHS], wt, timeout=180)
    if clean.returncode != 0:
        return f"failed:{(clean.stderr or clean.stdout).strip()[:160]}"
    removed = sum(1 for line in (clean.stdout or "").splitlines() if line.strip().startswith("Removing "))
    return f"removed:{removed}"


def completed_sessions(
    sid_map: dict | None = None,
    snapshot: JulesRemoteSnapshot | None = None,
):
    """(sid, task_id) for every COMPLETED jules session.

    task_id resolves FIRST from sid_map (session id → task id, built from tasks.yaml dispatch_log
    when we dispatched the task) and only THEN from the description regex. The regex path is
    fragile: `jules remote list` truncates the title, and the FLAME kernel can lead the prompt, so
    "Complete task <id>:" is often pushed out of the visible line — which silently broke harvesting
    (completed sessions never matched → never landed as PRs). sid_map is the robust primary matcher;
    the regex stays as a fallback for sessions we have no local record of."""
    sid_map = sid_map or {}
    remote = snapshot or probe_jules_remote_sessions(binary=JULES)
    if not remote.available:
        return []
    out = []
    for session in remote.sessions.values():
        if session.status != "completed":
            continue
        sid = session.session_id
        m = _TASK_ID_RE.search(session.raw)
        out.append((sid, sid_map.get(sid) or (m.group(1) if m else "")))
    return sorted(out)


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
    # apply the jules session patch directly into the isolated worktree (the staged-diff check
    # below is the real signal — a failed pull just yields an empty diff → no-op, never a crash)
    subprocess.run(
        [JULES, "remote", "pull", "--session", sid, "--apply"], cwd=str(wt), capture_output=True, text=True, timeout=180
    )
    _git(["add", "-A"], wt)
    retain = (
        f"local root retained: {wt}; branch retained: {branch}; "
        "cleanup delegated to docs/worktree-reclaim-acceptance.jsonl + reclaim-worktrees.py "
        "and docs/branch-reap-acceptance.jsonl + reap-branches.py"
    )
    if _git(["diff", "--cached", "--quiet"], wt).returncode == 0:
        generated_cleanup = purge_generated_payloads(wt)
        return f"no-op {task.id}: jules session {sid} produced no diff; generated cleanup {generated_cleanup}; {retain}"
    msg = f"{task.title}\n\nlimen task {task.id} (jules session {sid})"
    c = _git(
        [
            "-c",
            f"user.name={os.environ.get('LIMEN_COMMIT_NAME', '4444J99')}",
            "-c",
            f"user.email={os.environ.get('LIMEN_COMMIT_EMAIL', '4444J99@users.noreply.github.com')}",
            "commit",
            "-m",
            msg,
        ],
        wt,
    )
    if c.returncode != 0:
        generated_cleanup = purge_generated_payloads(wt)
        return f"FAIL {task.id}: commit ({c.stderr.strip()[:120]}); generated cleanup {generated_cleanup}; {retain}"
    p = _git(["push", "-u", "origin", branch], wt, timeout=300)
    if p.returncode != 0:
        generated_cleanup = purge_generated_payloads(wt)
        return f"FAIL {task.id}: push ({p.stderr.strip()[:120]}); generated cleanup {generated_cleanup}; {retain}"
    pr = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            task.repo,
            "--head",
            branch,
            "--base",
            base,
            "--title",
            f"[limen jules {task.id}] {task.title}"[:100],
            "--body",
            f"Lands completed jules session {sid}.\n\nlimen task {task.id}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if pr.returncode != 0:
        generated_cleanup = purge_generated_payloads(wt)
        return f"FAIL {task.id}: pr create ({pr.stderr.strip()[:120]}); generated cleanup {generated_cleanup}; {retain}"
    generated_cleanup = purge_generated_payloads(wt)
    return f"LANDED {task.id} -> {pr.stdout.strip()} ; generated cleanup {generated_cleanup}; {retain}"


def landed_pr_url(message: str, fallback: str) -> str:
    if "-> " not in message:
        return fallback
    return message.split("-> ", 1)[1].split(" ; ", 1)[0].strip() or fallback


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument(
        "--recover",
        action="store_true",
        help="also re-land jules tasks marked done that NEVER got a PR (the "
        "harvest gap: harvest closed them without applying the diff)",
    )
    args = ap.parse_args()

    lf = load_limen_file(TASKS)
    by_id = {t.id: t for t in lf.tasks}
    now = datetime.datetime.now(datetime.timezone.utc)

    # session id → task id, from every jules dispatch we recorded. Lets a completed remote session
    # match its task even when the session title doesn't carry "Complete task <id>:". Numeric ids
    # only — jules-land stores PR urls in session_id too, and those are not sessions.
    sid_map: dict[str, str] = {}
    for t in lf.tasks:
        for e in t.dispatch_log or []:
            sid = str(e.session_id or "")
            if sid.isdigit():
                sid_map[sid] = t.id

    def ever_pr(t) -> bool:
        return any("/pull/" in str(e.session_id or "") for e in (t.dispatch_log or []))

    done = 0
    for sid, tid in completed_sessions(sid_map):
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
            pr_url = landed_pr_url(msg, sid)
            t.status = "done"
            t.updated = now
            t.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent="jules",
                    session_id=pr_url,
                    status="done",
                    output=f"jules-land: landed session {sid} as PR",
                )
            )
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
