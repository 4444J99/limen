#!/usr/bin/env python3
"""Collect a redacted, frozen seven-agent whole-estate snapshot.

Only aggregate metadata and public receipt URLs leave this process. Prompt
bodies, local paths, raw identifiers, and full hashes are deliberately omitted.
"""

from __future__ import annotations

import collections
import datetime as dt
import glob
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import yaml

from model import (
    OUTCOMES,
    UTC,
    Window,
    codex_usage,
    cumulative_delta,
    extract_pr_urls,
    int_value,
    iso_z,
    parse_pr_url,
    parse_ts,
    sanitize_subject,
    union_seconds,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOME = Path.home()
SNAPSHOT = parse_ts("2026-07-19T15:11:00Z")
assert SNAPSHOT
WINDOWS = (
    Window(
        "completed_week",
        "Completed calendar week",
        parse_ts("2026-07-06T04:00:00Z"),
        parse_ts("2026-07-13T04:00:00Z"),
    ),
    Window(
        "latest_7d",
        "Latest seven days",
        parse_ts("2026-07-12T15:11:00Z"),
        SNAPSHOT,
    ),
)
AGENTS = ("codex", "claude", "agy", "opencode", "gemini", "copilot", "jules")
FAMILY = set(AGENTS)
REVIEW_START = min(window.start for window in WINDOWS)
PUBLIC_OWNERS = {"organvm", "4444j99"}
TOKEN_KEYS = {
    "codex": (
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "cached_input_tokens",
    ),
    "claude": (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ),
    "opencode": (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ),
    "copilot": (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ),
}


def hid(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def rows(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict):
                    yield value
    except OSError:
        return


def local_file_label(agent: str) -> str:
    return {
        "codex": "Codex rollout store",
        "claude": "Claude project transcript store",
        "agy": "Antigravity conversation summary store",
        "gemini": "Gemini native chat store",
    }[agent]


def add_session(
    out: list[dict[str, Any]],
    *,
    agent: str,
    native_id: str,
    parent_id: str | None,
    start: dt.datetime | None,
    end: dt.datetime | None,
    time_basis: str,
    events: int,
    token_events: list[tuple[dt.datetime, dict[str, int]]] | None = None,
    outcome: str = "coverage_unknown",
    receipt: str | None = None,
) -> None:
    if start is None and end is None:
        return
    left = start or end
    right = end or start
    assert left and right
    if left >= SNAPSHOT and right >= SNAPSHOT:
        return
    out.append(
        {
            "_native_id": native_id,
            "_parent_id": parent_id,
            "_token_events": token_events or [],
            "session": f"{agent}-{hid(native_id)}",
            "agent": agent,
            "role": "child" if parent_id else "root",
            "start": iso_z(left),
            "end": iso_z(min(right, SNAPSHOT)),
            "time_basis": time_basis,
            "events": events,
            "outcome": outcome,
            "receipt": receipt,
        }
    )


def collect_codex(out: list[dict[str, Any]]) -> dict[str, Any]:
    file_count = event_count = late = 0
    token_reconcile = collections.Counter()
    for name in glob.iglob(str(HOME / ".codex/sessions/**/*.jsonl"), recursive=True):
        path = Path(name)
        event_rows = list(rows(path))
        timestamps = [parse_ts(row.get("timestamp")) for row in event_rows]
        timestamps = [value for value in timestamps if value]
        if not timestamps or max(timestamps) < REVIEW_START or min(timestamps) >= SNAPSHOT:
            continue
        file_count += 1
        event_count += sum(REVIEW_START <= value < SNAPSHOT for value in timestamps)
        late += sum(value >= SNAPSHOT for value in timestamps)
        meta: dict[str, Any] = {}
        token_events: list[tuple[dt.datetime, dict[str, int]]] = []
        previous: dict[str, int] | None = None
        for row in event_rows:
            ts = parse_ts(row.get("timestamp"))
            if row.get("type") == "session_meta":
                meta = row.get("payload") or {}
            if not ts or not REVIEW_START <= ts < SNAPSHOT:
                continue
            payload = row.get("payload") or {}
            if row.get("type") == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info") or {}
                total = codex_usage(info.get("total_token_usage"))
                raw_delta = info.get("last_token_usage")
                delta = (
                    codex_usage(raw_delta)
                    if isinstance(raw_delta, dict)
                    else cumulative_delta(total, previous)
                )
                previous = total
                keep = {key: delta[key] for key in TOKEN_KEYS["codex"]}
                token_events.append((ts, keep))
                token_reconcile.update(keep)
        thread_source = str(meta.get("thread_source") or "")
        parent = meta.get("parent_thread_id")
        if not parent and "sub_agent" in thread_source:
            parent = "parent-unavailable"
        sid = str(meta.get("id") or meta.get("session_id") or path.stem)
        add_session(
            out,
            agent="codex",
            native_id=sid,
            parent_id=str(parent) if parent else None,
            start=min(timestamps),
            end=max(timestamps),
            time_basis="native event span",
            events=sum(REVIEW_START <= value < SNAPSHOT for value in timestamps),
            token_events=token_events,
        )
    return {
        "files": file_count,
        "events": event_count,
        "late_writes_excluded": late,
        "direct_token_aggregation": dict(token_reconcile),
    }


def collect_claude(out: list[dict[str, Any]]) -> dict[str, Any]:
    file_count = event_count = late = 0
    direct = collections.Counter()
    for name in glob.iglob(str(HOME / ".claude/projects/**/*.jsonl"), recursive=True):
        path = Path(name)
        data = list(rows(path))
        stamped = [(parse_ts(row.get("timestamp")), row) for row in data]
        stamped = [(ts, row) for ts, row in stamped if ts]
        if not stamped or max(ts for ts, _ in stamped) < REVIEW_START:
            continue
        before = [(ts, row) for ts, row in stamped if ts < SNAPSHOT]
        if not before:
            continue
        file_count += 1
        event_count += sum(ts >= REVIEW_START for ts, _ in before)
        late += sum(ts >= SNAPSHOT for ts, _ in stamped)
        tokens: list[tuple[dt.datetime, dict[str, int]]] = []
        child = "subagents" in path.parts
        sid = path.stem
        for ts, row in before:
            sid = str(row.get("sessionId") or sid)
            child = child or bool(row.get("isSidechain"))
            if row.get("type") != "assistant" or ts < REVIEW_START:
                continue
            message = row.get("message") or {}
            usage = message.get("usage") if isinstance(message, dict) else None
            if not isinstance(usage, dict):
                continue
            parts = {
                "input_tokens": int_value(usage.get("input_tokens")),
                "output_tokens": int_value(usage.get("output_tokens")),
                "cache_creation_input_tokens": int_value(
                    usage.get("cache_creation_input_tokens")
                ),
                "cache_read_input_tokens": int_value(usage.get("cache_read_input_tokens")),
            }
            tokens.append((ts, parts))
            direct.update(parts)
        add_session(
            out,
            agent="claude",
            native_id=sid,
            parent_id="parent-unavailable" if child else None,
            start=min(ts for ts, _ in before),
            end=max(ts for ts, _ in before),
            time_basis="native event span",
            events=sum(ts >= REVIEW_START for ts, _ in before),
            token_events=tokens,
        )
    return {
        "files": file_count,
        "events": event_count,
        "late_writes_excluded": late,
        "direct_token_aggregation": dict(direct),
    }


def ro_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def collect_opencode(out: list[dict[str, Any]]) -> dict[str, Any]:
    path = HOME / ".local/share/opencode/opencode.db"
    direct = collections.Counter()
    sessions = messages = 0
    with ro_db(path) as con:
        all_sessions = con.execute(
            "SELECT id,parent_id,time_created,time_updated FROM session "
            "WHERE time_updated>=? AND time_created<?",
            (int(REVIEW_START.timestamp() * 1000), int(SNAPSHOT.timestamp() * 1000)),
        ).fetchall()
        for session in all_sessions:
            sid = str(session["id"])
            token_events: list[tuple[dt.datetime, dict[str, int]]] = []
            stamped: list[dt.datetime] = []
            for message in con.execute(
                "SELECT time_created,data FROM message WHERE session_id=? ORDER BY time_created,id",
                (sid,),
            ):
                ts = parse_ts(message["time_created"])
                if not ts or ts >= SNAPSHOT:
                    continue
                stamped.append(ts)
                if ts < REVIEW_START:
                    continue
                try:
                    data = json.loads(message["data"])
                except (TypeError, ValueError):
                    continue
                native = data.get("tokens") if isinstance(data, dict) else None
                if not isinstance(native, dict):
                    continue
                cache = native.get("cache") or {}
                parts = {
                    "input_tokens": int_value(native.get("input")),
                    "output_tokens": int_value(native.get("output")),
                    "reasoning_tokens": int_value(native.get("reasoning")),
                    "cache_read_tokens": int_value(cache.get("read")),
                    "cache_write_tokens": int_value(cache.get("write")),
                }
                token_events.append((ts, parts))
                direct.update(parts)
            start = min(stamped) if stamped else parse_ts(session["time_created"])
            end = max(stamped) if stamped else parse_ts(session["time_updated"])
            add_session(
                out,
                agent="opencode",
                native_id=sid,
                parent_id=session["parent_id"],
                start=start,
                end=end,
                time_basis="native message span",
                events=len(stamped),
                token_events=token_events,
            )
            sessions += 1
            messages += len(stamped)
        sql_totals = con.execute(
            "SELECT COUNT(*) n FROM message WHERE time_created>=? AND time_created<?",
            (int(REVIEW_START.timestamp() * 1000), int(SNAPSHOT.timestamp() * 1000)),
        ).fetchone()["n"]
    return {
        "sessions": sessions,
        "messages_in_sessions": messages,
        "direct_message_count": sql_totals,
        "direct_token_aggregation": dict(direct),
    }


def collect_agy(out: list[dict[str, Any]]) -> dict[str, Any]:
    path = HOME / ".gemini/antigravity-cli/conversation_summaries.db"
    count = 0
    with ro_db(path) as con:
        records = con.execute(
            "SELECT conversation_id,parent_conversation_id,last_modified_time,step_count "
            "FROM conversation_summaries WHERE last_modified_time>=? AND last_modified_time<?",
            (iso_z(REVIEW_START), iso_z(SNAPSHOT)),
        ).fetchall()
        for row in records:
            ts = parse_ts(row["last_modified_time"])
            add_session(
                out,
                agent="agy",
                native_id=str(row["conversation_id"]),
                parent_id=row["parent_conversation_id"] or None,
                start=ts,
                end=ts,
                time_basis="native last-modified point; duration unknown",
                events=int_value(row["step_count"]),
            )
            count += 1
    return {"conversation_summaries": count, "tokens": "unknown"}


def collect_gemini(out: list[dict[str, Any]]) -> dict[str, Any]:
    files = events = 0
    for name in glob.iglob(str(HOME / ".gemini/tmp/*/chats/*.jsonl")):
        path = Path(name)
        data = list(rows(path))
        times = [parse_ts(row.get("timestamp")) for row in data]
        times = [value for value in times if value and value < SNAPSHOT]
        if not times or max(times) < REVIEW_START:
            continue
        # Antigravity CLI stores use a separate family adapter.
        if "agy" in str(path.parent.parent).lower() or "capfill" in str(path).lower():
            continue
        sid = path.stem
        add_session(
            out,
            agent="gemini",
            native_id=sid,
            parent_id=None,
            start=min(times),
            end=max(times),
            time_basis="native event span",
            events=sum(value >= REVIEW_START for value in times),
        )
        files += 1
        events += sum(value >= REVIEW_START for value in times)
    return {"files": files, "events": events, "tokens": "unknown"}


def collect_copilot(out: list[dict[str, Any]]) -> dict[str, Any]:
    path = HOME / ".copilot/session-store.db"
    direct = collections.Counter()
    usage_count = 0
    with ro_db(path) as con:
        sessions = con.execute(
            "SELECT id,created_at,updated_at FROM sessions WHERE updated_at>=? AND created_at<?",
            (iso_z(REVIEW_START), iso_z(SNAPSHOT)),
        ).fetchall()
        for session in sessions:
            token_events: list[tuple[dt.datetime, dict[str, int]]] = []
            event_times: list[dt.datetime] = []
            usage_ms = 0
            for row in con.execute(
                "SELECT created_at,input_tokens,output_tokens,cache_read_tokens,"
                "cache_write_tokens,reasoning_tokens,duration_ms "
                "FROM assistant_usage_events WHERE session_id=? AND created_at<?",
                (session["id"], iso_z(SNAPSHOT)),
            ):
                ts = parse_ts(row["created_at"])
                if not ts:
                    continue
                event_times.append(ts)
                if ts < REVIEW_START:
                    continue
                parts = {
                    "input_tokens": int_value(row["input_tokens"]),
                    "output_tokens": int_value(row["output_tokens"]),
                    "reasoning_tokens": int_value(row["reasoning_tokens"]),
                    "cache_read_tokens": int_value(row["cache_read_tokens"]),
                    "cache_write_tokens": int_value(row["cache_write_tokens"]),
                }
                token_events.append((ts, parts))
                direct.update(parts)
                usage_ms += int_value(row["duration_ms"])
                usage_count += 1
            start = min(event_times) if event_times else parse_ts(session["created_at"])
            end = max(event_times) if event_times else parse_ts(session["updated_at"])
            add_session(
                out,
                agent="copilot",
                native_id=str(session["id"]),
                parent_id=None,
                start=start,
                end=end,
                time_basis=(
                    f"native request span; metered request duration {usage_ms / 3600000:.2f}h"
                    if usage_ms
                    else "session shell; duration unknown"
                ),
                events=len(event_times),
                token_events=token_events,
            )
    return {
        "sessions": len(sessions),
        "usage_events": usage_count,
        "direct_token_aggregation": dict(direct),
    }


def event_agent(value: Any) -> str:
    agent = str(value or "").lower()
    return agent if agent in FAMILY else ""


def collect_board(sessions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    board = yaml.safe_load((ROOT / "tasks.yaml").read_text())
    asks: list[dict[str, Any]] = []
    jules_groups: dict[str, list[dt.datetime]] = collections.defaultdict(list)
    transition_counts = collections.Counter()
    for task in board.get("tasks") or []:
        relevant: list[tuple[dt.datetime, dict[str, Any]]] = []
        for event in task.get("dispatch_log") or []:
            ts = parse_ts(event.get("timestamp"))
            agent = event_agent(event.get("agent"))
            if ts and agent and REVIEW_START <= ts < SNAPSHOT:
                relevant.append((ts, event))
                transition_counts[agent] += 1
        if not relevant:
            continue
        relevant.sort(key=lambda pair: pair[0])
        agent = event_agent(relevant[-1][1].get("agent"))
        task_text = " ".join(
            [
                str(task.get("urls") or ""),
                str(task.get("context") or ""),
                *[
                    f"{event.get('session_id', '')} {event.get('output', '')}"
                    for _, event in relevant
                ],
            ]
        )
        receipt_urls = [
            url
            for url in extract_pr_urls(task_text)
            if (parse_pr_url(url) or ("", "", 0))[0].lower() in PUBLIC_OWNERS
        ]
        statuses = [str(event.get("status") or "").lower() for _, event in relevant]
        outcome = "coverage_unknown"
        if any("blocked" in status or status == "needs_human" for status in statuses):
            outcome = "blocked"
        elif receipt_urls:
            outcome = "durably_homed_open"
        elif statuses[-1] == "done":
            outcome = "not_done_or_unverified"
        asks.append(
            {
                "_receipt_urls": receipt_urls,
                "_start": relevant[0][0],
                "_end": relevant[-1][0],
                "ask": f"ask-{hid(str(task.get('id')))}",
                "agent": agent,
                "subject": sanitize_subject(str(task.get("title") or "")),
                "repo": str(task.get("repo") or "unknown"),
                "outcome": outcome,
                "receipt": receipt_urls[-1] if receipt_urls else None,
                "predicate": "remote receipt pending classification" if receipt_urls else "not proven",
                "observed_at": iso_z(relevant[-1][0]),
            }
        )
        for ts, event in relevant:
            if event_agent(event.get("agent")) != "jules":
                continue
            sid = str(event.get("session_id") or "")
            if sid:
                jules_groups[sid].append(ts)
    for sid, times in jules_groups.items():
        add_session(
            sessions,
            agent="jules",
            native_id=sid,
            parent_id=None,
            start=min(times),
            end=max(times),
            time_basis="board dispatch-to-terminal proxy",
            events=len(times),
        )
    return asks, {
        "tasks_with_family_activity": len(asks),
        "transitions": dict(transition_counts),
        "jules_session_proxies": len(jules_groups),
        "tokens": "unknown",
    }


def summarize(sessions: list[dict[str, Any]], asks: list[dict[str, Any]]) -> dict[str, Any]:
    comparison: list[dict[str, Any]] = []
    volume: list[dict[str, Any]] = []
    for window in WINDOWS:
        for agent in AGENTS:
            matched = []
            intervals: list[tuple[dt.datetime, dt.datetime]] = []
            token_totals = collections.Counter()
            for session in sessions:
                if session["agent"] != agent:
                    continue
                start = parse_ts(session["start"])
                end = parse_ts(session["end"])
                clipped = window.clip(start, end)
                if clipped is None:
                    continue
                matched.append(session)
                if "unknown" not in session["time_basis"] and clipped[1] > clipped[0]:
                    intervals.append(clipped)
                for ts, parts in session["_token_events"]:
                    if window.contains(ts):
                        token_totals.update(parts)
            ask_rows = [
                ask
                for ask in asks
                if ask["agent"] == agent
                and any(
                    window.contains(ts)
                    for ts in (ask["_start"], ask["_end"])
                )
            ]
            root_count = sum(row["role"] == "root" for row in matched)
            child_count = len(matched) - root_count
            summed = sum((end - start).total_seconds() for start, end in intervals)
            comparison.append(
                {
                    "window": window.label,
                    "agent": agent,
                    "root_sessions": root_count,
                    "child_sessions": child_count,
                    "session_span_hours": round(summed / 3600, 2),
                    "union_wall_hours": round(union_seconds(intervals) / 3600, 2),
                    "asks_observed": len(ask_rows),
                    "verified_done": sum(
                        row["outcome"] == "verified_done" for row in ask_rows
                    ),
                    "open_or_unknown": sum(
                        row["outcome"]
                        in {
                            "durably_homed_open",
                            "not_done_or_unverified",
                            "coverage_unknown",
                        }
                        for row in ask_rows
                    ),
                    "token_basis": (
                        ", ".join(TOKEN_KEYS[agent]) if agent in TOKEN_KEYS else "unknown"
                    ),
                    **{
                        key: token_totals[key]
                        for key in TOKEN_KEYS.get(agent, ())
                    },
                }
            )
            volume.append(
                {
                    "window": window.label,
                    "agent": agent,
                    "root_sessions": root_count,
                }
            )
    outcomes = []
    for agent in AGENTS:
        agent_asks = [row for row in asks if row["agent"] == agent]
        for outcome in OUTCOMES:
            outcomes.append(
                {
                    "agent": agent,
                    "outcome": outcome,
                    "ask_count": sum(row["outcome"] == outcome for row in agent_asks),
                }
            )
    appendix: dict[str, list[dict[str, Any]]] = {}
    for agent in AGENTS:
        clean = []
        for session in sessions:
            if session["agent"] != agent:
                continue
            clean.append(
                {
                    key: session.get(key)
                    for key in (
                        "session",
                        "role",
                        "start",
                        "end",
                        "time_basis",
                        "events",
                        "outcome",
                        "receipt",
                    )
                }
            )
        appendix[agent] = sorted(clean, key=lambda row: row["start"], reverse=True)
    return {
        "comparison": comparison,
        "root_session_volume": volume,
        "outcome_distribution": outcomes,
        "session_appendix": appendix,
    }


def main() -> int:
    sessions: list[dict[str, Any]] = []
    coverage = {
        "codex": collect_codex(sessions),
        "claude": collect_claude(sessions),
        "opencode": collect_opencode(sessions),
        "agy": collect_agy(sessions),
        "gemini": collect_gemini(sessions),
        "copilot": collect_copilot(sessions),
    }
    asks, board_coverage = collect_board(sessions)
    coverage["board_and_jules"] = board_coverage
    summary = summarize(sessions, asks)
    payload = {
        "schema": "limen.seven_agent_estate_review.v1",
        "snapshot_at": iso_z(SNAPSHOT),
        "windows": [
            {
                "id": window.id,
                "label": window.label,
                "start": iso_z(window.start),
                "end": iso_z(window.end),
                "half_open": True,
            }
            for window in WINDOWS
        ],
        "coverage": coverage,
        "estate": {
            "registry": "institutio/github/estate.yaml",
            "owners": ["organvm", "4444J99"],
            "remote_repository_count": None,
            "note": "Live remote census is populated by reconcile.py.",
        },
        "asks": [
            {
                key: value
                for key, value in ask.items()
                if not key.startswith("_")
            }
            for ask in asks
        ],
        **summary,
    }
    (HERE / "snapshot.json").write_text(json.dumps(payload, indent=2) + "\n")
    # Private linking material is short-lived and intentionally ignored.
    private = {
        "asks": [
            {
                "ask": ask["ask"],
                "receipt_urls": ask["_receipt_urls"],
            }
            for ask in asks
        ]
    }
    private_path = ROOT / ".limen-private/session-corpus/seven-agent-review-links.json"
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(json.dumps(private))
    print(
        json.dumps(
            {
                "sessions": len(sessions),
                "asks": len(asks),
                "appendix_rows": {
                    agent: len(summary["session_appendix"][agent]) for agent in AGENTS
                },
                "private_receipt_index": "written outside tracked report source",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
