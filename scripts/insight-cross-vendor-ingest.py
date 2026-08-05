#!/usr/bin/env python3
"""
Cross-vendor friction ingest — extends the insight-cadence organ with adapters for
every AI agent estate on the host machine.

Vendors:
  - claude    : ~/.claude/projects/ — JSONL session transcripts (already-known)
  - codex     : ~/.local/share/codex/history.jsonl (already-known)
  - opencode  : ~/.local/share/opencode/opencode.db — SQLite (NEW)
  - antigravity: ~/.gemini/antigravity-cli/ — history.jsonl + conversation_summaries.db (NEW)
  - cline     : ~/.cline/data/ — minimal JSON/logs (NEW, low-ROI, cheap adapter)
  - jules     : dormant oauth cache only — recorded as known-dormant, not skipped silently

Outputs per-vendor extraction packets to logs/insight-cross-vendor/<vendor>.json
Shape: { vendor, window_days, window_start_iso, run_at_iso, sessions_seen,
         friction_signals: [...], notable_patterns: [...], data_quality_notes: [...] }

PII firewall: packets contain ONLY counts, patterns, redacted stats.
No raw text, no filenames, no user-identifiable content is written.

Usage:
  python scripts/insight-cross-vendor-ingest.py [--window-days N] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
HOME = Path(os.environ.get("HOME", str(Path.home())))
OUT_DIR = LIMEN_ROOT / "logs" / "insight-cross-vendor"

DEFAULT_WINDOW_DAYS = 30

# Known vendor registry — every vendor must appear here; silence is not allowed.
# dormant=True means the estate exists but has no session data worth ingesting.
VENDOR_REGISTRY = {
    "claude": {
        "path": HOME / ".claude" / "projects",
        "dormant": False,
        "description": "Claude Code session JSONL transcripts",
    },
    "codex": {
        "path": HOME / ".local" / "share" / "codex" / "history.jsonl",
        "dormant": False,
        "description": "Codex history JSONL",
    },
    "opencode": {
        "path": HOME / ".local" / "share" / "opencode" / "opencode.db",
        "dormant": False,
        "description": "OpenCode SQLite session store",
    },
    "copilot": {
        "path": HOME / ".copilot" / "session-store.db",
        "dormant": False,
        "description": "GitHub Copilot CLI SQLite session store (sessions/turns/assistant_usage_events)",
    },
    "antigravity": {
        "path": HOME / ".gemini" / "antigravity-cli",
        "dormant": False,
        "description": "Gemini/Antigravity-CLI history JSONL + conversation_summaries.db",
    },
    "cline": {
        "path": HOME / ".cline" / "data",
        "dormant": False,
        "description": "Cline data directory (minimal session signals)",
    },
    "jules": {
        "path": HOME / ".jules",
        "dormant": True,
        "description": "Jules dormant oauth cache — no session data, estate acknowledged",
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Adapter: Claude Code — ~/.claude/projects/ JSONL sessions
# ---------------------------------------------------------------------------

def _ingest_claude(window_start: datetime) -> dict:
    root = VENDOR_REGISTRY["claude"]["path"]
    if not root.is_dir():
        return _empty_packet("claude", window_start, ["estate directory not found"])

    sessions_seen = 0
    error_count = 0
    correction_count = 0
    stall_count = 0
    total_turns = 0
    # Correction keywords — checked per line (no DOTALL), case-insensitive fast scan
    CORRECTION_SUBSTRINGS = (
        "that's wrong", "not right", "incorrect", "actually,", "wait,",
        "nevermind", "try again", "wrong approach", "undo that", "revert that",
    )
    MAX_SESSIONS = 500  # hard cap to prevent runaway I/O on 1316 project dirs
    # Each project dir contains JSONL files directly.
    # Fast path: use os.scandir + stat for mtime pre-filter on project dirs.
    project_dirs = list(root.iterdir()) if root.is_dir() else []
    for proj_dir in project_dirs:
        if not proj_dir.is_dir():
            continue
        # Fast pre-filter: skip entire project dir if its own mtime predates window
        try:
            dir_mtime = datetime.fromtimestamp(proj_dir.stat().st_mtime, tz=timezone.utc)
            if dir_mtime < window_start:
                continue
        except OSError:
            continue
        for jsonl_path in proj_dir.glob("*.jsonl"):
            if sessions_seen >= MAX_SESSIONS:
                break
            try:
                mtime = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)
                if mtime < window_start:
                    continue
                sessions_seen += 1
                # Line-by-line scan — avoid loading multi-MB file into regex engine
                file_turns = 0
                file_errors = 0
                file_corrections = 0
                with jsonl_path.open(encoding="utf-8", errors="replace") as fh:
                    for raw_line in fh:
                        if '"role"' in raw_line:
                            file_turns += 1
                        if '"is_error": true' in raw_line or '"is_error":true' in raw_line:
                            file_errors += 1
                        if '"role": "user"' in raw_line or '"role":"user"' in raw_line:
                            lower_line = raw_line.lower()
                            if any(kw in lower_line for kw in CORRECTION_SUBSTRINGS):
                                file_corrections += 1
                total_turns += file_turns
                error_count += file_errors
                correction_count += file_corrections
                # Stall: session has very few turns relative to line count
                if file_turns < 4 and jsonl_path.stat().st_size > 50_000:
                    stall_count += 1
            except OSError:
                pass

    # D-gap-2: classify tool errors by kind (context-window substring scan; counts only)
    # Runs a second pass only when errors were found; bounded to same MAX_SESSIONS set
    error_class: dict[str, int] = {
        "permission_denied": 0,
        "file_not_found_race": 0,
        "network_timeout_mcp": 0,
        "bash_exit_nonzero": 0,
        "parse_decode": 0,
        "interrupt_cancel": 0,
        "other": 0,
    }
    PERMISSION_PAT = (
        "permission denied", "permissiondenied", "eperm", "operation not permitted",
        "permission_error", "permission-error", "allowlist", "allow_list",
        "not allowed", "not permitted", "denied",
    )
    FILE_PAT = (
        "no such file", "enoent", "file not found", "not found", "does not exist",
        "cannot find", "no_such_file",
    )
    NETWORK_PAT = (
        "timeout", "timed out", "econnrefused", "econnreset", "network", "etimedout",
        "connection refused", "connection reset", "socket", "mcp",
        "fetch failed", "failed to fetch",
    )
    BASH_EXIT_PAT = ("exit code", "exit status", "exited with", "non-zero", "error code", "returned")
    PARSE_PAT = ("parse error", "json", "invalid", "syntax error", "unexpected token", "decode")
    INTERRUPT_PAT = ("interrupt", "cancelled", "canceled", "abort", "sigint", "killed")
    CONTEXT_WIN = 3

    if error_count > 0:
        sessions_classified = 0
        for proj_dir2 in project_dirs:
            if sessions_classified >= MAX_SESSIONS:
                break
            if not proj_dir2.is_dir():
                continue
            try:
                dir_mtime2 = datetime.fromtimestamp(proj_dir2.stat().st_mtime, tz=timezone.utc)
                if dir_mtime2 < window_start:
                    continue
            except OSError:
                continue
            for jsonl_path2 in proj_dir2.glob("*.jsonl"):
                if sessions_classified >= MAX_SESSIONS:
                    break
                try:
                    mtime2 = datetime.fromtimestamp(jsonl_path2.stat().st_mtime, tz=timezone.utc)
                    if mtime2 < window_start:
                        continue
                    sessions_classified += 1
                    lines2: list[str] = []
                    with jsonl_path2.open(encoding="utf-8", errors="replace") as fh2:
                        for raw_line2 in fh2:
                            lines2.append(raw_line2.lower())
                    for idx, line2 in enumerate(lines2):
                        if '"is_error": true' not in line2 and '"is_error":true' not in line2:
                            continue
                        start2 = max(0, idx - CONTEXT_WIN)
                        end2 = min(len(lines2), idx + CONTEXT_WIN + 1)
                        ctx = " ".join(lines2[start2:end2])
                        if any(p in ctx for p in PERMISSION_PAT):
                            error_class["permission_denied"] += 1
                        elif any(p in ctx for p in FILE_PAT):
                            error_class["file_not_found_race"] += 1
                        elif any(p in ctx for p in NETWORK_PAT):
                            error_class["network_timeout_mcp"] += 1
                        elif any(p in ctx for p in BASH_EXIT_PAT):
                            error_class["bash_exit_nonzero"] += 1
                        elif any(p in ctx for p in PARSE_PAT):
                            error_class["parse_decode"] += 1
                        elif any(p in ctx for p in INTERRUPT_PAT):
                            error_class["interrupt_cancel"] += 1
                        else:
                            error_class["other"] += 1
                except OSError:
                    pass

    friction_signals = []
    if error_count > 0:
        friction_signals.append({
            "signal": "tool_errors",
            "count": error_count,
            "description": f"{error_count} tool_result errors across {sessions_seen} sessions in window",
            # D-gap-2 classification (counts only; no text stored)
            "classification": error_class,
        })
    if correction_count > 0:
        friction_signals.append({
            "signal": "user_corrections",
            "count": correction_count,
            "description": f"{correction_count} apparent user-correction turns detected",
        })
    if stall_count > 0:
        friction_signals.append({
            "signal": "stall_sessions",
            "count": stall_count,
            "description": f"{stall_count} sessions with few turns relative to file size (stall indicator)",
        })

    notable_patterns = []
    if sessions_seen > 0 and total_turns > 0:
        avg_turns = total_turns / sessions_seen
        notable_patterns.append(f"avg_turns_per_session: {avg_turns:.1f}")
    if error_count > sessions_seen * 0.3 and sessions_seen > 0:
        notable_patterns.append("HIGH tool error rate (>30% of sessions have errors)")

    return {
        "vendor": "claude",
        "description": VENDOR_REGISTRY["claude"]["description"],
        "sessions_seen": sessions_seen,
        "friction_signals": friction_signals,
        "notable_patterns": notable_patterns,
        "data_quality_notes": [
            f"Scanned up to {MAX_SESSIONS} JSONL files (dir-mtime pre-filtered to window); found {sessions_seen}",
            "Line-by-line substring scan — fast, approximate counts; no full JSON parse",
        ],
    }


# ---------------------------------------------------------------------------
# Adapter: Codex — ~/.local/share/codex/history.jsonl
# ---------------------------------------------------------------------------

def _ingest_codex(window_start: datetime) -> dict:
    path = VENDOR_REGISTRY["codex"]["path"]
    if not path.exists():
        return _empty_packet("codex", window_start, ["history.jsonl not found"])

    sessions_seen = 0
    unique_sessions: set[str] = set()
    # Codex entries: { session_id, ts (unix sec), text }
    # We count sessions in window; text is NOT read (PII firewall)
    total_entries = 0
    session_entry_counts: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts", 0)
            if isinstance(ts, (int, float)):
                entry_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                continue
            if entry_dt < window_start:
                continue
            sid = rec.get("session_id", "")
            unique_sessions.add(sid)
            total_entries += 1
            session_entry_counts[sid] = session_entry_counts.get(sid, 0) + 1
    except OSError:
        return _empty_packet("codex", window_start, ["failed to read history.jsonl"])

    sessions_seen = len(unique_sessions)
    abandon_count = sum(1 for c in session_entry_counts.values() if c == 1)

    friction_signals = []
    if abandon_count > 0:
        friction_signals.append({
            "signal": "single_entry_sessions",
            "count": abandon_count,
            "description": f"{abandon_count} sessions with only one history entry (likely abandoned)",
        })

    avg_entries = total_entries / sessions_seen if sessions_seen else 0
    notable_patterns = [f"avg_history_entries_per_session: {avg_entries:.1f}"]
    if sessions_seen > 0 and abandon_count / sessions_seen > 0.4:
        notable_patterns.append("HIGH abandon rate: >40% of sessions have only one entry")

    return {
        "vendor": "codex",
        "description": VENDOR_REGISTRY["codex"]["description"],
        "sessions_seen": sessions_seen,
        "friction_signals": friction_signals,
        "notable_patterns": notable_patterns,
        "data_quality_notes": [
            f"Total history entries in window: {total_entries}",
            "Text field NOT read (PII firewall); signals derived from session_id and ts only",
        ],
    }


# ---------------------------------------------------------------------------
# Adapter: OpenCode — ~/.local/share/opencode/opencode.db SQLite
# ---------------------------------------------------------------------------

def _ingest_opencode(window_start: datetime) -> dict:
    db_path = VENDOR_REGISTRY["opencode"]["path"]
    if not db_path.exists():
        return _empty_packet("opencode", window_start, ["opencode.db not found"])

    window_ms = int(window_start.timestamp() * 1000)
    quality_notes = []

    try:
        # Read-only URI — never write to vendor store
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Session stats — bounded by window, LIMIT guard
        cur.execute(
            """
            SELECT
                COUNT(*) AS cnt,
                SUM(cost) AS total_cost,
                SUM(tokens_input) AS total_input,
                SUM(tokens_output) AS total_output,
                AVG(CASE WHEN time_updated > time_created
                         THEN (time_updated - time_created) / 1000.0 END) AS avg_duration_sec
            FROM session
            WHERE time_created >= ?
            LIMIT 1
            """,
            (window_ms,),
        )
        row = cur.fetchone()
        sessions_seen = int(row["cnt"] or 0)
        total_cost = float(row["total_cost"] or 0)
        total_input_tokens = int(row["total_input"] or 0)
        total_output_tokens = int(row["total_output"] or 0)
        avg_duration_sec = float(row["avg_duration_sec"] or 0)

        # Zero-cost sessions (likely errored before model call)
        cur.execute(
            "SELECT COUNT(*) FROM session WHERE time_created >= ? AND cost = 0 LIMIT 1",
            (window_ms,),
        )
        zero_cost_count = int(cur.fetchone()[0] or 0)

        # Error signals: parts with 'error' in data (bounded)
        cur.execute(
            """
            SELECT COUNT(*) FROM part
            WHERE session_id IN (
                SELECT id FROM session WHERE time_created >= ? LIMIT 5000
            )
            AND data LIKE '%error%'
            LIMIT 1
            """,
            (window_ms,),
        )
        error_part_count = int(cur.fetchone()[0] or 0)

        # Abandoned sessions: updated within 30s of creation, bounded
        cur.execute(
            """
            SELECT COUNT(*) FROM session
            WHERE time_created >= ?
            AND (time_updated - time_created) < 30000
            LIMIT 1
            """,
            (window_ms,),
        )
        abandoned_count = int(cur.fetchone()[0] or 0)

        # D-gap-1: classify rapid-abandon sessions (bounded; structure only, no text)
        # empty_shell    = <30s AND no messages at all
        # completed_fast = <30s AND tokens_input>0 OR tokens_output>0 (model was called)
        # aborted_after_content = remainder (has messages but zero tokens — user typed, no response)
        cur.execute(
            """
            SELECT COUNT(*) FROM session s
            WHERE s.time_created >= ?
            AND (s.time_updated - s.time_created) < 30000
            AND NOT EXISTS (SELECT 1 FROM message m WHERE m.session_id = s.id LIMIT 1)
            LIMIT 1
            """,
            (window_ms,),
        )
        abandon_empty_shell = int(cur.fetchone()[0] or 0)

        cur.execute(
            """
            SELECT COUNT(*) FROM session s
            WHERE s.time_created >= ?
            AND (s.time_updated - s.time_created) < 30000
            AND (s.tokens_output > 0 OR s.tokens_input > 0)
            LIMIT 1
            """,
            (window_ms,),
        )
        abandon_completed_fast = int(cur.fetchone()[0] or 0)

        # aborted_after_content = the remainder (has messages, no tokens)
        abandon_aborted_after_content = abandoned_count - abandon_empty_shell - abandon_completed_fast
        # clamp to 0 in case of overlap edge cases
        abandon_aborted_after_content = max(0, abandon_aborted_after_content)

        # Model distribution (bounded to top-10)
        cur.execute(
            """
            SELECT model, COUNT(*) as cnt
            FROM session
            WHERE time_created >= ? AND model IS NOT NULL
            GROUP BY model
            ORDER BY cnt DESC
            LIMIT 10
            """,
            (window_ms,),
        )
        model_dist = {r["model"]: r["cnt"] for r in cur.fetchall()}

        con.close()

    except sqlite3.Error as e:
        return _empty_packet("opencode", window_start, [f"SQLite error: {type(e).__name__}"])

    friction_signals = []
    if zero_cost_count > 0:
        friction_signals.append({
            "signal": "zero_cost_sessions",
            "count": zero_cost_count,
            "description": f"{zero_cost_count} sessions with $0 cost (likely errored or empty)",
        })
    if error_part_count > 0:
        friction_signals.append({
            "signal": "error_parts",
            "count": error_part_count,
            "description": f"{error_part_count} message parts contain 'error' substring",
        })
    if abandoned_count > 0:
        friction_signals.append({
            "signal": "rapid_abandon_sessions",
            "count": abandoned_count,
            "description": f"{abandoned_count} sessions updated within 30s of creation (rapid abandon)",
            # D-gap-1 classification (counts only; no text stored)
            "classification": {
                "empty_shell": abandon_empty_shell,
                "aborted_after_content": abandon_aborted_after_content,
                "completed_fast": abandon_completed_fast,
            },
        })

    notable_patterns = []
    if sessions_seen > 0:
        notable_patterns.append(f"total_cost_usd: {total_cost:.4f}")
        notable_patterns.append(f"avg_session_duration_sec: {avg_duration_sec:.0f}")
        notable_patterns.append(f"total_tokens: input={total_input_tokens} output={total_output_tokens}")
        if model_dist:
            top_model = max(model_dist, key=model_dist.get)
            notable_patterns.append(f"top_model: {top_model} ({model_dist[top_model]} sessions)")
    if sessions_seen > 0 and zero_cost_count / sessions_seen > 0.5:
        notable_patterns.append("MAJORITY of sessions have zero cost — check provider connectivity")
    if abandoned_count > 0:
        pct_empty = 100 * abandon_empty_shell / abandoned_count
        notable_patterns.append(
            f"abandon_classification: empty_shell={abandon_empty_shell} ({pct_empty:.0f}%),"
            f" completed_fast={abandon_completed_fast},"
            f" aborted_after_content={abandon_aborted_after_content}"
        )

    quality_notes.append(f"All queries bounded with LIMIT; window filter on time_created >= {window_ms}")
    quality_notes.append("Data field (JSON blob) not parsed — pattern match only for error detection")
    quality_notes.append(
        "D-gap-1 classification: token/message presence only; no message text read (PII firewall)"
    )

    return {
        "vendor": "opencode",
        "description": VENDOR_REGISTRY["opencode"]["description"],
        "sessions_seen": sessions_seen,
        "friction_signals": friction_signals,
        "notable_patterns": notable_patterns,
        "data_quality_notes": quality_notes,
    }


# ---------------------------------------------------------------------------
# Adapter: Antigravity/Gemini — ~/.gemini/antigravity-cli/
# ---------------------------------------------------------------------------

def _ingest_antigravity(window_start: datetime) -> dict:
    root = VENDOR_REGISTRY["antigravity"]["path"]
    if not root.is_dir():
        return _empty_packet("antigravity", window_start, ["antigravity-cli directory not found"])

    quality_notes: list[str] = []
    friction_signals = []
    notable_patterns = []

    # 1. history.jsonl — user prompts with timestamps
    history_path = root / "history.jsonl"
    history_entries = 0
    slash_command_count = 0
    sessions_from_history: set[str] = set()

    if history_path.exists():
        try:
            for line in history_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("timestamp", 0)
                if isinstance(ts, (int, float)):
                    entry_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                else:
                    continue
                if entry_dt < window_start:
                    continue
                history_entries += 1
                if rec.get("type") == "slash_command":
                    slash_command_count += 1
                cid = rec.get("conversationId", "")
                if cid:
                    sessions_from_history.add(cid)
        except OSError:
            quality_notes.append("history.jsonl read failed")
    else:
        quality_notes.append("history.jsonl not found")

    # 2. conversation_summaries.db — session-level friction signals
    summary_db = root / "conversation_summaries.db"
    sessions_seen = 0
    killed_count = 0

    if summary_db.exists():
        try:
            window_iso = window_start.strftime("%Y-%m-%d %H:%M:%S")
            con = sqlite3.connect(f"file:{summary_db}?mode=ro", uri=True, timeout=10)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM conversation_summaries WHERE last_modified_time >= ? LIMIT 1",
                (window_iso,),
            )
            sessions_seen = int(cur.fetchone()[0] or 0)

            cur.execute(
                "SELECT COUNT(*) FROM conversation_summaries WHERE last_modified_time >= ? AND killed = 1 LIMIT 1",
                (window_iso,),
            )
            killed_count = int(cur.fetchone()[0] or 0)

            # Step count distribution for stall detection
            cur.execute(
                """
                SELECT AVG(step_count) as avg_steps, MIN(step_count) as min_steps,
                       MAX(step_count) as max_steps
                FROM conversation_summaries
                WHERE last_modified_time >= ?
                LIMIT 1
                """,
                (window_iso,),
            )
            row = cur.fetchone()
            avg_steps = float(row["avg_steps"] or 0)

            # Single-step sessions (abandoned / stalled)
            cur.execute(
                "SELECT COUNT(*) FROM conversation_summaries WHERE last_modified_time >= ? AND step_count <= 1 LIMIT 1",
                (window_iso,),
            )
            single_step_count = int(cur.fetchone()[0] or 0)

            con.close()

            if killed_count > 0:
                friction_signals.append({
                    "signal": "killed_conversations",
                    "count": killed_count,
                    "description": f"{killed_count} conversations were killed (user-interrupted or timed-out)",
                })
            if single_step_count > 0:
                friction_signals.append({
                    "signal": "single_step_conversations",
                    "count": single_step_count,
                    "description": f"{single_step_count} conversations with <=1 step (likely abandoned)",
                })
            if avg_steps > 0:
                notable_patterns.append(f"avg_steps_per_conversation: {avg_steps:.1f}")

        except sqlite3.Error as e:
            quality_notes.append(f"conversation_summaries.db error: {type(e).__name__}")
    else:
        quality_notes.append("conversation_summaries.db not found or empty")

    # Use the richer count between history entries and summary db sessions
    sessions_seen = max(sessions_seen, len(sessions_from_history))

    if history_entries > 0:
        notable_patterns.append(f"history_entries_in_window: {history_entries}")
    if slash_command_count > 0:
        notable_patterns.append(f"slash_commands_used: {slash_command_count}")
        if slash_command_count / max(history_entries, 1) > 0.5:
            notable_patterns.append("HIGH slash-command usage ratio (power-user pattern)")

    quality_notes.append(f"conversation_summaries.db queried with datetime window >= {window_start.date()}")
    quality_notes.append("Per-conversation .db files not parsed (binary blob data; schema opaque)")

    return {
        "vendor": "antigravity",
        "description": VENDOR_REGISTRY["antigravity"]["description"],
        "sessions_seen": sessions_seen,
        "friction_signals": friction_signals,
        "notable_patterns": notable_patterns,
        "data_quality_notes": quality_notes,
    }


# ---------------------------------------------------------------------------
# Adapter: Cline — ~/.cline/data/ minimal signals
# ---------------------------------------------------------------------------

def _ingest_cline(window_start: datetime) -> dict:
    root = VENDOR_REGISTRY["cline"]["path"]
    if not root.is_dir():
        return _empty_packet("cline", window_start, ["cline data directory not found"])

    quality_notes: list[str] = []
    friction_signals = []
    notable_patterns = []

    # 1. Workspace count (each workspace dir = one VS Code project used with Cline)
    workspaces_dir = root / "workspaces"
    workspace_count = 0
    if workspaces_dir.is_dir():
        workspace_count = sum(1 for p in workspaces_dir.iterdir() if p.is_dir())

    # 2. Log file for error/crash signals
    log_file = root / "logs" / "cline-cli.1.log"
    log_lines = 0
    error_log_lines = 0
    debug_auth_failures = 0
    if log_file.exists():
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = rec.get("time", "")
                try:
                    entry_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if entry_dt < window_start:
                        continue
                except (ValueError, TypeError):
                    # No timestamp — count all entries in file
                    pass
                log_lines += 1
                level = rec.get("level", 0)
                if level >= 50:  # pino: 50=error, 60=fatal
                    error_log_lines += 1
                msg = str(rec.get("msg", ""))
                if "auth" in msg.lower() and ("fail" in msg.lower() or "error" in msg.lower()):
                    debug_auth_failures += 1
        except OSError:
            quality_notes.append("log file read failed")
    else:
        quality_notes.append("cline-cli.1.log not found — minimal session data available")

    # 3. State files = proxy for session count (each has workspaceState.json)
    sessions_seen = workspace_count  # best proxy available

    if error_log_lines > 0:
        friction_signals.append({
            "signal": "log_errors",
            "count": error_log_lines,
            "description": f"{error_log_lines} error/fatal level log entries",
        })
    if debug_auth_failures > 0:
        friction_signals.append({
            "signal": "auth_failures",
            "count": debug_auth_failures,
            "description": f"{debug_auth_failures} authentication-related log messages",
        })

    notable_patterns.append(f"workspace_count: {workspace_count}")
    notable_patterns.append(f"total_log_lines_in_window: {log_lines}")
    quality_notes.append("LOW-ROI adapter: Cline stores minimal structured session data outside of VS Code")
    quality_notes.append("sessions_seen = workspace directory count (proxy, not actual session count)")

    return {
        "vendor": "cline",
        "description": VENDOR_REGISTRY["cline"]["description"],
        "sessions_seen": sessions_seen,
        "friction_signals": friction_signals,
        "notable_patterns": notable_patterns,
        "data_quality_notes": quality_notes,
    }


# ---------------------------------------------------------------------------
# Adapter: GitHub Copilot CLI — ~/.copilot/session-store.db SQLite
# ---------------------------------------------------------------------------
#
# Store shape (v1.0.x): the live session data lives in session-store.db, NOT
# data.db (data.db.sessions is empty by design — it holds project/workspace
# metadata; the session-store is authoritative). Three tables carry signal:
#   sessions               (id, repository, branch, created_at, updated_at)  — datetime('now') text
#   turns                  (session_id, turn_index, timestamp)               — user↔assistant pairs
#   assistant_usage_events (session_id, model, *_tokens, total_nano_aiu,
#                           duration_ms, time_to_first_token_ms, finish_reason,
#                           content_filter_triggered)                        — per-model-call rows
#
# PII firewall: we read integer/enum columns only (token counts, timestamps,
# finish_reason enum, content_filter flag, model id). We NEVER read the text
# columns turns.user_message / turns.assistant_response / sessions.summary.

def _ingest_copilot(window_start: datetime) -> dict:
    db_path = VENDOR_REGISTRY["copilot"]["path"]
    if not db_path.exists():
        return _empty_packet("copilot", window_start, ["session-store.db not found"])

    # sessions.created_at is SQLite datetime('now') → "YYYY-MM-DD HH:MM:SS" (UTC).
    # Lexical string comparison on this ISO-like format is a correct window filter.
    window_iso = window_start.strftime("%Y-%m-%d %H:%M:%S")
    quality_notes: list[str] = []

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Session count in window
        cur.execute("SELECT COUNT(*) FROM sessions WHERE created_at >= ? LIMIT 1", (window_iso,))
        sessions_seen = int(cur.fetchone()[0] or 0)

        # Turn totals + single-turn (abandon) sessions in window, bounded
        cur.execute(
            """
            SELECT COUNT(*) AS turn_total FROM turns
            WHERE session_id IN (SELECT id FROM sessions WHERE created_at >= ? LIMIT 5000)
            LIMIT 1
            """,
            (window_iso,),
        )
        turn_total = int(cur.fetchone()[0] or 0)

        cur.execute(
            """
            SELECT COUNT(*) FROM sessions s
            WHERE s.created_at >= ?
            AND (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) <= 1
            LIMIT 1
            """,
            (window_iso,),
        )
        single_turn_count = int(cur.fetchone()[0] or 0)

        # Usage-event aggregates for in-window sessions (bounded subquery)
        cur.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0)  AS in_tok,
                COALESCE(SUM(output_tokens), 0) AS out_tok,
                COALESCE(SUM(total_nano_aiu), 0) AS nano_aiu,
                AVG(duration_ms)                AS avg_dur,
                AVG(time_to_first_token_ms)     AS avg_ttft,
                COALESCE(SUM(content_filter_triggered), 0) AS cf_hits,
                COUNT(*)                        AS event_count
            FROM assistant_usage_events
            WHERE session_id IN (SELECT id FROM sessions WHERE created_at >= ? LIMIT 5000)
            LIMIT 1
            """,
            (window_iso,),
        )
        row = cur.fetchone()
        total_input_tokens = int(row["in_tok"] or 0)
        total_output_tokens = int(row["out_tok"] or 0)
        total_nano_aiu = int(row["nano_aiu"] or 0)
        avg_duration_ms = float(row["avg_dur"] or 0)
        avg_ttft_ms = float(row["avg_ttft"] or 0)
        content_filter_hits = int(row["cf_hits"] or 0)
        event_count = int(row["event_count"] or 0)

        # finish_reason distribution (enum only, no text). 'stop'/'tool_calls'/
        # 'tool_use' are normal terminations; everything else (length,
        # content_filter, error, …) is an abnormal finish = friction.
        cur.execute(
            """
            SELECT finish_reason, COUNT(*) AS cnt
            FROM assistant_usage_events
            WHERE session_id IN (SELECT id FROM sessions WHERE created_at >= ? LIMIT 5000)
            GROUP BY finish_reason
            ORDER BY cnt DESC
            LIMIT 20
            """,
            (window_iso,),
        )
        finish_dist: dict[str, int] = {}
        normal_finish = {"stop", "tool_calls", "tool_use", "end_turn", None, ""}
        abnormal_finish_count = 0
        for r in cur.fetchall():
            fr = r["finish_reason"]
            finish_dist[str(fr)] = int(r["cnt"] or 0)
            if fr not in normal_finish:
                abnormal_finish_count += int(r["cnt"] or 0)

        # Model distribution (top-10)
        cur.execute(
            """
            SELECT model, COUNT(*) AS cnt
            FROM assistant_usage_events
            WHERE session_id IN (SELECT id FROM sessions WHERE created_at >= ? LIMIT 5000)
              AND model IS NOT NULL
            GROUP BY model ORDER BY cnt DESC LIMIT 10
            """,
            (window_iso,),
        )
        model_dist = {r["model"]: r["cnt"] for r in cur.fetchall()}

        con.close()

    except sqlite3.Error as e:
        return _empty_packet("copilot", window_start, [f"SQLite error: {type(e).__name__}"])

    friction_signals = []
    if single_turn_count > 0:
        friction_signals.append({
            "signal": "single_turn_sessions",
            "count": single_turn_count,
            "description": f"{single_turn_count} sessions with <=1 turn (opened then abandoned)",
        })
    if abnormal_finish_count > 0:
        friction_signals.append({
            "signal": "abnormal_finish_reasons",
            "count": abnormal_finish_count,
            "description": f"{abnormal_finish_count} model calls ended on a non-normal finish_reason "
                           f"(length/content_filter/error)",
            "classification": finish_dist,
        })
    if content_filter_hits > 0:
        friction_signals.append({
            "signal": "content_filter_triggered",
            "count": content_filter_hits,
            "description": f"{content_filter_hits} model calls tripped the content filter",
        })

    notable_patterns = []
    if sessions_seen > 0:
        avg_turns = turn_total / sessions_seen
        notable_patterns.append(f"avg_turns_per_session: {avg_turns:.1f}")
    if event_count > 0:
        notable_patterns.append(f"total_tokens: input={total_input_tokens} output={total_output_tokens}")
        notable_patterns.append(f"total_nano_aiu: {total_nano_aiu} (Copilot AI-unit cost proxy)")
        notable_patterns.append(f"avg_response_latency_ms: ttft={avg_ttft_ms:.0f} duration={avg_duration_ms:.0f}")
        if model_dist:
            top_model = max(model_dist, key=model_dist.get)
            notable_patterns.append(f"top_model: {top_model} ({model_dist[top_model]} calls)")
    if sessions_seen > 0 and single_turn_count / sessions_seen > 0.4:
        notable_patterns.append("HIGH single-turn rate: >40% of sessions abandoned after one turn")

    quality_notes.append(f"session-store.db queried read-only; window filter created_at >= '{window_iso}'")
    quality_notes.append("data.db.sessions is empty by design — session-store.db is the live store")
    quality_notes.append("Text columns (turns.user_message/assistant_response, sessions.summary) NOT read (PII firewall)")

    return {
        "vendor": "copilot",
        "description": VENDOR_REGISTRY["copilot"]["description"],
        "sessions_seen": sessions_seen,
        "friction_signals": friction_signals,
        "notable_patterns": notable_patterns,
        "data_quality_notes": quality_notes,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_packet(vendor: str, window_start: datetime, notes: list[str]) -> dict:
    return {
        "vendor": vendor,
        "description": VENDOR_REGISTRY.get(vendor, {}).get("description", ""),
        "sessions_seen": 0,
        "friction_signals": [],
        "notable_patterns": [],
        "data_quality_notes": notes,
    }


def _make_packet(vendor: str, window_days: int, window_start: datetime, run_at: datetime, data: dict) -> dict:
    return {
        "vendor": vendor,
        "window_days": window_days,
        "window_start_iso": _iso(window_start),
        "run_at_iso": _iso(run_at),
        **data,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ADAPTERS = {
    "claude": _ingest_claude,
    "codex": _ingest_codex,
    "opencode": _ingest_opencode,
    "copilot": _ingest_copilot,
    "antigravity": _ingest_antigravity,
    "cline": _ingest_cline,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-vendor friction ingest for insight-cadence organ")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                        help=f"Ingest window in days (default: {DEFAULT_WINDOW_DAYS})")
    parser.add_argument("--vendor", help="Run only this vendor adapter (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Print packets, write nothing")
    args = parser.parse_args()

    now = _now()
    window_start = now - timedelta(days=args.window_days)
    packets: list[dict] = []
    run_stats: dict[str, str] = {}

    target_vendors = [args.vendor] if args.vendor else list(ADAPTERS.keys())

    for vendor in target_vendors:
        if vendor not in ADAPTERS:
            print(f"[WARN] Unknown vendor: {vendor}", file=sys.stderr)
            continue
        try:
            data = ADAPTERS[vendor](window_start)
            packet = _make_packet(vendor, args.window_days, window_start, now, data)
            packets.append(packet)
            sigs = len(data.get("friction_signals", []))
            sess = data.get("sessions_seen", 0)
            run_stats[vendor] = f"sessions={sess} friction_signals={sigs}"
        except Exception as e:
            # Never crash the whole run on one vendor failure
            error_packet = _make_packet(vendor, args.window_days, window_start, now, {
                "vendor": vendor,
                "description": VENDOR_REGISTRY.get(vendor, {}).get("description", ""),
                "sessions_seen": 0,
                "friction_signals": [],
                "notable_patterns": [],
                "data_quality_notes": [f"Adapter raised {type(e).__name__}: {e}"],
            })
            packets.append(error_packet)
            run_stats[vendor] = f"ERROR: {type(e).__name__}"

    # Record dormant vendors explicitly (no-silent-caps rule)
    for vendor, meta in VENDOR_REGISTRY.items():
        if meta.get("dormant") and vendor not in target_vendors:
            dormant_packet = _make_packet(vendor, args.window_days, window_start, now, {
                "vendor": vendor,
                "description": meta["description"],
                "sessions_seen": 0,
                "friction_signals": [],
                "notable_patterns": [],
                "data_quality_notes": [
                    "DORMANT: vendor estate exists on host but has no session data to ingest",
                    f"Path: {meta['path']}",
                ],
            })
            packets.append(dormant_packet)
            run_stats[vendor] = "dormant"

    if args.dry_run:
        for p in packets:
            print(json.dumps(p, indent=2))
        return 0

    # Write per-vendor packets
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for p in packets:
        out_path = OUT_DIR / f"{p['vendor']}.json"
        _atomic_write(out_path, json.dumps(p, indent=2))
        written.append(str(out_path))

    # Write run manifest
    manifest = {
        "run_at_iso": _iso(now),
        "window_days": args.window_days,
        "window_start_iso": _iso(window_start),
        "vendors": run_stats,
        "packets_written": written,
    }
    manifest_path = OUT_DIR / "run-manifest.json"
    _atomic_write(manifest_path, json.dumps(manifest, indent=2))
    written.append(str(manifest_path))

    print(f"[insight-cross-vendor-ingest] {len(packets)} vendor packets written to {OUT_DIR}")
    for v, stat in run_stats.items():
        print(f"  {v}: {stat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
