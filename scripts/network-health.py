#!/usr/bin/env python3
"""Record local network-substrate health without changing routes or agents.

This is the durable receipt for the netmode/netmeter incident class: a legacy
LaunchAgent may keep running `netmode tick` and move links behind a session's
back. The script checks static safety gates plus redacted live launchd state,
then writes:

* a tracked Markdown receipt;
* an ignored private JSON receipt.

It never writes LaunchAgent state, never runs `netmode stop`, and never reads or
prints the untracked netmode config.
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
DOC_PATH = ROOT / "docs" / "network-health.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "network-health.json"
NETMODE_SCRIPT = ROOT / "scripts" / "netmode.sh"
NETMETER_PLIST = ROOT / "container" / "launchd" / "com.user.netmeter.plist"
LIVE_NETMODE_SCRIPT = HOME / "Library" / "Application Support" / "netmeter" / "netmode.sh"
LIVE_MODE_FILE = HOME / "Library" / "Application Support" / "netmeter" / "mode"
NETMODE_LABELS = (
    "com.user.netmeter",
    "com.user.netmode.netwatch",
    "com.user.netmode.keepalive",
    "com.user.netmode.recycle",
)


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def display_path(path: Path) -> str:
    try:
        return str(path.expanduser().resolve().relative_to(ROOT.resolve()))
    except (OSError, ValueError):
        return relpath(path)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def run_command(args: list[str], *, timeout: int = 10) -> dict[str, Any]:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"args": args, "returncode": 127, "stdout": "", "stderr": str(exc), "timed_out": True}
    return {
        "args": args,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": False,
    }


def netmode_static_checks(path: Path) -> dict[str, Any]:
    text = read_text(path)
    checks = {
        "present": bool(text),
        "background_switching_default_off": "BACKGROUND_SWITCHING=0" in text,
        "background_switching_guard": "if background_switching_enabled; then" in text,
        "observe_mode_default": "get_mode()" in text and "echo \"observe\"" in text,
        "stop_or_panic_command": "stop|panic) stop_agents" in text,
        "tick_observe_selftest": "tick observe-only does not call switch actuators" in text,
        "switch_optin_selftest": "tick switching can be explicitly opted in" in text,
    }
    missing = [name for name, ok in checks.items() if not ok]
    return {"path": str(path), "checks": checks, "ok": not missing, "missing": missing}


def netmeter_plist_snapshot(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            obj = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError) as exc:
        return {"path": str(path), "present": False, "ok": False, "error": str(exc)}
    program = obj.get("ProgramArguments") or []
    checks = {
        "present": True,
        "label_is_legacy_netmeter": obj.get("Label") == "com.user.netmeter",
        "run_at_load_false": obj.get("RunAtLoad") is False,
        "disabled_true": obj.get("Disabled") is True,
        "tick_program": "netmode.sh" in " ".join(str(part) for part in program) and "tick" in program,
    }
    missing = [name for name, ok in checks.items() if not ok]
    return {
        "path": str(path),
        "checks": checks,
        "ok": not missing,
        "missing": missing,
        "start_interval": obj.get("StartInterval"),
    }


def parse_disabled(stdout: str) -> dict[str, bool]:
    disabled: dict[str, bool] = {}
    pattern = re.compile(r'"([^"]+)"\s*=>\s*(true|false|disabled|enabled)')
    for line in stdout.splitlines():
        match = pattern.search(line)
        if match:
            disabled[match.group(1)] = match.group(2) in {"true", "disabled"}
    return disabled


def launchd_snapshot() -> dict[str, Any]:
    uid = os.getuid()
    disabled_result = run_command(["launchctl", "print-disabled", f"gui/{uid}"], timeout=10)
    disabled_map = parse_disabled(disabled_result.get("stdout") or "") if disabled_result["returncode"] == 0 else {}
    list_result = run_command(["launchctl", "list"], timeout=10)
    loaded_labels = set()
    if list_result["returncode"] == 0:
        for line in (list_result.get("stdout") or "").splitlines():
            for label in NETMODE_LABELS:
                if label in line:
                    loaded_labels.add(label)
    return {
        "disabled_probe": {
            "returncode": disabled_result["returncode"],
            "timed_out": disabled_result["timed_out"],
        },
        "list_probe": {"returncode": list_result["returncode"], "timed_out": list_result["timed_out"]},
        "labels": {
            label: {
                "disabled": disabled_map.get(label),
                "loaded": label in loaded_labels,
            }
            for label in NETMODE_LABELS
        },
    }


def mode_snapshot() -> dict[str, Any]:
    raw = read_text(LIVE_MODE_FILE).splitlines()
    mode = raw[0].strip() if raw else None
    allowed = {"observe", "seamless", "auto", "failover", "anchor", "solo", "ladder", "phone"}
    return {"path": str(LIVE_MODE_FILE), "mode": mode, "known": mode in allowed if mode else False}


def route_snapshot() -> dict[str, Any]:
    result = run_command(["route", "-n", "get", "default"], timeout=10)
    route: dict[str, Any] = {"returncode": result["returncode"], "timed_out": result["timed_out"]}
    for line in (result.get("stdout") or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("gateway:"):
            route["gateway"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("interface:"):
            route["interface"] = stripped.split(":", 1)[1].strip()
    return route


def derive_blockers(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not snapshot["tracked_netmode"]["ok"]:
        blockers.append(
            {
                "id": "network-netmode-static-safety-missing",
                "evidence": "Tracked scripts/netmode.sh is missing observe-only tick safety markers.",
                "details": snapshot["tracked_netmode"].get("missing") or [],
            }
        )
    if not snapshot["netmeter_plist"]["ok"]:
        blockers.append(
            {
                "id": "network-netmeter-plist-enabled",
                "evidence": "Legacy com.user.netmeter LaunchAgent template is not disabled/read-only safe.",
                "details": snapshot["netmeter_plist"].get("missing") or [snapshot["netmeter_plist"].get("error")],
            }
        )
    live = snapshot["live_netmode"]
    if live["checks"].get("present") and not live["ok"]:
        blockers.append(
            {
                "id": "network-live-netmode-script-stale",
                "evidence": "Live installed netmode.sh is missing the tracked observe-only safety markers.",
                "details": live.get("missing") or [],
            }
        )
    legacy = snapshot["launchd"]["labels"].get("com.user.netmeter") or {}
    if legacy.get("loaded") or legacy.get("disabled") is False:
        blockers.append(
            {
                "id": "network-legacy-netmeter-agent-active",
                "evidence": "Legacy com.user.netmeter is still loaded or explicitly enabled in launchd.",
                "details": legacy,
            }
        )
    return blockers


def build_snapshot() -> dict[str, Any]:
    snapshot = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tracked_netmode": netmode_static_checks(NETMODE_SCRIPT),
        "live_netmode": netmode_static_checks(LIVE_NETMODE_SCRIPT),
        "netmeter_plist": netmeter_plist_snapshot(NETMETER_PLIST),
        "launchd": launchd_snapshot(),
        "mode": mode_snapshot(),
        "route": route_snapshot(),
        "private_index": str(PRIVATE_INDEX),
    }
    blockers = derive_blockers(snapshot)
    snapshot["blockers"] = blockers
    snapshot["status"] = "healthy" if not blockers else "needs_attention"
    return snapshot


def bool_cell(value: Any) -> str:
    if value is True:
        return "`true`"
    if value is False:
        return "`false`"
    return "`unknown`"


def render_markdown(snapshot: dict[str, Any]) -> str:
    tracked = snapshot["tracked_netmode"]
    live = snapshot["live_netmode"]
    plist = snapshot["netmeter_plist"]
    route = snapshot["route"]
    mode = snapshot["mode"]
    launchd = snapshot["launchd"]["labels"]
    lines = [
        "# Network Health",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        f"Status: `{snapshot['status']}`",
        "",
        "## Scope",
        "",
        "- Records the netmode/netmeter launchd safety state after the legacy timer incident.",
        "- Read-only: no route changes, no launchctl writes, no credential/config reads, no agent stops.",
        "- The netmode config file may contain local SSIDs or provider details and is intentionally not printed.",
        "",
        "## Incident Class",
        "",
        "- This is not only a current connectivity receipt. It is a guard against the single-lane failure mode: one agent patches one symptom, leaves no reusable gate, and the next lane rediscovers the same substrate problem.",
        "- A network/environment repair is not closed until the tracked code, live installed path, launchd state, and conductor blocker surface all agree on the invariant.",
        "- Future lanes should treat a failed network-health receipt as substrate work first, not as incidental flakiness inside an unrelated task.",
        "",
        "## Live State",
        "",
        f"- Mode file: `{mode.get('mode') or 'unknown'}` at `{relpath(Path(mode['path']))}`.",
        (
            "- Default route: "
            f"`{route.get('interface', 'unknown')}` via `{route.get('gateway', 'unknown')}` "
            f"(probe rc `{route.get('returncode')}`)."
        ),
        "",
        "## Safety Gates",
        "",
        "| Gate | Status | Evidence |",
        "|---|---:|---|",
        f"| Tracked netmode observe-only tick gate | {bool_cell(tracked.get('ok'))} | `{display_path(Path(tracked['path']))}` missing: `{', '.join(tracked.get('missing') or []) or 'none'}` |",
        f"| Live installed netmode observe-only tick gate | {bool_cell(live.get('ok'))} | `{display_path(Path(live['path']))}` missing: `{', '.join(live.get('missing') or []) or 'none'}` |",
        f"| Legacy netmeter plist disabled | {bool_cell(plist.get('ok'))} | `{display_path(Path(plist['path']))}` missing: `{', '.join(plist.get('missing') or []) or 'none'}` |",
        "",
        "## Launchd Labels",
        "",
        "| Label | Disabled | Loaded |",
        "|---|---:|---:|",
    ]
    for label in NETMODE_LABELS:
        state = launchd.get(label) or {}
        lines.append(f"| `{label}` | {bool_cell(state.get('disabled'))} | {bool_cell(state.get('loaded'))} |")

    lines += [
        "",
        "## Blockers",
        "",
    ]
    blockers = snapshot.get("blockers") or []
    if blockers:
        for blocker in blockers:
            lines.append(f"- `{blocker['id']}`: {blocker['evidence']}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Verification",
        "",
        "- `bash -n scripts/netmode.sh`",
        "- `bash scripts/netmode.sh selftest`",
        "- `plutil -lint container/launchd/com.user.netmeter.plist`",
        "- `python3 scripts/network-health.py --write`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the local network health receipt.")
    parser.add_argument("--write", action="store_true", help="write tracked and private receipts")
    args = parser.parse_args()
    snapshot = build_snapshot()
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = f"network-health: {snapshot['status']} with {len(snapshot.get('blockers') or [])} blockers"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
