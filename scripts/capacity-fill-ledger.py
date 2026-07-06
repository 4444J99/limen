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
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "capacity-fill.json"
TASKS_PATH = ROOT / "tasks.yaml"
USAGE_PATH = ROOT / "logs" / "usage.json"
OLLAMA_MIN_PULL_FREE_GIB = 50.0
RATE_LIMIT_TAIL_LINES = 400

sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import capacity_census  # noqa: E402
from limen.dispatch import _reset_budget_if_needed  # noqa: E402
from limen.io import load_limen_file  # noqa: E402


def load_tasks_board() -> dict[str, Any]:
    try:
        lf = load_limen_file(TASKS_PATH)
        _reset_budget_if_needed(lf, dt.datetime.now(dt.timezone.utc))
        return lf.model_dump(mode="json", exclude_none=True)
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


def disk_free_gib(path: Path = HOME) -> float | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return round(usage.free / (1024**3), 1)


def ollama_next_build() -> str:
    free_gib = disk_free_gib()
    if free_gib is not None and free_gib < OLLAMA_MIN_PULL_FREE_GIB:
        return f"Clear local disk pressure before pulling qwen2.5-coder:7b; current free space is {free_gib:g} GiB."
    return "Pull the configured local model to light the floor lane."


def ollama_capacity_detail(detail: str) -> str:
    free_gib = disk_free_gib()
    if free_gib is None or free_gib >= OLLAMA_MIN_PULL_FREE_GIB:
        return detail
    base = detail.split("; no model pulled", 1)[0]
    return (
        f"{base}; no model pulled; local disk pressure blocks qwen2.5-coder:7b pull "
        f"({free_gib:g} GiB free, need >= {OLLAMA_MIN_PULL_FREE_GIB:g} GiB)"
    )


def read_opencode_clock() -> dict[str, Any] | None:
    path = HOME / ".local" / "share" / "opencode" / "clock.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def read_usage_snapshot() -> dict[str, Any] | None:
    try:
        value = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def usage_vendor(agent: str) -> dict[str, Any] | None:
    snapshot = read_usage_snapshot()
    vendors = snapshot.get("vendors") if isinstance(snapshot, dict) else None
    if not isinstance(vendors, dict):
        return None
    value = vendors.get(agent)
    return value if isinstance(value, dict) else None


def usage_signal_detail(agent: str) -> str | None:
    vendor = usage_vendor(agent)
    if not vendor:
        return None

    parts: list[str] = []
    health = vendor.get("health")
    if health:
        parts.append(f"usage health={health}")

    consumed = vendor.get("consumed")
    possible = vendor.get("possible")
    unit = str(vendor.get("unit") or "").strip()
    unit_suffix = f" {unit}" if unit else ""
    if consumed is not None:
        if possible not in (None, ""):
            parts.append(f"used={consumed}/{possible}{unit_suffix}")
        else:
            parts.append(f"used={consumed}{unit_suffix}")

    remaining = vendor.get("remaining")
    if remaining is not None:
        parts.append(f"remaining={remaining}")

    headroom = vendor.get("headroom_pct")
    if headroom is not None:
        parts.append(f"headroom={headroom}%")

    weekly = vendor.get("weekly_used_percent")
    if weekly is not None:
        parts.append(f"weekly={weekly}%")

    limit_source = str(vendor.get("limit_source") or "").strip()
    if limit_source:
        parts.append(f"source={limit_source}")

    signal = vendor.get("signal")
    if signal and not parts:
        parts.append(f"usage signal={signal}")

    return "; ".join(parts) if parts else None


def opencode_signal_quality() -> dict[str, str]:
    clock = read_opencode_clock()
    if not clock:
        usage = usage_signal_detail("opencode")
        return {
            "signal": "dispatch-count proxy",
            "trust": "proxy",
            "use": (
                f"{usage}; usable only as a dispatch-count fallback until opencode-clock writes its DB meter"
                if usage
                else "usable only as a dispatch-count fallback until opencode-clock writes its DB meter"
            ),
            "next_build": "Restore opencode-clock so the SQLite usage DB emits clock.json.",
        }
    health = str(clock.get("health", "unknown"))
    used = clock.get("used_pct", "unknown")
    accepting = clock.get("accepting_tasks", "unknown")
    updated = str(clock.get("updated_at") or clock.get("heartbeat") or "unknown")
    usage = usage_signal_detail("opencode")
    use = f"token clock health={health}; used={used}%; accepting_tasks={accepting}; updated={updated}"
    if usage:
        use = f"{use}; {usage}"
    return {
        "signal": "db-meter",
        "trust": "measured",
        "use": use,
        "next_build": "Keep opencode-clock fresh from the SQLite usage DB.",
    }


def recent_rate_limit(agent: str, tail_lines: int = RATE_LIMIT_TAIL_LINES) -> bool:
    log = ROOT / "logs" / "heartbeat.out.log"
    try:
        lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()[-tail_lines:]
    except OSError:
        return False
    pattern = re.compile(rf"\bRATE-LIMIT\s+{re.escape(agent)}\b")
    return any(pattern.search(line) for line in lines)


def rate_limit_watch(agent: str) -> str:
    if recent_rate_limit(agent):
        return "recent heartbeat rate-limit marker present"
    return "no recent heartbeat rate-limit marker"


def signal_use(agent: str, fallback: str) -> str:
    usage = usage_signal_detail(agent)
    if not usage:
        return fallback
    return f"{usage}; {fallback}"


def codex_signal_quality() -> dict[str, str]:
    vendor = usage_vendor("codex")
    signal = str((vendor or {}).get("signal") or "").strip()
    if signal == "vendor-rate-limit":
        return {
            "signal": "vendor rate-limit meter",
            "trust": "measured",
            "use": signal_use(
                "codex",
                "usable for pacing from provider rate_limits; weekly plan headroom is a steering input",
            ),
            "next_build": "Keep harvesting Codex vendor rate_limits into usage telemetry.",
        }
    return {
        "signal": "transcript-token estimate",
        "trust": "estimate",
        "use": signal_use("codex", "usable for pacing; tune cap against plan status"),
        "next_build": "Calibrate OpenAI plan pool cap from a trusted account meter.",
    }


def signal_quality(agent: str) -> dict[str, str]:
    agy_usage = usage_signal_detail("agy")
    gemini_usage = usage_signal_detail("gemini")
    jules_usage = usage_signal_detail("jules")
    rows: dict[str, dict[str, str]] = {
        "codex": codex_signal_quality(),
        "claude": {
            "signal": "transcript-token estimate",
            "trust": "estimate",
            "use": signal_use(
                "claude",
                "usable for pacing; rate-limit events still dominate stop decisions",
            ),
            "next_build": "Calibrate Claude plan pool cap from a trusted account meter.",
        },
        "opencode": opencode_signal_quality(),
        "agy": {
            "signal": "usage-telemetry proxy" if agy_usage else "dispatch-count proxy",
            "trust": "proxy + recent-rl" if agy_usage else "proxy",
            "use": signal_use(
                "agy",
                f"reachable; {rate_limit_watch('agy')}; not proof of provider quota",
            ),
            "next_build": "Add a provider-backed Agy meter or recent rate-limit receipt.",
        },
        "gemini": {
            "signal": "usage-telemetry proxy" if gemini_usage else "dispatch-count proxy",
            "trust": "proxy + recent-rl" if gemini_usage else "proxy",
            "use": signal_use(
                "gemini",
                f"reachable when auth is configured; {rate_limit_watch('gemini')}; daily cap remains board-derived",
            ),
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
            "next_build": ollama_next_build(),
        },
        "jules": {
            "signal": "usage-telemetry proxy" if jules_usage else "dispatch-count cap",
            "trust": "proxy + known cap" if jules_usage else "known cap",
            "use": signal_use(
                "jules",
                f"remote async service; {rate_limit_watch('jules')}; use for remote batch fill",
            ),
            "next_build": "Keep Jules remote-launch receipts and harvest status fresh.",
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
    census = [dict(row) for row in capacity_census(board)]
    for row in census:
        if row.get("agent") == "ollama" and not row.get("reachable"):
            row["detail"] = ollama_capacity_detail(str(row.get("detail", "unreachable")))
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
        # Hoist the pipe-escape out of the f-string braces (matches the census loop
        # above): a backslash inside an f-string expression is a SyntaxError on
        # Python 3.11 (PEP 701 only lifts that on 3.12+), and CI runs both.
        sig = str(signal.get("signal", "unknown")).replace("|", "\\|")
        trust = str(signal.get("trust", "unknown")).replace("|", "\\|")
        use = str(signal.get("use", "")).replace("|", "\\|")
        nxt = str(signal.get("next_build", "")).replace("|", "\\|")
        lines.append(f"| `{row['agent']}` | {sig} | {trust} | {use} | {nxt} |")

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
