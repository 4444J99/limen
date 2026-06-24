import json
import os
import re
import secrets
import shlex
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from limen.capacity import (
    canonical_agent,
    capacity_census,
    format_capacity_census,
    github_issue_ref,
)
from limen.io import load_limen_file, save_limen_file, queue_lock
from limen.models import BudgetTrack, DispatchLogEntry, LimenFile, Task
from limen.doctor import stale_tasks

# Backward compat alias — the canonical lock lives in io.py
_queue_lock = queue_lock

def _usage_dead_lanes() -> set[str]:
    """Lanes the LIVE usage meter (logs/usage.json, written by usage-telemetry.py) reports as
    out of safe usage — token-`exhausted`, `rate-limited`, or `low` (at/below the pacing reserve,
    so we stop BEFORE 0). `throttle` lanes stay UP — they still have runway; it's a steering
    signal for the split, not a stop. DERIVED from the live signal, never pinned: a lane auto-rejoins
    the instant its rolling window refills (no manual edit). This is what makes dispatch HONEST —
    we never assign a task to a lane that physically cannot produce, and we never burn one to 0."""
    f = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "logs" / "usage.json"
    try:
        vendors = (json.loads(f.read_text()) or {}).get("vendors", {})
    except (OSError, ValueError):
        return set()
    return {name for name, info in vendors.items()
            if isinstance(info, dict) and info.get("health") in ("exhausted", "rate-limited", "low")}


def _down_lanes() -> set[str]:
    """Lanes currently DOWN/unproductive. Two sources, unioned:
      1. logs/lanes-down.txt — a manual override file (one lane per line, '#' comments ok) for
         lanes a human knows are dead (e.g. agy bin missing); NOT pinned in code.
      2. the LIVE usage meter (_usage_dead_lanes) — lanes token-exhausted or rate-limited RIGHT NOW.
    Rebalance + dispatch + route skip these so tasks aren't wasted on a lane that can't produce.
    Source 2 self-heals (a lane rejoins when its window refills); remove a line from source 1 when
    that lane is healthy again (e.g. a paid GEMINI_API_KEY)."""
    f = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "logs" / "lanes-down.txt"
    manual: set[str] = set()
    try:
        manual = {ln.split("#")[0].strip() for ln in f.read_text().splitlines() if ln.split("#")[0].strip()}
    except OSError:
        pass
    return manual | _usage_dead_lanes()


def _run_capture(cmd: list[str], cwd: str | None = None, timeout: int = 600, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Like subprocess.run(capture_output, text, timeout) but launches the process in its OWN
    session/group and, on timeout, SIGKILLs the WHOLE group. Plain subprocess.run only kills the
    direct child — if an agent CLI (codex/claude/…) spawns grandchildren that inherit the stdout
    pipe, communicate() blocks on that open pipe FOREVER past the timeout, stalling the entire
    synchronous beat (observed: a 23-min hang despite timeout=600). Killing the group closes the
    pipes so the timeout actually fires. Still raises TimeoutExpired so callers' handlers run."""
    import signal
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # start_new_session=True makes proc.pid the session/group leader, so its PID == PGID.
        # Kill by proc.pid directly (don't getpgid — that raises if the direct child already
        # exited while a grandchild lives on holding the pipe). This reaps the grandchildren too.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def _dep_merged(dep_task: Task | None) -> bool:
    """A dependency is satisfied only when its PR is MERGED (in the base branch), not merely built.
    The reconcile (verify-dispatch→heal-dispatch) stamps a 'PR merged → done' dispatch_log entry on
    merge; we detect that marker. An unknown dep id is treated as unsatisfied (fail-safe)."""
    if dep_task is None:
        return False
    # match "merged" specifically — NOT the bare stem "merg", which also matches the heal marker
    # "PR open (awaiting merge) → done" and would unlock dependents on PR-OPEN instead of PR-MERGED.
    return any("merged" in str(e.output or "").lower() or "merged" in str(e.status or "").lower()
               for e in (dep_task.dispatch_log or []))


def _deps_met(task: Task, by_id: dict[str, Task]) -> bool:
    """True if every task in task.depends_on has a merged PR (or the task has no deps). Lets a
    dependent increment sit OPEN but un-dispatched until its predecessor lands — so the product
    roadmap self-advances as PRs merge, with no parallel-built conflicts."""
    deps = getattr(task, "depends_on", None) or []
    return all(_dep_merged(by_id.get(d)) for d in deps)


_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
# Git worktree add/remove briefly locks the PARENT repo index; serialize just that fast
# plumbing across threads so concurrent same-repo dispatches don't collide on index.lock.
# The slow agent run happens OUTSIDE this lock — that's where the parallelism lives.
_GIT_PLUMBING_LOCK = threading.Lock()


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
    # Explicit escape/test hook: when LIMEN_DISPATCH_CMD is set, route EVERY agent through that
    # stub command instead of the real lane CLIs. Production never sets it (the daemon relies on
    # the local-lane path below), so this only keeps unit tests hermetic — no real codex/opencode
    # subprocess blocking on auth/network. (Earlier the local-lane routing bypassed this hook,
    # which made test_dispatch_limit_and_per_agent_budget invoke the real codex CLI and hang.)
    cmd_override = os.environ.get("LIMEN_DISPATCH_CMD")
    if cmd_override:
        return _run_cmd([cmd_override, agent, _build_prompt(task)], task, dry_run)
    if agent == "copilot":
        return _call_copilot(task, dry_run)
    if agent == "github_actions":
        return _call_github_actions(task, dry_run)
    if agent in {"warp", "oz"}:
        return _call_warp_oz(agent, task, dry_run)
    if agent in _CONFIGURED_SERVICE_AGENTS:
        return _call_configured_paid_service(agent, task, dry_run)
    if agent in _LOCAL_AGENTS:
        return _call_local_agent(agent, task, dry_run)
    return _run_cmd(["agent-dispatch", agent, _build_prompt(task)], task, dry_run)


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
        result = _run_capture(
            cmd, cwd=cwd,
            timeout=int(os.environ.get("LIMEN_DISPATCH_TIMEOUT", "600")),
        )  # own process group → timeout SIGKILLs grandchildren too (no beat-stall hang)
        if result.returncode == 0:
            print(f"  dispatched: {task.id}")
            # Try to extract session ID from output if it's jules
            if cmd[0].endswith("jules"):
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


def _call_warp_oz(agent: str, task: Task, dry_run: bool) -> bool | str:
    if not task.repo:
        print(f"  SKIP {task.id}: {agent} lane needs task.repo")
        return False
    gh = os.environ.get("LIMEN_WARP_OZ_BIN", "gh")
    workflow = os.environ.get("LIMEN_WARP_OZ_WORKFLOW", "limen-warp-oz.yml")
    dispatch_repo = os.environ.get("LIMEN_WARP_OZ_REPO", "organvm/limen")
    cmd = [
        gh,
        "workflow",
        "run",
        workflow,
        "--repo",
        dispatch_repo,
        "-f",
        f"task_id={task.id}",
        "-f",
        f"repo={task.repo}",
        "-f",
        f"title={task.title}",
        "-f",
        f"agent={agent}",
        "-f",
        f"prompt={_build_prompt(task)}",
    ]
    result = _run_cmd(cmd, task, dry_run)
    if result is True and not dry_run:
        return f"warp-oz:{dispatch_repo}:{workflow}"
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
def _opencode_model() -> str:
    """Resolve the opencode lane model by DERIVING it from `opencode models`, never by
    pinning a model name ("names are outputs, not inputs"). Order:
      1. explicit LIMEN_OPENCODE_MODEL override (an input only by deliberate choice);
      2. query the models the account actually exposes → pick a PAID one if authed
         (opencode auth login wrote a credential), else a free coding model. Self-tunes
         to whatever exists today and survives any model rename — nothing pinned.
      3. last-resort ONLY if the query fails: a single env-overridable constant.
    """
    env = os.environ.get("LIMEN_OPENCODE_MODEL")
    if env:
        return env
    binv = os.environ.get("LIMEN_OPENCODE_BIN", "opencode")
    try:
        r = subprocess.run([binv, "models"], capture_output=True, text=True, timeout=20)
        models = [ln.strip() for ln in r.stdout.splitlines() if "/" in ln and " " not in ln.strip()]
        # Prefer a FREE coding model (works with no auth). We deliberately DON'T read
        # opencode's auth.json from Python — that read trips the macOS TCC "access data from
        # other apps" prompt on every beat. After `opencode auth login`, set
        # LIMEN_OPENCODE_MODEL=<paid model> to use the paid tier.
        free = [m for m in models if "-free" in m]
        if free:
            return next((m for m in free if "code" in m), free[0])
        if models:
            return models[0]
    except Exception:
        pass
    return os.environ.get("LIMEN_OPENCODE_MODEL_FALLBACK", "opencode/north-mini-code-free")


_LOCAL_AGENTS: dict[str, list[str]] = {
    "codex": ["exec", "--skip-git-repo-check", "--sandbox", "workspace-write"],
    # opencode: `run` with NO -m silently no-ops (no auth.json + no default model in
    # opencode.jsonc → 0 PRs). The model is injected LAZILY in _agent_argv() and DERIVED
    # from `opencode models` (never pinned, never resolved at import) — see _opencode_model().
    "opencode": ["run"],
    # gemini: flags FIRST, then -p LAST so the appended prompt immediately follows -p
    # (gemini errors "Not enough arguments following: -p" otherwise). auto_edit = edits-only.
    "gemini": ["--approval-mode", "auto_edit", "-p"],
    # agy/antigravity: -p (=--print) TAKES the prompt as its value, so it MUST come LAST
    # with the appended prompt immediately after it (same bug class as gemini). With -p not
    # last, it swallowed --dangerously-skip-permissions as the prompt → agent got no task
    # ("acknowledged, ready to assist") and wrote nothing. Flags first, -p last.
    "agy": ["--dangerously-skip-permissions", "-p"],
    "antigravity": ["--dangerously-skip-permissions", "-p"],
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


def _agent_argv(agent: str) -> list[str]:
    """Static lane flags + any LAZILY-derived per-run flags, so nothing is pinned or
    resolved at import time. opencode's model is derived here (only when it actually
    runs) from `opencode models` — names are outputs, not inputs."""
    flags = list(_LOCAL_AGENTS[agent])
    if agent == "opencode":
        model = _opencode_model()
        if model:
            flags += ["-m", model]
    return flags

# Per-task lane failover cascade (best-efficiency-first → cloud last). On a genuine
# lane FAILURE (down/error/timeout) a task re-routes to the next lane and stays open;
# the heartbeat dispatches lanes in THIS SAME ORDER, so a failed task walks down the
# spectrum within one tick. A no-op (empty diff) is task-intrinsic and never cascades.
# Exhausting the list marks the task failed. Keep this order == heartbeat.sh LANES order.
# agy/antigravity KEPT and HEALED: it writes to a scratch dir, so _bridge_agy_scratch carries
# that work into the worktree after the run (see _isolated_local_run) — productive lane again.
_LANE_CASCADE = ["codex", "opencode", "agy", "claude", "gemini", "jules"]
_NOOP = "__noop__"  # agent ran but produced no diff — do NOT cascade lanes


def _next_lane(current: str) -> str | None:
    """Next lane down the efficiency spectrum after `current`, or None if exhausted."""
    try:
        i = _LANE_CASCADE.index(current)
    except ValueError:
        return None
    return _LANE_CASCADE[i + 1] if i + 1 < len(_LANE_CASCADE) else None


# A lane's REAL limit is usually token-usage / rate, NOT the fixed per-day count. Every
# vendor signals exhaustion in its output; detect it and treat the LANE (not the task) as
# temporarily spent → cascade the task down + let the caller cool the lane. The per-day
# count stays only as a runaway/cost safety ceiling.
_RATELIMIT = "__ratelimit__"
# a local lane exceeded its wall-clock — the task is too big for a SYNCHRONOUS local run.
# Don't cascade it through every other local lane (each would also time out, burning ~900s
# apiece and gating beats). Route it straight to jules: async, no wall-clock cap, completes
# in the cloud. One timeout → jules, instead of 5 timeouts → failed.
_TIMEOUT = "__timeout__"
_RATE_PATTERNS = re.compile(
    r"rate.?limit|quota|usage limit|too many requests|\b429\b|\b529\b|"
    r"resource.?exhausted|overloaded|insufficient_quota|throttl|out of (?:tokens|credits)",
    re.IGNORECASE,
)


def _is_rate_limited(text: str) -> bool:
    return bool(_RATE_PATTERNS.search(text or ""))


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


def _clone_repo(task: Task) -> Path | None:
    """Clone task.repo locally when no checkout exists yet, so local lanes can
    work it instead of bleeding to the scarce cloud lane.

    Post-consolidation many repos (org scaffolding: --superproject, .github.io,
    org-dotgithub, _agent, …) live in the `organvm` org but were never cloned —
    _resolve_repo_dir correctly returns None for them. We clone on demand into
    $LIMEN_WORKDIR/<owner>/<name> using gh's auth (handles private repos), then
    the next _resolve_repo_dir finds it. Serialized on the git-plumbing lock so
    two same-repo dispatches don't race the same clone. Returns the dir or None.
    """
    if not task.repo or "/" not in task.repo:
        return None
    ws = Path(os.environ.get("LIMEN_WORKDIR", Path.home() / "Workspace"))
    dest = ws / task.repo  # ws/<owner>/<name>
    with _GIT_PLUMBING_LOCK:
        if (dest / ".git").exists():  # a concurrent dispatch already cloned it
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = subprocess.run(
                ["gh", "repo", "clone", task.repo, str(dest)],
                capture_output=True, text=True, timeout=600,
            )
        except Exception as e:
            print(f"  clone {task.repo} errored: {e}")
            return None
    if (dest / ".git").exists():
        print(f"  cloned {task.repo} → {dest}")
        return dest
    print(f"  clone {task.repo} failed: {r.stderr.strip()[:200]}")
    return None


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


def _git(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
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


def _bridge_agy_scratch(task: Task, wt: Path) -> None:
    """agy/antigravity do real work but write it to ~/.gemini/antigravity-cli/scratch/<name>/
    (a git copy of the repo) instead of the cwd worktree — there is no headless flag to make
    them target a cwd. So CARRY THE WORK HOME: find the scratch copy for THIS repo (match by
    its git remote == task.repo, newest wins under concurrency) and rsync its content into the
    worktree, so the normal add→commit→PR flow picks it up. Turns agy from no-op into a
    productive lane (use every part of the buffalo). Best-effort: never raises."""
    if not task.repo:
        return
    scratch = Path.home() / ".gemini" / "antigravity-cli" / "scratch"
    if not scratch.is_dir():
        return
    best = None
    try:
        for d in scratch.iterdir():
            if not d.is_dir() or not (d / ".git").exists():
                continue
            r = subprocess.run(["git", "-C", str(d), "remote", "get-url", "origin"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and task.repo.lower() in r.stdout.lower():
                if best is None or d.stat().st_mtime > best.stat().st_mtime:
                    best = d
        if best is None:  # fallback: newest scratch dir whose name resembles the repo
            name = task.repo.split("/")[-1].lower()
            cands = [d for d in scratch.iterdir()
                     if d.is_dir() and name.replace("--", "-") in d.name.lower().replace("--", "-")]
            best = max(cands, key=lambda p: p.stat().st_mtime, default=None)
        if best is None:
            return
        subprocess.run(["rsync", "-a", "--exclude", ".git", "--exclude", ".claude",
                        f"{best}/", f"{wt}/"], capture_output=True, text=True, timeout=180)
        print(f"  agy-bridge {task.id}: carried scratch '{best.name}' → worktree")
    except Exception as e:
        print(f"  agy-bridge {task.id}: skipped ({str(e)[:80]})")


def _isolated_local_run(agent: str, task: Task, dry_run: bool) -> bool | str:
    binary = os.environ.get(f"LIMEN_{agent.upper()}_BIN", _LOCAL_BIN.get(agent, agent))
    repo_dir = _resolve_repo_dir(task)
    if repo_dir is None and not dry_run:
        repo_dir = _clone_repo(task)  # post-move: clone on demand so local lanes can work it
    if repo_dir is None:
        msg = f"no local checkout of {task.repo or '(no repo)'}"
        if dry_run:
            print(f"  would [{msg}; clone-on-demand then isolate]: →{binary}→PR")
            return True
        print(f"  SKIP {task.id}: {msg} — clone-on-demand failed")
        return False

    base = _default_branch(repo_dir)
    slug = re.sub(r"[^a-zA-Z0-9._/-]+", "-", task.id.lower())
    # short unique suffix → retries never collide with a stale remote branch (non-fast-forward)
    suffix = secrets.token_hex(2)
    branch = f"limen/{slug}-{suffix}"
    wt = _ISOLATION_ROOT / (re.sub(r"[^a-zA-Z0-9._-]+", "-", task.id.lower()) + "-" + suffix)
    agent_cmd = [binary, *_agent_argv(agent), _build_prompt(task)]
    # 1800s (was 900): local lanes have ABUNDANT budget headroom (codex/claude/opencode ~60-92 left
    # per window) while jules is scarce (≈100/day). At 900s, big tasks — incl. the revenue/deploy
    # tasks (BLD2-*-deploy, REV-*) — timed out locally then bled to jules, exhausting the scarce lane
    # and stalling the money work. A longer local cap lets the cheap, abundant lanes finish the big
    # tasks (a hung run is still bounded — _run_capture kills the process group at the cap).
    lane_timeout = int(os.environ.get("LIMEN_LANE_TIMEOUT", "1800"))

    if dry_run:
        print(
            f"  would isolate {task.id}: worktree {wt} off origin/{base} "
            f"→ branch {branch} → {binary} {' '.join(_agent_argv(agent))} "
            f"→ commit → push → PR  (live checkout untouched)"
        )
        return True

    # 1) fresh base from origin — never the user's possibly-dirty working tree.
    # Hold the git-plumbing lock only for these fast parent-repo ops so concurrent
    # same-repo dispatches don't collide on index.lock (the slow run is unlocked).
    with _GIT_PLUMBING_LOCK:
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
        run_env = os.environ.copy()
        # gemini: API-key mode throttles hard under agentic use. If the user has done the
        # one-time Google sign-in (oauth_creds.json exists), DROP the API keys for gemini's
        # subprocess ONLY so it uses the higher-limit OAuth / Code-Assist tier — opencode
        # still needs the key, so this is gemini-scoped. Auto-heals the lane on login.
        # Gate on an ENV flag (set LIMEN_GEMINI_OAUTH=1 after the one-time Google sign-in)
        # rather than reading ~/.gemini from Python — that read trips the macOS TCC prompt.
        if agent == "gemini" and os.environ.get("LIMEN_GEMINI_OAUTH") == "1":
            for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"):
                run_env.pop(k, None)
        try:
            run = _run_capture(
                agent_cmd, cwd=str(wt), timeout=lane_timeout, env=run_env,
            )  # own process group → timeout SIGKILLs grandchildren too (no beat-stall hang)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT {task.id} after {lane_timeout}s — too big for sync local → routing to jules (async)")
            return _TIMEOUT  # finally drops the worktree; task re-routes to the async lane
        if run.returncode != 0:
            blob = (run.stderr or "") + (run.stdout or "")
            if _is_rate_limited(blob):
                print(f"  RATE-LIMIT {agent} on {task.id}: real limit hit (token/rate) — cooling lane, cascading")
                return _RATELIMIT
            print(f"  FAILED agent {task.id} ({run.returncode}): {run.stderr.strip()[:300]}")
            return False

        # 2b) agy/antigravity write to their scratch dir, not the worktree — carry it home
        if agent in ("agy", "antigravity"):
            _bridge_agy_scratch(task, wt)

        # 3) did the agent change anything?
        _git(["add", "-A"], wt)
        if _git(["diff", "--cached", "--quiet"], wt).returncode == 0:
            print(f"  no-op {task.id}: agent made no changes — no PR opened")
            return _NOOP  # task-intrinsic (nothing to change) — do NOT cascade lanes

        # 4) commit → push → PR
        msg = f"{task.title}\n\nlimen task {task.id}"
        c = _git(
            ["-c", f"user.name={os.environ.get('LIMEN_COMMIT_NAME', '4444J99')}",
             "-c", f"user.email={os.environ.get('LIMEN_COMMIT_EMAIL', '4444J99@users.noreply.github.com')}",
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
        # Arm auto-merge so the PR self-merges the moment CI goes green — making the merge gate
        # self-draining (CI is the gate, configured by setup-rulesets.py). Best-effort: repos
        # without branch protection / auto-merge disabled reject this harmlessly and the PR just
        # waits. This is the "no human needed to merge" half of autonomy.
        am = subprocess.run(
            ["gh", "pr", "merge", url, "--auto", "--squash"],
            cwd=str(wt), capture_output=True, text=True, timeout=60,
            stdin=subprocess.DEVNULL,
        )
        print(f"    auto-merge {'armed' if am.returncode == 0 else 'n/a'}: {task.id}"
              + ("" if am.returncode == 0 else f" ({am.stderr.strip()[:100]})"))
        return url
    finally:
        # leave the user's checkout pristine: drop the worktree, and the local
        # branch too once its commits are safely on the remote. Guard the parent-repo
        # plumbing so concurrent teardowns don't collide on index.lock.
        with _GIT_PLUMBING_LOCK:
            _git(["worktree", "remove", "--force", str(wt)], repo_dir)
            if pushed:
                _git(["branch", "-D", branch], repo_dir)


def _call_local_agent(agent: str, task: Task, dry_run: bool) -> bool | str:
    if os.environ.get("LIMEN_ISOLATION", "worktree").lower() != "off":
        return _isolated_local_run(agent, task, dry_run)
    # ── legacy in-place path (escape hatch; edits the live checkout directly)
    binary = os.environ.get(f"LIMEN_{agent.upper()}_BIN", _LOCAL_BIN.get(agent, agent))
    cmd = [binary, *_agent_argv(agent), _build_prompt(task)]
    cwd = _resolve_repo_dir(task)
    if cwd is None:
        msg = f"no local checkout of {task.repo or '(no repo)'}"
        if dry_run:
            print(f"  would [{msg}; clone first]: {binary} {' '.join(_agent_argv(agent))} …")
            return True
        print(f"  SKIP {task.id}: {msg} — clone it under $LIMEN_WORKDIR first")
        return False
    return _run_cmd(cmd, task, dry_run, cwd=str(cwd))


def _window_hours(agent: str) -> float:
    """Budget reset cadence (hours) for a vendor, DERIVED from logs/usage-limits.json —
    never pinned. '5h rolling' -> 5; '24h'/'today'/'day' -> 24; default 24. So codex/claude
    (5h rolling windows) refill ~5x/day instead of being throttled by a once-a-day cap,
    while jules/gemini/opencode/agy refill daily."""
    try:
        root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
        limits = json.load(open(root / "logs" / "usage-limits.json"))
        window = str((limits.get(agent) or {}).get("window", ""))
        m = re.search(r"(\d+)\s*h", window)
        if m:
            return float(m.group(1))
        if "today" in window or "day" in window:
            return 24.0
    except Exception:
        pass
    return 24.0


def _reset_budget_if_needed(limen: LimenFile, now: datetime) -> None:
    """Reset each vendor's spend on ITS OWN cadence (5h rolling for codex/claude, daily for
    the rest) so no reset window goes unused — replaces the single crude calendar-day reset."""
    track = limen.portal.budget.track
    for agent in list(limen.portal.budget.per_agent):
        last_iso = track.per_agent_reset.get(agent)
        last = None
        if last_iso:
            try:
                last = datetime.fromisoformat(last_iso)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
            except Exception:
                last = None
        if last is None or (now - last) >= timedelta(hours=_window_hours(agent)):
            track.per_agent[agent] = 0
            track.per_agent_reset[agent] = now.isoformat()
    track.date = now.strftime("%Y-%m-%d")
    track.spent = sum(track.per_agent.values())


def _remaining_budget(limen: LimenFile, agent: str, budget: int) -> int:
    """The per-vendor cadence cap is the binding gate (each refills on its own window); the
    global daily is only a backstop for agents that have no per-agent cap."""
    agent = canonical_agent(agent)
    track = limen.portal.budget.track
    agent_limit = limen.portal.budget.per_agent.get(agent)
    if agent_limit is not None:
        return max(0, agent_limit - track.per_agent.get(agent, 0))
    return max(0, budget - track.spent)


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
    down = _down_lanes()
    if agent_filter in down:
        print(f"Lane '{agent_filter}' is down by live usage/health gate; skipping dispatch")
        return

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

        result = call_agent_dispatch(agent_filter, task, dry_run)
        if not dry_run:
            _apply_result(task, agent_filter, result, now, track)
            if result and result not in (_NOOP, _RATELIMIT, _TIMEOUT):
                remaining -= task.budget_cost
            elif result == _RATELIMIT:
                save_limen_file(tasks_path, limen)
                print(f"── lane {agent_filter} rate-limited — cooling, {dispatched} dispatched this cycle")
                return

        dispatched += 1

    if not dry_run:
        save_limen_file(tasks_path, limen)

    print(f"── {mode}: {dispatched} task(s)")


def _apply_result(task: Task, agent: str, result: bool | str, now: datetime, track: BudgetTrack) -> None:
    """Apply one dispatch result to a task (same semantics as the serial path):
    success → dispatched + spend; no-op → cancelled; rate-limit/fail → cascade."""
    entry = DispatchLogEntry(timestamp=now, agent=agent, session_id=session_id(), status="dispatched")
    if result == _NOOP:
        entry.status = "noop"
        task.status = "cancelled"
        if "noop" not in task.labels:
            task.labels.append("noop")
    elif result == _RATELIMIT:
        nxt = _next_lane(agent)
        entry.status = f"ratelimited->{nxt or 'requeue'}"
        task.target_agent = nxt or agent
        task.status = "open"
    elif result == _TIMEOUT:
        # too big for a sync local lane → hand to jules (async, no wall-clock cap)
        entry.status = "timeout->jules"
        task.target_agent = "jules"
        task.status = "open"
        if "slow" not in task.labels:
            task.labels.append("slow")
    elif result:
        if isinstance(result, str):
            entry.session_id = result
        task.status = "dispatched"
        track.spent += task.budget_cost
        track.per_agent[agent] = track.per_agent.get(agent, 0) + task.budget_cost
    else:
        tried = f"tried:{agent}"
        if tried not in task.labels:
            task.labels.append(tried)
        nxt = _next_lane(agent)
        if nxt:
            entry.status = f"failed->{nxt}"
            task.target_agent = nxt
            task.status = "open"
        else:
            entry.status = "failed"
            task.status = "failed"
    task.updated = now
    task.dispatch_log.append(entry)


def dispatch_parallel(
    limen: LimenFile,
    tasks_path: Path,
    agents: list[str],
    per_agent_limit: int = 3,
    max_workers: int = 8,
    dry_run: bool = False,
) -> None:
    """RESERVE → RUN (parallel) → COMMIT. Fixes both serialism levels (across lanes AND
    within a lane) without racing tasks.yaml: the two file writes happen under this single
    process (serial), the slow agent runs happen concurrently in a thread pool, and a
    lane that hits its real rate-limit is cooled (its remaining reserved tasks re-queued)."""
    now = datetime.now(timezone.utc)
    _reset_budget_if_needed(limen, now)
    track = limen.portal.budget.track
    daily = limen.portal.budget.daily

    # ── RESERVE: pick balanced candidates per lane within budget; mark dispatched, save once
    picked: list[tuple[str, str]] = []  # (agent, task_id)
    spent_daily = track.spent
    id2 = {t.id: t for t in limen.tasks}  # for dependency resolution
    for agent in agents:
        cap = limen.portal.budget.per_agent.get(agent)
        agent_spent = track.per_agent.get(agent, 0)
        rem = daily - spent_daily if cap is None else max(0, min(daily - spent_daily, cap - agent_spent))
        if rem <= 0:
            continue
        cands = [t for t in limen.tasks
                 if t.status == "open" and (t.target_agent == agent or t.target_agent == "any")
                 and t.budget_cost <= rem and _deps_met(t, id2)]
        cands.sort(key=lambda t: _PRIORITY_ORDER.get(t.priority, 99))
        cands = cands[:per_agent_limit]
        for t in cands:
            if dry_run:
                picked.append((agent, t.id))
                continue
            t.status = "dispatched"  # reserve so nothing else grabs it
            t.updated = now
            picked.append((agent, t.id))

    if dry_run:
        print(f"── PARALLEL DRY-RUN — would dispatch {len(picked)} task(s) across {agents}:")
        for a, tid in picked:
            print(f"  {a}: {tid}")
        return
    if not picked:
        print(f"── PARALLEL: nothing to dispatch for {agents} within budget")
        return
    with queue_lock(tasks_path):
        save_limen_file(tasks_path, limen)  # reserve commit (atomic vs supervisor writes)

    # ── RUN: concurrent agent executions (worktree→PR / jules), no tasks.yaml access here
    id2task = {t.id: t for t in limen.tasks}
    cooled: set[str] = set()  # lanes that hit their real rate-limit this round

    def run_one(at: tuple[str, str]) -> tuple[str, str, bool | str]:
        agent, tid = at
        try:
            res = call_agent_dispatch(agent, id2task[tid], dry_run=False)
        except Exception as e:  # never let one task kill the pool
            print(f"  ERROR {agent} {tid}: {str(e)[:160]}")
            res = False
        return (agent, tid, res)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for agent, tid, res in ex.map(run_one, picked):
            results.append((agent, tid, res))
            if res == _RATELIMIT:
                cooled.add(agent)

    # ── COMMIT: reload FRESH under the lock so writes a supervisor (seed/heal/verify) made
    # during the unlocked run aren't clobbered; re-apply each result to the fresh task by id.
    # This is the #11 keystone — without the reload, this save would silently overwrite seeds.
    n_pr = n_noop = n_fail = n_rl = n_to = 0
    with queue_lock(tasks_path):
        fresh = load_limen_file(tasks_path)
        fid = {t.id: t for t in fresh.tasks}
        ftrack = fresh.portal.budget.track
        for agent, tid, res in results:
            ft = fid.get(tid)
            if ft is not None:
                _apply_result(ft, agent, res, now, ftrack)
            if res == _RATELIMIT:
                n_rl += 1
            elif res == _NOOP:
                n_noop += 1
            elif res == _TIMEOUT:
                n_to += 1
            elif res:
                n_pr += 1
            else:
                n_fail += 1
        save_limen_file(tasks_path, fresh)
    print(f"── PARALLEL done: {len(results)} ran · {n_pr} dispatched/PR · {n_noop} no-op · "
          f"{n_fail} failed→cascade · {n_rl} rate-limited · {n_to} timeout→jules"
          f"{' (lanes cooled: '+','.join(sorted(cooled))+')' if cooled else ''}")


def release_stale_tasks(
    limen: LimenFile,
    tasks_path: Path,
    hours: int = 24,
    dry_run: bool = True,
    agent: str | None = None,
) -> dict[str, Any]:
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
