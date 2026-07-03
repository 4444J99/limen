import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TypedDict

from limen.capacity import (
    canonical_agent,
    capacity_census,
    format_capacity_census,
    github_issue_ref,
    ollama_model,
    select_lanes,
)
from limen.io import load_limen_file, save_limen_file, queue_lock as _queue_lock
from limen.models import BudgetTrack, DispatchLogEntry, LimenFile, Task
from limen.doctor import stale_tasks
from limen.model_selection import (  # the shared model vocabulary — also used by the non-bypassable `claude` shim
    _CLAUDE_TIER_ORDER,
    _claude_fable_acceptance_present,
    _claude_fable_classes,
    _claude_opus_classes,
    _guard_fable_model_pin,
    _resolve_claude_model,
)
from limen.worktree_debt import worktree_debt_exceeded


def _load_limen_env() -> int:
    """Load ~/.limen.env into os.environ so agent subprocesses (gemini/codex/opencode/…) INHERIT the
    credentials. Without this, _run_cmd runs the CLIs with the daemon's bare env and a key that was
    landed in ~/.limen.env (or hydrated from 1Password by creds-hydrate.py) never reaches the tool —
    the exact reason a SET GEMINI_API_KEY still read as 'auth not configured'.

    No-overwrite: an explicitly-exported env var always wins (only fills what's MISSING). Idempotent,
    fail-open (any parse/IO error loads nothing rather than crash the beat). Returns the count loaded.
    Honors $LIMEN_ENV; values are never logged. See scripts/creds-hydrate.py (the hydration source)."""
    path = Path(os.environ.get("LIMEN_ENV", str(Path.home() / ".limen.env")))
    loaded = 0
    try:
        if not path.exists():
            return 0
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val
                loaded += 1
    except OSError:
        return loaded
    return loaded


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
    return {
        name
        for name, info in vendors.items()
        if isinstance(info, dict) and info.get("health") in ("exhausted", "rate-limited", "low")
    }


# Lanes whose CLI authenticates ONLY via an interactive browser OAuth flow — no headless / device-code
# fallback. agy (the antigravity-cli) is the case in point: in print mode it first tries a SILENT token
# refresh against the host below; if that network call fails it MISREADS the failure as "not logged in"
# and launches a Google sign-in browser tab (its browser.go: consumerOAuth). Unattended, that's one tab
# per beat. The refresh only fails when the host is unreachable — exactly what happens when the Mac is
# asleep / in dark-wake with no network (observed 2026-06-24, 01:34–05:37: ~20 tabs; the agy logs show
# `dial tcp: lookup oauth2.googleapis.com: no such host` → "silent auth failed, triggering OAuth"). So
# we map each such lane to the host its silent auth must reach, and gate dispatch on reaching it.
_BROWSER_OAUTH_LANES: dict[str, str] = {
    "agy": "oauth2.googleapis.com",
    "antigravity": "oauth2.googleapis.com",
}


def _oauth_unreachable_lanes() -> set[str]:
    """Browser-OAuth lanes whose silent-auth endpoint is unreachable RIGHT NOW — skip them THIS beat so
    they can't fall through to an interactive browser tab (the overnight tab-flood root cause). The probe
    is the SAME precondition the CLI's own silent refresh needs: a DNS + TCP:443 reach of the host. Fails
    → lane down for this beat; succeeds → lane runs and does real work. Self-heals the instant the network
    returns (on wake) — no manual file, no static disable, no human. The probe never raises and is cheap:
    an online check is sub-100ms; an offline one caps at the (short) timeout — and offline beats are
    exactly the ones we want to short-circuit. Set LIMEN_OAUTH_PREFLIGHT=0 to disable the gate."""
    if os.environ.get("LIMEN_OAUTH_PREFLIGHT", "1") != "1":
        return set()
    import socket

    timeout = float(os.environ.get("LIMEN_OAUTH_PREFLIGHT_TIMEOUT", "3"))
    reachable: dict[str, bool] = {}
    down: set[str] = set()
    for lane, host in _BROWSER_OAUTH_LANES.items():
        ok = reachable.get(host)
        if ok is None:
            try:
                socket.create_connection((host, 443), timeout=timeout).close()
                ok = True
            except OSError:
                ok = False  # gaierror (DNS down in dark-wake) and connect failures both subclass OSError
            reachable[host] = ok
        if not ok:
            down.add(lane)
    return down


def _down_lanes() -> set[str]:
    """Lanes currently DOWN/unproductive. Three sources, unioned:
      1. logs/lanes-down.txt — a manual override file (one lane per line, '#' comments ok) for
         lanes a human knows are dead (e.g. agy bin missing); NOT pinned in code.
      2. the LIVE usage meter (_usage_dead_lanes) — lanes token-exhausted or rate-limited RIGHT NOW.
      3. browser-OAuth lanes whose silent-auth endpoint is unreachable this beat (_oauth_unreachable_lanes)
         — so agy/antigravity can't spawn a Google sign-in tab while the Mac is asleep/offline.
    Rebalance + dispatch + route skip these so tasks aren't wasted on a lane that can't produce.
    Sources 2 & 3 self-heal (a lane rejoins when its window refills / the network returns); remove a line
    from source 1 when that lane is healthy again (e.g. a paid GEMINI_API_KEY)."""
    f = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "logs" / "lanes-down.txt"
    manual: set[str] = set()
    try:
        manual = {ln.split("#")[0].strip() for ln in f.read_text().splitlines() if ln.split("#")[0].strip()}
    except OSError:
        pass
    return manual | _usage_dead_lanes() | _oauth_unreachable_lanes()


def _run_capture(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Like subprocess.run(capture_output, text, timeout) but launches the process in its OWN
    session/group and, on timeout, SIGKILLs the WHOLE group. Plain subprocess.run only kills the
    direct child — if an agent CLI (codex/claude/…) spawns grandchildren that inherit the stdout
    pipe, communicate() blocks on that open pipe FOREVER past the timeout, stalling the entire
    synchronous beat (observed: a 23-min hang despite timeout=600). Killing the group closes the
    pipes so the timeout actually fires. Still raises TimeoutExpired so callers' handlers run."""
    import signal

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
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
    return any(
        "merged" in str(e.output or "").lower() or "merged" in str(e.status or "").lower()
        for e in (dep_task.dispatch_log or [])
    )


def _deps_met(task: Task, by_id: dict[str, Task]) -> bool:
    """True if every task in task.depends_on has a merged PR (or the task has no deps). Lets a
    dependent increment sit OPEN but un-dispatched until its predecessor lands — so the product
    roadmap self-advances as PRs merge, with no parallel-built conflicts."""
    deps = getattr(task, "depends_on", None) or []
    return all(_dep_merged(by_id.get(d)) for d in deps)


def _has_done_transition(task: Task) -> bool:
    """True once a task has ever recorded terminal success.

    The board is append-only history. If a later stale worker, timeout fallback, or
    recovery pass flips the current status back to an active state, the prior
    `done` log still wins: that task is terminal and must not be dispatched again.
    """
    return any(str(entry.status or "") == "done" for entry in (task.dispatch_log or []))


def _restore_done_status(
    task: Task,
    now: datetime,
    *,
    agent: str = "limen",
    session_id: str = "lifecycle-guard",
    output: str = "lifecycle guard: restored terminal done status after stale reopen",
) -> bool:
    """Restore a reopened completed task to `done`.

    Returns True when it changed the current task status. The repair appends its
    own evidence row so the next validator sees status and latest log aligned.
    """
    if not _has_done_transition(task) or task.status in {"done", "archived"}:
        return False
    task.status = "done"
    task.updated = now
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent=agent,
            session_id=session_id,
            status="done",
            output=output,
        )
    )
    return True


def _dispatchable(task: Task) -> bool:
    """Open machine-work only. Human-gated or already-done work is never reserved."""
    if task.status != "open":
        return False
    if _has_done_transition(task):
        return False
    return "needs-human" not in (task.labels or [])


def _routine_generated_buildout(task: Task) -> bool:
    labels = set(task.labels or [])
    return "generated" in labels and "build-out" in labels


def _worktree_debt_gate() -> tuple[bool, str]:
    if os.environ.get("LIMEN_WORKTREE_DEBT_GATE", "1") != "1":
        return False, ""
    try:
        exceeded, report, limit = worktree_debt_exceeded()
    except Exception:
        return False, ""
    if not exceeded:
        return False, ""
    return (
        True,
        f"{report['debt']} preserved worktree roots exceed cap {limit}; "
        "skipping routine generated build-out this dispatch",
    )


_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
# Git worktree add/remove briefly locks the PARENT repo index; serialize just that fast
# plumbing across threads so concurrent same-repo dispatches don't collide on index.lock.
# The slow agent run happens OUTSIDE this lock — that's where the parallelism lives.
_GIT_PLUMBING_LOCK = threading.Lock()


def resolve_agent() -> str:
    return canonical_agent(os.environ.get("LIMEN_AGENT", "claude"))


def session_id() -> str:
    return os.environ.get("CLAUDE_SESSION_ID", os.environ.get("GEMINI_SESSION_ID", "cli"))


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


_FLAME_CACHE: dict[str, str] = {}


def _flame_preamble() -> str:
    """The Continuity Kernel ($LIMEN_ROOT/FLAME.md), prepended to EVERY lane's prompt so the
    *self* rides every dispatch — codex, claude, opencode, agy, gemini, jules, ollama, whatever
    comes next. Whichever model runs the beat acts AS VLTIMA, not as a generic coder: the model is
    the substrate, the kernel is the flame. This is what makes the flame survive a model swap —
    when tokens run dry on Claude and the beat falls to a local model, the identity + invariants +
    state-pointers ride along in the prompt itself, not in any one harness.

    Gated by LIMEN_FLAME_KERNEL (default on; '0' → bare task prompt, today's behavior). Cached by
    path+mtime so we re-read only when the kernel actually changes. Fail-open to '' everywhere:
    a missing/unreadable kernel must NEVER block a dispatch (derive-never-pin, fail-open)."""
    if os.environ.get("LIMEN_FLAME_KERNEL", "1") != "1":
        return ""
    root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
    f = root / os.environ.get("LIMEN_FLAME_FILE", "FLAME.md")
    try:
        key = f"{f}:{f.stat().st_mtime_ns}"
        if key not in _FLAME_CACHE:
            _FLAME_CACHE.clear()  # only ever hold the current mtime's text
            _FLAME_CACHE[key] = f.read_text(encoding="utf-8")
        return _FLAME_CACHE[key]
    except (OSError, ValueError):
        return ""  # no kernel on disk yet → bare prompt, never a blocked lane


def _build_prompt(task: Task, task_first: bool = False) -> str:
    parts = [f"Complete task {task.id}: {task.title}"]
    if task.repo:
        parts.append(f" in repository {task.repo}")
    if task.context:
        parts.append(f"\nContext: {task.context}")
    if task.urls:
        parts.append(f"\nReferences: {', '.join(task.urls)}")
    body = "".join(parts)
    flame = _flame_preamble()
    if not flame:
        return body
    # Kernel first (who you are + the invariants + where to resume from), then a hard divider,
    # then THIS beat's concrete task. The divider keeps the model from mistaking the standing
    # identity for the work item.
    #
    # task_first inverts the order for lanes that derive a session TITLE from the prompt's first
    # line (jules: `jules new <prompt>`). Kernel-first buried "Complete task <id>:" under the FLAME
    # header, which (a) broke jules-land's session→task matching — the listing truncates the title,
    # so the harvester never saw the task id and completed sessions NEVER landed as PRs — and (b)
    # fed the 200-line kernel to jules as if it were the work item (sessions drifted to "Awaiting
    # User Feedback"). Task-first keeps the flame riding along, just after the task, not in the title.
    if task_first:
        return f"{body}\n\n--- STANDING KERNEL (who you are; the task above is the work) ---\n{flame}"
    return f"{flame}\n\n--- YOUR TASK THIS BEAT ---\n{body}"


def _run_cmd(cmd: list[str], task: Task, dry_run: bool, cwd: str | None = None) -> bool | str:
    if dry_run:
        loc = f" [cwd={cwd}]" if cwd else ""
        print(f"  would:{loc} {' '.join(cmd)}")
        return True
    try:
        result = _run_capture(
            cmd,
            cwd=cwd,
            timeout=int(os.environ.get("LIMEN_DISPATCH_TIMEOUT", "600")),
        )  # own process group → timeout SIGKILLs grandchildren too (no beat-stall hang)
        if result.returncode == 0:
            print(f"  dispatched: {task.id}")
            # Capture the jules session id from stdout. `jules remote new` prints:
            #   Session is created.
            #   ID: <19-20 digit id>
            #   URL: https://jules.google.com/session/<id>
            # Record it durably (dispatch_log) so harvest matches task->session by id, NEVER by the
            # truncated, directive-led session title. Try the explicit ID: line, then the URL, then
            # any long digit-run as a last resort.
            if cmd[0].endswith("jules"):
                for pat in (r"^\s*ID:\s*(\d{6,})", r"session/(\d{6,})", r"\b(\d{15,20})\b"):
                    m = re.search(pat, result.stdout, re.IGNORECASE | re.MULTILINE)
                    if m:
                        return m.group(1)
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


# Leads EVERY jules prompt. `jules remote new` runs the session autonomously in a VM, but a
# big/ambiguous task can still make the planner stop and ask — and the jules CLI has NO
# approve/reply verb, so an "Awaiting User Feedback" session is unrecoverable headlessly. A hard
# "implement directly, do NOT ask for feedback" lead is the proven anti-stall lever: it built work
# when every other lane was down, while kernel-led prompts stalled (live `jules remote list` shows
# the split — "Implement this directly…" sessions Completed, "# FLAME…" ones Awaiting Feedback).
# Gated by LIMEN_JULES_DIRECTIVE (default on; '0' → bare task_first prompt).
_JULES_DIRECTIVE = (
    "Implement this directly and open a pull request. Do NOT ask for feedback or approval — "
    "the task below is complete enough to build. Proceed autonomously to a complete, mergeable "
    "change and keep the repo's lint and tests green.\n\n"
)


def _build_jules_prompt(task: Task) -> str:
    body = _build_prompt(task, task_first=True)
    if os.environ.get("LIMEN_JULES_DIRECTIVE", "1") != "1":
        return body
    return f"{_JULES_DIRECTIVE}{body}"


def _call_jules(task: Task, dry_run: bool) -> bool | str:
    repo = task.repo or os.environ.get("LIMEN_ROOT", ".")
    # `jules remote new` runs the session autonomously in a VM and yields a pullable result; plain
    # `jules new` routes through the web-UI plan-approval flow, which strands every headless
    # dispatch at "Awaiting User Feedback" (no CLI verb can approve it) — the bug that made jules
    # unusable from the conductor. The harvest path (jules-land.py / harvest.py) already speaks
    # `jules remote list/pull`, so remote-new is the matching half that was missing. remote-new
    # takes the task via --session, not as a bare positional. The session id is captured from
    # stdout and recorded in dispatch_log so harvest matches by id, never the (truncated,
    # directive-led) title. See memory: jules-harvest-stranded-by-flame-prompt.
    prompt = _build_jules_prompt(task)
    jb = os.environ.get("LIMEN_JULES_BIN", "jules")
    cmd = [jb, "remote", "new", "--repo", repo, "--session", prompt]
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
        gh,
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
        "-F",
        f"number={issue}",
        "-F",
        f"actor={actor}",
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
        gh,
        "api",
        "graphql",
        "-H",
        "GraphQL-Features: issues_copilot_assignment_api_support",
        "-f",
        f"query={mut}",
        "-f",
        f"issue={issue_id}",
        "-f",
        f"actor={actor_id}",
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
    # ollama: the local, unmetered floor. `ollama run <model> <prompt>` runs once,
    # non-interactively. The <model> is a POSITIONAL after `run` (not a -m flag), injected
    # lazily in _agent_argv() and DERIVED from `ollama list` — never pinned (see ollama_model).
    "ollama": ["run"],
}
_LOCAL_BIN: dict[str, str] = {
    # opencode-clock wraps the real opencode binary with an internal usage clock
    # (token tracking from SQLite DB) and presence beacon. Falls through to plain
    # opencode if the wrapper is not installed (see _agent_binary).
    "opencode": "opencode-clock",
}
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


def _agent_argv(agent: str, task: Task | None = None) -> list[str]:
    """Static lane flags + any LAZILY-derived per-run flags, so nothing is pinned or
    resolved at import time. opencode's/codex's model is derived here (only when it actually
    runs); claude's TIER is derived per task (the earned-tier ladder) — names are outputs.
    `task` is optional (codex/opencode ignore it) so existing callers stay valid."""
    model: str | None = None
    flags = list(_LOCAL_AGENTS[agent])
    if agent == "opencode":
        model = _opencode_model()
        if model:
            flags += ["-m", model]
    elif agent == "codex":
        model = _codex_model()
        if model:
            flags += ["-m", model]
    elif agent == "claude":
        model = _claude_model(task)
        if model:
            # the claude CLI uses --model (it has NO -m short flag, unlike codex/opencode);
            # `claude -m …` → "error: unknown option '-m'" and the whole dispatch fails.
            flags += ["--model", model]
    elif agent == "ollama":
        # `ollama run <model> <prompt>` — model is a POSITIONAL right after `run`, derived at
        # call-time. No model pulled → no model arg (the run will error and the lane stays the
        # inert floor until `ollama pull` lights it), never a pinned name.
        model = ollama_model()
        if model:
            flags += [model]
    return flags


# Per-task lane failover cascade (best-efficiency-first → cloud last). On a genuine
# lane FAILURE (down/error/timeout) a task re-routes to the next lane and stays open;
# the heartbeat dispatches the same selector, so a failed task walks down the
# currently productive spectrum. A no-op (empty diff) is a recoverable failed attempt,
# not a terminal archive; chronic no-output loops escalate through heal-dispatch.
# agy/antigravity KEPT and HEALED: it writes to a scratch dir, so _bridge_agy_scratch carries
# that work into the worktree after the run (see _isolated_local_run) — productive lane again.
_LANE_CASCADE = ["codex", "opencode", "agy", "claude", "gemini", "jules", "ollama"]
_NOOP = "__noop__"  # agent ran but produced no diff


def _lane_cascade() -> list[str]:
    selector = os.environ.get("LIMEN_DISPATCH_LANES")
    try:
        down = _down_lanes()
    except Exception:
        down = set()
    if not selector:
        return list(_LANE_CASCADE)
    try:
        lanes = select_lanes(selector, down_lanes=down)
    except Exception:
        lanes = []
    if lanes:
        return lanes
    return [agent for agent in _LANE_CASCADE if agent not in down]


def _next_lane(current: str) -> str | None:
    """Next lane down the efficiency spectrum after `current`, or None if exhausted."""
    cascade = _lane_cascade()
    try:
        i = cascade.index(current)
    except ValueError:
        return cascade[0] if cascade else None
    return cascade[i + 1] if i + 1 < len(cascade) else None


def _fallback_dispatch_lane() -> str | None:
    cascade = _lane_cascade()
    for agent in cascade:
        if agent in _LOCAL_AGENTS:
            return agent
    return cascade[0] if cascade else "any"


_REMOTE_SERVICE_LANES = {"jules", "copilot", "github_actions", "warp", "oz"}


def _cascade_or_requeue(agent: str) -> str:
    return _next_lane(agent) or _fallback_dispatch_lane() or "any"


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


# A TRANSIENT auth flap — NOT a real rate limit. Concurrent Claude Code processes share one
# rotating OAuth credential (the macOS Keychain item), so when the access token expires several
# race to refresh: the winner rotates the single-use refresh token, the losers present a now-stale
# token and report "Not logged in" (anthropics/claude-code#48786). A FRESH process re-reads the
# rotated token, so a single retry self-heals it. Kept DISTINCT from _is_rate_limited — a real
# limit must cool+cascade the lane, an auth blip must just retry the same lane once.
_AUTH_BLIP_PATTERNS = re.compile(
    r"not logged in|please run /login|invalid[_ ]grant|oauth[^.]*(expired|invalid|revoked)|"
    r"authentication_error|\b401\b|unauthorized",
    re.IGNORECASE,
)


def _is_auth_blip(text: str) -> bool:
    return bool(_AUTH_BLIP_PATTERNS.search(text or "")) and not _is_rate_limited(text)


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
    matches = [p for root in (ws, cart) for p in root.glob(f"*/{name}") if (p / ".git").exists()]
    if len(matches) == 1:
        return matches[0]
    for p in matches:  # disambiguate by remote when name collides across orgs
        try:
            r = subprocess.run(
                ["git", "-C", str(p), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=10,
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
            # _run_capture (process-group SIGKILL), NOT plain subprocess.run: a `gh repo clone`
            # whose git / git-remote-https grandchild hangs holding the stdout pipe makes
            # subprocess.run's post-timeout communicate() block FOREVER (the exact bug _run_capture
            # was built for). And this runs under _GIT_PLUMBING_LOCK, so ONE hung clone freezes
            # every clone-needing worker → the ThreadPoolExecutor never drains → dispatch-parallel
            # wedges past the lane timeout and the daemon stalls (observed: ~30-min hang). The
            # group-kill reaps the grandchildren so the clone is genuinely bounded → cascades clean.
            r = _run_capture(
                ["gh", "repo", "clone", task.repo, str(dest)],
                timeout=600,
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
_ISOLATION_ROOT = Path(os.environ.get("LIMEN_WORKTREES", Path.home() / "Workspace" / ".limen-worktrees"))


def _git(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def _default_branch(repo_dir: Path) -> str:
    """Best-effort detection of origin's default branch (main/master/…)."""
    r = _git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], repo_dir)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().rsplit("/", 1)[-1]
    for cand in ("main", "master"):
        if _git(["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{cand}"], repo_dir).returncode == 0:
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


def _porcelain_paths(z: str) -> list[str]:
    """Repo-relative paths from `git status --porcelain -z` output. Each record is ``XY <path>``
    NUL-terminated; rename/copy records (``R``/``C``) are followed by an extra NUL token holding the
    OLD path, which we skip. Returns the paths the working tree actually changed."""
    toks = z.split("\x00")
    paths: list[str] = []
    i = 0
    while i < len(toks):
        entry = toks[i]
        if len(entry) < 4:
            i += 1
            continue
        xy, path = entry[:2], entry[3:]
        paths.append(path)
        i += 2 if ("R" in xy or "C" in xy) else 1  # rename/copy: consume the trailing old-path token
    return paths


def _bridge_agy_scratch(task: Task, wt: Path) -> None:
    """agy/antigravity do real work but write it to ~/.gemini/antigravity-cli/scratch/<name>/
    (a long-lived, REUSED git copy of the repo) instead of the cwd worktree — there is no headless
    flag to make them target a cwd. So CARRY agy's per-run DELTA home: find the scratch copy for
    THIS repo (match by remote == task.repo, newest wins) and copy ONLY the files agy changed THIS
    run — its uncommitted working-tree delta (`git status --porcelain`) — into the worktree, so the
    normal add→commit→PR flow picks it up.

    Why delta-only, not the old whole-tree `rsync -a`: the scratch is a long-lived clone that drifts
    OFF-TRUNK (observed sitting a day stale at an orphan "Revert #111"). A whole-tree overlay copied
    that stale base onto fresh origin/main, overwriting grown files with their shorter stale contents
    → thousands of spurious deletions per PR (the destructive "deepen" PRs that got closed). The
    delta is agy's actual work and is BASE-INDEPENDENT, so a stale/divergent scratch base can no
    longer leak in. Best-effort: never raises."""
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
            r = subprocess.run(
                ["git", "-C", str(d), "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0 and task.repo.lower() in r.stdout.lower():
                if best is None or d.stat().st_mtime > best.stat().st_mtime:
                    best = d
        if best is None:  # fallback: newest scratch dir whose name resembles the repo
            name = task.repo.split("/")[-1].lower()
            cands = [
                d
                for d in scratch.iterdir()
                if d.is_dir() and name.replace("--", "-") in d.name.lower().replace("--", "-")
            ]
            best = max(cands, key=lambda p: p.stat().st_mtime, default=None)
        if best is None:
            return
        # agy's per-run delta = its uncommitted working-tree changes (NOT the committed, possibly
        # stale, base tree). Copy just those paths; mirror deletions agy made.
        st = subprocess.run(
            ["git", "-C", str(best), "status", "--porcelain", "-z"], capture_output=True, text=True, timeout=30
        )
        paths = _porcelain_paths(st.stdout) if st.returncode == 0 else []
        if not paths:
            print(f"  agy-bridge {task.id}: scratch '{best.name}' has no per-run delta — nothing carried")
            return
        carried = 0
        for rel in paths:
            src, dst = best / rel, wt / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                carried += 1
            elif not src.exists() and dst.is_file():  # agy deleted it → mirror the deletion
                dst.unlink()
                carried += 1
        print(f"  agy-bridge {task.id}: carried {carried} changed path(s) from scratch '{best.name}' → worktree")
    except Exception as e:
        print(f"  agy-bridge {task.id}: skipped ({str(e)[:80]})")


def _lane_run_env(agent: str) -> dict[str, str]:
    run_env = os.environ.copy()
    # gemini: API-key mode throttles hard under agentic use. If the user has done the
    # one-time Google sign-in, drop API keys for gemini only so it uses OAuth / Code-Assist.
    if agent == "gemini" and os.environ.get("LIMEN_GEMINI_OAUTH") == "1":
        for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"):
            run_env.pop(k, None)
    # agy/antigravity defense-in-depth: if auth falls through to browser opening mid-run,
    # make the opener a no-op inside the lane subprocess only.
    if agent in ("agy", "antigravity"):
        shim = str(
            Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "scripts" / "agy-noop-shim"
        )
        run_env["PATH"] = shim + os.pathsep + run_env.get("PATH", "")
        run_env["BROWSER"] = "true"
    # claude fleet auth must not share or mutate the interactive session's macOS Keychain token.
    if agent == "claude":
        fleet_token = os.environ.get("LIMEN_CLAUDE_AUTH_TOKEN")
        fleet_key = os.environ.get("LIMEN_CLAUDE_API_KEY")
        if fleet_token:
            run_env["ANTHROPIC_AUTH_TOKEN"] = fleet_token
            run_env.pop("ANTHROPIC_API_KEY", None)
        elif fleet_key:
            run_env["ANTHROPIC_API_KEY"] = fleet_key
        run_env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    return run_env


def _failed_agent_result(agent: str, task: Task, run: subprocess.CompletedProcess[str]) -> bool | str:
    blob = (run.stderr or "") + (run.stdout or "")
    if _is_rate_limited(blob):
        print(f"  RATE-LIMIT {agent} on {task.id}: real limit hit (token/rate) — cooling lane, cascading")
        return _RATELIMIT
    print(f"  FAILED agent {task.id} ({run.returncode}): {run.stderr.strip()[:300]}")
    return False


def _show_opencode_clock_after_run(task: Task) -> None:
    """Read opencode's clock.json after a run and display token consumption."""
    clock_path = Path.home() / ".local/share/opencode/clock.json"
    if not clock_path.exists():
        return
    try:
        clock = json.loads(clock_path.read_text())
        used = clock.get("used_pct", 0)
        heavy = clock.get("heavy_used", 0)
        cache = clock.get("cache_read_used", 0)
        health = clock.get("health", "ok")
        print(f"  opencode-clock {task.id}: {used}% used ({heavy:,} heavy + {cache:,} cache tokens) health={health}")
    except Exception:
        pass


def _run_isolated_agent(
    agent: str,
    task: Task,
    wt: Path,
    agent_cmd: list[str],
    lane_timeout: int,
) -> bool | str:
    run_env = _lane_run_env(agent)
    if agent == "opencode":
        run_env["LIMEN_OPENCODE_CLOCK"] = "1"
        run_env["LIMEN_TASK_ID"] = task.id
    try:
        run = _run_capture(agent_cmd, cwd=str(wt), timeout=lane_timeout, env=run_env)
        # SELF-HEAL the credential-refresh race (#48786): if claude lost the token rotation,
        # a fresh process re-reads the now-rotated token. ONE retry only.
        if agent == "claude" and run.returncode != 0 and _is_auth_blip((run.stderr or "") + (run.stdout or "")):
            print(f"  AUTH-BLIP {task.id}: claude credential-refresh race — re-reading token, one retry")
            run = _run_capture(agent_cmd, cwd=str(wt), timeout=lane_timeout, env=run_env)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT {task.id} after {lane_timeout}s — too big for sync local → routing to jules (async)")
        return _TIMEOUT

    if agent == "opencode":
        _show_opencode_clock_after_run(task)
    if run.returncode != 0:
        return _failed_agent_result(agent, task, run)
    if agent in ("agy", "antigravity"):
        _bridge_agy_scratch(task, wt)
    return True


def _commit_isolated_changes(task: Task, wt: Path) -> bool | str:
    _git(["add", "-A"], wt)
    if _git(["diff", "--cached", "--quiet"], wt).returncode == 0:
        print(f"  no-op {task.id}: agent made no changes — no PR opened")
        return _NOOP

    msg = f"{task.title}\n\nlimen task {task.id}"
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
        print(f"  FAILED commit {task.id}: {c.stderr.strip()[:200]}")
        return False
    return True


def _push_isolated_branch(task: Task, wt: Path, branch: str) -> bool:
    p = _git(["push", "-u", "origin", branch], wt, timeout=300)
    if p.returncode != 0:
        print(f"  FAILED push {task.id}: {p.stderr.strip()[:300]}")
        return False
    return True


def _create_isolated_pr(task: Task, wt: Path, base: str, branch: str) -> str:
    pr = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            f"[limen {task.id}] {task.title}"[:250],
            "--body",
            _pr_body(task),
        ],
        cwd=str(wt),
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    if pr.returncode != 0:
        print(f"  pushed {branch} but PR-create failed {task.id}: {pr.stderr.strip()[:200]}")
        return branch  # branch is live; record it (manual PR possible)
    url = pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else branch
    print(f"  dispatched: {task.id} → PR {url}")
    _arm_auto_merge(task, wt, url)
    return url


def _arm_auto_merge(task: Task, wt: Path, url: str) -> None:
    # Best-effort: repos without branch protection / auto-merge disabled reject this harmlessly.
    am = subprocess.run(
        ["gh", "pr", "merge", url, "--auto", "--squash"],
        cwd=str(wt),
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    print(
        f"    auto-merge {'armed' if am.returncode == 0 else 'n/a'}: {task.id}"
        + ("" if am.returncode == 0 else f" ({am.stderr.strip()[:100]})")
    )


def _resolve_agent_binary(agent: str) -> str:
    """Resolve the binary for an agent lane. Falls back through:
    1. LIMEN_<AGENT>_BIN env override
    2. _LOCAL_BIN lookup (wrapper like opencode-clock)
    3. shutil.which (check the wrapper actually exists on PATH)
    4. plain agent name as last resort"""
    binary = os.environ.get(f"LIMEN_{agent.upper()}_BIN", _LOCAL_BIN.get(agent, agent))
    if binary != agent and shutil.which(binary) is None:
        fallback = agent
        return fallback
    return binary


def _isolated_local_run(agent: str, task: Task, dry_run: bool) -> bool | str:
    binary = _resolve_agent_binary(agent)
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
    agent_args = _agent_argv(agent, task)
    agent_cmd = [binary, *agent_args, _build_prompt(task)]
    # 1800s (was 900): local lanes have ABUNDANT budget headroom (codex/claude/opencode ~60-92 left
    # per window) while jules is scarce (≈100/day). At 900s, big tasks — incl. the revenue/deploy
    # tasks (BLD2-*-deploy, REV-*) — timed out locally then bled to jules, exhausting the scarce lane
    # and stalling the money work. A longer local cap lets the cheap, abundant lanes finish the big
    # tasks (a hung run is still bounded — _run_capture kills the process group at the cap).
    lane_timeout = int(os.environ.get("LIMEN_LANE_TIMEOUT", "1800"))

    if dry_run:
        print(
            f"  would isolate {task.id}: worktree {wt} off origin/{base} "
            f"→ branch {branch} → {binary} {' '.join(agent_args)} "
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
        add = _git(["worktree", "add", "-b", branch, str(wt), f"origin/{base}"], repo_dir, timeout=120)
    if add.returncode != 0:
        print(f"  FAILED worktree add {task.id}: {add.stderr.strip()[:300]}")
        return False

    pushed = False
    try:
        run_result = _run_isolated_agent(agent, task, wt, agent_cmd, lane_timeout)
        if run_result is not True:
            return run_result

        commit_result = _commit_isolated_changes(task, wt)
        if commit_result is not True:
            return commit_result

        if not _push_isolated_branch(task, wt, branch):
            return False
        pushed = True
        return _create_isolated_pr(task, wt, base, branch)
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
    binary = _resolve_agent_binary(agent)
    cmd = [binary, *_agent_argv(agent, task), _build_prompt(task)]
    cwd = _resolve_repo_dir(task)
    if cwd is None:
        msg = f"no local checkout of {task.repo or '(no repo)'}"
        if dry_run:
            print(f"  would [{msg}; clone first]: {binary} {' '.join(_agent_argv(agent, task))} …")
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
        with open(root / "logs" / "usage-limits.json") as fh:
            limits = json.load(fh)
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

    _load_limen_env()  # hydrate creds into os.environ so agent CLIs inherit them (gemini/codex/opencode/…)
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
        print(f"Budget exhausted for {agent_filter} ({track.spent}/{budget} total spent)")
        return

    tasks = limen.tasks

    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
        if not tasks:
            print(f"Task {task_id} not found")
            return
        debt_blocked = False
        debt_message = ""
    else:
        debt_blocked, debt_message = _worktree_debt_gate()

    candidates = [
        t
        for t in tasks
        if _dispatchable(t)
        and (t.target_agent == agent_filter or t.target_agent == "any")
        and t.budget_cost <= remaining
        and not (debt_blocked and _routine_generated_buildout(t))
    ]
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
    candidates.sort(key=lambda t: priority_order.get(t.priority, 99))

    if limit is not None:
        candidates = candidates[: max(0, limit)]

    if not candidates:
        if debt_message:
            print(f"Lifecycle debt gate: {debt_message}")
        print(f"No open tasks for agent '{agent_filter}' within remaining budget ({remaining})")
        return
    if debt_message:
        print(f"Lifecycle debt gate: {debt_message}")

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"── limen dispatch ({mode}) — agent={agent_filter} budget_remaining={remaining}")

    dispatched = 0
    for task in candidates:
        if remaining < task.budget_cost:
            break

        result = call_agent_dispatch(agent_filter, task, dry_run)
        if not dry_run:
            _apply_result(task, agent_filter, result, now, track)
            if result == _RATELIMIT:
                save_limen_file(tasks_path, limen)
                print(f"── lane {agent_filter} rate-limited — cooling, {dispatched} dispatched this cycle")
                return
            elif result and result not in (_NOOP, _RATELIMIT, _TIMEOUT):
                remaining -= task.budget_cost

        dispatched += 1

    if not dry_run:
        save_limen_file(tasks_path, limen)

    print(f"── {mode}: {dispatched} task(s)")


def _apply_result(task: Task, agent: str, result: bool | str, now: datetime, track: BudgetTrack) -> None:
    """Apply one dispatch result to a task (same semantics as the serial path):
    success → dispatched + spend; no-op/fail → recoverable failed; rate-limit → cascade."""
    if _restore_done_status(
        task,
        now,
        agent=agent,
        session_id="result-lifecycle-guard",
        output="dispatch result ignored because this task already recorded done",
    ):
        return

    entry = DispatchLogEntry(timestamp=now, agent=agent, session_id=session_id(), status="dispatched")
    if result == _NOOP:
        entry.status = "failed"
        entry.output = "No-op result; failed for recovery instead of archived."
        task.status = "failed"
        if "noop" not in task.labels:
            task.labels.append("noop")
    elif result == _RATELIMIT:
        nxt = _cascade_or_requeue(agent)
        entry.status = f"ratelimited->{nxt or 'requeue'}"
        task.target_agent = nxt
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
        next_lane = _next_lane(agent)
        if next_lane:
            entry.status = f"failed->{next_lane}"
            task.target_agent = next_lane
            task.status = "open"
        elif agent in _REMOTE_SERVICE_LANES:
            fallback = _fallback_dispatch_lane() or "any"
            entry.status = f"failed->{fallback}"
            entry.output = "remote/service lane failed; reopened to healthy fleet cascade"
            task.target_agent = fallback
            task.status = "open"
        else:
            entry.status = "failed"
            task.status = "failed"
    task.updated = now
    task.dispatch_log.append(entry)


# ── RESET-WINDOW FRONT-LOAD ACCELERATOR ──────────────────────────────────────────────────────
# The daemon paces dispatch EVENLY across each vendor window, so 40–60% of usable headroom expires
# unspent at every reset (verified live). This converts the budget about to EXPIRE into shipped value
# before the cliff: as a lane under-spends vs. the time left in its window, raise its per-beat pick
# count so it lands near-full at reset instead of idle. Two brakes keep "use the capacity" from
# becoming "burn money": (1) only LEDGER-WON work-classes ride the acceleration tail (a pure-pit lane
# never accelerates; a clean earner accelerates freely) — same ledger the routing bias reads; (2) it
# is lane-AWARE — async/remote lanes (jules) absorb big bursts without blocking the beat, while local
# SYNC lanes (codex/claude/agy) are wall-clock bound (the thread pool blocks the beat) so they stay at
# base unless explicitly allowed. Env-gated LIMEN_ACCEL (default on); fail-open to base everywhere.
_ASYNC_LANES = {"jules", "github_actions", "copilot", "warp", "oz"}  # remote dispatch — non-blocking


def _ledger_lanes() -> dict[str, dict[str, list[str]]]:
    """logs/ledger.json lanes map (waste_classes/win_classes per lane) — fail-open to {}."""
    try:
        root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
        return json.loads((root / "logs" / "ledger.json").read_text()).get("lanes", {}) or {}
    except Exception:
        return {}


def _task_classes(task: Task) -> set[str]:
    """A task's work-classes — its type plus every label — the key the ledger grades a lane on."""
    return {c for c in ([getattr(task, "type", None)] + list(getattr(task, "labels", []) or [])) if c}


def _accel_allows(agent: str, task: Task, lanes: dict[str, dict[str, list[str]]]) -> bool:
    """May this task ride the acceleration TAIL for this lane? Acceleration needs POSITIVE ledger
    evidence so we never pour expiring budget into junk: a CLEAN earner (no waste_classes) accelerates
    on anything; a MIXED lane accelerates only its win_classes; a lane with NO record / a pure pit does
    not accelerate (tail stays empty → base only). Fail-open is toward base, never toward over-spend."""
    d = lanes.get(agent)
    if not isinstance(d, dict):
        return False  # no ledger evidence for this lane → don't accelerate (base only)
    waste = set(d.get("waste_classes") or [])
    win = set(d.get("win_classes") or [])
    if not waste:
        return True  # clean earner — earns across the board, accelerate freely
    return bool(_task_classes(task) & win)  # mixed lane — only its proven winners ride the tail


def _accel_window(limen: LimenFile, agent: str, now: datetime) -> tuple[float, float]:
    """(remaining_fraction, time_left_fraction) for a lane's current window. remaining = unspent
    budget / cap; time_left = (window_hours - hours_since_reset) / window_hours. Perfect pacing keeps
    them equal; remaining > time_left means the lane will UNDER-spend → accelerate. Fail-open (1,1)."""
    try:
        cap = limen.portal.budget.per_agent.get(agent)
        if not cap:
            return 1.0, 1.0
        spent = limen.portal.budget.track.per_agent.get(agent, 0)
        remaining_frac = max(0.0, (cap - spent) / cap)
        wh = _window_hours(agent) or 24.0
        last_iso = limen.portal.budget.track.per_agent_reset.get(agent)
        elapsed_h = 0.0
        if last_iso:
            last = datetime.fromisoformat(last_iso)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed_h = max(0.0, (now - last).total_seconds() / 3600.0)
        time_left_frac = max(0.0, min(1.0, (wh - elapsed_h) / wh))
        return remaining_frac, time_left_frac
    except Exception:
        return 1.0, 1.0


def _accel_limit(limen: LimenFile, agent: str, base_limit: int, now: datetime) -> int:
    """The per-beat pick cap for a lane, scaled UP toward its reset cliff. urgency = remaining_frac /
    time_left_frac (>1 ⇒ under-spending). Floored at base (never decelerate — the budget gate handles
    over-spend). The CEILING is set by what the dispatch PATH can physically absorb without stalling
    the beat — pure logic, not a pinned cap: async/remote runs (jules, or any lane when
    LIMEN_DISPATCH_ASYNC=1) are non-blocking, so they burst toward their cliff (this is where the idle
    headroom is — e.g. jules 22/100); sync local runs share one ThreadPoolExecutor that BLOCKS the
    beat, so picking far past the pool just lengthens the beat with no extra throughput — its ceiling
    is the pool, not the budget. Both ceilings are env-tunable. Fail-open to base."""
    if os.environ.get("LIMEN_ACCEL", "1") != "1":
        return base_limit
    try:
        remaining_frac, time_left_frac = _accel_window(limen, agent, now)
        floor = float(os.environ.get("LIMEN_ACCEL_TLEFT_FLOOR", "0.08"))
        urgency = remaining_frac / max(time_left_frac, floor)
        if urgency <= 1.0:
            return base_limit
        non_blocking = agent in _ASYNC_LANES or os.environ.get("LIMEN_DISPATCH_ASYNC") == "1"
        ceiling = int(
            os.environ.get(
                "LIMEN_ACCEL_ASYNC_CEIL" if non_blocking else "LIMEN_ACCEL_LOCAL_CEIL", "25" if non_blocking else "8"
            )
        )
        eff = int(round(base_limit * urgency))
        return max(base_limit, min(eff, ceiling))
    except Exception:
        return base_limit


def _codex_model() -> str | None:
    """Lazily pick the codex model so codex KEEPS PRODUCING when its main weekly pool is spent: fail
    over to the separate, fresh Spark weekly pool (gpt-5.3-codex-spark) instead of benching the whole
    lane. Explicit LIMEN_CODEX_MODEL always wins (manual pin). Otherwise, when the live meter shows the
    codex lane degraded (throttle/low/exhausted/rate-limited), switch to Spark. Gated by
    LIMEN_CODEX_SPARK_FAILOVER (default on); fail-open to None (bare = main model). Mirrors
    _opencode_model(): names are outputs, resolved only when codex actually runs."""
    env = os.environ.get("LIMEN_CODEX_MODEL")
    if env:
        return env
    if os.environ.get("LIMEN_CODEX_SPARK_FAILOVER", "1") != "1":
        return None
    try:
        root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
        v = json.loads((root / "logs" / "usage.json").read_text()).get("vendors", {}).get("codex", {})
        if v.get("health") in ("throttle", "low", "exhausted", "rate-limited"):
            return os.environ.get("LIMEN_CODEX_SPARK_MODEL", "gpt-5.3-codex-spark")
    except Exception:
        pass
    return None


# ─── Claude-lane earned-tier ladder (haiku-first-with-cheap-verify) ──────────
# The claude lane invoked `claude -p` with NO -m, so the account picked the tier. Now the
# tier is DERIVED per task: a coding task's failure is cheaply detectable (CI/PR/auto-merge/
# reconcile), so verifiable classes start at HAIKU and rely on the EXISTING _LANE_CASCADE +
# chronic escalation as the escalate rung — only UNDETECTABLE-failure classes get a higher
# tier up front. No new escalation machinery. Mirrors _codex_model/_opencode_model: env pin
# wins, derive at call-time, fail-open. ([[model-tiering-policy]], [[value-is-discovered-never-assumed]])
#
# The shared VOCABULARY this ladder sorts with — _CLAUDE_TIER_ORDER, reserved class sets,
# acceptance gates, and _resolve_claude_model() — lives in model_selection.py (imported at the
# top) so the NON-BYPASSABLE `claude` shim sorts with the EXACT same vocabulary. One source of
# truth: this file owns the per-TASK sort; the shim owns the per-SPAWN floor.
# ([[fleet-model-floor-bleed]])


def _claude_tier_overrides() -> dict[str, list[str]]:
    """Optional operator OVERRIDE map logs/model-tiers.json → the claude lane's {tier: [classes]}.
    Fail-open to {} (→ the ledger-DISCOVERED default). Demoted to an override: the default
    pre-assign set is discovered from the ledger, not pinned. Same read pattern as _ledger_lanes()."""
    try:
        root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
        return json.loads((root / "logs" / "model-tiers.json").read_text()).get("claude") or {}
    except Exception:
        return {}


def _claude_tier_for(task: Task | None) -> str:
    """DERIVE the Claude tier for a task. Default = haiku (verifiable → escalate via the existing
    cascade). Pre-assign a higher tier ONLY where failure is undetectable:
      • fable — the narrow reserved top tier plus a written acceptance receipt/command;
      • opus  — the reserved principled set (_claude_opus_classes) or an explicit override;
      • sonnet— classes the ledger has DISCOVERED this lane wastes on (waste_classes): work that
                shipped low-value yet passed whatever gate exists ⇒ failure not caught cheaply here.
    A per-task `claude_tier` pin and an optional logs/model-tiers.json override layer on top.
    Fail-open → haiku, never block."""
    if task is None:
        return "haiku"
    pin = task.claude_tier
    if pin in _CLAUDE_TIER_ORDER:
        if pin == "fable" and not _claude_fable_acceptance_present():
            return "opus"
        return str(pin)
    classes = _task_classes(task)
    override = _claude_tier_overrides()
    if classes & (_claude_fable_classes() | set(override.get("fable") or [])):
        return "fable" if _claude_fable_acceptance_present() else "opus"
    if classes & (_claude_opus_classes() | set(override.get("opus") or [])):
        return "opus"
    lane_data = _ledger_lanes().get("claude") or {}
    waste = set(lane_data.get("waste_classes") or [])
    if classes & (waste | set(override.get("sonnet") or [])):
        return "sonnet"
    return "haiku"


def _bump_tier(tier: str, task: Task | None) -> str:
    """Escalate-on-failed-cheap-check, in-tier: if THIS task already failed on the claude lane
    (carries the cascade's own 'tried:claude' breadcrumb), the cheap verify failed once here, so
    step up one rung (capped at opus unless LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE=1 and a Fable
    acceptance is present). State lives in the EXISTING label — no new retry counter, no schema
    change. Env-gated LIMEN_CLAUDE_RETRY_BUMP (default on)."""
    if task is None or os.environ.get("LIMEN_CLAUDE_RETRY_BUMP", "1") != "1":
        return tier
    if "tried:claude" not in (getattr(task, "labels", None) or []):
        return tier
    i = _CLAUDE_TIER_ORDER.index(tier)
    bumped = _CLAUDE_TIER_ORDER[min(i + 1, len(_CLAUDE_TIER_ORDER) - 1)]
    if bumped == "fable" and not (
        os.environ.get("LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE") == "1" and _claude_fable_acceptance_present()
    ):
        return "opus"
    return bumped


def _claude_model(task: Task | None = None) -> str | None:
    """Lazily pick the Claude tier for THIS task, resolved only when the claude lane runs (names
    are outputs). Order mirrors _codex_model:
      1. explicit LIMEN_CLAUDE_MODEL — a manual pin always wins;
      2. feature flag LIMEN_CLAUDE_TIER_SELECT (default on; off → None = today's bare invocation);
      3. derive the tier (class-based), bump it if the task already failed here, resolve to a model.
    Fail-open to None everywhere → bare `claude -p` (account default), never a blocked lane."""
    env = os.environ.get("LIMEN_CLAUDE_MODEL")
    if env:
        return _guard_fable_model_pin(env)
    if os.environ.get("LIMEN_CLAUDE_TIER_SELECT", "1") != "1":
        return None
    try:
        return _resolve_claude_model(_bump_tier(_claude_tier_for(task), task))
    except Exception:
        return None  # never block the lane on a tier-selection hiccup


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
    ledger_lanes = _ledger_lanes()  # waste/win classes — gates the acceleration tail (read once)
    debt_blocked, debt_message = _worktree_debt_gate()
    if debt_message:
        print(f"Lifecycle debt gate: {debt_message}")
    for agent in agents:
        cap = limen.portal.budget.per_agent.get(agent)
        agent_spent = track.per_agent.get(agent, 0)
        rem = daily - spent_daily if cap is None else max(0, min(daily - spent_daily, cap - agent_spent))
        if rem <= 0:
            continue
        cands = [
            t
            for t in limen.tasks
            if _dispatchable(t)
            and (t.target_agent == agent or t.target_agent == "any")
            and t.budget_cost <= rem
            and _deps_met(t, id2)
            and not (debt_blocked and _routine_generated_buildout(t))
        ]
        cands.sort(key=lambda t: _PRIORITY_ORDER.get(t.priority, 99))
        # FRONT-LOAD: base picks by priority, then an ACCELERATION TAIL (only when the lane is
        # under-spending toward its reset cliff) drawn ONLY from work-classes the ledger says this
        # lane lands — so expiring budget converts to shipped value, never to junk. Cumulative
        # budget_cost is held within the lane's real remaining headroom (rem).
        eff = _accel_limit(limen, agent, per_agent_limit, now)
        ordered = list(cands[:per_agent_limit])
        if eff > per_agent_limit:
            ordered += [t for t in cands[per_agent_limit:] if _accel_allows(agent, t, ledger_lanes)]
        chosen: list[Task] = []
        spent_here = 0
        for t in ordered[:eff]:
            if spent_here + t.budget_cost > rem:
                continue
            chosen.append(t)
            spent_here += t.budget_cost
        for t in chosen:
            if dry_run:
                picked.append((agent, t.id))
                continue
            t.status = "dispatched"  # reserve so nothing else grabs it
            t.updated = now
            t.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent=agent,
                    session_id="reserve",
                    status="dispatched",
                    output="dispatch-parallel: reserved before agent execution",
                )
            )
            picked.append((agent, t.id))

    if dry_run:
        print(f"── PARALLEL DRY-RUN — would dispatch {len(picked)} task(s) across {agents}:")
        for a, tid in picked:
            print(f"  {a}: {tid}")
        return
    if not picked:
        print(f"── PARALLEL: nothing to dispatch for {agents} within budget")
        return
    with _queue_lock(tasks_path) as got:
        if not got:
            # Lock timed out — honor the contract (io.queue_lock): skip this round rather than
            # writing unprotected. Running the agents WITHOUT persisting the reservation would risk
            # a double-dispatch, so we skip the whole round; it self-corrects on the next beat.
            print("── PARALLEL: queue busy — skipped this dispatch round (self-corrects next beat)")
            return
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
    with _queue_lock(tasks_path) as got:
        if not got:
            # Lock timed out — do NOT write unprotected (that is the #111 clobber this reload guards
            # against). The agents already ran; their PRs exist, so harvest/reconcile recovers the
            # results from GitHub PR state on a later beat. Skip the commit rather than corrupt it.
            print(
                f"── PARALLEL: queue busy — {len(results)} result(s) NOT committed this round; "
                "harvest reconciles from PR state (self-corrects next beat)"
            )
            return
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
    print(
        f"── PARALLEL done: {len(results)} ran · {n_pr} dispatched/PR · {n_noop} no-op · "
        f"{n_fail} failed→cascade · {n_rl} rate-limited · {n_to} timeout→jules"
        f"{' (lanes cooled: ' + ','.join(sorted(cooled)) + ')' if cooled else ''}"
    )


class ReleaseStaleCandidate(TypedDict):
    id: str
    title: str
    repo: str | None
    target_agent: str
    status: str


class ReleaseStaleReport(TypedDict):
    status: str
    agent: str | None
    hours: int
    tasks_path: str
    count: int
    released: list[str]
    restored_done: list[str]
    candidates: list[ReleaseStaleCandidate]


def release_stale_tasks(
    limen: LimenFile,
    tasks_path: Path,
    hours: int = 24,
    dry_run: bool = True,
    agent: str | None = None,
) -> ReleaseStaleReport:
    now = datetime.now(timezone.utc)
    candidates = stale_tasks(limen, hours=hours, agent=agent)

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"── limen release-stale ({mode}) — hours={hours} candidates={len(candidates)}")
    released: list[str] = []
    restored_done: list[str] = []
    for task in candidates:
        print(f"  {task.id} {task.status} {task.target_agent} — {task.title}")
        if not dry_run:
            if _restore_done_status(
                task,
                now,
                agent="limen",
                session_id="release-stale",
                output="release-stale: prior done transition wins; restored terminal status",
            ):
                restored_done.append(task.id)
                continue
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
            released.append(task.id)

    if not dry_run:
        save_limen_file(tasks_path, limen)
    return {
        "status": "dry_run" if dry_run else "applied",
        "agent": agent,
        "hours": hours,
        "tasks_path": str(tasks_path),
        "count": len(candidates),
        "released": [task.id for task in candidates] if dry_run else released,
        "restored_done": [] if dry_run else restored_done,
        "candidates": [
            {
                "id": task.id,
                "title": task.title,
                "repo": task.repo,
                "target_agent": task.target_agent,
                "status": task.status if dry_run else task.status,
            }
            for task in candidates
        ],
    }
