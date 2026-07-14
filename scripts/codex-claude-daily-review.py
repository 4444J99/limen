#!/usr/bin/env python3
"""Build a bounded, redacted daily review of local Codex and Claude sessions.

This is deliberately narrower than the full session-corpus review. It scans a
single local-day window, delegates token/fanout analysis to the existing Limen
guards, and renders only metadata-safe evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path(os.environ.get("HOME", str(Path.home())))
DEFAULT_TZ = "America/New_York"
CODEX_ROOT = HOME / ".codex" / "sessions"
CLAUDE_ROOT = HOME / ".claude" / "projects"
PRIVATE_ROOT = ROOT / ".limen-private" / "session-corpus" / "daily-reviews"
REPORT_ROOT = ROOT / "docs" / "reviews"

USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "budget_tokens",
)

VERIFICATION_RE = re.compile(
    r"\b(pytest|py_compile|verify(?:-whole)?|validation|validated|test(?:s|ed|ing)?|"
    r"check-agent-docs|validate-task-board|npm test|pnpm test|tsc|lint)\b",
    re.IGNORECASE,
)
DURABLE_RE = re.compile(
    r"\b(commit(?:ted)?|git status|git diff|pull request|pr #?|merged|receipt|"
    r"docs/|reports?/|worktree|branch|wrote|write_outputs|--write)\b",
    re.IGNORECASE,
)
SPEND_FANOUT_VIOLATION_RE = re.compile(
    r"(billable budget exceeded|fanout exceeded|subagent fanout|agent/workflow fanout)",
    re.IGNORECASE,
)
ROLLOUT_TS_RE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_timestamp(value: str, *, local_tz: ZoneInfo) -> dt.datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(dt.timezone.utc)


def local_day_window(day: str, *, local_tz: ZoneInfo, now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    local_date = dt.date.fromisoformat(day)
    now_local = (now or utc_now()).astimezone(local_tz)
    start_local = dt.datetime.combine(local_date, dt.time.min, tzinfo=local_tz)
    end_local = start_local + dt.timedelta(days=1)
    if local_date == now_local.date() and now_local < end_local:
        end_local = now_local
    return start_local.astimezone(dt.timezone.utc), end_local.astimezone(dt.timezone.utc)


def resolve_window(
    *,
    date_text: str | None,
    since_text: str | None,
    until_text: str | None,
    local_tz: ZoneInfo,
    now: dt.datetime | None = None,
) -> tuple[str, dt.datetime, dt.datetime]:
    if date_text:
        label = date_text
        since, until = local_day_window(date_text, local_tz=local_tz, now=now)
    else:
        now_utc = now or utc_now()
        local_date = now_utc.astimezone(local_tz).date().isoformat()
        label = local_date
        since, until = local_day_window(local_date, local_tz=local_tz, now=now_utc)

    if since_text:
        since = parse_timestamp(since_text, local_tz=local_tz)
        label = since.astimezone(local_tz).date().isoformat()
    if until_text:
        until = parse_timestamp(until_text, local_tz=local_tz)
    if until <= since:
        raise ValueError(f"invalid review window: until {until.isoformat()} <= since {since.isoformat()}")
    return label, since, until


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_optional_ts(value: Any, *, local_tz: ZoneInfo | None = None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return parse_timestamp(str(value), local_tz=local_tz or ZoneInfo(DEFAULT_TZ))
    except (ValueError, TypeError):
        return None


def rollout_timestamp(path: Path) -> dt.datetime | None:
    match = ROLLOUT_TS_RE.search(path.name)
    if not match:
        return None
    date_part, hh, mm, ss = match.groups()
    return dt.datetime.fromisoformat(f"{date_part}T{hh}:{mm}:{ss}+00:00").astimezone(dt.timezone.utc)


def home_rel(path: str | Path) -> str:
    p = Path(path).expanduser()
    try:
        return str(p.resolve().relative_to(ROOT))
    except (OSError, ValueError):
        try:
            return "~/" + str(p.resolve().relative_to(HOME))
        except (OSError, ValueError):
            return str(path)


def short_id(value: str | None) -> str:
    text = str(value or "")
    return text[:12] + ("..." if len(text) > 12 else "")


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_millions(value: Any) -> str:
    try:
        return f"{int(value or 0) / 1_000_000:.1f}M"
    except (TypeError, ValueError):
        return "0.0M"


def ascii_text(value: Any) -> str:
    text = str(value)
    return (
        text.replace(" \u2014 ", " - ")
        .replace("\u2014", " - ")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


def utc_date_dirs(root: Path, since: dt.datetime, until: dt.datetime) -> list[Path]:
    dirs: list[Path] = []
    current = since.date()
    final = until.date()
    while current <= final:
        dirs.append(root / f"{current:%Y}" / f"{current:%m}" / f"{current:%d}")
        current += dt.timedelta(days=1)
    return dirs


def discover_codex_candidates(root: Path, since: dt.datetime, until: dt.datetime) -> list[Path]:
    files: list[Path] = []
    for directory in utc_date_dirs(root, since, until):
        if directory.exists():
            files.extend(sorted(directory.glob("*.jsonl")))
    return sorted({path.resolve(): path for path in files}.values())


def discover_claude_transcripts(root: Path, since: dt.datetime, until: dt.datetime) -> list[Path]:
    if not root.exists():
        return []
    paths: list[Path] = []
    for path in root.rglob("*.jsonl"):
        if "subagents" in path.parts:
            continue
        try:
            mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        except OSError:
            continue
        if since <= mtime < until:
            paths.append(path)
    return sorted(paths)


def run_json_command(cmd: list[str]) -> tuple[dict[str, Any] | None, int, str, str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    return payload, proc.returncode, proc.stdout, proc.stderr


def empty_usage() -> dict[str, int]:
    return {key: 0 for key in USAGE_KEYS}


def session_bounds(session: dict[str, Any]) -> tuple[dt.datetime | None, dt.datetime | None]:
    path = Path(str(session.get("path") or ""))
    start = parse_optional_ts(session.get("first_token_at")) or rollout_timestamp(path) or parse_optional_ts(session.get("mtime"))
    end = parse_optional_ts(session.get("last_token_at")) or start or parse_optional_ts(session.get("mtime"))
    return start, end


def intersects_window(start: dt.datetime | None, end: dt.datetime | None, since: dt.datetime, until: dt.datetime) -> bool:
    if start is None and end is None:
        return False
    if start is None:
        start = end
    if end is None:
        end = start
    assert start is not None and end is not None
    return end >= since and start < until


def failure_session_id(failure: str) -> str:
    return failure.split(":", 1)[0].strip()


def filter_failures(failures: list[str], session_ids: set[str]) -> list[str]:
    return [failure for failure in failures if failure_session_id(failure) in session_ids]


def scan_jsonl_signals(paths: list[Path]) -> dict[str, int]:
    counts = {"verification": 0, "durable": 0, "lines": 0}
    for path in paths:
        try:
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                counts["lines"] += 1
                if VERIFICATION_RE.search(line):
                    counts["verification"] += 1
                if DURABLE_RE.search(line):
                    counts["durable"] += 1
    return counts


def jsonl_time_bounds(paths: list[Path]) -> tuple[dt.datetime | None, dt.datetime | None]:
    first: dt.datetime | None = None
    last: dt.datetime | None = None
    for path in paths:
        try:
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                if '"timestamp"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                timestamp = parse_optional_ts(row.get("timestamp"))
                if timestamp is None:
                    continue
                first = timestamp if first is None else min(first, timestamp)
                last = timestamp if last is None else max(last, timestamp)
    return first, last


def run_codex_accounting(paths: list[Path], *, active_session_seconds: int) -> dict[str, Any]:
    if not paths:
        return {
            "generated_at": iso_z(utc_now()),
            "session_count": 0,
            "aggregate_totals": empty_usage(),
            "status": "ok",
            "active_status": "ok",
            "warnings": [],
            "failures": [],
            "active_warnings": [],
            "active_failures": [],
            "historical_failures": [],
            "sessions": [],
        }
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "codex-token-accounting.py"),
        *[str(path) for path in paths],
        "--since-hours",
        "0",
        "--limit-sessions",
        "0",
        "--max-phases",
        "100000",
        "--active-session-seconds",
        str(active_session_seconds),
        "--no-write",
        "--json",
    ]
    payload, code, stdout, stderr = run_json_command(cmd)
    if payload is None:
        return {
            "generated_at": iso_z(utc_now()),
            "session_count": 0,
            "aggregate_totals": empty_usage(),
            "status": "error",
            "active_status": "error",
            "warnings": [],
            "failures": [f"codex-token-accounting exited {code}: {(stderr or stdout).strip()[:500]}"],
            "active_warnings": [],
            "active_failures": [],
            "historical_failures": [],
            "sessions": [],
        }
    return payload


def summarize_codex(
    raw: dict[str, Any],
    since: dt.datetime,
    until: dt.datetime,
    *,
    generated_at: dt.datetime | None = None,
    active_session_seconds: int = 900,
) -> dict[str, Any]:
    sessions = []
    snapshot_at = generated_at or utc_now()
    for session in raw.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        phases = [
            phase
            for phase in session.get("phase_deltas") or []
            if parse_optional_ts((phase if isinstance(phase, dict) else {}).get("timestamp")) is not None
            and parse_optional_ts((phase if isinstance(phase, dict) else {}).get("timestamp")) <= until
        ]
        if phases:
            bounded_total = {
                key: int(((phases[-1].get("cumulative") or {}) if isinstance(phases[-1], dict) else {}).get(key) or 0)
                for key in USAGE_KEYS
            }
            session["totals"] = bounded_total
            session["first_token_at"] = phases[0].get("timestamp")
            session["last_token_at"] = phases[-1].get("timestamp")
            first_phase_ts = parse_optional_ts(phases[0].get("timestamp"))
            last_phase_ts = parse_optional_ts(phases[-1].get("timestamp"))
            if first_phase_ts is not None and last_phase_ts is not None:
                session["elapsed_seconds"] = int(max(0, (last_phase_ts - first_phase_ts).total_seconds()))
        elif session.get("token_count_events"):
            continue
        start, end = session_bounds(session)
        if not intersects_window(start, end, since, until):
            continue
        active_age = int(max(0, (snapshot_at - end).total_seconds())) if end is not None else None
        active = bool(active_age is not None and (active_session_seconds <= 0 or active_age <= active_session_seconds))
        compact = {
            "session_id": session.get("session_id"),
            "path": home_rel(session.get("path") or ""),
            "first_token_at": session.get("first_token_at"),
            "last_token_at": session.get("last_token_at"),
            "mtime": session.get("mtime"),
            "elapsed_seconds": session.get("elapsed_seconds"),
            "active": active,
            "active_age_seconds": active_age,
            "totals": {key: int((session.get("totals") or {}).get(key) or 0) for key in USAGE_KEYS},
        }
        sessions.append(compact)

    session_ids = {str(session.get("session_id")) for session in sessions}
    aggregate = empty_usage()
    for session in sessions:
        for key in USAGE_KEYS:
            aggregate[key] += int((session.get("totals") or {}).get(key) or 0)

    thresholds = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {}
    failures: list[str] = []
    warnings: list[str] = []
    active_failures: list[str] = []
    active_warnings: list[str] = []
    historical_failures: list[str] = []
    for session in sessions:
        sid = str(session.get("session_id") or session.get("path"))
        totals = session.get("totals") or {}
        uncached = int(totals.get("uncached_input_tokens") or 0)
        budget = int(totals.get("budget_tokens") or 0)
        elapsed = int(session.get("elapsed_seconds") or 0)
        sw: list[str] = []
        sf: list[str] = []
        if int(thresholds.get("warn_uncached_input_tokens") or 0) and uncached >= int(
            thresholds.get("warn_uncached_input_tokens") or 0
        ):
            sw.append(f"{sid}: uncached_input_tokens={uncached}")
        if int(thresholds.get("max_uncached_input_tokens") or 0) and uncached >= int(
            thresholds.get("max_uncached_input_tokens") or 0
        ):
            sf.append(f"{sid}: uncached_input_tokens={uncached}")
        if int(thresholds.get("max_budget_tokens") or 0) and budget >= int(thresholds.get("max_budget_tokens") or 0):
            sf.append(f"{sid}: budget_tokens={budget}")
        if int(thresholds.get("max_elapsed_seconds") or 0) and elapsed >= int(
            thresholds.get("max_elapsed_seconds") or 0
        ):
            sf.append(f"{sid}: elapsed_seconds={elapsed}")
        warnings.extend(sw)
        failures.extend(sf)
        if session.get("active"):
            active_warnings.extend(sw)
            active_failures.extend(sf)
        else:
            historical_failures.extend(sf)

    status = "fail" if failures else "warn" if warnings else "ok"
    active_status = "fail" if active_failures else "warn" if active_warnings else "ok"
    top = sorted(sessions, key=lambda item: int((item.get("totals") or {}).get("budget_tokens") or 0), reverse=True)
    return {
        "session_count": len(sessions),
        "candidate_count": len(raw.get("sessions") or []),
        "status": status,
        "active_status": active_status,
        "aggregate_totals": aggregate,
        "warnings": warnings,
        "failures": failures,
        "active_warnings": active_warnings,
        "active_failures": active_failures,
        "historical_failures": historical_failures,
        "top_sessions_by_budget": top[:10],
        "sessions": sessions,
    }


def write_filtered_jsonl(src: Path, dst: Path, cutoff: dt.datetime) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open(encoding="utf-8", errors="replace") as inp, dst.open("w", encoding="utf-8") as out:
        for line in inp:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = parse_optional_ts(row.get("timestamp"))
            if timestamp is not None and timestamp > cutoff:
                continue
            out.write(json.dumps(row, sort_keys=True) + "\n")


def filtered_claude_snapshot(path: Path, cutoff: dt.datetime, tmp_root: Path) -> Path:
    main = tmp_root / path.name
    write_filtered_jsonl(path, main, cutoff)
    source_subagents = path.with_suffix("") / "subagents"
    if source_subagents.exists():
        target_subagents = main.with_suffix("") / "subagents"
        for subagent in sorted(p for p in source_subagents.rglob("*.jsonl") if p.is_file()):
            write_filtered_jsonl(subagent, target_subagents / subagent.name, cutoff)
    return main


def run_claude_audit(path: Path, args: argparse.Namespace, *, cutoff: dt.datetime | None = None) -> dict[str, Any]:
    audit_path = path
    tmp: tempfile.TemporaryDirectory[str] | None = None
    if cutoff is not None:
        tmp = tempfile.TemporaryDirectory(prefix="limen-claude-review-")
        audit_path = filtered_claude_snapshot(path, cutoff, Path(tmp.name))
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "claude-workflow-guard.py"),
        "audit-transcript",
        str(audit_path),
        "--max-billable-tokens",
        str(args.max_claude_billable_tokens),
        "--max-opus-billable-tokens",
        str(args.max_claude_opus_billable_tokens),
        "--max-fable-billable-tokens",
        str(args.max_claude_fable_billable_tokens),
        "--max-agent-calls",
        str(args.max_claude_agent_calls),
        "--max-opus-agents",
        str(args.max_opus_agents),
        "--max-fable-agents",
        str(args.max_fable_agents),
    ]
    try:
        payload, code, stdout, stderr = run_json_command(cmd)
    finally:
        if tmp is not None:
            tmp.cleanup()
    if payload is None:
        return {
            "ok": False,
            "session": path.stem,
            "files": [str(path)],
            "billableTokens": 0,
            "opusBillableTokens": 0,
            "fableBillableTokens": 0,
            "outputTokens": 0,
            "cacheReadTokens": 0,
            "agentCalls": 0,
            "expensiveSubagents": 0,
            "fableSubagents": 0,
            "fableAcceptanceSeen": False,
            "violations": [f"claude-workflow-guard exited {code}: {(stderr or stdout).strip()[:500]}"],
        }
    payload["path"] = str(path)
    source_subagents = path.with_suffix("") / "subagents"
    files = [str(path)]
    if source_subagents.exists():
        files.extend(str(p) for p in sorted(source_subagents.rglob("*.jsonl")) if p.is_file())
    payload["files"] = files
    payload["returncode"] = code
    return payload


def summarize_claude(reports: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "billableTokens": 0,
        "opusBillableTokens": 0,
        "fableBillableTokens": 0,
        "outputTokens": 0,
        "cacheReadTokens": 0,
        "agentCalls": 0,
        "expensiveSubagents": 0,
        "fableSubagents": 0,
        "usageMessages": 0,
    }
    sessions: list[dict[str, Any]] = []
    violation_counts: dict[str, int] = {}
    unaccepted_fable: list[str] = []
    threshold_violations: list[str] = []

    for report in reports:
        sid = str(report.get("session") or Path(str(report.get("path") or "")).stem)
        for key in totals:
            totals[key] += int(report.get(key) or 0)
        violations = [str(item) for item in report.get("violations") or []]
        for violation in violations:
            violation_counts[violation] = violation_counts.get(violation, 0) + 1
        if any("Fable run lacks written acceptance command" in violation for violation in violations):
            unaccepted_fable.append(sid)
        if any(SPEND_FANOUT_VIOLATION_RE.search(violation) for violation in violations):
            threshold_violations.append(sid)
        sessions.append(
            {
                "session_id": sid,
                "path": home_rel(report.get("path") or ""),
                "files": [home_rel(path) for path in report.get("files") or []],
                "ok": bool(report.get("ok")),
                "billableTokens": int(report.get("billableTokens") or 0),
                "opusBillableTokens": int(report.get("opusBillableTokens") or 0),
                "fableBillableTokens": int(report.get("fableBillableTokens") or 0),
                "outputTokens": int(report.get("outputTokens") or 0),
                "cacheReadTokens": int(report.get("cacheReadTokens") or 0),
                "agentCalls": int(report.get("agentCalls") or 0),
                "expensiveSubagents": int(report.get("expensiveSubagents") or 0),
                "fableSubagents": int(report.get("fableSubagents") or 0),
                "fableAcceptanceSeen": bool(report.get("fableAcceptanceSeen")),
                "violations": violations,
            }
        )

    sessions.sort(key=lambda item: item["billableTokens"], reverse=True)
    failed = sum(1 for session in sessions if not session["ok"])
    return {
        "session_count": len(sessions),
        "failed_count": failed,
        "ok_count": len(sessions) - failed,
        "totals": totals,
        "violation_counts": dict(sorted(violation_counts.items(), key=lambda item: (-item[1], item[0]))),
        "unaccepted_fable_sessions": unaccepted_fable,
        "threshold_violation_sessions": sorted(set(threshold_violations)),
        "top_sessions_by_billable": sessions[:10],
        "sessions": sessions,
    }


def load_value_snapshot(since: dt.datetime, until: dt.datetime) -> dict[str, Any]:
    path = ROOT / "scripts" / "session-value-review.py"
    spec = importlib.util.spec_from_file_location("session_value_review_daily", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.PRIVATE_ROOT = ROOT / ".limen-private" / "session-corpus"
    module.BATCH_RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-batch-resolution-receipts.json"
    module.BATCH_REVIEW_INDEX = module.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
    module.DOC_PATH = ROOT / "docs" / "session-value-review.md"
    module.PRIVATE_INDEX = module.PRIVATE_ROOT / "lifecycle" / "session-value-review.json"
    module.GATE_HISTORY = module.PRIVATE_ROOT / "lifecycle" / "session-value-gate-history.jsonl"
    return module.build_snapshot(since, until)


def build_closure_gaps(
    codex: dict[str, Any],
    claude: dict[str, Any],
    *,
    long_session_seconds: int,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for session in codex.get("sessions") or []:
        elapsed = int(session.get("elapsed_seconds") or 0)
        if elapsed < long_session_seconds:
            continue
        original_path = Path(str(session.get("path") or "").replace("~/", str(HOME) + "/", 1))
        signals = scan_jsonl_signals([original_path])
        if signals["verification"] == 0 and signals["durable"] == 0:
            gaps.append(
                {
                    "agent": "codex",
                    "session_id": session.get("session_id"),
                    "elapsed_seconds": elapsed,
                    "path": session.get("path"),
                    "signals": signals,
                }
            )

    for session in claude.get("sessions") or []:
        files = [Path(str(path).replace("~/", str(HOME) + "/", 1)) for path in session.get("files") or []]
        first, last = jsonl_time_bounds(files)
        elapsed = int((last - first).total_seconds()) if first and last else 0
        if elapsed < long_session_seconds:
            continue
        signals = scan_jsonl_signals(files)
        if signals["verification"] == 0 and signals["durable"] == 0:
            gaps.append(
                {
                    "agent": "claude",
                    "session_id": session.get("session_id"),
                    "elapsed_seconds": elapsed,
                    "path": session.get("path"),
                    "signals": signals,
                }
            )
    return gaps


def build_violations(codex: dict[str, Any], claude: dict[str, Any], closure_gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if codex.get("active_failures"):
        violations.append(
            {
                "code": "codex_active_budget",
                "summary": f"{len(codex['active_failures'])} active Codex session(s) exceeded budget thresholds.",
                "evidence": codex["active_failures"],
            }
        )
    if claude.get("unaccepted_fable_sessions"):
        violations.append(
            {
                "code": "claude_fable_without_acceptance",
                "summary": f"{len(claude['unaccepted_fable_sessions'])} Claude session(s) used Fable without acceptance evidence.",
                "evidence": claude["unaccepted_fable_sessions"],
            }
        )
    if claude.get("threshold_violation_sessions"):
        violations.append(
            {
                "code": "claude_thresholds",
                "summary": f"{len(claude['threshold_violation_sessions'])} Claude session(s) crossed spend or fanout guard thresholds.",
                "evidence": claude["threshold_violation_sessions"],
            }
        )
    if closure_gaps:
        violations.append(
            {
                "code": "long_session_no_closeout_signal",
                "summary": f"{len(closure_gaps)} long session(s) had neither verification nor durable receipt signals.",
                "evidence": [
                    {
                        "agent": gap["agent"],
                        "session_id": gap["session_id"],
                        "elapsed_seconds": gap["elapsed_seconds"],
                        "path": gap["path"],
                    }
                    for gap in closure_gaps
                ],
            }
        )
    return violations


def derive_verdict(codex: dict[str, Any], claude: dict[str, Any], value: dict[str, Any], violations: list[dict[str, Any]]) -> str:
    metrics = value.get("metrics") or {}
    commits = int(metrics.get("commits") or 0)
    receipts = int(metrics.get("batch_receipts") or 0)
    claude_billable = int((claude.get("totals") or {}).get("billableTokens") or 0)
    codex_budget = int((codex.get("aggregate_totals") or {}).get("budget_tokens") or 0)
    if violations and receipts == 0:
        return "High activity created code movement, but session-lifecycle closure did not justify the premium-model spend."
    if violations:
        return "Some durable value landed, but the spend shape was not acceptable without tighter gates."
    if commits or receipts:
        return "The day produced durable value with no active budget breaker in this review window."
    if claude_billable or codex_budget:
        return "Spend occurred, but this review found no durable value receipt in the measured window."
    return "No meaningful local Codex/Claude spend was detected in the measured window."


def render_markdown(review: dict[str, Any]) -> str:
    codex = review["codex"]
    claude = review["claude"]
    value = review["value_context"]
    metrics = value.get("metrics") or {}
    codex_totals = codex.get("aggregate_totals") or {}
    claude_totals = claude.get("totals") or {}
    private_json = review["outputs"]["private_json"]
    lines = [
        f"# Codex/Claude Session Review - {review['date']}",
        "",
        f"Generated: `{review['generated_at']}`",
        f"Window: `{review['window']['since']}` to `{review['window']['until']}` ({review['window']['timezone']})",
        f"Snapshot cutoff: `{review['snapshot_at']}`; transcript rows newer than this are excluded from guard totals.",
        "",
        "## Verdict",
        "",
        review["verdict"],
        "",
        "## Spend And Fanout",
        "",
        f"- Codex: `{codex['session_count']}` sessions, `{fmt_millions(codex_totals.get('budget_tokens'))}` budget tokens, "
        f"`{fmt_millions(codex_totals.get('uncached_input_tokens'))}` uncached input, "
        f"`{fmt_millions(codex_totals.get('output_tokens'))}` output, "
        f"`{fmt_millions(codex_totals.get('reasoning_output_tokens'))}` reasoning.",
        f"- Codex guard state: active `{codex['active_status']}`, active failures `{len(codex.get('active_failures') or [])}`, "
        f"historical failures `{len(codex.get('historical_failures') or [])}`.",
        f"- Claude: `{claude['session_count']}` top-level sessions, `{claude['failed_count']}` failed guard, "
        f"`{fmt_millions(claude_totals.get('billableTokens'))}` billable, "
        f"`{fmt_millions(claude_totals.get('opusBillableTokens'))}` Opus, "
        f"`{fmt_millions(claude_totals.get('fableBillableTokens'))}` Fable, "
        f"`{fmt_int(claude_totals.get('agentCalls'))}` agent/workflow calls.",
        f"- Claude subagents: `{fmt_int(claude_totals.get('expensiveSubagents'))}` expensive-tier subagents, "
        f"`{fmt_int(claude_totals.get('fableSubagents'))}` Fable subagents.",
        f"- Value context: `{fmt_int(metrics.get('commits'))}` commits, `{fmt_int(metrics.get('batch_receipts'))}` prompt-batch receipts, "
        f"`{fmt_int(metrics.get('prompt_events_recorded'))}` prompt events recorded.",
        "",
        "## Ask Vs Done Critique",
        "",
    ]
    if review["violations"]:
        for violation in review["violations"]:
            lines.append(f"- `{violation['code']}`: {violation['summary']}")
    else:
        lines.append("- No active fail-on-violations condition was found.")
    if int(metrics.get("commits") or 0) and not int(metrics.get("batch_receipts") or 0):
        lines.append("- Commits moved, but prompt-batch receipts did not; work happened is not the same as lifecycle closure.")
    if codex.get("historical_failures"):
        lines.append("- Historical Codex failures remain visible but do not block this gate unless they are active.")
    if claude.get("unaccepted_fable_sessions"):
        lines.append("- Fable usage must be acceptance-receipted before it is allowed to count as legitimate premium spend.")
    lines += [
        "",
        "## Evolution Actions",
        "",
        f"- Run this bounded review directly: `python3 scripts/codex-claude-daily-review.py --date {review['date']} --until {review['window']['until']} --generated-at {review['snapshot_at']} --fail-on-violations`.",
        "- Keep Codex historical budget failures visible, but fail only on active budget breakers unless a future `--strict-history` mode is added.",
        "- Gate Claude Fable on written acceptance and cap Opus/Fable fanout at the transcript guard layer before dispatching broad verifier fleets.",
        "- Treat any long session without verification or durable receipt signals as an incomplete lifecycle, not as closed work.",
        "",
        "## Top Claude Guard Violations",
        "",
    ]
    if claude.get("violation_counts"):
        for violation, count in list(claude["violation_counts"].items())[:8]:
            lines.append(f"- `{count}` x {ascii_text(violation)}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Largest Codex Sessions",
        "",
        "| Session | Budget | Uncached | Output | Reasoning | Active |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for session in codex.get("top_sessions_by_budget") or []:
        totals = session.get("totals") or {}
        lines.append(
            f"| `{short_id(session.get('session_id'))}` | {fmt_int(totals.get('budget_tokens'))} | "
            f"{fmt_int(totals.get('uncached_input_tokens'))} | {fmt_int(totals.get('output_tokens'))} | "
            f"{fmt_int(totals.get('reasoning_output_tokens'))} | `{str(session.get('active')).lower()}` |"
        )
    if not codex.get("top_sessions_by_budget"):
        lines.append("| none | 0 | 0 | 0 | 0 | false |")
    lines += [
        "",
        "## Largest Claude Sessions",
        "",
        "| Session | Billable | Opus | Fable | Agent Calls | Guard |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for session in claude.get("top_sessions_by_billable") or []:
        lines.append(
            f"| `{short_id(session.get('session_id'))}` | {fmt_int(session.get('billableTokens'))} | "
            f"{fmt_int(session.get('opusBillableTokens'))} | {fmt_int(session.get('fableBillableTokens'))} | "
            f"{fmt_int(session.get('agentCalls'))} | `{'ok' if session.get('ok') else 'fail'}` |"
        )
    if not claude.get("top_sessions_by_billable"):
        lines.append("| none | 0 | 0 | 0 | 0 | ok |")
    lines += [
        "",
        "## Evidence Commands",
        "",
        f"- Daily review: `python3 scripts/codex-claude-daily-review.py --date {review['date']} --until {review['window']['until']} --generated-at {review['snapshot_at']} --write`",
        "- Codex accounting: `python3 scripts/codex-token-accounting.py <daily-files> --since-hours 0 --limit-sessions 0 --max-phases 100000 --no-write --json`",
        "- Claude transcript guard: `python3 scripts/claude-workflow-guard.py audit-transcript <filtered-session.jsonl>`",
        f"- Value context: `python3 scripts/session-value-review.py --since {review['window']['since']} --until {review['window']['until']}`",
        f"- Private JSON snapshot: `{private_json}`",
        "",
        "## Privacy",
        "",
        "- This tracked report contains no raw prompt or transcript bodies.",
        "- Evidence is limited to session ids, home-relative paths in the private JSON, token counts, guard strings, command names, and receipt metadata.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(review: dict[str, Any], markdown: str) -> None:
    report_path = Path(review["outputs"]["markdown"])
    private_path = Path(review["outputs"]["private_json"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown, encoding="utf-8")
    private_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_review(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    local_tz = ZoneInfo(args.timezone)
    label, since, until = resolve_window(
        date_text=args.date,
        since_text=args.since,
        until_text=args.until,
        local_tz=local_tz,
    )
    generated_at = parse_timestamp(args.generated_at, local_tz=local_tz) if args.generated_at else utc_now()
    snapshot_at = min(until, generated_at)
    codex_candidates = discover_codex_candidates(args.codex_sessions_root, since, until)
    codex_raw = run_codex_accounting(codex_candidates, active_session_seconds=args.active_session_seconds)
    codex = summarize_codex(
        codex_raw,
        since,
        snapshot_at,
        generated_at=snapshot_at,
        active_session_seconds=args.active_session_seconds,
    )

    claude_paths = discover_claude_transcripts(args.claude_projects_root, since, until)
    claude_cutoff = snapshot_at
    claude_reports = [run_claude_audit(path, args, cutoff=claude_cutoff) for path in claude_paths]
    claude = summarize_claude(claude_reports)

    markdown_path = REPORT_ROOT / f"codex-claude-session-review-{label}.md"
    private_path = PRIVATE_ROOT / f"codex-claude-{label}.json"
    try:
        value = load_value_snapshot(since, until)
        value["generated_at"] = iso_z(generated_at)
    except Exception as exc:
        value = {
            "generated_at": iso_z(generated_at),
            "window": {"since": iso_z(since), "until": iso_z(until)},
            "metrics": {},
            "findings": {"verdict": "value context unavailable"},
            "error": str(exc),
        }

    closure_gaps = build_closure_gaps(codex, claude, long_session_seconds=args.long_session_seconds)
    violations = build_violations(codex, claude, closure_gaps)
    review = {
        "schema": "limen.codex_claude_daily_review.v1",
        "date": label,
        "generated_at": iso_z(generated_at),
        "window": {
            "since": iso_z(since),
            "until": iso_z(until),
            "timezone": args.timezone,
        },
        "snapshot_at": iso_z(snapshot_at),
        "inputs": {
            "codex_candidate_files": len(codex_candidates),
            "codex_sessions_root": home_rel(args.codex_sessions_root),
            "claude_top_level_files": len(claude_paths),
            "claude_projects_root": home_rel(args.claude_projects_root),
        },
        "codex": codex,
        "claude": claude,
        "value_context": value,
        "closure_gaps": closure_gaps,
        "violations": violations,
        "verdict": derive_verdict(codex, claude, value, violations),
        "outputs": {
            "markdown": str(markdown_path),
            "private_json": home_rel(private_path),
        },
    }
    markdown = render_markdown(review)
    return review, markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="local YYYY-MM-DD day to review")
    parser.add_argument("--since", help="ISO timestamp override for window start")
    parser.add_argument("--until", help="ISO timestamp override for window end")
    parser.add_argument("--generated-at", help="ISO timestamp to stamp generated reports for reproducible snapshots")
    parser.add_argument("--timezone", default=DEFAULT_TZ)
    parser.add_argument("--codex-sessions-root", type=Path, default=CODEX_ROOT)
    parser.add_argument("--claude-projects-root", type=Path, default=CLAUDE_ROOT)
    parser.add_argument("--json", action="store_true", help="print the structured redacted JSON")
    parser.add_argument("--write", action="store_true", help="write tracked Markdown and ignored private JSON")
    parser.add_argument("--fail-on-violations", action="store_true", help="exit non-zero when this review finds gate violations")
    parser.add_argument("--active-session-seconds", type=int, default=int(os.environ.get("LIMEN_CODEX_TOKEN_GATE_ACTIVE_SECONDS", "900")))
    parser.add_argument("--long-session-seconds", type=int, default=14_400)
    parser.add_argument("--max-claude-billable-tokens", type=int, default=int(os.environ.get("LIMEN_MAX_CLAUDE_SESSION_TOKENS", "2000000")))
    parser.add_argument("--max-claude-opus-billable-tokens", type=int, default=int(os.environ.get("LIMEN_MAX_OPUS_SESSION_TOKENS", "750000")))
    parser.add_argument("--max-claude-fable-billable-tokens", type=int, default=int(os.environ.get("LIMEN_MAX_FABLE_SESSION_TOKENS", "1000000")))
    parser.add_argument("--max-claude-agent-calls", type=int, default=int(os.environ.get("LIMEN_MAX_AGENT_CALLS", "8")))
    parser.add_argument("--max-opus-agents", type=int, default=1)
    parser.add_argument("--max-fable-agents", type=int, default=1)
    args = parser.parse_args(argv)

    review, markdown = build_review(args)
    if args.write:
        write_outputs(review, markdown)
    if args.json:
        print(json.dumps(review, indent=2, sort_keys=True))
    else:
        print(markdown)
    if args.fail_on_violations and review["violations"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
