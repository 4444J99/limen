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
import ast
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
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "dispatch-health.json"
DOC_PATH = ROOT / "docs" / "dispatch-health.md"
PROMPT_PACKET_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
PROMPT_PACKET_DOC = ROOT / "docs" / "prompt-packet-ledger.md"
ALWAYS_WORKING_INDEX = Path(
    os.environ.get("LIMEN_ALWAYS_WORKING_INDEX", PRIVATE_ROOT / "lifecycle" / "always-working.json")
)
ALWAYS_WORKING_DOC = Path(os.environ.get("LIMEN_ALWAYS_WORKING_DOC", ROOT / "docs" / "always-working.md"))
LIVE_ROOT = Path(os.environ.get("LIMEN_LIVE_ROOT", HOME / "Workspace" / "limen"))
HEARTBEAT_PLIST = Path(
    os.environ.get("LIMEN_HEARTBEAT_PLIST", HOME / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist")
)
LAUNCHD_LABEL = os.environ.get("LIMEN_HEARTBEAT_LABEL", "com.limen.heartbeat")
IGNORED_GENERATED_RECEIPTS = {
    "docs/conductor-tranche.md",
    "docs/dispatch-health.md",
    "docs/live-root-gate.md",
    "docs/session-attack-paths.md",
    "docs/session-corpus-ledger.md",
    "docs/session-lifecycle-blockers.md",
}
HEARTBEAT_ENV_KEYS = (
    "LIMEN_ROOT",
    "LIMEN_WORKTREES",
    "LIMEN_WORKTREE_ROOT",
    "LIMEN_DISPATCH_ASYNC",
    "LIMEN_DISPATCH_LANES",
    "LIMEN_LOCAL_LIMIT",
    "LIMEN_ASYNC_MAX",
    "LIMEN_LANES",
)


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


def parse_async_skipped_down_lanes(output: str) -> list[str]:
    for line in output.splitlines():
        if "skipping down lanes:" not in line:
            continue
        _, _, raw = line.partition("skipping down lanes:")
        try:
            value = ast.literal_eval(raw.strip())
        except (SyntaxError, ValueError):
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]
    return []


def read_manual_down_lanes(root: Path) -> dict[str, str]:
    down_file = root / "logs" / "lanes-down.txt"
    reasons: dict[str, str] = {}
    try:
        lines = down_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return reasons
    for line in lines:
        lane_part, sep, comment = line.partition("#")
        lane = lane_part.strip()
        if not lane:
            continue
        reasons[lane] = comment.strip() if sep else ""
    return reasons


def read_usage_vendors(root: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads((root / "logs" / "usage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    vendors = data.get("vendors") if isinstance(data, dict) else {}
    if not isinstance(vendors, dict):
        return {}
    return {str(name): info for name, info in vendors.items() if isinstance(info, dict)}


def skipped_down_lane_reasons(lanes: list[str], root: Path) -> dict[str, dict[str, Any]]:
    manual = read_manual_down_lanes(root)
    usage = read_usage_vendors(root)
    reasons: dict[str, dict[str, Any]] = {}
    for lane in lanes:
        lane_name = str(lane)
        if lane_name in manual:
            reasons[lane_name] = {
                "source": "manual",
                "path": "logs/lanes-down.txt",
                "note": manual[lane_name],
            }
            continue
        info = usage.get(lane_name)
        if info:
            reasons[lane_name] = {
                "source": "usage",
                "health": info.get("health"),
                "signal": info.get("signal"),
                "unit": info.get("unit"),
                "remaining": info.get("remaining"),
                "possible": info.get("possible"),
                "headroom_pct": info.get("headroom_pct"),
                "limit_source": info.get("limit_source"),
            }
            continue
        reasons[lane_name] = {"source": "unknown"}
    return reasons


def render_skipped_lane_reason(lane: str, reason: dict[str, Any]) -> str:
    source = reason.get("source")
    if source == "manual":
        note = str(reason.get("note") or "").strip()
        suffix = f"; {receipt_line(note)}" if note else ""
        return f"`{lane}`: manual down file `{reason.get('path')}`{suffix}."
    if source == "usage":
        details = [
            f"usage health `{reason.get('health')}`",
            f"signal `{reason.get('signal')}`",
        ]
        remaining = reason.get("remaining")
        possible = reason.get("possible")
        if remaining is not None and possible is not None:
            details.append(f"remaining `{remaining}` of `{possible}`")
        elif remaining is not None:
            details.append(f"remaining `{remaining}`")
        headroom = reason.get("headroom_pct")
        if headroom is not None:
            details.append(f"headroom `{headroom}%`")
        return f"`{lane}`: " + "; ".join(details) + "."
    return f"`{lane}`: down source unknown from async dry-run output."


def receipt_line(line: str) -> str:
    replacements = {
        "\u2500": "-",
        "\u2192": "->",
        "\u2013": "-",
        "\u2014": "-",
        "\u00b7": ";",
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
        "env": {key: env.get(key) for key in HEARTBEAT_ENV_KEYS},
    }


def generated_plist_snapshot() -> dict[str, Any]:
    script = ROOT / "scripts" / "gen-launchd-plist.sh"
    if not script.exists():
        return {"present": False, "path": str(script), "env": {}, "probe": {"returncode": None}}
    env = dict(os.environ)
    env["LIMEN_ROOT"] = str(LIVE_ROOT)
    result = run_command(["bash", str(script), "--stdout"], cwd=ROOT, env=env, timeout=12)
    summary = command_summary(result)
    if result.get("returncode") != 0:
        return {"present": False, "path": str(script), "env": {}, "probe": summary}
    try:
        data = plistlib.loads(str(result.get("stdout") or "").encode("utf-8"))
    except (plistlib.InvalidFileException, ValueError):
        return {"present": False, "path": str(script), "env": {}, "probe": summary}
    raw_env = data.get("EnvironmentVariables") or {}
    return {
        "present": True,
        "path": str(script),
        "label": data.get("Label"),
        "program_arguments": data.get("ProgramArguments") or [],
        "env": {key: raw_env.get(key) for key in HEARTBEAT_ENV_KEYS},
        "probe": summary,
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


def parse_dirty(status_text: str, ignored_paths: set[str] | None = None) -> dict[str, Any]:
    ignored_paths = ignored_paths or set()
    tracked: list[str] = []
    untracked: list[str] = []
    ignored: list[str] = []
    for line in [line for line in status_text.splitlines() if line and not line.startswith("## ")]:
        path = line[3:] if len(line) > 3 else line
        if path in ignored_paths:
            ignored.append(path)
            continue
        if line.startswith("?? "):
            untracked.append(path)
        else:
            tracked.append(path)
    dirty_paths = tracked + untracked
    return {
        "dirty_entries": len(dirty_paths),
        "dirty_paths": dirty_paths[:30],
        "dirty_truncated": len(dirty_paths) > 30,
        "ignored_dirty_entries": len(ignored),
        "ignored_dirty_paths": ignored,
    }


def git_snapshot(root: Path) -> dict[str, Any]:
    status_text = git_output(root, ["status", "--porcelain=v1", "--branch"]) or ""
    lines = status_text.splitlines()
    dirty = parse_dirty(status_text, IGNORED_GENERATED_RECEIPTS)
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
        **dirty,
    }


def watchdog_snapshot() -> dict[str, Any]:
    result = run_command(["python3", "scripts/watchdog.py", "--dry-run"], cwd=ROOT, timeout=40)
    summary = command_summary(result)
    output = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    summary["healthy"] = result.get("returncode") == 0 and "HEALTHY" in output
    return summary


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _host_local_ceiling() -> int:
    return max(1, os.cpu_count() or 1)


def async_probe_snapshot(enabled: bool, *, launchd: dict[str, Any], plist: dict[str, Any]) -> dict[str, Any]:
    if not enabled:
        return {"requested": False}
    loaded_env = launchd.get("env") if isinstance(launchd.get("env"), dict) else {}
    plist_env = plist.get("env") if isinstance(plist.get("env"), dict) else {}
    lanes = str(loaded_env.get("LIMEN_DISPATCH_LANES") or plist_env.get("LIMEN_DISPATCH_LANES") or "auto")
    max_runs = _positive_int(
        loaded_env.get("LIMEN_ASYNC_MAX") or plist_env.get("LIMEN_ASYNC_MAX"),
        _host_local_ceiling(),
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT / 'cli' / 'src'}:{env.get('PYTHONPATH', '')}"
    env["LIMEN_DISPATCH_LANES"] = lanes
    env["LIMEN_ASYNC_MAX"] = str(max_runs)
    result = run_command(
        [
            "python3",
            "scripts/dispatch-async.py",
            "--lanes",
            lanes,
            "--per-lane",
            "3",
            "--max",
            str(max_runs),
            "--dry-run",
        ],
        cwd=ROOT,
        env=env,
        timeout=120,
    )
    summary = command_summary(result)
    output = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    summary["requested"] = True
    summary["lanes"] = lanes
    summary["max"] = max_runs
    summary["ok"] = result.get("returncode") == 0 and not result.get("timed_out")
    summary["skipped_down_lanes"] = parse_async_skipped_down_lanes(output)
    summary["skipped_down_reasons"] = skipped_down_lane_reasons(summary["skipped_down_lanes"], ROOT)
    return summary


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def prompt_packet_snapshot() -> dict[str, Any]:
    index = load_json(PROMPT_PACKET_INDEX)
    if not index:
        return {
            "present": False,
            "path": str(PROMPT_PACKET_INDEX),
            "public_doc": str(PROMPT_PACKET_DOC),
            "status": "missing",
            "open_packets": 0,
            "conductor_required_packets": 0,
            "ready_after_predicate_packets": 0,
            "recorded_packets": 0,
            "dispatchability": {},
            "top_open_packets": [],
        }

    open_packets = [item for item in index.get("open_packets") or [] if isinstance(item, dict)]
    recorded_packets = [item for item in index.get("recorded_packets") or [] if isinstance(item, dict)]
    dispatchability: dict[str, int] = {}
    for packet in open_packets:
        key = str(packet.get("dispatchability") or "unknown")
        dispatchability[key] = dispatchability.get(key, 0) + 1
    conductor_required = sum(
        1
        for packet in open_packets
        if str(packet.get("dispatchability") or "")
        in {"codex-owner-packet", "needs-owner-repo", "needs-predicate", "unknown"}
    )
    ready_after_predicate = sum(
        1 for packet in open_packets if str(packet.get("dispatchability") or "") == "ready-after-predicate"
    )
    return {
        "present": True,
        "path": str(PROMPT_PACKET_INDEX),
        "public_doc": str(PROMPT_PACKET_DOC),
        "status": "clear" if not open_packets else "needs-conductor",
        "generated_at": index.get("generated_at"),
        "open_packets": len(open_packets),
        "conductor_required_packets": conductor_required,
        "ready_after_predicate_packets": ready_after_predicate,
        "recorded_packets": len(recorded_packets),
        "dispatchability": dispatchability,
        "top_open_packets": [
            {
                "id": str(packet.get("id") or ""),
                "family": str(packet.get("family") or ""),
                "dispatchability": str(packet.get("dispatchability") or "unknown"),
                "agent_fit": receipt_line(str(packet.get("agent_fit") or "")),
                "verification": receipt_line(str(packet.get("verification") or "")),
            }
            for packet in open_packets[:5]
        ],
    }


def always_working_snapshot() -> dict[str, Any]:
    index = load_json(ALWAYS_WORKING_INDEX)
    if not index:
        return {
            "present": False,
            "path": str(ALWAYS_WORKING_INDEX),
            "public_doc": str(ALWAYS_WORKING_DOC),
            "status": "missing",
            "required_open_count": 0,
            "blocked_count": 0,
            "done_count": 0,
            "next_item_id": "",
            "next_item_status": "",
            "top_required_items": [],
        }

    items = [item for item in index.get("items") or [] if isinstance(item, dict)]
    required = [
        item for item in items if str(item.get("status") or "") in {"assigned_from_existing_work", "needs_assignment"}
    ]
    return {
        "present": True,
        "path": str(ALWAYS_WORKING_INDEX),
        "public_doc": str(ALWAYS_WORKING_DOC),
        "status": str(index.get("status") or "unknown"),
        "generated_at": index.get("generated_at"),
        "required_open_count": int(index.get("required_open_count") or len(required)),
        "blocked_count": int(index.get("blocked_count") or 0),
        "done_count": int(index.get("done_count") or 0),
        "next_item_id": str(index.get("next_item_id") or ""),
        "next_item_status": str(index.get("next_item_status") or ""),
        "top_required_items": [
            {
                "id": str(item.get("id") or ""),
                "workstream": str(item.get("workstream") or ""),
                "status": str(item.get("status") or ""),
                "verdict": receipt_line(str(item.get("verdict") or "")),
            }
            for item in required[:5]
        ],
    }


def derive_blockers(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    generated = snapshot.get("generated_heartbeat_plist") or {"present": False, "env": {}}
    plist = snapshot["heartbeat_plist"]
    loaded = snapshot["launchd"]
    git = snapshot["live_root_git"]
    watchdog = snapshot["watchdog"]
    async_probe = snapshot["async_probe"]
    prompt_packets = snapshot["prompt_packets"]
    always_working = snapshot["always_working"]

    if not plist.get("present"):
        blockers.append({"id": "heartbeat-plist-missing", "evidence": "LaunchAgent plist was not found."})
    elif plist.get("keep_alive") is not True:
        blockers.append({"id": "heartbeat-keepalive-not-true", "evidence": "LaunchAgent KeepAlive is not true."})

    if not loaded.get("running"):
        blockers.append({"id": "heartbeat-launchd-not-running", "evidence": f"launchd state is {loaded.get('state')}."})

    if generated.get("present") and plist.get("present"):
        generated_env = generated.get("env") or {}
        plist_env = plist.get("env") or {}
        drift = [
            key
            for key in HEARTBEAT_ENV_KEYS
            if generated_env.get(key) is not None and generated_env.get(key) != plist_env.get(key)
        ]
        if drift:
            evidence = ", ".join(
                f"{key}: generated={generated_env.get(key)!r} installed={plist_env.get(key)!r}" for key in drift[:4]
            )
            if len(drift) > 4:
                evidence += f", +{len(drift) - 4} more"
            blockers.append({"id": "heartbeat-generated-plist-env-drift", "evidence": evidence})

    if not watchdog.get("healthy"):
        blockers.append(
            {
                "id": "heartbeat-watchdog-unhealthy",
                "evidence": watchdog.get("last_line") or "watchdog did not report healthy.",
            }
        )

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

    plist_dispatch_lanes = (plist.get("env") or {}).get("LIMEN_DISPATCH_LANES")
    loaded_dispatch_lanes = (loaded.get("env") or {}).get("LIMEN_DISPATCH_LANES")
    if plist_dispatch_lanes != loaded_dispatch_lanes:
        blockers.append(
            {
                "id": "heartbeat-dispatch-lanes-env-drift",
                "evidence": (f"plist LIMEN_DISPATCH_LANES={plist_dispatch_lanes!r}, loaded={loaded_dispatch_lanes!r}."),
            }
        )

    for key in ("LIMEN_WORKTREES", "LIMEN_WORKTREE_ROOT", "LIMEN_ASYNC_MAX"):
        plist_value = (plist.get("env") or {}).get(key)
        loaded_value = (loaded.get("env") or {}).get(key)
        if plist_value != loaded_value:
            blockers.append(
                {
                    "id": "heartbeat-loaded-env-drift",
                    "evidence": f"plist {key}={plist_value!r}, loaded={loaded_value!r}.",
                }
            )

    if async_probe.get("requested") and not async_probe.get("ok"):
        blockers.append(
            {
                "id": "async-dry-run-unhealthy",
                "evidence": async_probe.get("last_line") or "async dry-run did not complete cleanly.",
            }
        )

    if int(prompt_packets.get("conductor_required_packets") or 0):
        blockers.append(
            {
                "id": "prompt-packets-need-conductor",
                "evidence": (
                    f"{prompt_packets.get('conductor_required_packets')} open prompt packet(s) need "
                    "conductor owner/predicate routing before lane dispatch can claim prompt progress."
                ),
            }
        )

    if not always_working.get("present"):
        blockers.append(
            {
                "id": "always-working-reconciliation-missing",
                "evidence": "No current always-working reconciliation receipt is available.",
            }
        )
    elif int(always_working.get("required_open_count") or 0):
        blockers.append(
            {
                "id": "always-working-required-work-open",
                "evidence": (
                    f"{always_working.get('required_open_count')} required promise workstream(s) remain open; "
                    f"next item {always_working.get('next_item_id') or 'unknown'}."
                ),
            }
        )

    return blockers


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    plist = read_plist(HEARTBEAT_PLIST)
    launchd = launchd_snapshot()
    snapshot: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_heartbeat_plist": generated_plist_snapshot(),
        "heartbeat_plist": plist,
        "launchd": launchd,
        "live_root_git": git_snapshot(LIVE_ROOT),
        "verified_worktree": git_snapshot(ROOT),
        "watchdog": watchdog_snapshot(),
        "async_probe": async_probe_snapshot(bool(args.probe_async), launchd=launchd, plist=plist),
        "prompt_packets": prompt_packet_snapshot(),
        "always_working": always_working_snapshot(),
    }
    blockers = derive_blockers(snapshot)
    snapshot["blockers"] = blockers
    snapshot["status"] = "healthy" if not blockers else "blocked"
    return snapshot


def render_markdown(snapshot: dict[str, Any]) -> str:
    generated = snapshot["generated_heartbeat_plist"]
    plist = snapshot["heartbeat_plist"]
    loaded = snapshot["launchd"]
    live = snapshot["live_root_git"]
    verified = snapshot["verified_worktree"]
    watchdog = snapshot["watchdog"]
    async_probe = snapshot["async_probe"]
    prompt_packets = snapshot["prompt_packets"]
    always_working = snapshot["always_working"]
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
        f"- Generated plist probe: `{generated.get('present')}` from `{relpath(Path(generated.get('path') or ''))}`.",
        f"- Generated LIMEN_WORKTREES: `{(generated.get('env') or {}).get('LIMEN_WORKTREES')}`.",
        f"- Generated LIMEN_WORKTREE_ROOT: `{(generated.get('env') or {}).get('LIMEN_WORKTREE_ROOT')}`.",
        f"- Generated LIMEN_DISPATCH_ASYNC: `{(generated.get('env') or {}).get('LIMEN_DISPATCH_ASYNC')}`.",
        f"- Generated LIMEN_ASYNC_MAX: `{(generated.get('env') or {}).get('LIMEN_ASYNC_MAX')}`.",
        f"- LaunchAgent plist: `{relpath(Path(plist.get('path') or HEARTBEAT_PLIST))}` present `{plist.get('present')}`.",
        f"- Plist KeepAlive: `{plist.get('keep_alive')}`; RunAtLoad: `{plist.get('run_at_load')}`.",
        f"- Plist LIMEN_ROOT: `{(plist.get('env') or {}).get('LIMEN_ROOT')}`.",
        f"- Plist LIMEN_WORKTREES: `{(plist.get('env') or {}).get('LIMEN_WORKTREES')}`.",
        f"- Plist LIMEN_WORKTREE_ROOT: `{(plist.get('env') or {}).get('LIMEN_WORKTREE_ROOT')}`.",
        f"- Plist LIMEN_DISPATCH_ASYNC: `{(plist.get('env') or {}).get('LIMEN_DISPATCH_ASYNC')}`.",
        f"- Plist LIMEN_DISPATCH_LANES: `{(plist.get('env') or {}).get('LIMEN_DISPATCH_LANES')}`.",
        f"- Plist LIMEN_ASYNC_MAX: `{(plist.get('env') or {}).get('LIMEN_ASYNC_MAX')}`.",
        f"- Plist LIMEN_LANES: `{(plist.get('env') or {}).get('LIMEN_LANES')}`.",
        f"- Loaded launchd state: `{loaded.get('state')}` pid `{loaded.get('pid')}`.",
        f"- Loaded LIMEN_ROOT: `{(loaded.get('env') or {}).get('LIMEN_ROOT')}`.",
        f"- Loaded LIMEN_WORKTREES: `{(loaded.get('env') or {}).get('LIMEN_WORKTREES')}`.",
        f"- Loaded LIMEN_WORKTREE_ROOT: `{(loaded.get('env') or {}).get('LIMEN_WORKTREE_ROOT')}`.",
        f"- Loaded LIMEN_DISPATCH_ASYNC: `{(loaded.get('env') or {}).get('LIMEN_DISPATCH_ASYNC')}`.",
        f"- Loaded LIMEN_DISPATCH_LANES: `{(loaded.get('env') or {}).get('LIMEN_DISPATCH_LANES')}`.",
        f"- Loaded LIMEN_ASYNC_MAX: `{(loaded.get('env') or {}).get('LIMEN_ASYNC_MAX')}`.",
        f"- Loaded LIMEN_LANES: `{(loaded.get('env') or {}).get('LIMEN_LANES')}`.",
        f"- Watchdog dry-run healthy: `{watchdog.get('healthy')}`; `{watchdog.get('first_line')}`.",
        "",
        "## Async Dispatch",
        "",
        f"- Async dry-run requested: `{async_probe.get('requested')}`.",
        f"- Async dry-run lanes: `{async_probe.get('lanes', '')}`; max `{async_probe.get('max', '')}`.",
        f"- Async dry-run ok: `{async_probe.get('ok')}`; timed out `{async_probe.get('timed_out', False)}`.",
        f"- Async dry-run summary: `{async_probe.get('last_line', '')}`.",
    ]
    skipped_down_lanes = async_probe.get("skipped_down_lanes") or []
    if skipped_down_lanes:
        lines.append(f"- Async skipped down lanes: `{', '.join(str(lane) for lane in skipped_down_lanes)}`.")
        skipped_down_reasons = async_probe.get("skipped_down_reasons") or {}
        for lane in skipped_down_lanes:
            lane_name = str(lane)
            reason = skipped_down_reasons.get(lane_name)
            if isinstance(reason, dict):
                lines.append(f"  - {render_skipped_lane_reason(lane_name, reason)}")

    lines += [
        "",
        "## Prompt Packet Gate",
        "",
        f"- Prompt packet index present: `{prompt_packets.get('present')}`.",
        f"- Prompt packet status: `{prompt_packets.get('status')}`.",
        f"- Open prompt packets: `{prompt_packets.get('open_packets')}`.",
        f"- Conductor-required packets: `{prompt_packets.get('conductor_required_packets')}`.",
        f"- Ready-after-predicate packets: `{prompt_packets.get('ready_after_predicate_packets')}`.",
        f"- Recorded packets: `{prompt_packets.get('recorded_packets')}`.",
        f"- Public packet ledger: `{relpath(Path(prompt_packets.get('public_doc') or PROMPT_PACKET_DOC))}`.",
    ]
    for packet in prompt_packets.get("top_open_packets") or []:
        lines.append(
            f"  - `{packet.get('id')}`: `{packet.get('dispatchability')}`; "
            f"{packet.get('agent_fit') or 'no agent fit recorded'}."
        )

    lines += [
        "",
        "## Always-Working Gate",
        "",
        f"- Reconciliation index present: `{always_working.get('present')}`.",
        f"- Reconciliation status: `{always_working.get('status')}`.",
        f"- Required open workstreams: `{always_working.get('required_open_count')}`.",
        f"- Blocked workstreams: `{always_working.get('blocked_count')}`.",
        f"- Done from receipt: `{always_working.get('done_count')}`.",
        f"- Next item: `{always_working.get('next_item_id')}` (`{always_working.get('next_item_status')}`).",
        f"- Public reconciliation: `{relpath(Path(always_working.get('public_doc') or ALWAYS_WORKING_DOC))}`.",
    ]
    for item in always_working.get("top_required_items") or []:
        lines.append(
            f"  - `{item.get('id')}`: `{item.get('workstream')}` / `{item.get('status')}`; "
            f"{item.get('verdict') or 'no verdict'}."
        )

    lines += [
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
    if live.get("ignored_dirty_entries"):
        lines.append(f"- Ignored generated receipt dirty entries: `{live.get('ignored_dirty_entries')}`.")
        for path in live.get("ignored_dirty_paths") or []:
            lines.append(f"  - `{path}`")
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
        "- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`",
        "- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`",
        "- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`",
        "- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`",
        "- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`",
        f"- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes {async_probe.get('lanes') or 'auto'} --per-lane 3 --max {async_probe.get('max') or _host_local_ceiling()} --dry-run`",
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
