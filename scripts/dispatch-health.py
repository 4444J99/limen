#!/usr/bin/env python3
"""Record heartbeat/dispatch substrate health without mutating the live daemon.

This receipt answers a narrow conductor question: does the code we just verified
match the Limen root that launchd is actually running, and are heartbeat plus
async-dispatch probes healthy enough to trust?

It is read-only. It does not restart launchd, edit plist files, touch
tasks.yaml, switch branches, or repair credentials.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "dispatch-health.json"
DOC_PATH = ROOT / "docs" / "dispatch-health.md"
LIVE_ROOT = Path(os.environ.get("LIMEN_LIVE_ROOT", HOME / "Workspace" / "limen"))
HEARTBEAT_PLIST = Path(
    os.environ.get("LIMEN_HEARTBEAT_PLIST", HOME / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist")
)
LAUNCHD_LABEL = os.environ.get("LIMEN_HEARTBEAT_LABEL", "com.limen.heartbeat")


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "args": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "args": args,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
        }
    except OSError as exc:
        return {"args": args, "returncode": None, "stdout": "", "stderr": str(exc), "timed_out": False}


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def command_summary(result: dict[str, Any]) -> dict[str, Any]:
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    lines = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
    return {
        "returncode": result.get("returncode"),
        "timed_out": bool(result.get("timed_out")),
        "line_count": len(lines),
        "first_line": receipt_line(lines[0]) if lines else "",
        "last_line": receipt_line(lines[-1]) if lines else "",
    }


def receipt_line(line: str) -> str:
    replacements = {
        "\u2500": "-",
        "\u2192": "->",
        "\u2013": "-",
        "\u2014": "-",
    }
    for src, dst in replacements.items():
        line = line.replace(src, dst)
    return line.encode("ascii", "replace").decode("ascii")


def read_plist(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {"present": False, "path": str(path)}
    env = data.get("EnvironmentVariables") or {}
    return {
        "present": True,
        "path": str(path),
        "label": data.get("Label"),
        "keep_alive": data.get("KeepAlive"),
        "run_at_load": data.get("RunAtLoad"),
        "program_arguments": data.get("ProgramArguments") or [],
        "env": {
            "LIMEN_ROOT": env.get("LIMEN_ROOT"),
            "LIMEN_DISPATCH_ASYNC": env.get("LIMEN_DISPATCH_ASYNC"),
            "LIMEN_LANES": env.get("LIMEN_LANES"),
            "LIMEN_LOCAL_LIMIT": env.get("LIMEN_LOCAL_LIMIT"),
        },
    }


def parse_launchd_print(text: str) -> dict[str, Any]:
    env: dict[str, str] = {}
    in_env = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "environment = {":
            in_env = True
            continue
        if in_env and stripped == "}":
            in_env = False
            continue
        if in_env:
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*) => (.*)", stripped)
            if match and match.group(1).startswith("LIMEN_"):
                env[match.group(1)] = match.group(2)
    state_match = re.search(r"^\s*state = (.+)$", text, re.MULTILINE)
    pid_match = re.search(r"^\s*pid = ([0-9]+)$", text, re.MULTILINE)
    return {
        "present": bool(text.strip()),
        "running": bool(state_match and state_match.group(1).strip() == "running"),
        "state": state_match.group(1).strip() if state_match else "missing",
        "pid": pid_match.group(1) if pid_match else None,
        "env": env,
    }


def launchd_snapshot() -> dict[str, Any]:
    result = run_command(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"], timeout=8)
    parsed = parse_launchd_print(str(result.get("stdout") or ""))
    parsed["probe"] = command_summary(result)
    return parsed


def git_output(root: Path, args: list[str], timeout: int = 12) -> str | None:
    result = run_command(["git", "-C", str(root), *args], timeout=timeout)
    if result.get("returncode") == 0:
        return str(result.get("stdout") or "").strip()
    return None


def git_snapshot(root: Path) -> dict[str, Any]:
    status_text = git_output(root, ["status", "--porcelain=v1", "--branch"]) or ""
    lines = status_text.splitlines()
    dirty = [line for line in lines if line and not line.startswith("## ")]
    ahead_behind = git_output(root, ["rev-list", "--left-right", "--count", "HEAD...origin/main"])
    ahead = behind = None
    if ahead_behind:
        parts = ahead_behind.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            ahead, behind = int(parts[0]), int(parts[1])
    head = git_output(root, ["rev-parse", "HEAD"])
    origin_main = git_output(root, ["rev-parse", "origin/main"])
    return {
        "path": str(root),
        "present": root.exists(),
        "is_git": (root / ".git").exists() or bool(git_output(root, ["rev-parse", "--git-dir"])),
        "branch": git_output(root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "head": head,
        "origin_main": origin_main,
        "matches_origin_main": bool(head and origin_main and head == origin_main),
        "ahead_origin_main": ahead,
        "behind_origin_main": behind,
        "status_summary": lines[0] if lines else "",
        "dirty_entries": len(dirty),
        "dirty_paths": [line[3:] if len(line) > 3 else line for line in dirty[:30]],
        "dirty_truncated": len(dirty) > 30,
    }


def watchdog_snapshot() -> dict[str, Any]:
    result = run_command(["python3", "scripts/watchdog.py", "--dry-run"], cwd=ROOT, timeout=40)
    summary = command_summary(result)
    output = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    summary["healthy"] = result.get("returncode") == 0 and "HEALTHY" in output
    return summary


def async_probe_snapshot(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"requested": False}
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT / 'cli' / 'src'}:{env.get('PYTHONPATH', '')}"
    result = run_command(
        [
            "python3",
            "scripts/dispatch-async.py",
            "--lanes",
            "codex,opencode,agy,claude,gemini,jules",
            "--per-lane",
            "3",
            "--max",
            "12",
            "--dry-run",
        ],
        cwd=ROOT,
        env=env,
        timeout=120,
    )
    summary = command_summary(result)
    summary["requested"] = True
    summary["ok"] = result.get("returncode") == 0 and not result.get("timed_out")
    return summary


def derive_blockers(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    plist = snapshot["heartbeat_plist"]
    loaded = snapshot["launchd"]
    git = snapshot["live_root_git"]
    watchdog = snapshot["watchdog"]
    async_probe = snapshot["async_probe"]

    if not plist.get("present"):
        blockers.append({"id": "heartbeat-plist-missing", "evidence": "LaunchAgent plist was not found."})
    elif plist.get("keep_alive") is not True:
        blockers.append({"id": "heartbeat-keepalive-not-true", "evidence": "LaunchAgent KeepAlive is not true."})

    if not loaded.get("running"):
        blockers.append({"id": "heartbeat-launchd-not-running", "evidence": f"launchd state is {loaded.get('state')}."})

    if not watchdog.get("healthy"):
        blockers.append({"id": "heartbeat-watchdog-unhealthy", "evidence": watchdog.get("last_line") or "watchdog did not report healthy."})

    if git.get("present") and not git.get("matches_origin_main"):
        blockers.append(
            {
                "id": "live-root-not-at-origin-main",
                "evidence": (
                    f"live root branch {git.get('branch')} head {str(git.get('head') or '')[:12]} "
                    f"differs from origin/main {str(git.get('origin_main') or '')[:12]}."
                ),
            }
        )
    if int(git.get("dirty_entries") or 0):
        blockers.append(
            {
                "id": "live-root-dirty",
                "evidence": f"live root has {git.get('dirty_entries')} dirty entries.",
            }
        )

    plist_async = (plist.get("env") or {}).get("LIMEN_DISPATCH_ASYNC")
    loaded_async = (loaded.get("env") or {}).get("LIMEN_DISPATCH_ASYNC")
    if plist_async != loaded_async:
        blockers.append(
            {
                "id": "heartbeat-loaded-env-drift",
                "evidence": f"plist LIMEN_DISPATCH_ASYNC={plist_async!r}, loaded={loaded_async!r}.",
            }
        )

    if async_probe.get("requested") and not async_probe.get("ok"):
        blockers.append(
            {
                "id": "async-dry-run-unhealthy",
                "evidence": async_probe.get("last_line") or "async dry-run did not complete cleanly.",
            }
        )

    return blockers


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "heartbeat_plist": read_plist(HEARTBEAT_PLIST),
        "launchd": launchd_snapshot(),
        "live_root_git": git_snapshot(LIVE_ROOT),
        "verified_worktree": git_snapshot(ROOT),
        "watchdog": watchdog_snapshot(),
        "async_probe": async_probe_snapshot(bool(args.probe_async)),
    }
    blockers = derive_blockers(snapshot)
    snapshot["blockers"] = blockers
    snapshot["status"] = "healthy" if not blockers else "blocked"
    return snapshot


def render_markdown(snapshot: dict[str, Any]) -> str:
    plist = snapshot["heartbeat_plist"]
    loaded = snapshot["launchd"]
    live = snapshot["live_root_git"]
    verified = snapshot["verified_worktree"]
    watchdog = snapshot["watchdog"]
    async_probe = snapshot["async_probe"]
    blockers = snapshot["blockers"]
    lines = [
        "# Dispatch Health",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        f"Status: `{snapshot['status']}`",
        "",
        "## Incident Class",
        "",
        "- Dispatch/heartbeat health is not proven by tests in a detached worktree alone.",
        "- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.",
        "- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.",
        "",
        "## Heartbeat",
        "",
        f"- LaunchAgent plist: `{relpath(Path(plist.get('path') or HEARTBEAT_PLIST))}` present `{plist.get('present')}`.",
        f"- Plist KeepAlive: `{plist.get('keep_alive')}`; RunAtLoad: `{plist.get('run_at_load')}`.",
        f"- Plist LIMEN_ROOT: `{(plist.get('env') or {}).get('LIMEN_ROOT')}`.",
        f"- Plist LIMEN_DISPATCH_ASYNC: `{(plist.get('env') or {}).get('LIMEN_DISPATCH_ASYNC')}`.",
        f"- Loaded launchd state: `{loaded.get('state')}` pid `{loaded.get('pid')}`.",
        f"- Loaded LIMEN_ROOT: `{(loaded.get('env') or {}).get('LIMEN_ROOT')}`.",
        f"- Loaded LIMEN_DISPATCH_ASYNC: `{(loaded.get('env') or {}).get('LIMEN_DISPATCH_ASYNC')}`.",
        f"- Watchdog dry-run healthy: `{watchdog.get('healthy')}`; `{watchdog.get('first_line')}`.",
        "",
        "## Async Dispatch",
        "",
        f"- Async dry-run requested: `{async_probe.get('requested')}`.",
        f"- Async dry-run ok: `{async_probe.get('ok')}`; timed out `{async_probe.get('timed_out', False)}`.",
        f"- Async dry-run summary: `{async_probe.get('last_line', '')}`.",
        "",
        "## Live Root",
        "",
        f"- Live root: `{relpath(Path(live.get('path') or LIVE_ROOT))}`.",
        f"- Branch: `{live.get('branch')}`; status `{live.get('status_summary')}`.",
        f"- HEAD: `{live.get('head')}`.",
        f"- origin/main: `{live.get('origin_main')}`.",
        f"- Matches origin/main: `{live.get('matches_origin_main')}`; ahead `{live.get('ahead_origin_main')}` behind `{live.get('behind_origin_main')}`.",
        f"- Dirty entries: `{live.get('dirty_entries')}`.",
    ]
    for path in live.get("dirty_paths") or []:
        lines.append(f"  - `{path}`")
    if live.get("dirty_truncated"):
        lines.append("  - `<truncated>`")

    lines += [
        "",
        "## Verified Worktree",
        "",
        f"- Verified worktree: `{relpath(Path(verified.get('path') or ROOT))}`.",
        f"- Branch: `{verified.get('branch')}`; status `{verified.get('status_summary')}`.",
        f"- HEAD matches origin/main: `{verified.get('matches_origin_main')}`.",
        "",
        "## Blockers",
        "",
    ]
    if blockers:
        for blocker in blockers:
            lines.append(f"- `{blocker['id']}`: {blocker['evidence']}")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Commands",
        "",
        "- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`",
        "- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`",
        "- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`",
        "- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the heartbeat/dispatch health receipt.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--probe-async", action="store_true", help="run the bounded async dispatch dry-run probe")
    args = parser.parse_args()
    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = f"dispatch-health: {snapshot['status']} with {len(snapshot['blockers'])} blockers"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
