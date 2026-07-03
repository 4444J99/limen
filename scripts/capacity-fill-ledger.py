#!/usr/bin/env python3
"""Refresh the Claude-capacity fill ledger for lane productivity triage.

The command writes:
- `docs/capacity-fill.md`: redacted capacity census for operators
- `.limen-private/session-corpus/lifecycle/capacity-fill.json`: private structured snapshot

It is intentionally read-only with respect to tasks/credentials/auth/deploy gates: this only
re-derives reachability and remaining lane headroom from local receipts and configuration.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "capacity-fill.json"
TASKS_PATH = ROOT / "tasks.yaml"

sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import capacity_census  # noqa: E402



def load_tasks_board() -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError:
        return {}
    try:
        return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_display(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


def signal_quality(agent: str) -> dict[str, str]:
    opencode_clock = HOME / ".local" / "share" / "opencode" / "clock.json"
    rows: dict[str, dict[str, str]] = {
        "codex": {
            "signal": "transcript-token estimate",
            "trust": "estimate",
            "use": "usable for pacing; tune cap against plan status",
            "next_build": "Calibrate OpenAI plan pool cap from a trusted account meter.",
        },
        "claude": {
            "signal": "transcript-token estimate",
            "trust": "estimate",
            "use": "usable for pacing; rate-limit events still dominate stop decisions",
            "next_build": "Calibrate Claude plan pool cap from a trusted account meter.",
        },
        "opencode": {
            "signal": "db-meter" if opencode_clock.exists() else "dispatch-count proxy",
            "trust": "measured" if opencode_clock.exists() else "proxy",
            "use": "best local paid-lane signal when the DB clock is present",
            "next_build": "Keep opencode-clock fresh from the SQLite usage DB.",
        },
        "agy": {
            "signal": "dispatch-count proxy",
            "trust": "proxy",
            "use": "reachable, but not proof of provider quota",
            "next_build": "Add a provider-backed Agy meter or recent rate-limit receipt.",
        },
        "gemini": {
            "signal": "dispatch-count proxy",
            "trust": "proxy",
            "use": "reachable when auth is configured; daily cap remains board-derived",
            "next_build": "Add a Gemini quota/rate-limit receipt if available.",
        },
        "github_actions": {
            "signal": "workflow reachability",
            "trust": "reachability",
            "use": "can launch workflow packets; not a local quota meter",
            "next_build": "Surface queued/running workflow capacity from GitHub checks.",
        },
        "ollama": {
            "signal": "local model presence",
            "trust": "binary/model",
            "use": "down until a model is pulled",
            "next_build": "Pull the configured local model to light the floor lane.",
        },
        "jules": {
            "signal": "dispatch-count cap",
            "trust": "known cap",
            "use": "down locally until CLI/service path is available",
            "next_build": "Restore Jules CLI/service reachability.",
        },
        "copilot": {
            "signal": "assignability probe",
            "trust": "reachability",
            "use": "down until Copilot coding agent assignment is confirmed",
            "next_build": "Enable Copilot coding agent and set LIMEN_COPILOT_ENABLED=1.",
        },
        "warp": {
            "signal": "credential presence",
            "trust": "credential gate",
            "use": "down until WARP_API_KEY is installed",
            "next_build": "Install WARP_API_KEY locally and as the workflow secret.",
        },
        "oz": {
            "signal": "credential presence",
            "trust": "credential gate",
            "use": "down until WARP_API_KEY is installed",
            "next_build": "Install WARP_API_KEY locally and as the workflow secret.",
        },
    }
    return rows.get(
        agent,
        {
            "signal": "unknown",
            "trust": "unknown",
            "use": "not enough local signal",
            "next_build": "Define this lane in the capacity signal table.",
        },
    )


def build_snapshot(board: dict[str, Any]) -> dict[str, Any]:
    census = capacity_census(board)
    blocked = [row for row in census if not row["reachable"]]
    claude = next((row for row in census if row["agent"] == "claude"), None)
    signals = {row["agent"]: signal_quality(row["agent"]) for row in census}
    return {
        "generated_at": now_iso(),
        "status": "healthy" if not blocked else "blocked",
        "census": census,
        "signals": signals,
        "blocked_count": len(blocked),
        "blocked_agents": [row["agent"] for row in blocked],
        "blocked_details": {row["agent"]: row["detail"] for row in blocked},
        "claude": claude,
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    census = snapshot["census"]
    blocked_agents = snapshot["blocked_agents"]
    blocked_count = snapshot["blocked_count"]

    lines = [
        "# Capacity Fill",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        "",
        "## Capacity Census",
        "",
        "| Agent | Kind | Reachable | Remaining | Limit | Detail |",
        "|---|---|---|---|---|---|",
    ]

    for row in census:
        remaining = "unlimited" if row["remaining"] is None else str(row["remaining"])
        limit = "unlimited" if row["limit"] is None else str(row["limit"])
        reachable = "up" if row["reachable"] else "down"
        detail = str(row["detail"]).replace("|", "\\|")
        lines.append(f"| `{row['agent']}` | {row['kind']} | `{reachable}` | {remaining} | {limit} | {detail} |")

    lines += [
        "",
        "## Signal Quality",
        "",
        "| Agent | Signal | Trust | Use | Next Build |",
        "|---|---|---|---|---|",
    ]
    signals = snapshot.get("signals") or {}
    for row in census:
        signal = signals.get(row["agent"]) or {}
        lines.append(
            "| "
            f"`{row['agent']}` | "
            f"{str(signal.get('signal', 'unknown')).replace('|', '\\|')} | "
            f"{str(signal.get('trust', 'unknown')).replace('|', '\\|')} | "
            f"{str(signal.get('use', '')).replace('|', '\\|')} | "
            f"{str(signal.get('next_build', '')).replace('|', '\\|')} |"
        )

    lines += [
        "",
        "## Blockers",
        "",
    ]
    if blocked_agents:
        for agent in blocked_agents:
            lines.append(f"- `{agent}`: {snapshot['blocked_details'].get(agent, 'unreachable')}")
    else:
        lines.append("- none")

    claude = snapshot["claude"]
    if claude:
        lines += [
            "",
            "## Claude",
            "",
            f"- Binary/path reachable: `{claude['reachable']}`.",
            f"- Remaining capacity: `{claude['remaining'] if claude['remaining'] is not None else 'unlimited'}`.",
            f"- Limit: `{claude['limit'] if claude['limit'] is not None else 'unlimited'}`.",
            f"- Detail: {claude['detail']}.",
            "",
        ]

    if blocked_count:
        route = (
            "Run `python3 scripts/dispatch-health.py --write --probe-async` for a heartbeat/operator snapshot,"
            " then re-run `python3 scripts/capacity-fill-ledger.py --write` after repairs."
        )
    else:
        route = (
            "Capacity census is green for active lanes. Continue normal dispatch/board work and monitor this"
            " file as a capacity fill checkpoint."
        )

    lines += [
        "## Contract",
        "",
        "- This ledger does not modify tasks, credentials, workflow state, or remote systems.",
        f"- {route}",
        "",
        "## Commands",
        "",
        "- Refresh this ledger: `python3 scripts/capacity-fill-ledger.py --write`",
        "- Refresh dispatch heartbeat: `python3 scripts/dispatch-health.py --write --probe-async`",
    ]

    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the capacity fill ledger.")
    parser.add_argument("--write", action="store_true", help="write tracked markdown and private JSON")
    args = parser.parse_args()

    board = load_tasks_board()
    snapshot = build_snapshot(board)
    markdown = render_markdown(snapshot)

    if args.write:
        write_outputs(snapshot, markdown)
        print(f"capacity-fill-ledger: {snapshot['status']} with {snapshot['blocked_count']} blockers; wrote {DOC_PATH}")
    else:
        print(markdown, end="")
        print(f"capacity-fill-ledger: {snapshot['status']} with {snapshot['blocked_count']} blockers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
