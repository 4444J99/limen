#!/usr/bin/env python3
"""Summarize Codex token_count events and enforce bounded-session budgets.

The Codex JSONL stream emits structured event_msg/payload.type=token_count rows.
This script reads those rows directly, reports per-session cumulative totals and
per-event deltas, and can fail when a recent session exceeds configured budgets.

The budget metric intentionally ignores cached input:

    budget_tokens = uncached_input_tokens + output_tokens + reasoning_output_tokens

Cached replay can dominate raw totals without indicating fresh spend; uncached
input plus generated/reasoning output is the operator-facing waste signal.

Active vs. historical failures
------------------------------
A session's over-budget-ness is a permanent, append-only fact: once a JSONL
records a runaway session it stays over budget forever. A gate that blocks on
*any* recent over-budget session therefore lets one finished burn poison every
unrelated receipt-safe continuation until the file ages out of the report
window -- cross-session contamination. So failures are split by liveness:

    active_failures     -- fresh session still over budget => something is
                           burning right now; a circuit breaker should trip.
    historical_failures -- a finished session that went over budget; keep it
                           visible (report ``status`` stays ``fail``) but do NOT
                           block on it.

``--fail-on-budget`` exits non-zero on any failure (strict; CI / manual audit).
``--fail-on-active-budget`` exits non-zero only on ``active_failures`` -- the
right signal for the continuation beat's backpressure breaker.

Liveness is keyed on the newest in-band ``token_count`` timestamp, with the
session file's mtime only as a compatibility fallback when no token timestamp is
available. This keeps shell/tool polling, receipt generation, and closeout log
collection from making a finished over-budget transcript look like a live model
runaway. A genuine active runaway still emits fresh token_count events, which is
the signal this breaker exists to stop.

If a session has a terminal ``task_complete`` event after its newest token event,
it is immediately historical. Do not make the operator wait for an arbitrary
age-out window once the harness has already recorded that the task ended.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
HOME = Path(os.environ.get("HOME", str(Path.home())))
DEFAULT_SESSIONS_ROOT = HOME / ".codex" / "sessions"
DEFAULT_OUTPUT = ROOT / "logs" / "codex-token-report.json"
CODEX_RESUME_RE = re.compile(r"\bcodex\s+exec\s+resume\s+([0-9a-f][0-9a-f-]{20,})\b")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def normalize_usage(raw: dict[str, Any] | None) -> dict[str, int]:
    raw = raw or {}
    input_tokens = as_int(raw.get("input_tokens"))
    cached_input_tokens = as_int(raw.get("cached_input_tokens"))
    output_tokens = as_int(raw.get("output_tokens"))
    reasoning_output_tokens = as_int(raw.get("reasoning_output_tokens"))
    total_tokens = as_int(raw.get("total_tokens")) or input_tokens + output_tokens
    uncached_input_tokens = max(0, input_tokens - cached_input_tokens)
    budget_tokens = uncached_input_tokens + output_tokens + reasoning_output_tokens
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
        "budget_tokens": budget_tokens,
    }


def delta_usage(current: dict[str, int], previous: dict[str, int] | None) -> dict[str, int]:
    if previous is None:
        return dict(current)
    delta = {key: max(0, current.get(key, 0) - previous.get(key, 0)) for key in current}
    delta["uncached_input_tokens"] = max(
        0,
        delta.get("input_tokens", 0) - delta.get("cached_input_tokens", 0),
    )
    delta["budget_tokens"] = (
        delta.get("uncached_input_tokens", 0)
        + delta.get("output_tokens", 0)
        + delta.get("reasoning_output_tokens", 0)
    )
    return delta


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    try:
        with path.open(encoding="utf-8", errors="ignore") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield line_no, row
    except OSError:
        return


def session_id_from_path(path: Path) -> str:
    name = path.stem
    if name.startswith("rollout-"):
        return name[len("rollout-") :]
    return name


def summarize_session(path: Path, *, max_phases: int) -> dict[str, Any]:
    session_id = session_id_from_path(path)
    first_ts: dt.datetime | None = None
    last_ts: dt.datetime | None = None
    last_total: dict[str, int] | None = None
    phases: list[dict[str, Any]] = []
    token_events = 0
    missing_usage_events = 0
    context_window: int | None = None
    rate_limits: dict[str, Any] | None = None
    last_task_started_at: dt.datetime | None = None
    last_task_complete_at: dt.datetime | None = None

    for line_no, row in iter_jsonl(path):
        row_type = row.get("type")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if row_type == "session_meta" and isinstance(payload, dict):
            session_id = str(payload.get("id") or session_id)

        event_type = payload.get("type")
        timestamp = parse_ts(row.get("timestamp"))
        if event_type == "task_started" and timestamp is not None:
            last_task_started_at = timestamp
        elif event_type == "task_complete" and timestamp is not None:
            last_task_complete_at = timestamp

        if event_type != "token_count":
            continue

        token_events += 1
        if timestamp is not None:
            first_ts = timestamp if first_ts is None else min(first_ts, timestamp)
            last_ts = timestamp if last_ts is None else max(last_ts, timestamp)

        rate_limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else rate_limits
        info = payload.get("info")
        if not isinstance(info, dict):
            missing_usage_events += 1
            continue

        context_window = as_int(info.get("model_context_window")) or context_window
        cumulative = normalize_usage(info.get("total_token_usage"))
        raw_delta = info.get("last_token_usage")
        delta = normalize_usage(raw_delta) if isinstance(raw_delta, dict) else delta_usage(cumulative, last_total)
        last_total = cumulative
        phases.append(
            {
                "index": len(phases) + 1,
                "line": line_no,
                "timestamp": timestamp.isoformat(timespec="seconds") if timestamp else None,
                "delta": delta,
                "cumulative": cumulative,
            }
        )

    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds")
    except OSError:
        mtime = None

    elapsed_seconds = None
    if first_ts is not None and last_ts is not None:
        elapsed_seconds = int(max(0, (last_ts - first_ts).total_seconds()))

    totals = last_total or normalize_usage({})
    truncated = max(0, len(phases) - max_phases)
    if max_phases >= 0:
        phases = phases[-max_phases:] if max_phases else []

    return {
        "session_id": session_id,
        "path": str(path),
        "mtime": mtime,
        "first_token_at": first_ts.isoformat(timespec="seconds") if first_ts else None,
        "last_token_at": last_ts.isoformat(timespec="seconds") if last_ts else None,
        "last_task_started_at": last_task_started_at.isoformat(timespec="seconds") if last_task_started_at else None,
        "last_task_complete_at": last_task_complete_at.isoformat(timespec="seconds") if last_task_complete_at else None,
        "elapsed_seconds": elapsed_seconds,
        "token_count_events": token_events,
        "missing_usage_events": missing_usage_events,
        "model_context_window": context_window,
        "totals": totals,
        "phase_deltas": phases,
        "truncated_phase_deltas": truncated,
        "rate_limits": rate_limits,
    }


def expand_paths(paths: list[Path], sessions_root: Path) -> list[Path]:
    roots = paths or [sessions_root]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.jsonl"))
    unique = {path.resolve(): path for path in files if path.name.endswith(".jsonl")}
    return list(unique.values())


def filter_recent(files: list[Path], since_hours: float | None, limit: int | None) -> list[Path]:
    cutoff = None
    if since_hours is not None and since_hours > 0:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=since_hours)

    rows: list[tuple[float, Path]] = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        if cutoff is not None and dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc) < cutoff:
            continue
        rows.append((stat.st_mtime, path))
    rows.sort(key=lambda item: item[0], reverse=True)
    if limit is not None and limit > 0:
        rows = rows[:limit]
    return [path for _mtime, path in rows]


def thresholds_from_args(args: argparse.Namespace) -> dict[str, int]:
    return {
        "warn_uncached_input_tokens": args.warn_uncached_input,
        "max_uncached_input_tokens": args.max_uncached_input,
        "max_budget_tokens": args.max_budget_tokens,
        "max_elapsed_seconds": args.max_elapsed_seconds,
    }


def evaluate_session(session: dict[str, Any], thresholds: dict[str, int]) -> tuple[list[str], list[str]]:
    totals = session.get("totals") or {}
    warnings: list[str] = []
    failures: list[str] = []
    sid = str(session.get("session_id") or session.get("path"))

    uncached = int(totals.get("uncached_input_tokens") or 0)
    budget = int(totals.get("budget_tokens") or 0)
    elapsed = session.get("elapsed_seconds")
    elapsed_i = int(elapsed) if elapsed is not None else 0

    if thresholds["warn_uncached_input_tokens"] and uncached >= thresholds["warn_uncached_input_tokens"]:
        warnings.append(f"{sid}: uncached_input_tokens={uncached}")
    if thresholds["max_uncached_input_tokens"] and uncached >= thresholds["max_uncached_input_tokens"]:
        failures.append(f"{sid}: uncached_input_tokens={uncached}")
    if thresholds["max_budget_tokens"] and budget >= thresholds["max_budget_tokens"]:
        failures.append(f"{sid}: budget_tokens={budget}")
    if thresholds["max_elapsed_seconds"] and elapsed_i >= thresholds["max_elapsed_seconds"]:
        failures.append(f"{sid}: elapsed_seconds={elapsed_i}")
    return warnings, failures


def session_activity_timestamp(session: dict[str, Any]) -> dt.datetime | None:
    """Return the timestamp that should drive active-budget liveness."""
    last_token_at = parse_ts(session.get("last_token_at"))
    last_started_at = parse_ts(session.get("last_task_started_at"))
    last_complete_at = parse_ts(session.get("last_task_complete_at"))
    if last_complete_at is not None:
        last_work_at = max(ts for ts in [last_token_at, last_started_at] if ts is not None) if (
            last_token_at or last_started_at
        ) else None
        if last_work_at is None or last_complete_at >= last_work_at:
            return None
    return last_token_at or parse_ts(session.get("mtime"))


def session_age_seconds(session: dict[str, Any], now: dt.datetime) -> int | None:
    active_at = session_activity_timestamp(session)
    if active_at is None:
        return None
    return int(max(0, (now - active_at).total_seconds()))


def is_active_session(session: dict[str, Any], now: dt.datetime, active_seconds: int) -> bool:
    if active_seconds <= 0:
        return True
    age = session_age_seconds(session, now)
    # Fail-open on unknown liveness: a session whose token timestamp / mtime we cannot read is
    # treated as NOT active (routed to historical / non-blocking). This breaker
    # exists to stop piling work on a live runaway; when liveness is unknowable
    # we prefer not to stall receipt-safe continuation -- the exact bug this
    # split fixes. See test_active_helpers_* for the pinned contract.
    return age is not None and age <= active_seconds


def truthy_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def live_codex_resume_session_ids() -> set[str]:
    """Return session ids visible in live `codex exec resume <sid>` commands.

    Default-session scans use this as a process-backed liveness proof for non-current
    sessions. The current interactive thread is still keyed by CODEX_THREAD_ID; old
    transcripts without a matching live resume process are historical even if their
    JSONL mtime is fresh from recent probing.
    """
    try:
        proc = subprocess.run(
            ["ps", "-axo", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return set()
    if proc.returncode != 0:
        return set()
    return {match.group(1) for match in CODEX_RESUME_RE.finditer(proc.stdout or "")}


def require_live_process_gate(args: argparse.Namespace) -> bool:
    raw = os.environ.get("LIMEN_CODEX_TOKEN_GATE_REQUIRE_LIVE_PROCESS")
    if raw is not None:
        return truthy_env("LIMEN_CODEX_TOKEN_GATE_REQUIRE_LIVE_PROCESS", True)
    if args.paths:
        return False
    try:
        return Path(args.sessions_root).resolve() == DEFAULT_SESSIONS_ROOT.resolve()
    except OSError:
        return False


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    sessions_root = args.sessions_root
    files = filter_recent(expand_paths([Path(p) for p in args.paths], sessions_root), args.since_hours, args.limit_sessions)
    sessions = [summarize_session(path, max_phases=args.max_phases) for path in files]
    thresholds = thresholds_from_args(args)
    now = dt.datetime.now(dt.timezone.utc)
    active_seconds = max(0, int(args.active_session_seconds))
    current_thread_id = os.environ.get("CODEX_THREAD_ID", "").strip()
    ignore_current_thread = (
        bool(current_thread_id)
        and not args.include_current_thread
        and os.environ.get("LIMEN_CODEX_TOKEN_GATE_IGNORE_CURRENT_THREAD", "1") == "1"
    )
    require_live_process = require_live_process_gate(args)
    live_resume_session_ids = live_codex_resume_session_ids() if require_live_process else set()

    warnings: list[str] = []
    failures: list[str] = []
    active_warnings: list[str] = []
    active_failures: list[str] = []
    historical_failures: list[str] = []
    for session in sessions:
        age = session_age_seconds(session, now)
        active = is_active_session(session, now, active_seconds)
        current_thread = ignore_current_thread and session.get("session_id") == current_thread_id
        if (
            active
            and require_live_process
            and not current_thread
            and str(session.get("session_id") or "") not in live_resume_session_ids
        ):
            active = False
            session["active_gate_exclusion"] = "no-live-codex-resume-process"
        session["active_age_seconds"] = age
        session["mtime_age_seconds"] = session_age_seconds({"mtime": session.get("mtime")}, now)
        session["active"] = active
        session["current_thread"] = current_thread
        if current_thread:
            session["active_gate_exclusion"] = "current-codex-thread"
        sw, sf = evaluate_session(session, thresholds)
        warnings.extend(sw)
        failures.extend(sf)
        if active and not current_thread:
            active_warnings.extend(sw)
            active_failures.extend(sf)
        else:
            historical_failures.extend(sf)

    aggregate = normalize_usage({})
    for session in sessions:
        totals = session.get("totals") or {}
        for key in aggregate:
            aggregate[key] += int(totals.get(key) or 0)

    status = "fail" if failures else "warn" if warnings else "ok"
    # active_status is the "is anything wrong RIGHT NOW" signal: it ignores
    # historical over-budget sessions so a finished burn does not read as an
    # ongoing incident. status stays "fail" for visibility; active_status is
    # what a live-health consumer should watch.
    active_status = "fail" if active_failures else "warn" if active_warnings else "ok"
    return {
        "generated_at": utc_now(),
        "sessions_root": str(sessions_root),
        "since_hours": args.since_hours,
        "session_count": len(sessions),
        "thresholds": thresholds,
        "active_session_seconds": active_seconds,
        "current_thread_id": current_thread_id if ignore_current_thread else None,
        "require_live_process_gate": require_live_process,
        "live_resume_session_ids": sorted(live_resume_session_ids),
        "status": status,
        "active_status": active_status,
        "aggregate_totals": aggregate,
        "warnings": warnings,
        "failures": failures,
        "active_warnings": active_warnings,
        "active_failures": active_failures,
        "historical_failures": historical_failures,
        "sessions": sessions,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="JSONL files or directories; defaults to ~/.codex/sessions")
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS_ROOT)
    parser.add_argument("--since-hours", type=float, default=float(os.environ.get("LIMEN_CODEX_TOKEN_REPORT_HOURS", "6")))
    parser.add_argument("--limit-sessions", type=int, default=int(os.environ.get("LIMEN_CODEX_TOKEN_REPORT_LIMIT", "25")))
    parser.add_argument("--max-phases", type=int, default=int(os.environ.get("LIMEN_CODEX_TOKEN_REPORT_PHASES", "50")))
    parser.add_argument(
        "--warn-uncached-input",
        type=int,
        default=int(os.environ.get("LIMEN_CODEX_WARN_UNCACHED_INPUT_TOKENS", "300000")),
    )
    parser.add_argument(
        "--max-uncached-input",
        type=int,
        default=int(os.environ.get("LIMEN_CODEX_MAX_UNCACHED_INPUT_TOKENS", "600000")),
    )
    parser.add_argument(
        "--max-budget-tokens",
        type=int,
        default=int(os.environ.get("LIMEN_CODEX_MAX_BUDGET_TOKENS", "800000")),
    )
    parser.add_argument(
        "--max-elapsed-seconds",
        type=int,
        default=int(os.environ.get("LIMEN_CODEX_MAX_ELAPSED_SECONDS", "14400")),
    )
    parser.add_argument("--output", type=Path, default=Path(os.environ.get("LIMEN_CODEX_TOKEN_REPORT", DEFAULT_OUTPUT)))
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", help="print the full JSON report to stdout")
    parser.add_argument("--fail-on-budget", action="store_true", help="exit non-zero on threshold failures")
    parser.add_argument(
        "--fail-on-active-budget",
        action="store_true",
        help="exit non-zero only when a still-fresh session exceeds configured budgets",
    )
    parser.add_argument(
        "--active-session-seconds",
        type=int,
        default=int(os.environ.get("LIMEN_CODEX_TOKEN_GATE_ACTIVE_SECONDS", "900")),
        help="token-count freshness window for --fail-on-active-budget; 0 treats every reported session as active",
    )
    parser.add_argument(
        "--include-current-thread",
        action="store_true",
        help="include CODEX_THREAD_ID in active failures instead of treating the measuring thread as historical",
    )
    args = parser.parse_args(argv)

    report = build_report(args)
    if not args.no_write:
        write_report(args.output, report)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        totals = report["aggregate_totals"]
        print(
            "codex-token-accounting: "
            f"{report['status']} sessions={report['session_count']} "
            f"budget={totals['budget_tokens']} uncached={totals['uncached_input_tokens']} "
            f"cached={totals['cached_input_tokens']} output={totals['output_tokens']} "
            f"reasoning={totals['reasoning_output_tokens']} "
            f"active_status={report['active_status']} "
            f"active_failures={len(report['active_failures'])} historical_failures={len(report['historical_failures'])}"
        )
        if report["failures"]:
            print("  failures: " + "; ".join(report["failures"][:3]))
        elif report["warnings"]:
            print("  warnings: " + "; ".join(report["warnings"][:3]))

    if args.fail_on_budget and report["failures"]:
        return 2
    if args.fail_on_active_budget and report["active_failures"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
