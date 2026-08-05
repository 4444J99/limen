#!/usr/bin/env python3
"""Build a redacted lifecycle crosswalk from prompts to sessions, worktrees, and tasks.

The tracked markdown is intentionally counts-only and receipt-oriented. The ignored
private index keeps source paths, stable hashes, and prompt-event hashes so the raw
material can be found in the private cartridge without committing prompt text.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))
from limen.runtime_config import RUNTIME_URL_ENV_ORDER, runtime_api_url  # noqa: E402

# Doc artifacts belong to the repo this script lives in — never to the runtime root — so a
# dev/worktree run cannot silently dirty the live checkout (LIMEN_ROOT keeps owning the board).
REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
DOC_PATH = REPO / "docs" / "prompt-lifecycle-ledger.md"
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
EVERY_ASK_PATH = REPO / "EVERY-ASK-LEDGER.md"
EVERY_ASK_CURATED_BEGIN = "<!-- CURATED:BEGIN -->"
EVERY_ASK_CURATED_END = "<!-- CURATED:END -->"
TASKS_PATH = ROOT / "tasks.yaml"
WORKTREE_ROOT = ROOT.parent / ".limen-worktrees"
OPENCODE_DB = HOME / ".local" / "share" / "opencode" / "opencode.db"
AGY_CLI_ROOT = HOME / ".gemini" / "antigravity-cli"
AGY_CLI_HISTORY = AGY_CLI_ROOT / "history.jsonl"
AGY_CLI_CONVERSATIONS = AGY_CLI_ROOT / "conversations"
GITHUB_PR_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


def int_or_default(raw: Any, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


DISPATCH_GRACE_SECONDS = int_or_default(os.environ.get("LIMEN_LANE_TIMEOUT"), 900) + 600
GH_RETRIES = max(1, int_or_default(os.environ.get("LIMEN_GH_RECEIPT_RETRIES"), 3))
TRANSIENT_GH_ERROR_BITS = (
    "connect: network is unreachable",
    "connection reset",
    "connection refused",
    "i/o timeout",
    "tls handshake timeout",
    "temporary failure",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
)

LOCAL_SOURCES = [
    ("codex-sessions", HOME / ".codex" / "sessions", ("*",)),
    ("codex-history", HOME / ".codex", ("history.jsonl",)),
    ("codex-attachments", HOME / ".codex" / "attachments", ("*",)),
    ("claude-projects", HOME / ".claude" / "projects", ("*",)),
    ("claude-tasks", HOME / ".claude" / "tasks", ("*",)),
    ("claude-plans", HOME / ".claude" / "plans", ("*",)),
    ("claude-file-history", HOME / ".claude" / "file-history", ("*",)),
    ("gemini-tmp-agy", HOME / ".gemini" / "tmp", ("capfill-agy-*/chats/*.jsonl", "*agy*/chats/*.jsonl")),
    ("agy-cli-history", AGY_CLI_ROOT, ("history.jsonl",)),
]

TASK_BODY_MARKERS = (
    "Complete task ",
    "## Current task",
    "## Task",
    "## Work packet",
    "## Packet",
    "### Task",
    "TASK:",
    "Task:",
)

VALID_STATUSES = {
    "open",
    "dispatched",
    "in_progress",
    "done",
    "failed",
    "failed_blocked",
    "needs_human",
    "archived",
}


def iso_from_ts(ts: float | None) -> str | None:
    if not ts:
        return None
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat(timespec="seconds")


def fmt_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    val = float(n)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(val)} {unit}"
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{n} B"


def stable_hash(text: str, length: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def full_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def parse_ts(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def iso_from_epoch_ms(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def maybe_decode_wrapped_string(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] == '"':
        try:
            decoded = json.loads(stripped)
        except ValueError:
            return text
        if isinstance(decoded, str):
            return decoded
    return text


def normalize_task_body(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if stripped.startswith("<session_context>"):
        return "", "session_context"
    if stripped.startswith("# FLAME"):
        positions = [(stripped.find(marker), marker) for marker in TASK_BODY_MARKERS if stripped.find(marker) >= 0]
        if positions:
            pos, _marker = min(positions, key=lambda item: item[0])
            return stripped[pos:], "flame_with_task_body"
        return "", "flame_scaffold"
    return stripped, "direct"


def prompt_fingerprint(text: str) -> dict[str, Any]:
    text = maybe_decode_wrapped_string(text)
    task_body, body_kind = normalize_task_body(text)
    prompt_bytes = len(text.encode("utf-8", errors="replace"))
    task_body_bytes = len(task_body.encode("utf-8", errors="replace"))
    return {
        "prompt_hash": full_hash(text),
        "prompt_bytes": prompt_bytes,
        "task_body_hash": full_hash(task_body) if task_body else None,
        "task_body_bytes": task_body_bytes,
        "body_kind": body_kind,
    }


def blob_text_spans(blob: bytes | None, *, min_len: int = 40) -> list[str]:
    if not blob:
        return []
    decoded = blob.decode("utf-8", errors="ignore")
    chars: list[str] = []
    for ch in decoded:
        if ch in "\n\r\t" or (ch.isprintable() and unicodedata.category(ch)[0] != "C"):
            chars.append(ch)
        else:
            chars.append("\0")
    out: list[str] = []
    seen: set[str] = set()
    for part in "".join(chars).split("\0"):
        text = part.strip()
        if len(text) < min_len or sum(c.isalpha() for c in text) < 12:
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def agy_prompt_from_spans(spans: list[str]) -> str | None:
    prompt_markers = ("# FLAME", "## FLAME", "Complete task ", "/goal", "Repo:", "Rules:", "Context:")
    candidates = [span for span in spans if any(marker in span for marker in prompt_markers)]
    if not candidates:
        candidates = [span for span in spans if len(span) >= 120]
    if not candidates:
        return None
    text = max(candidates, key=len).strip()
    return text.lstrip("#,- \n\t") or text


def iter_source_files(days: int | None) -> list[dict[str, Any]]:
    cutoff = None if days is None else dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
    rows: list[dict[str, Any]] = []
    for source, root, patterns in LOCAL_SOURCES:
        if not root.exists():
            continue
        seen: set[Path] = set()
        candidates = [root] if root.is_file() else [path for pattern in patterns for path in root.rglob(pattern)]
        for path in candidates:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                st = path.stat()
            except OSError:
                continue
            if cutoff is not None and st.st_mtime < cutoff:
                continue
            rows.append(
                {
                    "source": source,
                    "path": path,
                    "display_path": relpath(path),
                    "size": st.st_size,
                    "mtime": iso_from_ts(st.st_mtime),
                }
            )
    rows.sort(key=lambda r: (r["mtime"] or "", r["source"], str(r["path"])), reverse=True)
    return rows


def text_from_content(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(text_from_content(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("text", "content", "message", "input"):
            if key in value:
                out.extend(text_from_content(value[key]))
        return out
    return []


def prompt_texts(source: str, obj: dict[str, Any]) -> list[str]:
    if source == "codex-history":
        return text_from_content(obj.get("text"))

    if source == "gemini-tmp-agy":
        texts: list[str] = []
        if obj.get("type") == "user":
            texts.extend(text_from_content(obj.get("content")))
        set_obj = obj.get("$set")
        if isinstance(set_obj, dict) and isinstance(set_obj.get("messages"), list):
            for rec in set_obj["messages"]:
                if isinstance(rec, dict) and rec.get("type") == "user":
                    texts.extend(text_from_content(rec.get("content")))
        return texts

    if source == "agy-cli-history":
        return text_from_content(obj.get("display"))

    payload = obj.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "user_message":
            return text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))
        if payload.get("type") == "message" and payload.get("role") == "user":
            return text_from_content(payload.get("content"))

    typ = obj.get("type")
    if source.startswith("claude"):
        if typ == "user":
            msg = obj.get("message")
            if isinstance(msg, dict) and msg.get("role") not in (None, "user"):
                return []
            return text_from_content(msg)
        if typ == "last-prompt":
            return text_from_content(obj.get("lastPrompt"))
        if typ == "queue-operation" and obj.get("operation") == "enqueue":
            return text_from_content(obj.get("content"))

    if source == "claude-tasks":
        return (
            text_from_content(obj.get("prompt"))
            + text_from_content(obj.get("content"))
            + text_from_content(obj.get("description"))
        )
    return []


def read_json_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if path.suffix == ".jsonl" or path.name.endswith(".jsonl") or path.name == "history.jsonl":
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(obj, dict):
                        records.append(obj)
        except OSError:
            pass
        return records
    if path.suffix == ".json":
        try:
            obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return []
        if isinstance(obj, dict):
            return [obj]
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    return []


def session_meta_from_records(source: str, row: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    session_id: str | None = None
    cwd: str | None = None
    event_times: list[str] = []
    prompt_hashes: list[str] = []
    task_body_hashes: list[str] = []
    body_kind_counts: Counter[str] = Counter()
    prompt_bytes = 0
    task_body_bytes = 0

    for obj in records:
        timestamp = obj.get("timestamp") or obj.get("ts")
        if timestamp is not None:
            event_times.append(str(timestamp))
        if source == "codex-history" and obj.get("session_id"):
            session_id = str(obj.get("session_id"))
        if obj.get("sessionId"):
            session_id = str(obj.get("sessionId"))
        payload = obj.get("payload")
        if isinstance(payload, dict):
            if payload.get("session_id"):
                session_id = str(payload.get("session_id"))
            if payload.get("cwd"):
                cwd = str(payload.get("cwd"))
        if obj.get("cwd"):
            cwd = str(obj.get("cwd"))
        for text in prompt_texts(source, obj):
            fingerprint = prompt_fingerprint(text)
            prompt_bytes += int(fingerprint["prompt_bytes"])
            task_body_bytes += int(fingerprint["task_body_bytes"])
            prompt_hashes.append(str(fingerprint["prompt_hash"]))
            if fingerprint["task_body_hash"]:
                task_body_hashes.append(str(fingerprint["task_body_hash"]))
            body_kind_counts[str(fingerprint["body_kind"])] += 1

    if session_id is None:
        session_id = row["path"].stem
    session_key = stable_hash(f"{source}:{session_id}:{row['display_path']}", 20)
    return {
        "session_key": session_key,
        "session_id_hash": stable_hash(session_id, 20),
        "source": source,
        "path": str(row["path"]),
        "display_path": row["display_path"],
        "size": row["size"],
        "mtime": row["mtime"],
        "event_count": len(records),
        "first_event": min(event_times) if event_times else None,
        "last_event": max(event_times) if event_times else None,
        "cwd": cwd,
        "cwd_hash": stable_hash(cwd, 20) if cwd else None,
        "prompt_event_count": len(prompt_hashes),
        "prompt_bytes": prompt_bytes,
        "task_body_bytes": task_body_bytes,
        "first_prompt_hash": prompt_hashes[0] if prompt_hashes else None,
        "last_prompt_hash": prompt_hashes[-1] if prompt_hashes else None,
        "prompt_hashes": prompt_hashes,
        "task_body_hashes": task_body_hashes,
        "body_kind_counts": dict(sorted(body_kind_counts.items())),
    }


def opencode_part_texts(parts: list[sqlite3.Row]) -> list[str]:
    texts: list[str] = []
    for part in parts:
        try:
            data = json.loads(part["data"]) if part["data"] else {}
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        typ = data.get("type")
        if typ in ("text", "compaction"):
            text = data.get("text") or data.get("summary")
            if isinstance(text, str) and text.strip():
                texts.append(text)
        elif typ == "subtask":
            prompt = data.get("prompt") or data.get("description")
            if isinstance(prompt, str) and prompt.strip():
                texts.append(prompt)
    return texts


def opencode_virtual_sessions(days: int | None) -> list[dict[str, Any]]:
    if not OPENCODE_DB.exists():
        return []
    cutoff_ms = None
    if days is not None:
        cutoff_ms = int((dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400) * 1000)
    try:
        con = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    con.row_factory = sqlite3.Row
    try:
        where = "WHERE time_updated >= ?" if cutoff_ms is not None else ""
        params: tuple[Any, ...] = (cutoff_ms,) if cutoff_ms is not None else ()
        sessions = con.execute(
            "SELECT id, title, directory, time_created, time_updated, summary_additions, "
            "summary_deletions, summary_files, summary_diffs, cost, tokens_input, "
            "tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write, model "
            f"FROM session {where} ORDER BY time_created, id",
            params,
        ).fetchall()
    except sqlite3.Error:
        con.close()
        return []

    out: list[dict[str, Any]] = []
    db_display = relpath(OPENCODE_DB)
    for session in sessions:
        sid = str(session["id"])
        try:
            messages = con.execute(
                "SELECT id, time_created, time_updated, data FROM message WHERE session_id=? ORDER BY time_created, id",
                (sid,),
            ).fetchall()
            parts_by_message: dict[str, list[sqlite3.Row]] = defaultdict(list)
            part_count = 0
            for part in con.execute(
                "SELECT message_id, time_created, time_updated, data FROM part WHERE session_id=? "
                "ORDER BY time_created, id",
                (sid,),
            ):
                parts_by_message[str(part["message_id"])].append(part)
                part_count += 1
        except sqlite3.Error:
            continue

        event_times = [
            ts
            for ts in (
                iso_from_epoch_ms(row["time_created"])
                for row in list(messages) + [p for ps in parts_by_message.values() for p in ps]
            )
            if ts
        ]
        prompt_hashes: list[str] = []
        task_body_hashes: list[str] = []
        body_kind_counts: Counter[str] = Counter()
        prompt_bytes = 0
        task_body_bytes = 0
        for message in messages:
            try:
                data = json.loads(message["data"]) if message["data"] else {}
            except (TypeError, ValueError):
                continue
            if not isinstance(data, dict) or data.get("role") != "user":
                continue
            texts = opencode_part_texts(parts_by_message.get(str(message["id"]), []))
            text = "\n\n".join(texts)
            if not text.strip():
                continue
            fingerprint = prompt_fingerprint(text)
            prompt_bytes += int(fingerprint["prompt_bytes"])
            task_body_bytes += int(fingerprint["task_body_bytes"])
            prompt_hashes.append(str(fingerprint["prompt_hash"]))
            if fingerprint["task_body_hash"]:
                task_body_hashes.append(str(fingerprint["task_body_hash"]))
            body_kind_counts[str(fingerprint["body_kind"])] += 1

        summary_diffs = []
        try:
            decoded = json.loads(session["summary_diffs"]) if session["summary_diffs"] else []
            if isinstance(decoded, list):
                summary_diffs = [stable_hash(str(item), 20) for item in decoded]
        except (TypeError, ValueError):
            summary_diffs = []

        session_id = sid
        out.append(
            {
                "session_key": stable_hash(f"opencode-db:{session_id}:{OPENCODE_DB}", 20),
                "session_id_hash": stable_hash(session_id, 20),
                "source": "opencode-db",
                "path": str(OPENCODE_DB),
                "display_path": f"{db_display}#{stable_hash(session_id, 12)}",
                "source_file": str(OPENCODE_DB),
                "virtual_source": True,
                "size": 0,
                "mtime": iso_from_epoch_ms(session["time_updated"]),
                "event_count": len(messages) + part_count,
                "first_event": min(event_times) if event_times else None,
                "last_event": max(event_times) if event_times else None,
                "cwd": session["directory"],
                "cwd_hash": stable_hash(session["directory"], 20) if session["directory"] else None,
                "prompt_event_count": len(prompt_hashes),
                "prompt_bytes": prompt_bytes,
                "task_body_bytes": task_body_bytes,
                "first_prompt_hash": prompt_hashes[0] if prompt_hashes else None,
                "last_prompt_hash": prompt_hashes[-1] if prompt_hashes else None,
                "prompt_hashes": prompt_hashes,
                "task_body_hashes": task_body_hashes,
                "body_kind_counts": dict(sorted(body_kind_counts.items())),
                "title_hash": stable_hash(session["title"], 20) if session["title"] else None,
                "model_hash": stable_hash(session["model"], 20) if session["model"] else None,
                "summary_files": session["summary_files"],
                "summary_additions": session["summary_additions"],
                "summary_deletions": session["summary_deletions"],
                "summary_diff_hashes": summary_diffs,
                "tokens": {
                    "input": session["tokens_input"],
                    "output": session["tokens_output"],
                    "reasoning": session["tokens_reasoning"],
                    "cache_read": session["tokens_cache_read"],
                    "cache_write": session["tokens_cache_write"],
                },
                "cost": session["cost"],
            }
        )
    con.close()
    return out


def agy_cli_conversation_sessions(days: int | None) -> list[dict[str, Any]]:
    if not AGY_CLI_CONVERSATIONS.exists():
        return []
    cutoff = None if days is None else dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
    out: list[dict[str, Any]] = []
    for path in sorted(AGY_CLI_CONVERSATIONS.glob("*.db")):
        try:
            st = path.stat()
        except OSError:
            continue
        if cutoff is not None and st.st_mtime < cutoff:
            continue
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT idx, step_type, status, step_payload, metadata, task_details, "
                "error_details, render_info FROM steps ORDER BY idx"
            ).fetchall()
        except sqlite3.Error:
            con.close()
            continue
        prompt_hashes: list[str] = []
        task_body_hashes: list[str] = []
        prompt_bytes = 0
        task_body_bytes = 0
        body_kind_counts: Counter[str] = Counter()
        for row in rows:
            if int(row["step_type"]) != 14:
                continue
            spans: list[str] = []
            for column in ("step_payload", "metadata", "task_details", "error_details", "render_info"):
                spans.extend(blob_text_spans(row[column]))
            prompt = agy_prompt_from_spans(spans)
            if not prompt:
                continue
            fingerprint = prompt_fingerprint(prompt)
            prompt_bytes += int(fingerprint["prompt_bytes"])
            task_body_bytes += int(fingerprint["task_body_bytes"])
            prompt_hashes.append(str(fingerprint["prompt_hash"]))
            if fingerprint["task_body_hash"]:
                task_body_hashes.append(str(fingerprint["task_body_hash"]))
            body_kind_counts[str(fingerprint["body_kind"])] += 1
        con.close()
        sid = path.stem
        out.append(
            {
                "session_key": stable_hash(f"agy-cli-conversations:{sid}:{path}", 20),
                "session_id_hash": stable_hash(sid, 20),
                "source": "agy-cli-conversations",
                "path": str(path),
                "display_path": relpath(path),
                "size": st.st_size,
                "mtime": iso_from_ts(st.st_mtime),
                "event_count": len(rows),
                "first_event": None,
                "last_event": None,
                "cwd": None,
                "cwd_hash": None,
                "prompt_event_count": len(prompt_hashes),
                "prompt_bytes": prompt_bytes,
                "task_body_bytes": task_body_bytes,
                "first_prompt_hash": prompt_hashes[0] if prompt_hashes else None,
                "last_prompt_hash": prompt_hashes[-1] if prompt_hashes else None,
                "prompt_hashes": prompt_hashes,
                "task_body_hashes": task_body_hashes,
                "body_kind_counts": dict(sorted(body_kind_counts.items())),
            }
        )
    return out


def current_worktree_report() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "worktree-debt.py"), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return {"total": 0, "debt": 0, "by_reason": {}, "items": [], "error": proc.stderr.strip()}
    return json.loads(proc.stdout)


def run_cmd(argv: list[str], *, cwd: Path | None = None, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd or ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 1, "", str(exc))


def is_transient_gh_error(proc: subprocess.CompletedProcess[str]) -> bool:
    text = f"{proc.stderr}\n{proc.stdout}".lower()
    return any(bit in text for bit in TRANSIENT_GH_ERROR_BITS)


def run_gh_cmd(argv: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    last = subprocess.CompletedProcess(argv, 1, "", "not run")
    for attempt in range(GH_RETRIES):
        last = run_cmd(argv, timeout=timeout)
        if last.returncode == 0 or not is_transient_gh_error(last) or attempt == GH_RETRIES - 1:
            return last
        time.sleep(min(4.0, 0.75 * (attempt + 1)))
    return last


def repo_from_remote(remote: str) -> str | None:
    remote = remote.strip()
    patterns = [
        r"github\.com[:/]([^/\s]+/[^/\s.]+?)(?:\.git)?$",
        r"https://github\.com/([^/\s]+/[^/\s.]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, remote)
        if match:
            return match.group(1)
    return None


def gh_pr_view(owner: str, repo: str, number: str) -> dict[str, Any]:
    full_repo = f"{owner}/{repo}"
    proc = run_gh_cmd(
        [
            "gh",
            "pr",
            "view",
            number,
            "--repo",
            full_repo,
            "--json",
            "number,title,state,isDraft,mergedAt,url,headRefName,baseRefName,updatedAt",
        ],
        timeout=30,
    )
    data: dict[str, Any]
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
        except ValueError as exc:
            return {"ok": False, "repo": full_repo, "number": int(number), "error": str(exc)}
    else:
        rest = run_gh_cmd(["gh", "api", f"repos/{full_repo}/pulls/{number}"], timeout=30)
        if rest.returncode != 0:
            error = proc.stderr.strip() or proc.stdout.strip()
            rest_error = rest.stderr.strip() or rest.stdout.strip()
            if rest_error and rest_error != error:
                error = f"{error}; REST fallback: {rest_error}" if error else rest_error
            return {"ok": False, "repo": full_repo, "number": int(number), "error": error}
        try:
            row = json.loads(rest.stdout)
        except ValueError as exc:
            return {"ok": False, "repo": full_repo, "number": int(number), "error": str(exc)}
        if not isinstance(row, dict):
            return {"ok": False, "repo": full_repo, "number": int(number), "error": "unexpected REST payload"}
        data = {
            "number": row.get("number"),
            "title": row.get("title"),
            "state": str(row.get("state") or "").upper(),
            "isDraft": row.get("draft"),
            "mergedAt": row.get("merged_at"),
            "url": row.get("html_url"),
            "headRefName": (row.get("head") or {}).get("ref") if isinstance(row.get("head"), dict) else None,
            "baseRefName": (row.get("base") or {}).get("ref") if isinstance(row.get("base"), dict) else None,
            "updatedAt": row.get("updated_at"),
        }
    return {
        "ok": True,
        "repo": full_repo,
        "number": data.get("number"),
        "state": "MERGED" if data.get("mergedAt") else data.get("state"),
        "isDraft": data.get("isDraft"),
        "url": data.get("url"),
        "headRefName": data.get("headRefName"),
        "baseRefName": data.get("baseRefName"),
        "updatedAt": data.get("updatedAt"),
        "title_hash": stable_hash(data.get("title") or "", 20),
    }


def gh_prs_for_branch(repo: str, branch: str) -> list[dict[str, Any]]:
    proc = run_gh_cmd(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--state",
            "all",
            "--limit",
            "10",
            "--json",
            "number,title,state,isDraft,mergedAt,url,headRefName,baseRefName,updatedAt",
        ],
        timeout=30,
    )
    if proc.returncode == 0:
        try:
            rows = json.loads(proc.stdout or "[]")
        except ValueError as exc:
            return [{"ok": False, "repo": repo, "branch": branch, "error": str(exc)}]
    else:
        owner = repo.split("/", 1)[0]
        rest = run_gh_cmd(
            [
                "gh",
                "api",
                "--method",
                "GET",
                f"repos/{repo}/pulls",
                "-f",
                f"head={owner}:{branch}",
                "-f",
                "state=all",
                "-f",
                "per_page=10",
            ],
            timeout=30,
        )
        if rest.returncode != 0:
            error = proc.stderr.strip() or proc.stdout.strip()
            rest_error = rest.stderr.strip() or rest.stdout.strip()
            if rest_error and rest_error != error:
                error = f"{error}; REST fallback: {rest_error}" if error else rest_error
            return [{"ok": False, "repo": repo, "branch": branch, "error": error}]
        try:
            rest_rows = json.loads(rest.stdout or "[]")
        except ValueError as exc:
            return [{"ok": False, "repo": repo, "branch": branch, "error": str(exc)}]
        if not isinstance(rest_rows, list):
            return [{"ok": False, "repo": repo, "branch": branch, "error": "unexpected REST payload"}]
        rows = [
            {
                "number": row.get("number"),
                "title": row.get("title"),
                "state": str(row.get("state") or "").upper(),
                "isDraft": row.get("draft"),
                "mergedAt": row.get("merged_at"),
                "url": row.get("html_url"),
                "headRefName": (row.get("head") or {}).get("ref") if isinstance(row.get("head"), dict) else None,
                "baseRefName": (row.get("base") or {}).get("ref") if isinstance(row.get("base"), dict) else None,
                "updatedAt": row.get("updated_at"),
            }
            for row in rest_rows
            if isinstance(row, dict)
        ]
    return [
        {
            "ok": True,
            "repo": repo,
            "number": row.get("number"),
            "state": "MERGED" if row.get("mergedAt") else row.get("state"),
            "isDraft": row.get("isDraft"),
            "url": row.get("url"),
            "headRefName": row.get("headRefName"),
            "baseRefName": row.get("baseRefName"),
            "updatedAt": row.get("updatedAt"),
            "title_hash": stable_hash(row.get("title") or "", 20),
        }
        for row in rows
    ]


def worktree_remote_receipts(worktrees: list[dict[str, Any]]) -> dict[str, Any]:
    receipts: list[dict[str, Any]] = []
    for item in worktrees:
        path = Path(item.get("path", ""))
        receipt: dict[str, Any] = {
            "name": item.get("name"),
            "path": str(path),
            "debt": bool(item.get("debt")),
            "debt_reason": item.get("reason"),
            "git": False,
            "repo": None,
            "branch": None,
            "head": None,
            "remote_branch": "unknown",
            "prs": [],
        }
        if not path.exists() or not ((path / ".git").exists() or (path / ".git").is_file()):
            receipt["remote_branch"] = "not-a-git-dir"
            receipts.append(receipt)
            continue
        receipt["git"] = True
        branch = run_cmd(["git", "-C", str(path), "branch", "--show-current"], timeout=10).stdout.strip()
        head = run_cmd(["git", "-C", str(path), "rev-parse", "--short=12", "HEAD"], timeout=10).stdout.strip()
        remote = run_cmd(["git", "-C", str(path), "remote", "get-url", "origin"], timeout=10).stdout.strip()
        repo = repo_from_remote(remote)
        receipt.update({"branch": branch or None, "head": head or None, "repo": repo})
        if repo and branch:
            ls = run_cmd(["git", "-C", str(path), "ls-remote", "--heads", "origin", branch], timeout=30)
            receipt["remote_branch"] = "present" if ls.returncode == 0 and ls.stdout.strip() else "missing"
            receipt["prs"] = gh_prs_for_branch(repo, branch)
        receipts.append(receipt)
    ok_prs = [pr for receipt in receipts for pr in receipt.get("prs", []) if pr.get("ok")]
    return {
        "receipts": receipts,
        "git_roots": sum(1 for r in receipts if r["git"]),
        "repos": sorted({r["repo"] for r in receipts if r.get("repo")}),
        "remote_branches_present": sum(1 for r in receipts if r.get("remote_branch") == "present"),
        "remote_branches_missing": sum(1 for r in receipts if r.get("remote_branch") == "missing"),
        "open_prs": sum(1 for pr in ok_prs if pr.get("state") == "OPEN"),
        "merged_prs": sum(1 for pr in ok_prs if pr.get("state") == "MERGED"),
        "closed_prs": sum(1 for pr in ok_prs if pr.get("state") == "CLOSED"),
    }


def task_remote_pr_receipts(tasks_text: str, limit: int = 1000, workers: int = 8) -> dict[str, Any]:
    refs = sorted({match.groups() for match in GITHUB_PR_RE.finditer(tasks_text)})
    selected_refs = refs if limit <= 0 else refs[:limit]
    receipts: list[dict[str, Any]] = []
    if selected_refs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            future_map = {
                executor.submit(gh_pr_view, owner, repo, number): (owner, repo, number)
                for owner, repo, number in selected_refs
            }
            for future in concurrent.futures.as_completed(future_map):
                owner, repo, number = future_map[future]
                try:
                    receipts.append(future.result())
                except Exception as exc:
                    receipts.append(
                        {
                            "ok": False,
                            "repo": f"{owner}/{repo}",
                            "number": int(number),
                            "error": str(exc),
                        }
                    )
    receipts.sort(key=lambda r: (str(r.get("repo", "")), int(r.get("number") or 0)))
    counts = Counter(r.get("state", "ERROR") if r.get("ok") else "ERROR" for r in receipts)
    return {
        "seen_pr_refs": len(refs),
        "checked_pr_refs": len(receipts),
        "limit": limit,
        "counts": dict(sorted(counts.items())),
        "receipts": receipts,
        "truncated": limit > 0 and len(refs) > limit,
    }


def probe_url(url: str, *, expect_json: bool = False, timeout: int = 10) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(1024 * 256)
            out: dict[str, Any] = {
                "url": url,
                "ok": 200 <= resp.status < 400,
                "status": resp.status,
                "bytes_sampled": len(body),
            }
            if expect_json:
                try:
                    out["json_keys"] = sorted(json.loads(body.decode("utf-8", errors="replace")).keys())
                except ValueError as exc:
                    out["json_error"] = str(exc)
            return out
    except (OSError, urllib.error.URLError) as exc:
        return {"url": url, "ok": False, "error": str(exc)}


def cloud_receipts() -> dict[str, Any]:
    firebase_base = os.environ.get("LIMEN_PUBLIC_SITE_URL", "https://device-streaming-067d747a.web.app").rstrip("/")
    public_surfaces = [
        f"{firebase_base}/surface-manifest.json",
        f"{firebase_base}/public-surface-manifest.json",
        f"{firebase_base}/qa",
        f"{firebase_base}/client",
    ]
    runtime_url = runtime_api_url(ROOT)
    env_flags = {
        name: bool(os.environ.get(name))
        for name in (
            *RUNTIME_URL_ENV_ORDER,
            "LIMEN_API_TOKEN",
            "LIMEN_CLIENT_TOKEN",
            "CLOUDFLARE_API_TOKEN",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "VERCEL_TOKEN",
            "NETLIFY_AUTH_TOKEN",
        )
    }
    runtime_probe = None
    if runtime_url:
        runtime_probe = probe_url(runtime_url.rstrip("/") + "/health", expect_json=True)
    return {
        "public_site_url": firebase_base,
        "public_surface_probes": [probe_url(url, expect_json=url.endswith(".json")) for url in public_surfaces],
        "runtime_url_configured": bool(runtime_url),
        "runtime_health_probe": runtime_probe,
        "env_flags": env_flags,
        "cloudflare_deploy_auth_present": env_flags["CLOUDFLARE_API_TOKEN"],
    }


def codex_quicken_receipt() -> dict[str, Any]:
    path = ROOT / "logs" / "codex-session-lifecycle.jsonl"
    if not path.is_file():
        return {"present": False, "path": str(path)}
    last: dict[str, Any] | None = None
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except ValueError:
                    continue
    except OSError as exc:
        return {"present": False, "path": str(path), "error": str(exc)}
    if not last:
        return {"present": False, "path": str(path)}
    return {
        "present": True,
        "path": str(path),
        "generated_at": last.get("generated_at"),
        "session_count": last.get("session_count", 0),
        "by_state": last.get("by_state") or {},
        "by_family": last.get("by_family") or {},
    }


def attach_worktree_slugs(sessions: list[dict[str, Any]], worktrees: list[dict[str, Any]]) -> None:
    slugs = [item["name"] for item in worktrees]
    for session in sessions:
        haystack = " ".join(str(x) for x in (session.get("display_path"), session.get("path"), session.get("cwd")) if x)
        matched = next((slug for slug in slugs if slug in haystack), None)
        if matched is None:
            match = re.search(r"(?:limen-worktrees|--limen-worktrees-)[/-]?([A-Za-z0-9._-]+)", haystack)
            matched = match.group(1) if match else None
        session["worktree_slug"] = matched


def load_task_snapshot(worktree_slugs: list[str]) -> dict[str, Any]:
    if not TASKS_PATH.is_file():
        return {"present": False}
    text = TASKS_PATH.read_text(encoding="utf-8", errors="replace")
    data = yaml.safe_load(text) or {}
    tasks = data.get("tasks") or []
    status_counts = Counter(str(task.get("status", "missing")) for task in tasks if isinstance(task, dict))
    invalid = sorted(status for status in status_counts if status not in VALID_STATUSES)
    exact_slug_refs = [slug for slug in worktree_slugs if slug in text]
    now = dt.datetime.now(dt.timezone.utc)
    chronic_reopen = 0
    dispatched_without_pr = 0
    dispatched_with_pr = 0
    dispatched_jules_async = 0
    dispatched_running = 0
    done_with_pr_receipt = 0
    stranded_ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        log = task.get("dispatch_log") or []
        reopen_hits = sum(
            1
            for entry in log
            if isinstance(entry, dict)
            and ("reopened" in str(entry.get("output", "")).lower() or str(entry.get("status", "")).lower() == "open")
        )
        failure_hits = sum(
            1 for entry in log if isinstance(entry, dict) and "failed" in str(entry.get("status", "")).lower()
        )
        if reopen_hits >= 2 and failure_hits >= 2:
            chronic_reopen += 1
        urls = task.get("urls") or []
        has_pr = any("pull/" in str(url) for url in urls) or any(
            "pull/" in str((entry or {}).get("session_id", "")) for entry in log if isinstance(entry, dict)
        )
        if task.get("status") == "dispatched":
            if has_pr:
                dispatched_with_pr += 1
            elif task.get("target_agent") == "jules":
                dispatched_jules_async += 1
            else:
                updated = parse_ts(task.get("updated"))
                task_id = str(task.get("id", ""))
                async_running = (ROOT / "logs" / "async-runs").exists() and any(
                    (ROOT / "logs" / "async-runs").glob(f"{task_id}__*.running")
                )
                if async_running or (updated and (now - updated).total_seconds() < DISPATCH_GRACE_SECONDS):
                    dispatched_running += 1
                else:
                    dispatched_without_pr += 1
                    stranded_ids.add(task_id)
        if task.get("status") == "done" and has_pr:
            done_with_pr_receipt += 1

    chronic_reopen = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id", ""))
        status = task.get("status")
        if status not in {"open", "failed"} and not (status == "dispatched" and task_id in stranded_ids):
            continue
        log = task.get("dispatch_log") or []
        reopens = sum(1 for entry in log if isinstance(entry, dict) and str(entry.get("status")) == "open")
        ever_pr = any("pull/" in str((entry or {}).get("session_id", "")) for entry in log if isinstance(entry, dict))
        if reopens >= 3 and not ever_pr:
            chronic_reopen += 1
    return {
        "present": True,
        "text": text,
        "task_count": len(tasks),
        "status_counts": dict(sorted(status_counts.items())),
        "invalid_statuses": invalid,
        "exact_slug_refs": exact_slug_refs,
        "chronic_reopen_candidates": chronic_reopen,
        "dispatched_without_pr_receipt": dispatched_without_pr,
        "dispatched_with_pr_receipt": dispatched_with_pr,
        "dispatched_jules_async": dispatched_jules_async,
        "dispatched_running": dispatched_running,
        "done_with_pr_receipt": done_with_pr_receipt,
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    rows = iter_source_files(args.days)
    sessions: list[dict[str, Any]] = []
    for row in rows:
        records = read_json_records(row["path"])
        sessions.append(session_meta_from_records(row["source"], row, records))
    sessions.extend(opencode_virtual_sessions(args.days))
    sessions.extend(agy_cli_conversation_sessions(args.days))

    wt_report = current_worktree_report()
    worktrees = wt_report.get("items") or []
    attach_worktree_slugs(sessions, worktrees)
    task_snapshot = load_task_snapshot([item["name"] for item in worktrees if isinstance(item, dict)])
    remote = {"enabled": not args.no_remote}
    if not args.no_remote:
        remote["worktrees"] = worktree_remote_receipts(worktrees)
        remote["task_prs"] = task_remote_pr_receipts(
            task_snapshot.get("text", ""),
            args.remote_pr_limit,
            args.remote_workers,
        )
    cloud = {"enabled": not args.no_cloud}
    if not args.no_cloud:
        cloud.update(cloud_receipts())
    task_snapshot_private = {k: v for k, v in task_snapshot.items() if k != "text"}

    by_source: dict[str, dict[str, Any]] = {}
    for session in sessions:
        item = by_source.setdefault(
            session["source"],
            {
                "source": session["source"],
                "files": 0,
                "bytes": 0,
                "prompt_events": 0,
                "prompt_bytes": 0,
                "task_body_bytes": 0,
                "event_records": 0,
                "newest": None,
            },
        )
        item["files"] += 1
        item["bytes"] += int(session["size"])
        item["prompt_events"] += int(session["prompt_event_count"])
        item["prompt_bytes"] += int(session.get("prompt_bytes") or 0)
        item["task_body_bytes"] += int(session.get("task_body_bytes") or 0)
        item["event_records"] += int(session["event_count"])
        if item["newest"] is None or (session["mtime"] or "") > item["newest"]:
            item["newest"] = session["mtime"]

    body_kind_counts = Counter()
    for session in sessions:
        body_kind_counts.update(session.get("body_kind_counts") or {})

    sessions_by_worktree = Counter(s["worktree_slug"] for s in sessions if s.get("worktree_slug"))
    prompt_by_worktree = defaultdict(int)
    for session in sessions:
        if session.get("worktree_slug"):
            prompt_by_worktree[session["worktree_slug"]] += int(session["prompt_event_count"])

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "horizon_days": args.days,
        "sources": sorted(by_source.values(), key=lambda x: (-x["prompt_events"], x["source"])),
        "body_kind_counts": dict(sorted(body_kind_counts.items())),
        "sessions": sessions,
        "worktree_report": wt_report,
        "task_snapshot": task_snapshot_private,
        "remote": remote,
        "cloud": cloud,
        "codex_quicken": codex_quicken_receipt(),
        "sessions_by_worktree": dict(sessions_by_worktree.most_common()),
        "prompt_events_by_worktree": dict(sorted(prompt_by_worktree.items())),
        "private_index": str(PRIVATE_INDEX),
    }


def load_curated_block(path: Path) -> str:
    """Carry the judgment layer (ask-cluster themes/grades, LLM- or hand-authored) across
    regenerations verbatim — the mechanical register refreshes around it."""
    try:
        text = path.read_text()
    except OSError:
        return ""
    begin = text.find(EVERY_ASK_CURATED_BEGIN)
    end = text.find(EVERY_ASK_CURATED_END)
    if begin == -1 or end == -1 or end <= begin:
        return ""
    return text[begin + len(EVERY_ASK_CURATED_BEGIN) : end].strip("\n")


def _redact_cwd(cwd: str | None) -> str:
    if not cwd:
        return "-"
    name = Path(cwd).name or str(cwd)
    if "private" in name.lower():
        return "(private)"
    return name


def render_every_ask(snapshot: dict[str, Any], curated: str, *, max_rows: int = 120) -> str:
    """The regenerable EVERY-ASK register: every session that carried operator asks in the
    horizon, newest-first, receipts-oriented and redacted (hashes/counts, no prompt text).
    Deterministic for a given snapshot — no wall-clock stamp — so a same-data re-run is a no-op."""
    horizon = "all local history" if snapshot["horizon_days"] is None else f"last {snapshot['horizon_days']} days"
    sources = snapshot["sources"]
    newest = max((s["newest"] or "" for s in sources), default="") or "n/a"
    total_prompts = sum(int(s["prompt_events"]) for s in sources)
    ask_sessions = [s for s in snapshot["sessions"] if int(s.get("prompt_event_count") or 0) > 0]
    ask_sessions.sort(key=lambda s: (s.get("mtime") or "", s["session_key"]), reverse=True)

    lines = [
        "# Prompt occurrence register (compatibility view)",
        "",
        "> Regenerated by `scripts/prompt-lifecycle-ledger.py --every-ask --write` (mechanical rows below,",
        "> curated judgment block preserved between markers). Raw prompt text never lands here — hashes,",
        "> counts, and receipts only; the full text lives in the private session corpus.",
        ">",
        f"> Horizon: `{horizon}` · newest source event `{newest}` · **{total_prompts}** prompt events across "
        f"**{len(ask_sessions)}** prompt-carrying sessions. The canonical per-ask control plane is "
        "`docs/prompt-atom-ledger.md`; a session row is not an ask or completion receipt.",
        "",
        "## Prompt-event session register (newest-first)",
        "",
        "`Direct` is the legacy non-scaffold bucket. It can contain operator text, transport echoes,",
        "or directly fed frames and therefore does not prove operator authorship.",
        "",
        "| When | Source | Where | Prompt events | Legacy direct | Worktree |",
        "|---|---|---|---:|---:|---|",
    ]
    for session in ask_sessions[:max_rows]:
        when = (session.get("mtime") or "")[:10] or "n/a"
        direct = int((session.get("body_kind_counts") or {}).get("direct") or 0)
        lines.append(
            f"| {when} | `{session['source']}` | `{_redact_cwd(session.get('cwd'))}` | "
            f"{session['prompt_event_count']} | {direct} | `{session.get('worktree_slug') or '-'}` |"
        )
    if len(ask_sessions) > max_rows:
        lines.append("")
        lines.append(
            f"_{len(ask_sessions) - max_rows} older prompt-carrying sessions not shown — full rows in the "
            f"private index (`{relpath(PRIVATE_INDEX)}`)._"
        )

    by_source = {s["source"]: s for s in sources}
    lines += [
        "",
        "## Source coverage",
        "",
        "| Source | Sessions | Prompt events |",
        "|---|---:|---:|",
    ]
    for name, s in sorted(by_source.items(), key=lambda kv: -int(kv[1]["prompt_events"])):
        lines.append(f"| `{name}` | {s['files']} | {s['prompt_events']} |")

    lines += [
        "",
        "## Curated ask-clusters (judgment layer)",
        "",
        EVERY_ASK_CURATED_BEGIN,
        curated
        if curated
        else "_No curated clusters yet — seed this block from the latest retrospective "
        "(`docs/reviews/`); it is preserved verbatim across regenerations._",
        EVERY_ASK_CURATED_END,
        "",
        "## Provenance",
        "",
        "- The original hand-curated session ledger (2026-06-19, session `9750bef7`) is preserved at "
        "`docs/every-ask/2026-06-19-session-9750bef7.md`.",
        "- Receipts, worktree links, and remote PR verification: `docs/prompt-lifecycle-ledger.md`.",
        "",
    ]
    return "\n".join(lines)


def render_markdown(snapshot: dict[str, Any]) -> str:
    horizon = "all local history" if snapshot["horizon_days"] is None else f"last {snapshot['horizon_days']} days"
    sources = snapshot["sources"]
    total_files = sum(int(s["files"]) for s in sources)
    total_bytes = sum(int(s["bytes"]) for s in sources)
    total_prompts = sum(int(s["prompt_events"]) for s in sources)
    total_task_body_bytes = sum(int(s.get("task_body_bytes") or 0) for s in sources)
    wt = snapshot["worktree_report"]
    tasks = snapshot["task_snapshot"]
    remote = snapshot.get("remote", {})
    cloud = snapshot.get("cloud", {})
    codex_quicken = snapshot.get("codex_quicken", {})
    current_worktrees = {item["name"] for item in wt.get("items", [])}
    linked_worktrees = set(snapshot["sessions_by_worktree"]) & current_worktrees
    unlinked_worktrees = sorted(current_worktrees - linked_worktrees)

    lines = [
        "# Prompt Lifecycle Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Horizon: `{horizon}`",
        "",
        "## Canonical Decision",
        "",
        "- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.",
        "- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.",
        "- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.",
        "- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.",
        "",
        "## Redacted Prompt Coverage",
        "",
        f"Indexed `{total_files}` app/session files, `{fmt_bytes(total_bytes)}`, with `{total_prompts}` prompt-like user events hashed into the private index.",
        f"Normalized task-body payload covered `{fmt_bytes(total_task_body_bytes)}` after stripping recognized scaffold-only prompt frames.",
        "",
        "| Source | Files/Sessions | Prompt Events | Prompt Bytes | Task Body Bytes | Event Records | Size | Newest |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for source in sources:
        lines.append(
            f"| `{source['source']}` | {source['files']} | {source['prompt_events']} | "
            f"{fmt_bytes(int(source.get('prompt_bytes') or 0))} | "
            f"{fmt_bytes(int(source.get('task_body_bytes') or 0))} | "
            f"{source['event_records']} | {fmt_bytes(int(source['bytes']))} | "
            f"`{source['newest'] or 'n/a'}` |"
        )
    if not sources:
        lines.append("| none | 0 | 0 | 0 B | 0 B | 0 | 0 B | n/a |")

    body_kind_counts = snapshot.get("body_kind_counts") or {}
    lines += [
        "",
        "## Prompt Body Mix",
        "",
        "| Body Kind | Prompt Events |",
        "|---|---:|",
    ]
    for kind, count in sorted(body_kind_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{kind}` | {count} |")
    if not body_kind_counts:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Prompt To Worktree Crosswalk",
        "",
        f"- Current `.limen-worktrees` roots scanned: `{wt.get('total', 0)}`; debt roots: `{wt.get('debt', 0)}`.",
        f"- Current worktree roots with at least one local session/prompt receipt: `{len(linked_worktrees)}`.",
        f"- Current worktree roots without a local session receipt in this index: `{len(unlinked_worktrees)}`.",
        "",
        "| Worktree Root | Session Files | Prompt Events | Debt Reason |",
        "|---|---:|---:|---|",
    ]
    reason_by_root = {item["name"]: item.get("reason", "") for item in wt.get("items", [])}
    for root in sorted(current_worktrees):
        lines.append(
            f"| `{root}` | {snapshot['sessions_by_worktree'].get(root, 0)} | "
            f"{snapshot['prompt_events_by_worktree'].get(root, 0)} | "
            f"`{reason_by_root.get(root, 'n/a')}` |"
        )
    if not current_worktrees:
        lines.append("| none | 0 | 0 | n/a |")

    lines += [
        "",
        "## Task Board Crosswalk",
        "",
    ]
    if tasks.get("present"):
        status_bits = ", ".join(f"`{k}` {v}" for k, v in tasks["status_counts"].items())
        lines += [
            f"- Task records: `{tasks['task_count']}`.",
            f"- Status distribution: {status_bits}.",
            f"- Invalid statuses outside canonical set: `{len(tasks['invalid_statuses'])}`.",
            f"- Current worktree root slugs mentioned exactly in `tasks.yaml`: `{len(tasks['exact_slug_refs'])}` / `{wt.get('total', 0)}`.",
            f"- Chronic reopen-loop candidates: `{tasks['chronic_reopen_candidates']}`.",
            f"- Dispatched tasks with PR receipt: `{tasks['dispatched_with_pr_receipt']}`.",
            f"- Dispatched Jules async tasks without PR yet: `{tasks['dispatched_jules_async']}`.",
            f"- Dispatched local tasks still inside running grace/no-op guard: `{tasks['dispatched_running']}`.",
            f"- Dispatched local tasks stranded without PR receipt: `{tasks['dispatched_without_pr_receipt']}`.",
            f"- Done tasks with PR receipt still visible in dispatch log/URLs: `{tasks['done_with_pr_receipt']}`.",
        ]
    else:
        lines.append("- `tasks.yaml` was not found.")

    lines += [
        "",
        "## Remote Receipts",
        "",
    ]
    if remote.get("enabled") and remote.get("worktrees"):
        wr = remote["worktrees"]
        tprs = remote.get("task_prs", {})
        pr_counts = ", ".join(f"`{k}` {v}" for k, v in (tprs.get("counts") or {}).items()) or "none"
        lines += [
            f"- GitHub worktree repos seen: `{len(wr.get('repos', []))}`.",
            f"- Git worktree roots with remote branch present: `{wr.get('remote_branches_present', 0)}`; missing: `{wr.get('remote_branches_missing', 0)}`.",
            f"- Branch-linked PR states: `OPEN` {wr.get('open_prs', 0)}, `MERGED` {wr.get('merged_prs', 0)}, `CLOSED` {wr.get('closed_prs', 0)}.",
            f"- Task-board GitHub PR refs seen: `{tprs.get('seen_pr_refs', 0)}`; checked: `{tprs.get('checked_pr_refs', 0)}`; states: {pr_counts}.",
        ]
        if tprs.get("truncated"):
            lines.append(f"- Task PR receipt scan truncated at `{tprs.get('limit')}` refs.")
    elif remote.get("enabled"):
        lines.append("- Remote receipt collection ran but produced no GitHub worktree data.")
    else:
        lines.append("- Remote receipt collection disabled for this run.")

    lines += [
        "",
        "## Cloud Receipts",
        "",
    ]
    if cloud.get("enabled"):
        public_ok = sum(1 for p in cloud.get("public_surface_probes", []) if p.get("ok"))
        public_total = len(cloud.get("public_surface_probes", []))
        env_flags = cloud.get("env_flags", {})
        env_bits = ", ".join(f"`{k}`={'present' if v else 'absent'}" for k, v in sorted(env_flags.items()))
        lines += [
            f"- Public site probed: `{cloud.get('public_site_url')}`; `{public_ok}` / `{public_total}` probes passed.",
            f"- Runtime URL configured: `{cloud.get('runtime_url_configured')}`; runtime health probe ok: `{bool((cloud.get('runtime_health_probe') or {}).get('ok'))}`.",
            f"- Cloudflare deploy auth present: `{cloud.get('cloudflare_deploy_auth_present')}`.",
            f"- Cloud env flags: {env_bits}.",
        ]
    else:
        lines.append("- Cloud receipt collection disabled for this run.")

    lines += [
        "",
        "## Roadblocks And Potholes",
        "",
        "- The app screenshots are partially covered by local Codex history and Claude project/task stores, but screenshots alone are not durable enough to be the corpus. The durable object is now filesystem source + private object copy + redacted hash ledger.",
        "- Remote/cloud receipts are part of the lifecycle proof, but they are not substitutes for preserving local raw prompt/session material.",
        "- Worktree roots still do not have first-class task-board receipt fields; exact slug references are the bridge to add before automatic drain can be trusted.",
        "- Dispatch receipt classification must distinguish async Jules work from stranded local no-PR work; otherwise the conductor burns attention on healthy async reservations.",
        "- Prompt/session coverage is now hashed, but lifecycle judgment still needs owner actions: dirty roots need PRs or blocker records, and open PR receipts need merge or named supersession.",
    ]
    if codex_quicken.get("present"):
        states = ", ".join(
            f"`{state}` {count}" for state, count in sorted((codex_quicken.get("by_state") or {}).items())
        )
        lines.append(
            "- Codex now has prompt-event coverage plus `codex-quicken.py` lifecycle classification: "
            f"`{codex_quicken.get('session_count', 0)}` sessions"
            f"{'; ' + states if states else ''}."
        )
    else:
        lines.append(
            "- Codex has prompt-event coverage through `history.jsonl` and session JSONL, but no "
            "`codex-quicken.py` lifecycle journal was found yet."
        )
    task_pr_errors = (
        int(((remote.get("task_prs") or {}).get("counts") or {}).get("ERROR", 0)) if remote.get("enabled") else 0
    )
    if task_pr_errors:
        lines.append(
            f"- Remote task-board PR receipt scan has `{task_pr_errors}` GitHub/API errors; rerun before using those refs as closure proof."
        )

    lines += [
        "",
        "## Drain Queue",
        "",
    ]
    drain_queues = sorted((ROOT / "docs").glob("session-lifecycle-drain-queue-*.md"))
    if drain_queues:
        for path in drain_queues:
            lines.append(f"- Session lifecycle drain queue: `{path.relative_to(ROOT)}`.")
    else:
        lines.append("- No tracked session lifecycle drain queue yet.")

    lines += [
        "",
        "## Private Outputs",
        "",
        f"- Prompt lifecycle private index: `{relpath(PRIVATE_INDEX)}`.",
        f"- Raw object cartridge: `{relpath(PRIVATE_ROOT / 'objects')}`.",
        "- The private index contains source paths, session hashes, prompt hashes, CWD hashes, and worktree links; it contains no prompt text.",
        "",
        "## Commands",
        "",
        "- Refresh this ledger with remote/cloud receipts: `python3 scripts/prompt-lifecycle-ledger.py --write --all`",
        "- Refresh local-only when offline: `python3 scripts/prompt-lifecycle-ledger.py --write --all --no-remote --no-cloud`",
        "- Refresh and absorb raw session/app files: `python3 scripts/session-corpus-ledger.py --write --all --materialize`",
        "- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`",
        "- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`",
        "- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`",
        "- Inspect lifecycle debt: `python3 scripts/worktree-debt.py --json`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.write_text(markdown)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the redacted prompt/session lifecycle ledger.")
    parser.add_argument("--days", type=int, default=None, help="local app-store horizon to index")
    parser.add_argument("--all", action="store_true", help="index all local app-store history")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--no-remote", action="store_true", help="skip GitHub remote receipt checks")
    parser.add_argument("--no-cloud", action="store_true", help="skip public cloud/runtime probes")
    parser.add_argument("--remote-pr-limit", type=int, default=1000, help="maximum task PR refs to verify; 0 means all")
    parser.add_argument("--remote-workers", type=int, default=8, help="parallel GitHub PR receipt workers")
    parser.add_argument(
        "--every-ask",
        action="store_true",
        help="also regenerate the root EVERY-ASK-LEDGER.md register (curated block preserved)",
    )
    args = parser.parse_args()
    if args.all:
        args.days = None
    if args.days is not None and args.days <= 0:
        args.days = None

    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot)
    every_ask_md = None
    if args.every_ask:
        every_ask_md = render_every_ask(snapshot, load_curated_block(EVERY_ASK_PATH))
    if args.write:
        write_outputs(snapshot, markdown)
        if every_ask_md is not None:
            EVERY_ASK_PATH.write_text(every_ask_md)
    else:
        print(every_ask_md if every_ask_md is not None else markdown)
    total_files = sum(int(s["files"]) for s in snapshot["sources"])
    total_prompts = sum(int(s["prompt_events"]) for s in snapshot["sources"])
    horizon = "all history" if args.days is None else f"{args.days}d"
    msg = f"prompt-lifecycle-ledger: {total_files} files, {total_prompts} prompt events over {horizon}"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
        if every_ask_md is not None:
            msg += f" and {EVERY_ASK_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
