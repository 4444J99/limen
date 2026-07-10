import json
import math
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, TypedDict

from limen import census
from limen.capacity import (
    DEFAULT_GITHUB_ACTIONS_WORKFLOW,
    canonical_agent,
    capacity_census,
    format_capacity_census,
    github_issue_ref,
    local_floor_classes,
    local_floor_enabled,
    ollama_model,
    select_lanes,
)
from limen.io import load_limen_file, save_limen_file, queue_lock as _queue_lock
from limen.models import BudgetTrack, DispatchLogEntry, LimenFile, Task
from limen.doctor import stale_tasks
from limen.provider_selection import (
    catalog_hash,
    discover_opencode_models,
    discover_warp_override,
    effective_profile,
    execution_profile_for,
    paid_service_block_reason,
    select_opencode_model,
)
from limen.model_selection import (  # the shared model vocabulary — also used by the non-bypassable `claude` shim
    _CLAUDE_TIER_ORDER,
    _claude_fable_acceptance_present,
    _claude_fable_classes,
    _claude_opus_classes,
    _fable_capped_tier,
    _fable_fallback_tier,
    _fable_reserve_receipt_present,
    _guard_fable_model_pin,
    _resolve_claude_model,
)
from limen.worktree_debt import worktree_debt_exceeded
from limen.worktree_roots import default_worktrees_root


def _int_or_default(raw: object, default: int) -> int:
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw) if math.isfinite(raw) else default
    if isinstance(raw, str | bytes | bytearray):
        try:
            return int(raw)
        except ValueError:
            return default
    return default


def _float_or_default(raw: object, default: float) -> float:
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int | float | str | bytes | bytearray):
        try:
            value = float(raw)
        except ValueError:
            return default
        return value if math.isfinite(value) else default
    return default


def _env_int(name: str, default: int) -> int:
    return _int_or_default(os.environ.get(name), default)


def _env_float(name: str, default: float) -> float:
    return _float_or_default(os.environ.get(name), default)


def _truthy_env(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


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
    so we stop BEFORE 0). `throttle` usually stays UP as a steering signal, but a throttle signal
    with zero remaining/headroom is already out of runway and must stop too. DERIVED from the live
    signal, never pinned: a lane auto-rejoins the instant its rolling window refills (no manual edit).
    This is what makes dispatch HONEST — we never assign a task to a lane that physically cannot
    produce, and we never burn one to 0."""
    f = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "logs" / "usage.json"
    try:
        vendors = (json.loads(f.read_text()) or {}).get("vendors", {})
    except (OSError, ValueError):
        return set()
    dead: set[str] = set()
    for name, info in vendors.items():
        if not isinstance(info, dict):
            continue
        health = info.get("health")
        if _weak_proxy_exhaustion(name, info):
            continue
        if health in ("exhausted", "rate-limited", "low"):
            dead.add(name)
            continue
        if health == "throttle" and (_usage_zero(info.get("remaining")) or _usage_zero(info.get("headroom_pct"))):
            dead.add(name)
    return dead


def _weak_proxy_exhaustion(name: str, info: dict) -> bool:
    """A weak dispatch-count proxy is not proof of provider exhaustion.

    Agy has no readable vendor quota meter yet. Its usage row is a board-derived dispatch-count
    proxy, so a high count should pace reservations through the board budget, not remove the lane
    entirely. A real rate-limit signal still gates it.
    """
    if name != "agy":
        return False
    if info.get("health") == "rate-limited" or info.get("recent_rate_limit"):
        return False
    signal = str(info.get("signal") or "")
    source = str(info.get("limit_source") or "")
    return signal in {"dispatch-count", "count", "runs"} and "operator board cap" in source


def _usage_zero(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float | str | bytes | bytearray):
        try:
            return float(value) == 0.0
        except ValueError:
            return False
    return False


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

    timeout = max(0.1, _env_float("LIMEN_OAUTH_PREFLIGHT_TIMEOUT", 3.0))
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


def run_always_working_before_dispatch(tasks_path: Path, *, dry_run: bool = False) -> bool:
    """Emit missing always-working owner tickets before reserving more work.

    The writer is a gate for the canonical live board only. Dry-runs and test/temp boards stay
    read-only; the heartbeat/dispatch paths still share the same live pre-reservation behavior.
    """
    if dry_run or os.environ.get("LIMEN_ALWAYS_WORKING_BEFORE_DISPATCH", "1") != "1":
        return True
    root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))).resolve()
    try:
        if tasks_path.resolve() != (root / "tasks.yaml").resolve():
            return True
    except OSError:
        return True
    script = root / "scripts" / "always-working.py"
    if not script.exists():
        print(f"Always-working gate skipped: missing {script}")
        return os.environ.get("LIMEN_ALWAYS_WORKING_HARD_GATE") != "1"
    try:
        result = _run_capture(
            [
                sys.executable,
                str(script),
                "--write",
                "--emit-task-tickets",
                "--tasks",
                str(tasks_path),
            ],
            cwd=str(root),
            timeout=max(1, _env_int("LIMEN_ALWAYS_WORKING_TIMEOUT", 180)),
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        print("Always-working gate timed out before dispatch reservation")
        return os.environ.get("LIMEN_ALWAYS_WORKING_TIMEOUT_HARD_GATE", "0") != "1"
    except OSError as exc:
        print(f"Always-working gate failed before dispatch reservation: {exc}")
        return os.environ.get("LIMEN_ALWAYS_WORKING_HARD_GATE", "1") != "1"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        suffix = f": {detail[-1][:240]}" if detail else ""
        print(f"Always-working gate failed before dispatch reservation{suffix}")
        return os.environ.get("LIMEN_ALWAYS_WORKING_HARD_GATE", "1") != "1"
    output = (result.stdout or "").strip()
    if output:
        print(f"Always-working gate: {output.splitlines()[-1][:240]}")
    return True


_DISPATCH_ADMISSION_POLICY = "dispatch-admission-v1"
_DISPATCH_ADMISSION_GATE_HOURS = "1.5"
_CHRONIC_EXEMPT_LABELS = {"chronic-ok", "allow-repeat-dispatch", "fresh-evidence"}
_NOOP_PATTERNS = ("no-op", "noop")
_AWAITING_PATTERNS = ("awaiting_user_feedback", "awaiting user feedback", "awaiting-user-feedback")
_MISSING_SESSION_PATTERNS = ("missing session id", "missing session_id", "without session id", "no session id")
_DUPLICATE_BRANCH_PATTERNS = (
    "duplicate branch",
    "branch already exists",
    "head ref already exists",
    "duplicate head",
)
_PUSH_REJECTION_PATTERNS = ("push rejected", "failed to push", "non-fast-forward", "remote rejected")


def _root_for_dispatch(tasks_path: Path | None = None) -> Path:
    if os.environ.get("LIMEN_ROOT"):
        return Path(os.environ["LIMEN_ROOT"]).expanduser().resolve()
    if tasks_path is not None:
        try:
            path = tasks_path.expanduser().resolve()
        except OSError:
            path = tasks_path.expanduser()
        return path.parent if path.name == "tasks.yaml" else path
    return Path.cwd()


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _parse_iso_timestamp(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_json_stdout(stdout: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _short_proc_output(proc: subprocess.CompletedProcess[str] | None, limit: int = 500) -> str:
    if proc is None:
        return ""
    text = (proc.stdout or proc.stderr or "").strip()
    return f"{text[:limit]}...[truncated]" if len(text) > limit else text


def _first_command(payload: dict[str, Any]) -> str:
    commands = payload.get("next_commands") if isinstance(payload.get("next_commands"), list) else []
    return str(commands[0]) if commands else ""


def _run_handoff_relay(root: Path, *, refresh: bool) -> dict[str, Any]:
    script = root / "scripts" / "handoff-relay.py"
    result: dict[str, Any] = {
        "path": str(root / "logs" / "handoff.json"),
        "refreshed": False,
        "refresh_returncode": None,
        "refresh_output": "",
        "check_returncode": 1,
        "check_output": "",
        "ok": False,
    }
    if not script.exists():
        result["check_output"] = f"missing {script}"
        return result
    refresh_proc: subprocess.CompletedProcess[str] | None = None
    if refresh:
        try:
            refresh_proc = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=max(1, _env_int("LIMEN_HANDOFF_RELAY_TIMEOUT", 30)),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result.update(
                {
                    "refreshed": True,
                    "refresh_returncode": 1,
                    "refresh_output": str(exc),
                    "check_output": str(exc),
                }
            )
            return result
    try:
        check_proc = subprocess.run(
            [sys.executable, str(script), "--check"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(1, _env_int("LIMEN_HANDOFF_RELAY_TIMEOUT", 30)),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.update(
            {
                "refreshed": bool(refresh),
                "refresh_returncode": refresh_proc.returncode if refresh_proc else None,
                "refresh_output": _short_proc_output(refresh_proc),
                "check_returncode": 1,
                "check_output": str(exc),
            }
        )
        return result
    result.update(
        {
            "refreshed": bool(refresh),
            "refresh_returncode": refresh_proc.returncode if refresh_proc else None,
            "refresh_output": _short_proc_output(refresh_proc),
            "check_returncode": check_proc.returncode,
            "check_output": _short_proc_output(check_proc),
            "ok": check_proc.returncode == 0,
        }
    )
    return result


def _handoff_next_action_source(root: Path) -> bool:
    handoff = _load_json_file(root / "logs" / "handoff.json")
    generated = _parse_iso_timestamp(handoff.get("generated"))
    if generated is None:
        return False
    max_age_min = _env_int("LIMEN_HANDOFF_MAX_AGE_MIN", 90)
    if (datetime.now(timezone.utc) - generated).total_seconds() > max(1, max_age_min) * 60:
        return False
    return isinstance(handoff.get("next_action"), dict)


def _prompt_batch_source(root: Path) -> bool:
    lifecycle = root / ".limen-private" / "session-corpus" / "lifecycle"
    index = _load_json_file(lifecycle / "prompt-batch-review-ledger.json")
    raw_coverage = index.get("coverage")
    coverage = raw_coverage if isinstance(raw_coverage, dict) else {}
    queue = index.get("review_queue") if isinstance(index.get("review_queue"), list) else []
    try:
        open_batches = int(coverage.get("open_review_batches") or 0)
    except (TypeError, ValueError):
        open_batches = 0
    return open_batches > 0 or bool(queue)


def _product_ledger_source(root: Path) -> bool:
    lifecycle = root / ".limen-private" / "session-corpus" / "lifecycle"
    ledger = _load_json_file(lifecycle / "product-ledger.json")
    return bool(ledger.get("next_unblocked")) if isinstance(ledger.get("next_unblocked"), list) else False


def _always_working_source(root: Path, tasks_path: Path | None) -> bool:
    lifecycle = root / ".limen-private" / "session-corpus" / "lifecycle"
    index = _load_json_file(lifecycle / "always-working.json")
    raw_items = index.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    if any(isinstance(item, dict) and item.get("assignment_packet") for item in items):
        return True
    if tasks_path is None:
        return False
    try:
        board = load_limen_file(tasks_path)
    except Exception:
        return False
    return any(task.status == "open" and str(task.id or "").startswith("AW-") for task in board.tasks)


def _explicit_task_source(tasks_path: Path | None, task_id: str | None) -> bool:
    if not task_id or tasks_path is None:
        return False
    try:
        board = load_limen_file(tasks_path)
    except Exception:
        return False
    task = next((candidate for candidate in board.tasks if candidate.id == task_id), None)
    if task is None:
        return False
    text = _task_search_text(task)
    has_owner = bool(task.repo or task.urls or "owner" in text)
    has_predicate = any(term in text for term in ("predicate", "verify", "test ", "pytest", "check ", "receipt target"))
    has_receipt = any(term in text for term in ("receipt", "pull/", " pr ", "github.com", "output", "owner"))
    if has_owner and has_predicate and has_receipt:
        return True
    return bool(
        os.environ.get("LIMEN_DISPATCH_TASK_OVERRIDE_REASON")
        and os.environ.get("LIMEN_DISPATCH_TASK_OVERRIDE_PREDICATE")
    )


def _next_action_sources(root: Path, tasks_path: Path | None, task_id: str | None) -> list[str]:
    if not _truthy_env("LIMEN_REQUIRE_NEXT_ACTION_SOURCE", True):
        return ["disabled"]
    sources: list[str] = []
    if _handoff_next_action_source(root):
        sources.append("handoff_relay")
    if _prompt_batch_source(root):
        sources.append("prompt_batch_queue")
    if _product_ledger_source(root):
        sources.append("product_ledger")
    if _always_working_source(root, tasks_path):
        sources.append("always_working_packet")
    if _explicit_task_source(tasks_path, task_id):
        sources.append("explicit_task_id")
    return sources


def _session_value_admission_gate(
    root: Path,
    *,
    tasks_path: Path | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    explicit_source = _explicit_task_source(
        tasks_path or Path(os.environ.get("LIMEN_TASKS", root / "tasks.yaml")), task_id
    )
    if explicit_source:
        return {"allow": True, "exit_code": 0, "action": "explicit_task_id", "skipped": True}
    if not _truthy_env("LIMEN_SESSION_VALUE_GATE", True):
        return {"allow": True, "exit_code": 0, "action": "disabled", "skipped": True}
    script = root / "scripts" / "session-value-review.py"
    hours = os.environ.get(
        "LIMEN_VALUE_GATE_HOURS",
        os.environ.get("LIMEN_ASYNC_VALUE_GATE_HOURS", _DISPATCH_ADMISSION_GATE_HOURS),
    )
    command = f"python3 scripts/session-value-review.py --gate --hours {hours} --no-record-gate"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--gate", "--hours", hours, "--no-record-gate"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(1, _env_int("LIMEN_VALUE_GATE_TIMEOUT", _env_int("LIMEN_ASYNC_VALUE_GATE_TIMEOUT", 90))),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "allow": False,
            "exit_code": 20,
            "action": "session_value_unavailable",
            "reason": f"session value gate unavailable: {exc}",
            "next_command": command,
            "output": str(exc),
        }
    gate = _parse_json_stdout(proc.stdout)
    gate["returncode"] = proc.returncode
    gate["output"] = _short_proc_output(proc)
    gate["next_command"] = _first_command(gate)
    if proc.returncode == 0:
        gate["allow"] = True
        return gate
    gate["allow"] = False
    if not gate.get("reason"):
        gate["reason"] = (proc.stderr or proc.stdout or "session value gate blocked dispatch").strip()
    if not gate.get("next_command"):
        gate["next_command"] = command
    return gate


def dispatch_admission_check(
    tasks_path: Path | None = None,
    *,
    task_id: str | None = None,
    refresh_handoff: bool = True,
) -> dict[str, Any]:
    """Fail-closed dispatch admission shared by every worker launch path."""
    root = _root_for_dispatch(tasks_path)
    tasks_path = tasks_path or Path(os.environ.get("LIMEN_TASKS", root / "tasks.yaml"))
    result: dict[str, Any] = {
        "policy": _DISPATCH_ADMISSION_POLICY,
        "allow": True,
        "dispatch_allowed": True,
        "status": "allowed",
        "exit_code": 0,
        "reason": "dispatch admission allowed",
        "next_command": "",
        "sources": [],
    }
    pause_marker = root / "logs" / "AUTONOMY_PAUSED"
    if pause_marker.exists() and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
        try:
            recorded_reason = " ".join(
                line.strip() for line in pause_marker.read_text(encoding="utf-8").splitlines() if line.strip()
            )[:500]
        except OSError:
            recorded_reason = "autonomy pause marker is present"
        result.update(
            {
                "allow": False,
                "dispatch_allowed": False,
                "status": "blocked",
                "exit_code": 10,
                "reason": recorded_reason or "autonomy pause marker is present",
                "next_command": f"remove {pause_marker} only after its recorded release predicate is satisfied",
                "sources": ["autonomy_pause"],
            }
        )
        return result
    if not _truthy_env("LIMEN_DISPATCH_ADMISSION", True):
        result.update({"reason": "dispatch admission disabled by LIMEN_DISPATCH_ADMISSION", "sources": ["disabled"]})
        return result

    if _truthy_env("LIMEN_REQUIRE_HANDOFF", True):
        handoff = _run_handoff_relay(root, refresh=refresh_handoff)
        result["handoff"] = handoff
        if not handoff.get("ok"):
            result.update(
                {
                    "allow": False,
                    "dispatch_allowed": False,
                    "status": "alert",
                    "exit_code": 20,
                    "reason": "handoff relay check failed; refresh handoff before launching workers",
                    "next_command": "python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check",
                }
            )
            return result

    value_gate = _session_value_admission_gate(root, tasks_path=tasks_path, task_id=task_id)
    result["value_gate"] = value_gate
    gate_rc = int(value_gate.get("returncode", value_gate.get("exit_code", 0)) or 0)
    if not value_gate.get("allow", gate_rc == 0):
        status = "blocked" if gate_rc == 10 else "alert"
        result.update(
            {
                "allow": False,
                "dispatch_allowed": False,
                "status": status,
                "exit_code": 10 if gate_rc == 10 else 20,
                "reason": str(
                    value_gate.get("reason")
                    or (
                        "session value gate requested a lane switch before generic dispatch"
                        if gate_rc == 10
                        else "session value gate stopped dispatch"
                    )
                ),
                "next_command": str(value_gate.get("next_command") or ""),
            }
        )
        return result

    sources = _next_action_sources(root, tasks_path, task_id)
    result["sources"] = sources
    if not sources:
        result.update(
            {
                "allow": False,
                "dispatch_allowed": False,
                "status": "blocked",
                "exit_code": 10,
                "reason": (
                    "no concrete next-action source "
                    "(handoff relay, prompt batch, product ledger, always-working packet, or explicit task id)"
                ),
                "next_command": "python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check",
            }
        )
        return result

    result["reason"] = f"dispatch admission allowed via {', '.join(sources)}"
    result["next_command"] = str(value_gate.get("next_command") or "")
    return result


def print_dispatch_admission_block(prefix: str, admission: dict[str, Any]) -> None:
    action = ""
    value_gate = admission.get("value_gate")
    if isinstance(value_gate, dict):
        action = str(value_gate.get("action") or "")
    label = action or str(admission.get("status") or admission.get("exit_code") or "blocked")
    print(f"{prefix}: dispatch admission blocked ({label})")
    reason = str(admission.get("reason") or "").strip()
    if reason:
        print(f"{prefix}: reason: {reason[:500]}")
    next_command = str(admission.get("next_command") or "").strip()
    if next_command:
        print(f"{prefix}: next command: {next_command}")


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


def _has_pr_open_transition(task: Task) -> bool:
    """True once a task has recorded a durable open-PR receipt.

    Open PRs are not terminal like `done`, but they are durable work receipts. A later stale
    local no-op result must not demote the task or invite duplicate dispatch against the same
    owner repo.
    """
    return any(
        str(entry.status or "") == "pr_open"
        or (str(entry.status or "") == "dispatched" and "/pull/" in str(entry.session_id or "").lower())
        for entry in (task.dispatch_log or [])
    )


def _restore_pr_open_status(
    task: Task,
    now: datetime,
    *,
    agent: str = "limen",
    session_id: str = "pr-open-lifecycle-guard",
    output: str = "dispatch result ignored because this task already recorded an open PR",
) -> bool:
    """Keep an open-PR task out of no-op/failed churn."""
    if not _has_pr_open_transition(task):
        return False
    if task.status != "dispatched":
        task.status = "dispatched"
    task.updated = now
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent=agent,
            session_id=session_id,
            status="dispatched",
            output=output,
        )
    )
    return True


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
    if _has_done_transition(task) or _has_pr_open_transition(task):
        return False
    return "needs-human" not in (task.labels or [])


def _entry_text(entry: DispatchLogEntry) -> str:
    return " ".join(
        str(part or "")
        for part in (
            entry.status,
            entry.route_to,
            entry.session_id,
            entry.output,
            entry.agent,
        )
    ).lower()


def _entry_matches(entry: DispatchLogEntry, patterns: tuple[str, ...]) -> bool:
    text = _entry_text(entry)
    return any(pattern in text for pattern in patterns)


def _outcome_entries(task: Task) -> list[DispatchLogEntry]:
    skip = {"dispatched", "in_progress", "open"}
    return [
        entry
        for entry in (task.dispatch_log or [])
        if str(entry.status or "") not in skip
        or bool(getattr(entry, "route_to", None))
        or _entry_matches(entry, ("failed", "no-op", "timeout", "rate limit"))
    ]


def _has_fresh_owner_state(task: Task) -> bool:
    for entry in (task.dispatch_log or [])[-4:]:
        text = _entry_text(entry)
        if str(entry.status or "") in {"done", "pr_open"} or (
            str(entry.status or "") == "dispatched" and "/pull/" in str(entry.session_id or "").lower()
        ):
            return True
        if "pull/" in text or "new head" in text or "checks green" in text or "check passed" in text:
            return True
    return False


def chronic_dispatch_reason(task: Task) -> str | None:
    """Classify reopened tasks that have already shown repeated non-progress."""
    labels = {str(label).strip().lower() for label in (task.labels or [])}
    if labels & _CHRONIC_EXEMPT_LABELS or _has_fresh_owner_state(task):
        return None
    outcomes = _outcome_entries(task)
    last_two = outcomes[-2:]
    if len(last_two) < 2:
        return None
    if all(_entry_matches(entry, _NOOP_PATTERNS) for entry in last_two):
        return "repeated-no-op"
    if all(_entry_matches(entry, _AWAITING_PATTERNS) for entry in last_two):
        return "awaiting-user-feedback-loop"
    if all(_entry_matches(entry, _MISSING_SESSION_PATTERNS) for entry in last_two):
        return "missing-session-id-loop"
    if all(_entry_matches(entry, _DUPLICATE_BRANCH_PATTERNS) for entry in last_two):
        return "duplicate-branch-loop"
    if all(_entry_matches(entry, _PUSH_REJECTION_PATTERNS) for entry in last_two):
        return "push-rejection-loop"
    missing_session_entries = [
        entry
        for entry in last_two
        if not str(entry.session_id or "").strip()
        or str(entry.session_id or "").strip().lower() in {"none", "null", "undefined", "undefined#undefined"}
    ]
    if len(missing_session_entries) == 2:
        return "missing-session-id-loop"
    return None


_ACTIVE_SUPERSEDER_STATUSES = {"open", "dispatched", "in_progress", "needs_human", "failed_blocked"}


def _superseded_by_rebase_task(task: Task, tasks_by_id: dict[str, Task]) -> bool:
    """A live conflict/rebase task is the correct route before an older CI-fix sibling.

    Self-heal task IDs are stable by kind: HEAL-cifix-<repo-slug>-<pr> and
    HEAL-rebase[-stale]-<repo-slug>-<pr>. If a PR changes from CI-red to conflicting,
    the corrected rebase ticket must win instead of the stale CI-fix ticket looping.
    """
    task_id = str(task.id or "")
    prefix = "HEAL-cifix-"
    if not task_id.startswith(prefix):
        return False
    suffix = task_id[len(prefix) :]
    for sibling_id in (f"HEAL-rebase-{suffix}", f"HEAL-rebase-stale-{suffix}"):
        sibling = tasks_by_id.get(sibling_id)
        if sibling is not None and str(sibling.status or "") in _ACTIVE_SUPERSEDER_STATUSES:
            return True
    return False


def _routine_generated_buildout(task: Task) -> bool:
    labels = set(task.labels or [])
    return "generated" in labels and "build-out" in labels


_VALUE_LABELS = {
    "financial",
    "low-burn-priority",
    "product",
    "revenue",
    "sell-ready",
    "value",
    "value-repo",
    "value-tier",
}
_VALUE_WORKSTREAMS = {"conductor", "financial", "product", "revenue"}
_LIFECYCLE_TERMS = {
    "always-working",
    "agy-scratch",
    "blocked",
    "blocker",
    "closeout",
    "corpus",
    "custody",
    "cvstos",
    "disk",
    "keeper",
    "lifecycle",
    "owner-blocker",
    "prompt",
    "prompt-batch",
    "prompt-packet",
    "reclaim",
    "record-keeper",
    "recordkeeper",
    "scratch",
    "session-lifecycle",
    "storage",
    "substrate",
    "tabularius",
    "ticket",
    "worktree",
    "worktree-lifecycle",
}
_LIFECYCLE_TEXT_TERMS = _LIFECYCLE_TERMS - {
    # These are meaningful as explicit labels/workstreams, but too broad inside repo slugs or
    # PR titles such as "conversation-corpus-engine" or "promptscope".
    "corpus",
    "prompt",
    "ticket",
}


def _normalize_repo_slug(repo: object) -> str:
    value = str(repo or "").strip()
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if value.startswith(prefix):
            value = value.removeprefix(prefix)
            break
    if value.endswith(".git"):
        value = value[:-4]
    return value.strip("/").lower()


def _value_tier_repos() -> set[str]:
    repos: set[str] = {r.strip() for r in os.environ.get("LIMEN_VALUE_REPOS", "").split(",") if r.strip()}
    fpath = os.environ.get(
        "LIMEN_VALUE_REPOS_FILE",
        str(Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "value-repos.json"),
    )
    try:
        data = json.loads(Path(fpath).read_text())
        for item in data.get("repos", []):
            repos.add(item if isinstance(item, str) else (item.get("repo") or ""))
    except Exception:
        pass
    repos.discard("")
    return {_normalize_repo_slug(repo) for repo in repos}


def _task_search_text(task: Task) -> str:
    parts = [
        task.id,
        task.title,
        task.context,
        task.repo,
        task.workstream,
        task.type,
        " ".join(str(label) for label in (task.labels or [])),
        " ".join(str(url) for url in (task.urls or [])),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _dispatch_focus_bucket(task: Task, value_repos: set[str]) -> int:
    repo = _normalize_repo_slug(task.repo)
    labels = {str(label).strip().lower() for label in (task.labels or [])}
    workstream = str(task.workstream or "").strip().lower()
    if repo and repo in value_repos:
        return 0
    if labels & _VALUE_LABELS or workstream in _VALUE_WORKSTREAMS:
        return 0
    if str(task.id or "").startswith(("AW-", "REV-")):
        return 0
    if labels & _LIFECYCLE_TERMS or workstream in _LIFECYCLE_TERMS:
        return 0
    text = " ".join(
        str(part or "")
        for part in (
            task.id,
            task.title,
            task.context,
            task.type,
        )
    ).lower()
    if any(term in text for term in _LIFECYCLE_TEXT_TERMS):
        return 0
    return 1


def _value_gate_configured(value_repos: set[str]) -> bool:
    if os.environ.get("LIMEN_VALUE_GATE", "1") != "1":
        return False
    return bool(value_repos or os.environ.get("LIMEN_VALUE_GATE_STRICT") == "1")


def task_passes_value_gate(task: Task, value_repos: set[str] | None = None) -> bool:
    value_repos = value_repos if value_repos is not None else _value_tier_repos()
    if not _value_gate_configured(value_repos):
        return True
    return _dispatch_focus_bucket(task, value_repos) == 0


def sort_value_gate_candidates(
    candidates: list[Task],
    value_repos: set[str] | None = None,
    *,
    disk_pressure: bool = False,
) -> list[Task]:
    value_repos = value_repos if value_repos is not None else _value_tier_repos()
    gated = [task for task in candidates if task_passes_value_gate(task, value_repos)]
    if not _value_gate_configured(value_repos):
        gated = list(candidates)
    if disk_pressure:
        focused = [task for task in gated if _dispatch_focus_bucket(task, value_repos) == 0]
        if focused:
            gated = focused
    return sorted(
        gated,
        key=lambda task: (
            _dispatch_focus_bucket(task, value_repos),
            _PRIORITY_ORDER.get(task.priority, 99),
            str(task.id),
        ),
    )


def _routine_generated_buildout_allowed(task: Task) -> bool:
    if not _routine_generated_buildout(task):
        return True
    allowed = _value_tier_repos()
    return bool(task.repo and task.repo in allowed)


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
_MODEL_SELECTION_RECEIPTS: dict[str, dict[str, Any]] = {}


def _record_model_selection(
    task: Task | None,
    *,
    profile: dict[str, object],
    selected_model: str | None,
    source: str,
    fingerprint: str | None = None,
) -> None:
    if task is None:
        return
    _MODEL_SELECTION_RECEIPTS[task.id] = {
        "execution_profile": profile,
        "selected_model": selected_model,
        "selection_source": source,
        "catalog_hash": fingerprint,
    }


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


def _verification_discipline() -> str:
    return (
        "--- VERIFICATION DISCIPLINE ---\n"
        "Use the narrowest predicate that proves this task: inspect the failing CI check, "
        "run the specific test/lint/typecheck/build it names, or run a focused local equivalent. "
        "For GitHub PR repair, inspect the PR's actual statusCheckRollup and workflow list; do not "
        "assume a Limen-owned workflow file such as limen-agent.yml exists in the target repo. "
        "Do not run scripts/verify-whole.sh, the full pytest suite, or broad commands like "
        "`python -m pytest web/api/tests cli/tests -q` unless this task explicitly requires full "
        "repo readiness or the narrow predicate proves the broader gate is the only relevant failure. "
        "Record the exact predicate you ran and its result."
    )


def _value_gate_discipline(task: Task) -> str:
    try:
        value_repos = _value_tier_repos()
    except Exception:
        value_repos = set()
    repo = task.repo or ""
    normalized_repo = _normalize_repo_slug(repo)
    labels = task.labels or []
    urls = task.urls or []
    depends_on = task.depends_on or []
    return (
        "--- VALUE GATE ---\n"
        "Before editing, state whether this is worth doing now and defend it with the stats below. "
        "Proceed only when the work is value-tier, prompt/lifecycle, blocker-clearing, or explicitly "
        "queued revenue/owner work. Do not do generic busywork just because a task exists.\n"
        "For a value-tier repo, prefer the path that creates public proof, discoverability, warm leads, "
        "or revenue access; work on internal CI/rebase/test churn only when it directly unblocks that "
        "outward-facing path.\n"
        "Public GitHub activity must not become commit-only churn. Use "
        "`python3 scripts/github-contribution-balance.py --login 4444J99 --json` when choosing the "
        "next public action; target <=60% commits, >=15% issues, >=15% PRs, and >=10% reviews. "
        "If the mix is out of balance, prefer substantive PR review, real issue criteria, and PR "
        "packaging before more direct commits.\n"
        "Pain-point fixes should become reusable public surfaces when safe: keep private data in a "
        "private adapter or redacted fixture, then publish the method, CLI, workflow, demo, or owner "
        "receipt that lets the same fix attract users, leads, or revenue.\n"
        f"Stats: priority={task.priority}; budget_cost={task.budget_cost}; "
        f"workstream={task.workstream or 'none'}; repo={repo or 'none'}; "
        f"repo_in_value_tier={str(normalized_repo in value_repos).lower()}; "
        f"value_tier_repo_count={len(value_repos)}; labels={len(labels)}; urls={len(urls)}; "
        f"depends_on={len(depends_on)}.\n"
        "If the stats do not justify the work, record the smallest owner route/blocker and stop "
        "without broad repo churn."
    )


def _build_prompt(task: Task, task_first: bool = False) -> str:
    parts = [f"Complete task {task.id}: {task.title}"]
    if task.repo:
        parts.append(f" in repository {task.repo}")
    if task.context:
        parts.append(f"\nContext: {task.context}")
    if task.urls:
        parts.append(f"\nReferences: {', '.join(task.urls)}")
    pr_ref = _task_github_pr_ref(task)
    if pr_ref:
        parts.append(
            f"\nGitHub PR context: this task names {pr_ref[0]}#{pr_ref[1]}. "
            "For PR-fix/rebase tasks, inspect that PR before editing; when available, dispatch "
            "bases this isolated branch on the PR head and targets the repair PR back to that head."
        )
    body = f"{''.join(parts)}\n\n{_value_gate_discipline(task)}\n\n{_verification_discipline()}"
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
            timeout=max(1, _env_int("LIMEN_DISPATCH_TIMEOUT", 600)),
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
                print(f"  FAILED jules dispatch {task.id}: no session id in CLI output")
                if result.stdout:
                    print(f"    stdout: {result.stdout[:500]}")
                return False
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
    repo = _remote_repo_arg(task)
    if repo is None:
        msg = f"remote lane needs GitHub owner/repo, got {task.repo or '(no repo)'}"
        if dry_run:
            print(f"  would BLOCK {task.id}: {msg}")
            return True
        print(f"  BLOCKED {task.id}: {msg}")
        return _blocked_result(msg)
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
    workflow = os.environ.get("LIMEN_GITHUB_ACTIONS_WORKFLOW", DEFAULT_GITHUB_ACTIONS_WORKFLOW)
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
    if reason := paid_service_block_reason(task):
        if dry_run:
            print(f"  would BLOCK {task.id}: {reason}")
            return True
        print(f"  BLOCKED {task.id}: {reason}")
        return _blocked_result(reason)
    requested_profile = execution_profile_for(task)
    plan_accepted = _claude_fable_acceptance_present()
    profile = effective_profile(requested_profile, plan_accepted=plan_accepted)
    router_override = os.environ.get("LIMEN_WARP_MODEL_OVERRIDE")
    router = None
    if router_override:
        oz_vendor = census.by_name("oz")
        router = discover_warp_override(
            oz_vendor.binary if oz_vendor is not None else "oz",
            override=router_override,
            timeout=max(1, _env_int("LIMEN_WARP_CATALOG_TIMEOUT", 30)),
        )
    if router_override and not router:
        reason = "configured Warp model override is absent from the live Oz catalog"
        if dry_run:
            print(f"  would BLOCK {task.id}: {reason}")
            return True
        print(f"  BLOCKED {task.id}: {reason}")
        _record_model_selection(
            task,
            profile=profile.as_dict(),
            selected_model=None,
            source="warp_override_missing",
        )
        return _blocked_result(reason)
    _record_model_selection(
        task,
        profile=profile.as_dict(),
        selected_model=router,
        source="warp_override" if router else "warp_auto",
    )
    gh = os.environ.get("LIMEN_WARP_OZ_BIN", "gh")
    workflow = os.environ.get("LIMEN_WARP_OZ_WORKFLOW", "limen-warp-oz.yml")
    dispatch_repo = os.environ.get("LIMEN_WARP_OZ_REPO", "organvm/limen")
    intent = (
        "Planning only: return a build packet and do not implement."
        if requested_profile.planning_only and plan_accepted
        else "Execute the task and verify the narrow acceptance predicate."
    )
    prompt = (
        f"{_build_prompt(task)}\n\n--- EXECUTION INTENT ---\n"
        f"profile: {profile.as_json()}\n{intent}\n"
        "Select capabilities from the live provider catalog; do not assume a named underlying model."
    )
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
        f"execution_profile={profile.as_json()}",
        "-f",
        f"prompt={prompt}",
    ]
    if router:
        cmd.extend(["-f", f"model={router}"])
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
def _opencode_model(task: Task | None = None) -> str | None:
    """Select a reachable OpenCode model by live capabilities, never by name."""

    binary = os.environ.get("LIMEN_OPENCODE_BIN", "opencode")
    models = discover_opencode_models(
        binary,
        timeout=max(1, _env_int("LIMEN_OPENCODE_CATALOG_TIMEOUT", 30)),
    )
    requested = execution_profile_for(task)
    profile = effective_profile(requested, plan_accepted=_claude_fable_acceptance_present())
    override = os.environ.get("LIMEN_OPENCODE_MODEL")
    if override:
        selected = next((model for model in models if model.model_id == override and model.satisfies(profile)), None)
        _record_model_selection(
            task,
            profile=profile.as_dict(),
            selected_model=selected.model_id if selected else None,
            source="opencode_override" if selected else "opencode_override_missing",
            fingerprint=catalog_hash(models),
        )
        return selected.model_id if selected else None
    selected = select_opencode_model(models, profile)
    _record_model_selection(
        task,
        profile=profile.as_dict(),
        selected_model=selected.model_id if selected else None,
        source="opencode_live_catalog" if selected else "opencode_no_capable_model",
        fingerprint=catalog_hash(models),
    )
    return selected.model_id if selected else None


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
        model = _opencode_model(task)
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
# DERIVED from the census register (the single vendor umbrella) — no longer a hand-typed copy.
# census owns the order literal (_LANE_CASCADE_ORDER); test_census still asserts the two are equal.
_LANE_CASCADE = census.lane_cascade()
_NOOP = "__noop__"  # agent ran but produced no diff


def _lane_cascade() -> list[str]:
    selector = os.environ.get("LIMEN_DISPATCH_LANES")
    try:
        down = _down_lanes()
    except Exception:
        down = set()
    if not selector:
        try:
            live = set(select_lanes("auto", down_lanes=down))
        except Exception:
            live = set()
        if live:
            return [agent for agent in _LANE_CASCADE if agent in live and agent not in down]
        return [agent for agent in _LANE_CASCADE if agent not in down]
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


def _fallback_dispatch_lane(*, exclude: set[str] | None = None) -> str | None:
    excluded = exclude or set()
    cascade = _lane_cascade()
    for agent in cascade:
        if agent not in excluded and agent in _LOCAL_AGENTS:
            return agent
    for agent in cascade:
        if agent not in excluded:
            return agent
    return "any"


_REMOTE_SERVICE_LANES = {"jules", "copilot", "github_actions", "warp", "oz"}


def _cascade_or_requeue(agent: str) -> str:
    return _next_lane(agent) or _fallback_dispatch_lane() or "any"


def _local_floor_allowed_for_task(task: Task) -> bool:
    try:
        if not local_floor_enabled():
            return False
        if not task.repo:
            return False
        classes = _task_classes(task)
        if not classes & local_floor_classes():
            return False
        if classes & (_claude_opus_classes() | _claude_fable_classes()):
            return False
        return ollama_model() is not None
    except Exception:
        return False


def _remote_service_failure_lane(task: Task, agent: str) -> str:
    floor_allowed = _local_floor_allowed_for_task(task)
    next_lane = _next_lane(agent)
    if next_lane and (next_lane != "ollama" or floor_allowed):
        return next_lane
    fallback = _fallback_dispatch_lane(exclude=set() if floor_allowed else {"ollama"})
    return fallback or ("ollama" if floor_allowed else "any")


def _agy_live_root_registry_task(task: Task) -> bool:
    """Agy has been observed ignoring cwd for registry-discovery prompts.

    Discovery tasks that promote an external repo by editing Limen registry files
    (`value-repos.json`, `DISCOVERY.md`) must not run on Agy/Antigravity until
    that CLI can be proven to honor the isolated worktree.
    """
    fields = [task.id or "", task.title or "", task.context or "", *(task.urls or [])]
    text = "\n".join(str(field) for field in fields).lower()
    return str(task.id or "").startswith("DISCOVER-") and ("value-repos.json" in text or "discovery.md" in text)


def _limen_registry_promotion_task(task: Task) -> bool:
    """Registry promotion edits Limen-owned files, so local checkout lanes need a bridge first."""
    fields = [task.id or "", task.title or "", task.context or "", *(task.urls or [])]
    text = "\n".join(str(field) for field in fields).lower()
    return str(task.id or "").startswith("DISCOVER-") and "value-repos.json" in text


def _limen_repo_task(task: Task) -> bool:
    """Limen-root PR repair has repeatedly triggered prohibited broad local checks."""
    return str(task.repo or "").lower() == "organvm/limen"


def _organvm_engine_task(task: Task) -> bool:
    """Claude has repeatedly used full pytest on organvm-engine PR repair tasks."""
    return str(task.repo or "").lower() == "organvm/organvm-engine"


def _agent_timed_out_on_task(agent: str, task: Task) -> bool:
    return any(
        canonical_agent(str(entry.agent or "")) == agent
        and (
            str(entry.status or "").startswith("timeout->")
            or (bool(getattr(entry, "route_to", None)) and "timeout" in str(entry.output or "").lower())
        )
        for entry in (task.dispatch_log or [])
    )


def agent_can_run_task(agent: str, task: Task) -> bool:
    agent = canonical_agent(agent)
    if _agent_timed_out_on_task(agent, task):
        return False
    if agent == "ollama" and not _local_floor_allowed_for_task(task):
        return False
    if agent in _LOCAL_AGENTS and _limen_registry_promotion_task(task):
        return False
    if agent in {"agy", "antigravity"} and (_agy_live_root_registry_task(task) or _limen_repo_task(task)):
        return False
    if agent in {"codex", "claude"} and _limen_repo_task(task):
        return False
    if agent == "claude" and _organvm_engine_task(task):
        return False
    return True


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
_FAILED_BLOCKED_PREFIX = "__failed_blocked__:"
_RATE_PATTERNS = re.compile(
    r"rate.?limit|quota|usage limit|too many requests|\b429\b|\b529\b|"
    r"resource.?exhausted|overloaded|insufficient_quota|throttl|out of (?:tokens|credits)",
    re.IGNORECASE,
)


def _is_rate_limited(text: str) -> bool:
    return bool(_RATE_PATTERNS.search(text or ""))


def _blocked_result(reason: str) -> str:
    return _FAILED_BLOCKED_PREFIX + " ".join((reason or "blocked").split())[:500]


def _is_blocked_result(result: bool | str) -> bool:
    return isinstance(result, str) and result.startswith(_FAILED_BLOCKED_PREFIX)


def _blocked_reason(result: bool | str) -> str:
    if not _is_blocked_result(result):
        return ""
    return str(result)[len(_FAILED_BLOCKED_PREFIX) :]


_REPO_UNAVAILABLE_PATTERNS = re.compile(
    r"could not resolve to a repository|repository not found|http 404|not found",
    re.IGNORECASE,
)


def _repo_unavailable_reason(repo: str | None) -> str | None:
    if not repo or "/" not in repo:
        return "task has no dispatchable repo"
    try:
        result = _run_capture(
            ["gh", "repo", "view", repo, "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return None
    blob = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
    if _REPO_UNAVAILABLE_PATTERNS.search(blob):
        return f"repo unavailable: {repo}; {blob[:240]}"
    return None


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


_GITHUB_REMOTE_RE = re.compile(r"(?:github\.com[:/])([^/\s]+)/([^/\s]+?)(?:\.git)?$")


def _path_like_repo(repo: str | None) -> bool:
    if not repo:
        return False
    return repo.startswith(("~/", "/", "./", "../"))


def _local_repo_path(repo: str | None) -> Path | None:
    if not _path_like_repo(repo):
        return None
    path = Path(str(repo)).expanduser()
    if (path / ".git").exists():
        return path
    return None


def _github_slug_from_remote(remote: str | None) -> str | None:
    match = _GITHUB_REMOTE_RE.search((remote or "").strip())
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _github_slug_from_local_repo(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return _github_slug_from_remote(result.stdout)


def _remote_repo_arg(task: Task) -> str | None:
    """Return a GitHub owner/repo slug for remote service lanes.

    Remote lanes cannot clone `~/Workspace/...` paths. Local-path tasks may still name a real repo;
    derive the slug from origin so the cloud lane receives a valid repository argument.
    """
    repo = task.repo or os.environ.get("LIMEN_ROOT", ".")
    if _path_like_repo(repo):
        path = _local_repo_path(repo)
        return _github_slug_from_local_repo(path) if path is not None else None
    return repo if "/" in repo else None


def _resolve_repo_dir(task: Task) -> Path | None:
    """Find a local git checkout of task.repo (owner/name) across known roots.

    Falls back to matching by repo name under any org dir (the local checkout's
    org can differ from the GitHub remote org, e.g. local organvm/ vs remote
    a-organvm/), disambiguating by the git remote when multiple names collide.
    """
    if not task.repo:
        return None
    local_path = _local_repo_path(task.repo)
    if local_path is not None:
        return local_path
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
    if _path_like_repo(task.repo):
        return _resolve_repo_dir(task)
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
_ISOLATION_ROOT = default_worktrees_root()
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


def _git(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


_GIT_CONFIG_LOCK_RE = re.compile(r"could not lock config file|config\.lock|File exists", re.IGNORECASE)


def _git_plumbing(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run a short Git plumbing command with retry for transient parent-repo config locks."""
    result = _git(args, cwd, timeout=timeout)
    for attempt in range(4):
        if result.returncode == 0 or not _GIT_CONFIG_LOCK_RE.search(result.stderr or ""):
            return result
        time.sleep(0.5 * (attempt + 1))
        result = _git(args, cwd, timeout=timeout)
    return result


def _default_branch(repo_dir: Path) -> str:
    """Best-effort detection of origin's default branch (main/master/…)."""
    r = _git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], repo_dir)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().rsplit("/", 1)[-1]
    for cand in ("main", "master"):
        if _git(["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{cand}"], repo_dir).returncode == 0:
            return cand
    return "main"


_GITHUB_PR_URL_RE = re.compile(
    r"github\.com[:/](?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/(?:pull|pulls)/(?P<num>\d+)",
    re.IGNORECASE,
)
_GITHUB_REPO_PR_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<num>\d+)\b",
    re.IGNORECASE,
)


def _task_github_pr_ref(task: Task) -> tuple[str, int] | None:
    """Return the GitHub ``owner/repo#number`` a task clearly names, if it matches task.repo."""
    task_repo = _normalize_repo_slug(task.repo)
    if task_repo and "/" not in task_repo:
        task_repo = ""
    texts: list[str] = []
    texts.extend(str(url or "") for url in (task.urls or []))
    texts.extend([str(task.title or ""), str(task.context or "")])
    for text in texts:
        for regex in (_GITHUB_PR_URL_RE, _GITHUB_REPO_PR_RE):
            for match in regex.finditer(text):
                repo = _normalize_repo_slug(match.group("repo"))
                if task_repo and repo != task_repo:
                    continue
                try:
                    return repo, int(match.group("num"))
                except ValueError:
                    continue
    return None


def _same_repo_pr_head_for_task(task: Task) -> dict[str, str] | None:
    """Resolve same-repo PR tasks to their head branch, else fail open to default branch."""
    ref = _task_github_pr_ref(task)
    if not ref:
        return None
    repo, number = ref
    try:
        run = _run_capture(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--repo",
                repo,
                "--json",
                "headRefName,headRepositoryOwner,baseRefName,state",
            ],
            timeout=max(1, _env_int("LIMEN_PR_CONTEXT_TIMEOUT", 20)),
        )
    except Exception:
        return None
    if run.returncode != 0:
        return None
    try:
        data = json.loads(run.stdout or "{}")
    except ValueError:
        return None
    if str(data.get("state") or "").upper() != "OPEN":
        return None
    head_ref = str(data.get("headRefName") or "").strip()
    if not head_ref:
        return None
    owner_raw = data.get("headRepositoryOwner") or {}
    head_owner = owner_raw.get("login") if isinstance(owner_raw, dict) else str(owner_raw or "")
    repo_owner = repo.split("/", 1)[0]
    if head_owner and head_owner.lower() != repo_owner.lower():
        return None
    return {
        "repo": repo,
        "number": str(number),
        "head_ref": head_ref,
        "base_ref": str(data.get("baseRefName") or ""),
    }


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
            elif src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
                carried += 1
            elif not src.exists() and (dst.exists() or dst.is_symlink()):  # agy deleted it → mirror the deletion
                if dst.is_dir() and not dst.is_symlink():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
                carried += 1
        print(f"  agy-bridge {task.id}: carried {carried} changed path(s) from scratch '{best.name}' → worktree")
    except Exception as e:
        print(f"  agy-bridge {task.id}: skipped ({str(e)[:80]})")


def _lane_run_env(agent: str, wt: Path | None = None) -> dict[str, str]:
    run_env = os.environ.copy()
    if wt is not None:
        live_root = os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))
        run_env["LIMEN_LIVE_ROOT"] = live_root
        run_env["LIMEN_ROOT"] = str(wt)
        run_env["LIMEN_TASKS"] = str(wt / "tasks.yaml")
        run_env["PWD"] = str(wt)
        run_env["OLDPWD"] = live_root
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
        run_env.pop("ANTHROPIC_API_KEY", None)
        if fleet_token:
            run_env["ANTHROPIC_AUTH_TOKEN"] = fleet_token
        elif fleet_key:
            run_env["ANTHROPIC_API_KEY"] = fleet_key
        run_env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    return run_env


def _failed_agent_result(agent: str, task: Task, run: subprocess.CompletedProcess[str]) -> bool | str:
    blob = (run.stderr or "") + (run.stdout or "")
    if _is_rate_limited(blob):
        print(f"  RATE-LIMIT {agent} on {task.id}: real limit hit (token/rate) — cooling lane, cascading")
        return _RATELIMIT
    print(f"  FAILED agent {agent} on {task.id} ({run.returncode}): {run.stderr.strip()[:300]}")
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
    run_env = _lane_run_env(agent, wt)
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
    if agent == "ollama":
        # `ollama run` answers on stdout and cannot edit files — without an artifact the run
        # hits the no-changes trap in _commit_isolated_changes and false-fails as _NOOP.
        # Persist the report so the commit -> PR -> ledger-grading path sees the real work.
        out = (run.stdout or "").strip()
        if out:
            reports = wt / "reports"
            reports.mkdir(exist_ok=True)
            (reports / f"{task.id}.md").write_text(out + "\n")
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


def _existing_pr_url(pr_head: dict[str, str]) -> str:
    return f"https://github.com/{pr_head['repo']}/pull/{pr_head['number']}"


def _push_existing_pr_head(task: Task, wt: Path, pr_head: dict[str, str]) -> bool:
    head_ref = pr_head["head_ref"]
    p = _git(["push", "origin", f"HEAD:{head_ref}"], wt, timeout=300)
    if p.returncode != 0:
        print(f"  FAILED push existing PR head {task.id}: {p.stderr.strip()[:300]}")
        return False
    print(f"  updated existing PR head {task.id}: {pr_head['repo']}#{pr_head['number']} ({head_ref})")
    return True


def _record_worktree_birth(
    task: Task,
    wt: Path,
    branch: str,
    checkout_ref: str,
    pr_base: str,
    *,
    existing_pr: bool,
) -> None:
    """Record the remote owner contract for a new disposable checkout outside the work tree."""
    gitdir = _git(["rev-parse", "--git-dir"], wt)
    if gitdir.returncode != 0 or not gitdir.stdout.strip():
        return
    gitdir_path = Path(gitdir.stdout.strip())
    if not gitdir_path.is_absolute():
        gitdir_path = wt / gitdir_path
    payload = {
        "schema": "limen.worktree_birth.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task.id,
        "repo": task.repo,
        "root": str(wt),
        "checkout_ref": checkout_ref,
        "local_branch": branch,
        "remote_branch": branch,
        "pr_base": pr_base,
        "existing_pr": existing_pr,
        "done_predicate": "remote branch pushed and PR/open-PR receipt recorded",
        "cleanup_owner": "scripts/reclaim-worktrees.py + docs/worktree-reclaim-acceptance.jsonl",
    }
    try:
        gitdir_path.mkdir(parents=True, exist_ok=True)
        (gitdir_path / "limen-worktree-birth.json").write_text(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        return
    _record_worktree_lifecycle(task, wt, branch, "created", "remote-receipt-required", "not-run", False)


def _unpreserved_work_reason(wt: Path, base_ref: str) -> str:
    """Return why reclaiming an isolated worktree needs preservation first.

    Empty/no-op worktrees are cleanup candidates, but physical removal still belongs to the
    receipt-backed reclaim/reap organs. Dirty worktrees, unreadable worktrees, or branches with
    commits not proven on the remote/base ref must stay for the worktree preservation lane.
    """
    status = _git(["status", "--porcelain", "-z"], wt)
    if status.returncode != 0:
        return "status-unreadable"
    if status.stdout:
        return "dirty-working-tree"

    ahead = _git(["rev-list", "--count", f"{base_ref}..HEAD"], wt)
    if ahead.returncode != 0:
        return "ahead-check-unreadable"
    try:
        if int((ahead.stdout or "0").strip() or "0") > 0:
            return "unpushed-commits"
    except ValueError:
        return "ahead-check-unreadable"
    return ""


def _purge_generated_payloads(wt: Path) -> str:
    """Remove ignored/generated weight from a retained isolated worktree.

    Source and untracked non-ignored files are preserved. This is the lifecycle invariant that keeps
    retained checkouts from becoming 1-2 GiB roots just because an agent installed dependencies.
    """
    if not wt.exists():
        return "missing"
    clean = _git(["clean", "-Xdf", "--", *_GENERATED_CLEAN_PATHS], wt, timeout=180)
    if clean.returncode != 0:
        return f"failed:{(clean.stderr or clean.stdout).strip()[:160]}"
    removed = sum(1 for line in (clean.stdout or "").splitlines() if line.strip().startswith("Removing "))
    return f"removed:{removed}"


def _record_worktree_lifecycle(
    task: Task | None,
    wt: Path,
    branch: str,
    state: str,
    reason: str,
    generated_cleanup: str,
    pushed: bool,
) -> None:
    root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
    try:
        log = root / "logs" / "worktree-lifecycle.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "task_id": getattr(task, "id", None),
                        "repo": getattr(task, "repo", None),
                        "root": str(wt),
                        "branch": branch,
                        "state": state,
                        "reason": reason,
                        "pushed": pushed,
                        "generated_cleanup": generated_cleanup,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    except OSError:
        pass


def _cleanup_isolated_worktree(
    repo_dir: Path,
    wt: Path,
    branch: str,
    base_ref: str,
    pushed: bool,
    task: Task | None = None,
) -> None:
    """Classify isolated worktrees for later receipt-backed cleanup.

    This function intentionally does not remove roots or branch refs. Local deletion requires the
    shared archive/redaction acceptance ledgers consumed by reclaim-worktrees.py and
    reap-branches.py.
    """
    if not wt.exists():
        if pushed:
            print(
                f"  retained isolated branch {branch}; "
                "branch cleanup delegated to docs/branch-reap-acceptance.jsonl + reap-branches.py"
            )
            _record_worktree_lifecycle(task, wt, branch, "branch-retained", "worktree-missing", "missing", pushed)
        return

    reason = "" if pushed else _unpreserved_work_reason(wt, base_ref)
    generated_cleanup = _purge_generated_payloads(wt)
    if reason:
        print(f"  preserved isolated worktree {wt} for bridge ({reason}; branch {branch})")
        _record_worktree_lifecycle(task, wt, branch, "preserved", reason, generated_cleanup, pushed)
        return

    print(
        f"  retained isolated worktree {wt} ({'pushed' if pushed else 'clean-noop'}; branch {branch}); "
        f"generated cleanup {generated_cleanup}; "
        "cleanup delegated to docs/worktree-reclaim-acceptance.jsonl + reclaim-worktrees.py "
        "and docs/branch-reap-acceptance.jsonl + reap-branches.py"
    )
    _record_worktree_lifecycle(
        task,
        wt,
        branch,
        "retained",
        "pushed" if pushed else "clean-noop",
        generated_cleanup,
        pushed,
    )


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
        blocked = _repo_unavailable_reason(task.repo)
        if blocked:
            print(f"  BLOCKED {task.id}: {blocked}")
            return _blocked_result(blocked)
        repo_dir = _clone_repo(task)  # post-move: clone on demand so local lanes can work it
    if repo_dir is None:
        msg = f"no local checkout of {task.repo or '(no repo)'}"
        if dry_run:
            print(f"  would [{msg}; clone-on-demand then isolate]: →{binary}→PR")
            return True
        print(f"  SKIP {task.id}: {msg} — clone-on-demand failed")
        return False

    base = _default_branch(repo_dir)
    pr_head = _same_repo_pr_head_for_task(task)
    checkout_ref = f"origin/{base}"
    pr_base = base
    fetch_refspec: str | None = base
    if pr_head:
        head_ref = pr_head["head_ref"]
        checkout_ref = f"origin/{head_ref}"
        pr_base = head_ref
        fetch_refspec = f"+refs/heads/{head_ref}:refs/remotes/origin/{head_ref}"
    slug = re.sub(r"[^a-zA-Z0-9._/-]+", "-", task.id.lower())
    # Unique suffix: retries should not collide with stale local/remote refs. The add path still
    # retries because old no-op runs left many empty local branches behind.
    suffix = secrets.token_hex(4)
    branch = f"limen/{slug}-{suffix}"
    wt = _ISOLATION_ROOT / (re.sub(r"[^a-zA-Z0-9._-]+", "-", task.id.lower()) + "-" + suffix)
    agent_args = _agent_argv(agent, task)
    prompt = _build_prompt(task)
    if os.environ.get("LIMEN_ISOLATION_PROMPT_GUARD", "1") == "1":
        prompt = (
            f"{prompt}\n\n--- ISOLATION CONTRACT ---\n"
            "You are running inside an isolated git worktree. Treat the current working directory "
            "and $LIMEN_ROOT as the only writable checkout. Do not edit the live root, do not edit "
            "$LIMEN_LIVE_ROOT, and do not edit tasks.yaml; the dispatcher records task state."
        )
    agent_cmd = [binary, *agent_args, prompt]
    # 1800s (was 900): local lanes have ABUNDANT budget headroom (codex/claude/opencode ~60-92 left
    # per window) while jules is scarce (≈100/day). At 900s, big tasks — incl. the revenue/deploy
    # tasks (BLD2-*-deploy, REV-*) — timed out locally then bled to jules, exhausting the scarce lane
    # and stalling the money work. A longer local cap lets the cheap, abundant lanes finish the big
    # tasks (a hung run is still bounded — _run_capture kills the process group at the cap).
    lane_timeout = max(1, _env_int("LIMEN_LANE_TIMEOUT", 1800))

    if dry_run:
        pr_note = f"; PR base {pr_base}" if pr_head else ""
        print(
            f"  would isolate {task.id}: worktree {wt} off {checkout_ref}{pr_note} "
            f"→ branch {branch} → {binary} {' '.join(agent_args)} "
            f"→ commit → push → PR  (live checkout untouched)"
        )
        return True

    # 1) fresh base from origin — never the user's possibly-dirty working tree.
    # Hold the git-plumbing lock only for these fast parent-repo ops so concurrent
    # same-repo dispatches don't collide on index.lock (the slow run is unlocked).
    add = subprocess.CompletedProcess([], 1, "", "worktree add was not attempted")
    for attempt in range(6):
        if attempt:
            suffix = secrets.token_hex(4)
            branch = f"limen/{slug}-{suffix}"
            wt = _ISOLATION_ROOT / (re.sub(r"[^a-zA-Z0-9._-]+", "-", task.id.lower()) + "-" + suffix)
        with _GIT_PLUMBING_LOCK:
            if attempt == 0:
                if fetch_refspec:
                    _git_plumbing(["fetch", "origin", fetch_refspec], repo_dir, timeout=300)
            _ISOLATION_ROOT.mkdir(parents=True, exist_ok=True)
            if wt.exists():  # leftover from a prior clean/no-op run
                _cleanup_isolated_worktree(repo_dir, wt, branch, checkout_ref, pushed=False, task=task)
                if wt.exists():
                    print(f"  retrying worktree add {task.id}: preserved existing worktree at {wt}")
                    continue
            add = _git_plumbing(["worktree", "add", "-b", branch, str(wt), checkout_ref], repo_dir, timeout=120)
        if add.returncode == 0:
            break
        if re.search(r"branch .* already exists|is already checked out", add.stderr or "", re.IGNORECASE):
            print(f"  retrying worktree add {task.id}: stale branch collision on {branch}")
            continue
        break
    if add.returncode != 0:
        print(f"  FAILED worktree add {task.id}: {add.stderr.strip()[:300]}")
        return False
    _record_worktree_birth(task, wt, branch, checkout_ref, pr_base, existing_pr=bool(pr_head))

    pushed = False
    try:
        start_head_result = _git(["rev-parse", "HEAD"], wt)
        start_head = start_head_result.stdout.strip() if start_head_result.returncode == 0 else ""
        run_result = _run_isolated_agent(agent, task, wt, agent_cmd, lane_timeout)
        if run_result is not True:
            return run_result

        commit_result = _commit_isolated_changes(task, wt)
        if pr_head:
            current_head_result = _git(["rev-parse", "HEAD"], wt)
            current_head = current_head_result.stdout.strip() if current_head_result.returncode == 0 else ""
            agent_committed = bool(start_head and current_head and current_head != start_head)
            if commit_result == _NOOP and not agent_committed:
                return commit_result
            if commit_result is not True and not (commit_result == _NOOP and agent_committed):
                return commit_result
            if not _push_existing_pr_head(task, wt, pr_head):
                return False
            pushed = True
            url = _existing_pr_url(pr_head)
            print(f"  dispatched: {task.id} → existing PR {url}")
            _arm_auto_merge(task, wt, url)
            return url

        if commit_result is not True:
            return commit_result

        if not _push_isolated_branch(task, wt, branch):
            return False
        pushed = True
        return _create_isolated_pr(task, wt, pr_base, branch)
    finally:
        # leave the user's checkout pristine: drop the worktree, and the local
        # branch too once its commits are safely on the remote, or when the attempt
        # produced no local work. Keep dirty/ahead failed worktrees for preservation.
        with _GIT_PLUMBING_LOCK:
            _cleanup_isolated_worktree(repo_dir, wt, branch, checkout_ref, pushed=pushed, task=task)


def _call_local_agent(agent: str, task: Task, dry_run: bool) -> bool | str:
    if not agent_can_run_task(agent, task):
        print(f"  SKIP {task.id}: {agent} is gated for Limen registry discovery tasks")
        return False
    if agent == "opencode" and "-m" not in _agent_argv(agent, task):
        reason = "no code-capable model is exposed by the live OpenCode catalog"
        if dry_run:
            print(f"  would BLOCK {task.id}: {reason}")
            return True
        print(f"  BLOCKED {task.id}: {reason}")
        return _blocked_result(reason)
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


def _reset_budget_if_needed(limen: LimenFile, now: datetime) -> bool:
    """Reset each vendor's spend on ITS OWN cadence (5h rolling for codex/claude, daily for
    the rest) so no reset window goes unused — replaces the single crude calendar-day reset.

    Returns True when a NON-ZERO counter was cleared, so callers can PERSIST the reset even on a
    beat that then dispatches nothing. Without that, a lane whose stale counter has hit its cap can
    never self-clear: the reset computes in memory but is discarded on a no-candidate/gated
    early-return, so the lane stays at remaining=0 forever (the jules deadlock). [[no-never-happens-again]]"""
    track = limen.portal.budget.track
    cleared_nonzero = False
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
            if track.per_agent.get(agent, 0):
                cleared_nonzero = True
            track.per_agent[agent] = 0
            track.per_agent_reset[agent] = now.isoformat()
    track.date = now.strftime("%Y-%m-%d")
    track.spent = sum(track.per_agent.values())
    return cleared_nonzero


def _remaining_budget(limen: LimenFile, agent: str, budget: int) -> int:
    """The per-vendor cadence cap is the binding gate (each refills on its own window); the
    global daily is only a backstop for agents that have no per-agent cap."""
    agent = canonical_agent(agent)
    track = limen.portal.budget.track
    agent_limit = limen.portal.budget.per_agent.get(agent)
    if agent_limit is not None:
        return max(0, agent_limit - track.per_agent.get(agent, 0))
    return max(0, budget - track.spent)


def _commit_dispatch_results(
    tasks_path: Path,
    limen: LimenFile,
    results: list[tuple[str, str, bool | str]],
    now: datetime,
) -> None:
    """COMMIT for the serial path, mirroring dispatch_parallel's commit: reload FRESH under the
    queue lock and re-apply each result by id. The caller's snapshot is minutes stale by the time
    agents finish — saving it whole erases every concurrent write made meanwhile (keeper folds,
    route stamps, status transitions): the lost-update board wipe. A task completed elsewhere in
    the interim keeps its terminal status (_apply_result's lifecycle guards); a task removed from
    the fresh board is skipped."""
    with _queue_lock(tasks_path) as got:
        if not got:
            print(
                f"── dispatch: queue busy — {len(results)} result(s) NOT committed this round; "
                "harvest reconciles from PR state (self-corrects next beat)"
            )
            return
        fresh = load_limen_file(tasks_path) if tasks_path.exists() else limen
        _reset_budget_if_needed(fresh, now)
        fid = {t.id: t for t in fresh.tasks}
        ftrack = fresh.portal.budget.track
        for agent, tid, res in results:
            ft = fid.get(tid)
            if ft is not None:
                _apply_result(ft, agent, res, now, ftrack)
        save_limen_file(tasks_path, fresh)


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

    admission = dispatch_admission_check(tasks_path, task_id=task_id)
    if not admission.get("allow", False):
        print_dispatch_admission_block("dispatch", admission)
        return

    _load_limen_env()  # hydrate creds into os.environ so agent CLIs inherit them (gemini/codex/opencode/…)
    if not run_always_working_before_dispatch(tasks_path, dry_run=dry_run):
        print("Always-working gate blocked dispatch before reservation")
        return
    if _reset_budget_if_needed(limen, now) and not dry_run:
        # Persist a cadence reset even when this call then dispatches nothing / bails at the
        # down-gate — otherwise a stale-counter lane (jules) stays gated to remaining=0 forever.
        # Committed via fresh reload, not this snapshot: the caller may hold a board loaded
        # before other writers ran.
        _commit_dispatch_results(tasks_path, limen, [], now)
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

    # Serial dispatch gates on dependencies the SAME way dispatch_parallel does (line ~1706): a
    # dependent increment stays OPEN but un-dispatched until its predecessor's PR merges, so the
    # roadmap self-advances with no parallel-built conflicts. Without this, bulk `limen dispatch`
    # dispatched dependents immediately, violating depends_on ordering the parallel path enforces.
    # An EXPLICIT single-task dispatch (`limen dispatch --task X`) is a deliberate human override and
    # bypasses the gate; only BULK dispatch respects it.
    id2 = {t.id: t for t in limen.tasks}
    value_repos = _value_tier_repos()
    raw_candidates = [
        t
        for t in tasks
        if _dispatchable(t)
        and (t.target_agent == agent_filter or t.target_agent == "any")
        and agent_can_run_task(agent_filter, t)
        and t.budget_cost <= remaining
        and (task_id is not None or _deps_met(t, id2))
        and (task_id is not None or not _superseded_by_rebase_task(t, id2))
        and (task_id is not None or chronic_dispatch_reason(t) is None)
        and not (debt_blocked and _routine_generated_buildout(t))
        and _routine_generated_buildout_allowed(t)
    ]
    candidates = sort_value_gate_candidates(raw_candidates, value_repos)

    if limit is not None:
        candidates = candidates[: max(0, limit)]

    if not candidates:
        if raw_candidates and _value_gate_configured(value_repos):
            print(f"Value gate: withheld {len(raw_candidates)} non-value candidate(s) for '{agent_filter}'")
        if debt_message:
            print(f"Lifecycle debt gate: {debt_message}")
        print(f"No open tasks for agent '{agent_filter}' within remaining budget ({remaining})")
        return
    if debt_message:
        print(f"Lifecycle debt gate: {debt_message}")

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"── limen dispatch ({mode}) — agent={agent_filter} budget_remaining={remaining}")

    dispatched = 0
    results: list[tuple[str, str, bool | str]] = []
    for task in candidates:
        if remaining < task.budget_cost:
            break

        result = call_agent_dispatch(agent_filter, task, dry_run)
        if not dry_run:
            # In-memory apply keeps this loop's bookkeeping consistent; persistence happens
            # once at commit, re-applied onto a FRESH board (never this stale snapshot).
            _apply_result(task, agent_filter, result, now, track)
            results.append((agent_filter, task.id, result))
            if result == _RATELIMIT:
                _commit_dispatch_results(tasks_path, limen, results, now)
                print(f"── lane {agent_filter} rate-limited — cooling, {dispatched} dispatched this cycle")
                return
            elif result and result not in (_NOOP, _RATELIMIT, _TIMEOUT) and not _is_blocked_result(result):
                remaining -= task.budget_cost

        dispatched += 1

    if not dry_run:
        _commit_dispatch_results(tasks_path, limen, results, now)

    print(f"── {mode}: {dispatched} task(s)")


def _apply_result(
    task: Task,
    agent: str,
    result: bool | str,
    now: datetime,
    track: BudgetTrack,
    *,
    charge_budget: bool = True,
) -> None:
    """Apply one dispatch result to a task (same semantics as the serial path):
    success → dispatched + spend; no-op/fail → recoverable failed; rate-limit → cascade."""
    if task.status in {"done", "archived"} and _has_done_transition(task):
        return
    if _restore_done_status(
        task,
        now,
        agent=agent,
        session_id="result-lifecycle-guard",
        output="dispatch result ignored because this task already recorded done",
    ):
        return
    if result in {_NOOP, False} and _restore_pr_open_status(
        task,
        now,
        agent=agent,
        session_id="result-lifecycle-guard",
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
        entry.status = "open"
        entry.route_to = nxt
        entry.output = f"rate limited on {agent}; reopened to live fleet route"
        task.target_agent = nxt
        task.status = "open"
    elif result == _TIMEOUT:
        # too big for a sync local lane → hand to jules (async, no wall-clock cap)
        entry.status = "open"
        entry.route_to = "jules"
        entry.output = f"timeout on {agent}; reopened to asynchronous lane"
        task.target_agent = "jules"
        task.status = "open"
        if "slow" not in task.labels:
            task.labels.append("slow")
    elif _is_blocked_result(result):
        entry.status = "failed_blocked"
        entry.output = _blocked_reason(result)
        task.status = "failed_blocked"
        if "blocked:routing" not in task.labels:
            task.labels.append("blocked:routing")
    elif result:
        if isinstance(result, str):
            entry.session_id = result
        task.status = "dispatched"
        if charge_budget:
            track.spent += task.budget_cost
            track.per_agent[agent] = track.per_agent.get(agent, 0) + task.budget_cost
    else:
        tried = f"tried:{agent}"
        if tried not in task.labels:
            task.labels.append(tried)
        if agent in _REMOTE_SERVICE_LANES:
            fallback = _remote_service_failure_lane(task, agent)
            entry.status = "open"
            entry.route_to = fallback
            entry.output = "remote/service lane failed; reopened to healthy fleet cascade"
            task.target_agent = fallback
            task.status = "open"
        elif next_lane := _next_lane(agent):
            entry.status = "open"
            entry.route_to = next_lane
            entry.output = f"{agent} lane failed; reopened to healthy fleet cascade"
            task.target_agent = next_lane
            task.status = "open"
        else:
            entry.status = "failed"
            task.status = "failed"
    if selection := _MODEL_SELECTION_RECEIPTS.pop(task.id, None):
        entry.execution_profile = selection.get("execution_profile")
        entry.selected_model = selection.get("selected_model")
        entry.selection_source = selection.get("selection_source")
        entry.catalog_hash = selection.get("catalog_hash")
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
        floor = max(0.001, _env_float("LIMEN_ACCEL_TLEFT_FLOOR", 0.08))
        urgency = remaining_frac / max(time_left_frac, floor)
        if urgency <= 1.0:
            return base_limit
        non_blocking = agent in _ASYNC_LANES or os.environ.get("LIMEN_DISPATCH_ASYNC") == "1"
        ceiling = _env_int(
            "LIMEN_ACCEL_ASYNC_CEIL" if non_blocking else "LIMEN_ACCEL_LOCAL_CEIL",
            25 if non_blocking else 8,
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


def _earned_fable_tier() -> str:
    """A Fable selection that already cleared the acceptance receipt, resolved against the LIVE
    weekly cap (`logs/fable-allotment.json`): 'fable' when the cap still allows it, else the
    fallback tier (Opus). This is the runtime backstop the receipt gate alone cannot provide —
    it enforces the 40% deliberate / 50% hard ladder against actual tokens burned this week."""
    capped = _fable_capped_tier(_fable_reserve_receipt_present())
    return capped if capped is not None else "fable"


def _claude_tier_for(task: Task | None) -> str:
    """DERIVE the Claude tier for a task. Default = haiku (verifiable → escalate via the existing
    cascade). Pre-assign a higher tier ONLY where failure is undetectable:
      • fable — the narrow reserved top tier plus a written acceptance receipt/command;
      • opus  — the reserved principled set (_claude_opus_classes) or an explicit override;
      • sonnet— classes the ledger has DISCOVERED this lane wastes on (waste_classes): work that
                shipped low-value yet passed whatever gate exists ⇒ failure not caught cheaply here.
    A per-task `claude_tier` pin and an optional logs/model-tiers.json override layer on top.
    Fable is additionally gated by the LIVE weekly cap (`_earned_fable_tier`): a valid receipt is
    necessary-not-sufficient once the week's Fable spend is at/over cap. Fail-open → haiku."""
    if task is None:
        return "haiku"
    pin = task.claude_tier
    if pin in _CLAUDE_TIER_ORDER:
        if pin == "fable" and not _claude_fable_acceptance_present():
            return _fable_fallback_tier()
        if pin == "fable":
            return _earned_fable_tier()
        return str(pin)
    classes = _task_classes(task)
    override = _claude_tier_overrides()
    if classes & (_claude_fable_classes() | set(override.get("fable") or [])):
        return _earned_fable_tier() if _claude_fable_acceptance_present() else _fable_fallback_tier()
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


def _select_parallel_reservations(
    limen: LimenFile,
    agents: list[str],
    per_agent_limit: int,
    now: datetime,
    *,
    dry_run: bool,
    debt_blocked: bool,
) -> list[tuple[str, str]]:
    """Pick and optionally reserve parallel-dispatch tasks on the supplied fresh board."""
    track = limen.portal.budget.track
    daily = limen.portal.budget.daily
    picked: list[tuple[str, str]] = []
    spent_daily = track.spent
    id2 = {t.id: t for t in limen.tasks}
    ledger_lanes = _ledger_lanes()
    value_repos = _value_tier_repos()
    for agent in agents:
        cap = limen.portal.budget.per_agent.get(agent)
        agent_spent = track.per_agent.get(agent, 0)
        rem = daily - spent_daily if cap is None else max(0, min(daily - spent_daily, cap - agent_spent))
        if rem <= 0:
            continue
        raw_cands = [
            t
            for t in limen.tasks
            if _dispatchable(t)
            and (t.target_agent == agent or t.target_agent == "any")
            and agent_can_run_task(agent, t)
            and t.budget_cost <= rem
            and _deps_met(t, id2)
            and not _superseded_by_rebase_task(t, id2)
            and chronic_dispatch_reason(t) is None
            and not (debt_blocked and _routine_generated_buildout(t))
            and _routine_generated_buildout_allowed(t)
        ]
        cands = sort_value_gate_candidates(raw_cands, value_repos)
        # FRONT-LOAD: base picks by priority, then an ACCELERATION TAIL (only when the lane is
        # under-spending toward its reset cliff) drawn ONLY from work-classes the ledger says this
        # lane lands — so expiring budget converts to shipped value, never to junk.
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
        spent_daily += spent_here
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
    return picked


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
    admission = dispatch_admission_check(tasks_path)
    if not admission.get("allow", False):
        print_dispatch_admission_block("dispatch-parallel", admission)
        return
    if not run_always_working_before_dispatch(tasks_path, dry_run=dry_run):
        print("Always-working gate blocked parallel dispatch before reservation")
        return
    debt_blocked, debt_message = _worktree_debt_gate()
    if debt_message:
        print(f"Lifecycle debt gate: {debt_message}")

    if dry_run:
        _reset_budget_if_needed(limen, now)
        picked = _select_parallel_reservations(
            limen,
            agents,
            per_agent_limit,
            now,
            dry_run=True,
            debt_blocked=debt_blocked,
        )
        print(f"── PARALLEL DRY-RUN — would dispatch {len(picked)} task(s) across {agents}:")
        for a, tid in picked:
            print(f"  {a}: {tid}")
        return

    # ── RESERVE: re-read inside the queue lock, then pick and mark dispatched on that fresh board.
    # The caller may have loaded `limen` before a supervisor/heartbeat wrote tasks.yaml; saving that
    # stale snapshot would erase concurrent task additions, completions, or budget resets.
    with _queue_lock(tasks_path) as got:
        if not got:
            # Lock timed out — honor the contract (io.queue_lock): skip this round rather than
            # writing unprotected. Running the agents WITHOUT persisting the reservation would risk
            # a double-dispatch, so we skip the whole round; it self-corrects on the next beat.
            print("── PARALLEL: queue busy — skipped this dispatch round (self-corrects next beat)")
            return
        fresh = load_limen_file(tasks_path) if tasks_path.exists() else limen
        reset = _reset_budget_if_needed(fresh, now)
        picked = _select_parallel_reservations(
            fresh,
            agents,
            per_agent_limit,
            now,
            dry_run=False,
            debt_blocked=debt_blocked,
        )
        if not picked:
            if reset:
                save_limen_file(tasks_path, fresh)
            print(f"── PARALLEL: nothing to dispatch for {agents} within budget")
            return
        save_limen_file(tasks_path, fresh)  # reserve commit (atomic vs supervisor writes)
        limen = fresh

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
    n_pr = n_noop = n_fail = n_rl = n_to = n_blocked = 0
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
            elif _is_blocked_result(res):
                n_blocked += 1
            elif res and not _is_blocked_result(res):
                n_pr += 1
            else:
                n_fail += 1
        save_limen_file(tasks_path, fresh)
    print(
        f"── PARALLEL done: {len(results)} ran · {n_pr} dispatched/PR · {n_noop} no-op · "
        f"{n_fail} failed→cascade · {n_blocked} blocked · {n_rl} rate-limited · {n_to} timeout→jules"
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
    if not dry_run:
        # APPLY re-selects and mutates on a FRESH board under the queue lock — persisting the
        # caller's snapshot would erase every write made since it was loaded (the dispatch
        # lost-update wipe). The fresh re-select also means we only reopen tasks that are STILL
        # stale at write time, not ones another process just progressed.
        with _queue_lock(tasks_path) as got:
            if not got:
                print("── release-stale: queue busy — skipped this round (self-corrects next beat)")
                return {
                    "status": "skipped_queue_busy",
                    "agent": agent,
                    "hours": hours,
                    "tasks_path": str(tasks_path),
                    "count": 0,
                    "released": [],
                    "restored_done": [],
                    "candidates": [],
                }
            fresh = load_limen_file(tasks_path) if tasks_path.exists() else limen
            candidates = stale_tasks(fresh, hours=hours, agent=agent)
            for task in candidates:
                print(f"  {task.id} {task.status} {task.target_agent} — {task.title}")
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
            save_limen_file(tasks_path, fresh)
    else:
        for task in candidates:
            print(f"  {task.id} {task.status} {task.target_agent} — {task.title}")

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
                "status": task.status,
            }
            for task in candidates
        ],
    }
