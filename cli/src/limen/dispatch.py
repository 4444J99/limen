import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from limen.capacity import (
    canonical_agent,
    capacity_census,
    format_capacity_census,
    github_issue_ref,
)
from limen.io import save_limen_file
from limen.models import DispatchLogEntry, LimenFile, Task
from limen.doctor import stale_tasks


def resolve_agent() -> str:
    return canonical_agent(os.environ.get("LIMEN_AGENT", "claude"))


def session_id() -> str:
    return os.environ.get(
        "CLAUDE_SESSION_ID", os.environ.get("GEMINI_SESSION_ID", "cli")
    )


def call_agent_dispatch(agent: str, task: Task, dry_run: bool) -> bool | str:
    agent = canonical_agent(agent)
    if agent == "jules":
        return _call_jules(task, dry_run)
    if agent == "copilot":
        return _call_copilot(task, dry_run)
    if agent == "github_actions":
        return _call_github_actions(task, dry_run)
    if agent in _CONFIGURED_SERVICE_AGENTS:
        return _call_configured_paid_service(agent, task, dry_run)
    if agent in _LOCAL_AGENTS:
        return _call_local_agent(agent, task, dry_run)
    dispatch_cmd = os.environ.get("LIMEN_DISPATCH_CMD", "agent-dispatch")
    prompt = _build_prompt(task)
    cmd = [dispatch_cmd, agent, prompt]
    return _run_cmd(cmd, task, dry_run)


def _build_prompt(task: Task) -> str:
    parts = [f"Complete task {task.id}: {task.title}"]
    if task.repo:
        parts.append(f" in repository {task.repo}")
    if task.context:
        parts.append(f"\nContext: {task.context}")
    if task.urls:
        parts.append(f"\nReferences: {', '.join(task.urls)}")
    return "".join(parts)


def _run_cmd(cmd: list[str], task: Task, dry_run: bool, cwd: str | None = None) -> bool | str:
    if dry_run:
        loc = f" [cwd={cwd}]" if cwd else ""
        print(f"  would:{loc} {' '.join(cmd)}")
        return True
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            stdin=subprocess.DEVNULL,
            cwd=cwd,
        )
        if result.returncode == 0:
            print(f"  dispatched: {task.id}")
            # Try to extract session ID from output if it's jules
            if cmd[0].endswith("jules"):
                import re

                match = re.search(r"session\s+(\d+)", result.stdout, re.IGNORECASE)
                if match:
                    return match.group(1)
                # Just look for any large number
                match = re.search(r"\b(\d{15,20})\b", result.stdout)
                if match:
                    return match.group(1)
            return True
        print(f"  FAILED ({result.returncode}): {task.id}")
        if result.stderr:
            print(f"    stderr: {result.stderr[:500]}")
        return False
    except FileNotFoundError:
        print(f"  dispatch command not found: {cmd[0]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  timed out: {task.id}")
        return False


def _call_jules(task: Task, dry_run: bool) -> bool | str:
    repo = task.repo or os.environ.get("LIMEN_ROOT", ".")
    prompt = _build_prompt(task)
    cmd = [os.environ.get("LIMEN_JULES_BIN", "jules"), "new", "--repo", repo, prompt]
    return _run_cmd(cmd, task, dry_run)


def _call_copilot(task: Task, dry_run: bool) -> bool | str:
    ref = github_issue_ref(task)
    if ref is None:
        print(f"  SKIP {task.id}: copilot lane needs an existing GitHub issue URL")
        return False
    repo, issue = ref
    gh = os.environ.get("LIMEN_COPILOT_BIN", "gh")
    actor = os.environ.get("LIMEN_COPILOT_ACTOR", "copilot-swe-agent")

    if dry_run:
        print(f"  would: {gh} api graphql (fetch node IDs + replaceActorsForAssignable for {actor} on {repo}#{issue})")
        return True

    owner, name = repo.split("/", 1)
    query = """
    query($owner: String!, $name: String!, $number: Int!, $actor: String!) {
      repository(owner: $owner, name: $name) { issue(number: $number) { id } }
      user(login: $actor) { id }
    }
    """
    import json
    import subprocess
    q_cmd = [
        gh, "api", "graphql",
        "-f", f"query={query}",
        "-F", f"owner={owner}",
        "-F", f"name={name}",
        "-F", f"number={issue}",
        "-F", f"actor={actor}",
    ]
    r = subprocess.run(q_cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"  FAILED copilot query {task.id}: {r.stderr.strip()}")
        return False

    try:
        data = json.loads(r.stdout)["data"]
        issue_id = data["repository"]["issue"]["id"]
        actor_id = data["user"]["id"]
    except Exception as e:
        print(f"  FAILED copilot parse {task.id}: {e}")
        return False

    mut = """
    mutation($issue: ID!, $actor: ID!) {
      replaceActorsForAssignable(input: { assignableId: $issue, actorIds: [$actor] }) {
        assignable { id }
      }
    }
    """
    cmd = [
        gh, "api", "graphql",
        "-H", "GraphQL-Features: issues_copilot_assignment_api_support",
        "-f", f"query={mut}",
        "-f", f"issue={issue_id}",
        "-f", f"actor={actor_id}",
    ]
    result = _run_cmd(cmd, task, dry_run)
    if result is True and not dry_run:
        return f"https://github.com/{repo}/issues/{issue}"
    return result


def _call_github_actions(task: Task, dry_run: bool) -> bool | str:
    if not task.repo:
        print(f"  SKIP {task.id}: github_actions lane needs task.repo")
        return False
    gh = os.environ.get("LIMEN_GITHUB_ACTIONS_BIN", "gh")
    workflow = os.environ.get("LIMEN_GITHUB_ACTIONS_WORKFLOW", "limen-agent.yml")
    cmd = [
        gh,
        "workflow",
        "run",
        workflow,
        "--repo",
        task.repo,
        "-f",
        f"task_id={task.id}",
        "-f",
        f"repo={task.repo}",
        "-f",
        f"title={task.title}",
        "-f",
        f"prompt={_build_prompt(task)}",
    ]
    result = _run_cmd(cmd, task, dry_run)
    if result is True and not dry_run:
        return f"github-actions:{task.repo}:{workflow}"
    return result


# Local non-interactive agents — run inside a working copy of the task's repo.
# Verified CLI verbs (2026-06-16 live probe): codex exec, opencode run,
# gemini -p, agy -p, claude -p. (Jules is the async-cloud lane above.)
#
# WRITE MODE matters: several CLIs default to read-only / no-edit in headless
# mode, so they'd execute but never change a file. Flags below opt each into
# autonomous workspace writes:
#   - codex: needs --skip-git-repo-check (else aborts outside a "trusted" dir)
#     and --sandbox workspace-write (default sandbox is read-only). exec is
#     already non-interactive (approval: never).
#   - claude: -p prints; --permission-mode acceptEdits lets it apply edits.
#   - opencode/agy: edit by default in run/-p mode (verified READY headless).
#   - gemini: requires GEMINI_API_KEY / settings.json auth (not configured;
#     lane is wired but will fail until auth is set).
_LOCAL_AGENTS: dict[str, list[str]] = {
    "codex": ["exec", "--skip-git-repo-check", "--sandbox", "workspace-write"],
    "opencode": ["run"],
    "gemini": ["-p"],
    "agy": ["-p"],
    "claude": ["-p", "--permission-mode", "acceptEdits"],
}
_LOCAL_BIN: dict[str, str] = {}
_CONFIGURED_SERVICE_AGENTS = {"warp", "oz"}


def _call_configured_paid_service(agent: str, task: Task, dry_run: bool) -> bool | str:
    prompt = _build_prompt(task)
    env_cmd = os.environ.get(f"LIMEN_{agent.upper()}_DISPATCH_CMD")
    if env_cmd:
        try:
            cmd = [*shlex.split(env_cmd), prompt]
        except ValueError as exc:
            print(f"  SKIP {task.id}: invalid LIMEN_{agent.upper()}_DISPATCH_CMD: {exc}")
            return False
    else:
        dispatch_cmd = os.environ.get("LIMEN_DISPATCH_CMD", "agent-dispatch")
        cmd = [dispatch_cmd, agent, prompt]
    return _run_cmd(cmd, task, dry_run)


def _resolve_repo_dir(task: Task) -> Path | None:
    """Find a local git checkout of task.repo (owner/name) across known roots.

    Falls back to matching by repo name under any org dir (the local checkout's
    org can differ from the GitHub remote org, e.g. local organvm/ vs remote
    a-organvm/), disambiguating by the git remote when multiple names collide.
    """
    if not task.repo:
        return None
    org, _, name = task.repo.partition("/")
    ws = Path(os.environ.get("LIMEN_WORKDIR", Path.home() / "Workspace"))
    cart = Path.home() / "Workspace" / ".home-cartridge" / "Code"
    for cand in (ws / task.repo, ws / org / name, ws / name, cart / org / name, cart / name):
        if (cand / ".git").exists():
            return cand
    matches = [
        p for root in (ws, cart) for p in root.glob(f"*/{name}") if (p / ".git").exists()
    ]
    if len(matches) == 1:
        return matches[0]
    for p in matches:  # disambiguate by remote when name collides across orgs
        try:
            r = subprocess.run(
                ["git", "-C", str(p), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and task.repo.lower() in r.stdout.lower():
                return p
        except Exception:
            pass
    return matches[0] if matches else None


# ── Isolation: every local agent works like Jules — in its own throwaway git
# worktree off origin/<default>, on a fresh branch, producing a reviewable PR.
# It NEVER touches the user's live working copy or current branch (only the
# checkout's object store + remotes are read). Afterwards the worktree AND the
# local branch are removed; the only surviving artifacts are the remote branch +
# PR. This is the universal default for ALL local lanes (codex/opencode/agy/
# claude/gemini) — set LIMEN_ISOLATION=off only for a deliberate in-place run.
_ISOLATION_ROOT = Path(
    os.environ.get("LIMEN_WORKTREES", Path.home() / "Workspace" / ".limen-worktrees")
)


def _git(args: list[str], cwd, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, stdin=subprocess.DEVNULL,
    )


def _default_branch(repo_dir: Path) -> str:
    """Best-effort detection of origin's default branch (main/master/…)."""
    r = _git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], repo_dir)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().rsplit("/", 1)[-1]
    for cand in ("main", "master"):
        if _git(
            ["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{cand}"], repo_dir
        ).returncode == 0:
            return cand
    return "main"


def _pr_body(task: Task) -> str:
    lines = [f"Autonomous **limen** dispatch of task `{task.id}`.", ""]
    if task.context:
        lines += [task.context, ""]
    if task.urls:
        lines += ["Refs: " + ", ".join(task.urls), ""]
    lines.append("_Produced in an isolated worktree off origin — review before merge._")
    return "\n".join(lines)


def _isolated_local_run(agent: str, task: Task, dry_run: bool) -> bool | str:
    binary = os.environ.get(f"LIMEN_{agent.upper()}_BIN", _LOCAL_BIN.get(agent, agent))
    repo_dir = _resolve_repo_dir(task)
    if repo_dir is None:
        msg = f"no local checkout of {task.repo or '(no repo)'}"
        if dry_run:
            print(f"  would [{msg}; clone first]: isolate→{binary}→PR")
            return True
        print(f"  SKIP {task.id}: {msg} — clone it under $LIMEN_WORKDIR first")
        return False

    base = _default_branch(repo_dir)
    branch = "limen/" + re.sub(r"[^a-zA-Z0-9._/-]+", "-", task.id.lower())
    wt = _ISOLATION_ROOT / re.sub(r"[^a-zA-Z0-9._-]+", "-", task.id.lower())
    agent_cmd = [binary, *_LOCAL_AGENTS[agent], _build_prompt(task)]

    if dry_run:
        print(
            f"  would isolate {task.id}: worktree {wt} off origin/{base} "
            f"→ branch {branch} → {binary} {' '.join(_LOCAL_AGENTS[agent])} "
            f"→ commit → push → PR  (live checkout untouched)"
        )
        return True

    # 1) fresh base from origin — never the user's possibly-dirty working tree
    _git(["fetch", "origin", base], repo_dir, timeout=300)
    _ISOLATION_ROOT.mkdir(parents=True, exist_ok=True)
    if wt.exists():  # leftover from a prior run
        _git(["worktree", "remove", "--force", str(wt)], repo_dir)
    _git(["branch", "-D", branch], repo_dir)  # clear stale same-named branch
    add = _git(
        ["worktree", "add", "-b", branch, str(wt), f"origin/{base}"], repo_dir, timeout=120
    )
    if add.returncode != 0:
        print(f"  FAILED worktree add {task.id}: {add.stderr.strip()[:300]}")
        return False

    pushed = False
    try:
        # 2) run the agent inside the isolated tree
        run = subprocess.run(
            agent_cmd, cwd=str(wt), capture_output=True, text=True,
            timeout=900, stdin=subprocess.DEVNULL,
        )
        if run.returncode != 0:
            print(f"  FAILED agent {task.id} ({run.returncode}): {run.stderr.strip()[:300]}")
            return False

        # 3) did the agent change anything?
        _git(["add", "-A"], wt)
        if _git(["diff", "--cached", "--quiet"], wt).returncode == 0:
            print(f"  no-op {task.id}: agent made no changes — no PR opened")
            return False  # not dispatched → free to re-route/retry

        # 4) commit → push → PR
        msg = f"{task.title}\n\nlimen task {task.id}"
        c = _git(
            ["-c", "user.name=limen", "-c", "user.email=limen@local",
             "commit", "-m", msg], wt
        )
        if c.returncode != 0:
            print(f"  FAILED commit {task.id}: {c.stderr.strip()[:200]}")
            return False
        p = _git(["push", "-u", "origin", branch], wt, timeout=300)
        if p.returncode != 0:
            print(f"  FAILED push {task.id}: {p.stderr.strip()[:300]}")
            return False
        pushed = True
        pr = subprocess.run(
            ["gh", "pr", "create", "--base", base, "--head", branch,
             "--title", f"[limen {task.id}] {task.title}"[:250],
             "--body", _pr_body(task)],
            cwd=str(wt), capture_output=True, text=True, timeout=120,
            stdin=subprocess.DEVNULL,
        )
        if pr.returncode != 0:
            print(f"  pushed {branch} but PR-create failed {task.id}: {pr.stderr.strip()[:200]}")
            return branch  # branch is live; record it (manual PR possible)
        url = pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else branch
        print(f"  dispatched: {task.id} → PR {url}")
        return url
    finally:
        # leave the user's checkout pristine: drop the worktree, and the local
        # branch too once its commits are safely on the remote.
        _git(["worktree", "remove", "--force", str(wt)], repo_dir)
        if pushed:
            _git(["branch", "-D", branch], repo_dir)


def _call_local_agent(agent: str, task: Task, dry_run: bool) -> bool | str:
    if os.environ.get("LIMEN_ISOLATION", "worktree").lower() != "off":
        return _isolated_local_run(agent, task, dry_run)
    # ── legacy in-place path (escape hatch; edits the live checkout directly)
    binary = os.environ.get(f"LIMEN_{agent.upper()}_BIN", _LOCAL_BIN.get(agent, agent))
    cmd = [binary, *_LOCAL_AGENTS[agent], _build_prompt(task)]
    cwd = _resolve_repo_dir(task)
    if cwd is None:
        msg = f"no local checkout of {task.repo or '(no repo)'}"
        if dry_run:
            print(f"  would [{msg}; clone first]: {binary} {' '.join(_LOCAL_AGENTS[agent])} …")
            return True
        print(f"  SKIP {task.id}: {msg} — clone it under $LIMEN_WORKDIR first")
        return False
    return _run_cmd(cmd, task, dry_run, cwd=str(cwd))


def _reset_budget_if_needed(limen: LimenFile, now: datetime) -> None:
    today = now.strftime("%Y-%m-%d")
    track = limen.portal.budget.track
    if track.date != today:
        track.date = today
        track.spent = 0
        track.per_agent = {agent: 0 for agent in limen.portal.budget.per_agent}


def _remaining_budget(limen: LimenFile, agent: str, budget: int) -> int:
    agent = canonical_agent(agent)
    track = limen.portal.budget.track
    daily_remaining = budget - track.spent
    agent_limit = limen.portal.budget.per_agent.get(agent)
    if agent_limit is None:
        return max(0, daily_remaining)
    agent_spent = track.per_agent.get(agent, 0)
    return max(0, min(daily_remaining, agent_limit - agent_spent))


def dispatch_tasks(
    limen: LimenFile,
    tasks_path: Path,
    agent: str | None = None,
    budget: int | None = None,
    dry_run: bool = True,
    task_id: str | None = None,
    limit: int | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    budget = budget or limen.portal.budget.daily

    _reset_budget_if_needed(limen, now)
    track = limen.portal.budget.track

    agent_filter = canonical_agent(agent or resolve_agent())
    remaining = _remaining_budget(limen, agent_filter, budget)
    print(format_capacity_census(capacity_census(limen, budget_limit=budget)))
    if remaining <= 0:
        print(
            f"Budget exhausted for {agent_filter} ({track.spent}/{budget} total spent)"
        )
        return

    tasks = limen.tasks

    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
        if not tasks:
            print(f"Task {task_id} not found")
            return

    candidates = [
        t
        for t in tasks
        if t.status == "open"
        and (t.target_agent == agent_filter or t.target_agent == "any")
        and t.budget_cost <= remaining
    ]
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
    candidates.sort(key=lambda t: priority_order.get(t.priority, 99))

    if limit is not None:
        candidates = candidates[: max(0, limit)]

    if not candidates:
        print(
            f"No open tasks for agent '{agent_filter}' within remaining budget ({remaining})"
        )
        return

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(
        f"── limen dispatch ({mode}) — agent={agent_filter} budget_remaining={remaining}"
    )

    dispatched = 0
    for task in candidates:
        if remaining < task.budget_cost:
            break

        entry = DispatchLogEntry(
            timestamp=now,
            agent=agent_filter,
            session_id=session_id(),
            status="dispatched",
        )

        success = call_agent_dispatch(agent_filter, task, dry_run)
        if not success and not dry_run:
            entry.status = "failed"
            task.status = "failed"
            task.updated = now
            task.dispatch_log.append(entry)
        elif not dry_run:
            if isinstance(success, str):
                entry.session_id = success
            task.status = "dispatched"
            task.updated = now
            task.dispatch_log.append(entry)
            track.spent += task.budget_cost
            track.per_agent[agent_filter] = (
                track.per_agent.get(agent_filter, 0) + task.budget_cost
            )
            remaining -= task.budget_cost

        dispatched += 1

    if not dry_run:
        save_limen_file(tasks_path, limen)

    print(f"── {mode}: {dispatched} task(s)")


def release_stale_tasks(
    limen: LimenFile,
    tasks_path: Path,
    hours: int = 24,
    dry_run: bool = True,
    agent: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    candidates = stale_tasks(limen, hours=hours, agent=agent)

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(
        f"── limen release-stale ({mode}) — hours={hours} candidates={len(candidates)}"
    )
    for task in candidates:
        print(f"  {task.id} {task.status} {task.target_agent} — {task.title}")
        if not dry_run:
            task.status = "open"
            task.updated = now
            task.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent="limen",
                    session_id=session_id(),
                    status="open",
                    output=f"Released stale claim after {hours}h",
                )
            )

    if not dry_run:
        save_limen_file(tasks_path, limen)
    return {
        "status": "dry_run" if dry_run else "applied",
        "agent": agent,
        "hours": hours,
        "tasks_path": str(tasks_path),
        "count": len(candidates),
        "released": [task.id for task in candidates],
        "candidates": [
            {
                "id": task.id,
                "title": task.title,
                "repo": task.repo,
                "target_agent": task.target_agent,
                "status": task.status if dry_run else "open",
            }
            for task in candidates
        ],
    }
