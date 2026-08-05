#!/usr/bin/env python3
"""Full-stack prompt/session review across Codex, Claude, OpenCode, and Agy.

The private output is intentionally verbatim. The tracked report is counts,
hashes, and findings only, so the repo can keep processing private prompt
material without publishing it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
OUT_DIR = PRIVATE_ROOT / "full-stack-review"
PRIVATE_PROMPTS = OUT_DIR / "verbatim-prompts.jsonl"
PRIVATE_REVIEW = OUT_DIR / "agent-session-review.json"
DOC_PATH = ROOT / "docs" / "agent-session-full-stack-review.md"

CODEX_SESSIONS = HOME / ".codex" / "sessions"
CODEX_HISTORY = HOME / ".codex" / "history.jsonl"
CLAUDE_PROJECTS = HOME / ".claude" / "projects"
CLAUDE_TASKS = HOME / ".claude" / "tasks"
OPENCODE_DB = HOME / ".local" / "share" / "opencode" / "opencode.db"
GEMINI_TMP = HOME / ".gemini" / "tmp"
AGY_CLI_ROOT = HOME / ".gemini" / "antigravity-cli"
AGY_CLI_HISTORY = AGY_CLI_ROOT / "history.jsonl"
AGY_CLI_CONVERSATIONS = AGY_CLI_ROOT / "conversations"
AGY_CLI_SUMMARIES = AGY_CLI_ROOT / "conversation_summaries.db"
AGY_CLI_IMPLICIT = AGY_CLI_ROOT / "implicit"
ANTIGRAVITY_STATE = HOME / ".gemini" / "antigravity" / "antigravity_state.pbtxt"
ANTIGRAVITY_SUMMARIES = HOME / ".gemini" / "antigravity" / "agyhub_summaries_proto.pb"
ANTIGRAVITY_HOME = HOME / ".gemini" / "antigravity"
ANTIGRAVITY_IDE_HOME = HOME / ".gemini" / "antigravity-ide"
ANTIGRAVITY_IDE_SUPPORT = HOME / "Library" / "Application Support" / "Antigravity IDE"
ANTIGRAVITY_APP_SUPPORT = HOME / "Library" / "Application Support" / "Antigravity"


VERIFY_RE = re.compile(
    r"\b("
    r"verify-whole\.sh|pytest|ruff|mypy|py_compile|npm run (?:build|check|test)|"
    r"pnpm (?:test|build)|vitest|git diff --check|verify|predicate|tests? passed|passed"
    r")\b",
    re.I,
)
RECEIPT_RE = re.compile(
    r"(https://github\.com/[^)\s]+/pull/\d+|\bPR\s*#?\d+\b|\bcommit\s+[0-9a-f]{7,40}\b|"
    r"\b[0-9a-f]{7,40}\b|\.jsonl\b|\.md\b|\.json\b|artifact|receipt)",
    re.I,
)
FAIL_RE = re.compile(
    r"\b(failed|failure|blocked|error|exception|timeout|rate.?limit|permission|auth|quota|"
    r"resource_exhausted|needs_human|not found|no-op|noop|aborted|interrupted)\b",
    re.I,
)
DONE_RE = re.compile(r"\b(done|complete|completed|verified|passed|merged|pushed|landed|shipped)\b", re.I)
SCOPE_RE = re.compile(
    r"(/Users/|~/|\.py\b|\.ts\b|\.tsx\b|\.md\b|\.json\b|scripts/|docs/|cli/|web/|"
    r"tasks\.yaml|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|LIMEN-[0-9A-Z-]+|[A-Z]+-[A-Za-z0-9-]+)"
)
PREDICATE_RE = re.compile(r"\b(test|verify|predicate|acceptance|done when|passes|green|run)\b", re.I)
GATE_RE = re.compile(r"\b(gate|human|approval|do not|never|ask|confirm|irreversible|outward)\b", re.I)
BROAD_RE = re.compile(r"\b(all|everything|full stack|autonomous|keep working|never stop|whole|entire|every)\b", re.I)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.M)
PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+?)\s*$", re.M)
MUTATING_TOOL_NAMES = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
AGY_MUTATING_ACTION_RE = re.compile(
    r"\b(edit|fix|writ|creat|replac|updat|append|add|lower|resolv)\b",
    re.I,
)
AGY_MUTATING_PAYLOAD_KEYS = {
    "AllowMultiple",
    "CodeContent",
    "EndLine",
    "Instruction",
    "Overwrite",
    "ReplacementChunks",
    "ReplacementContent",
    "StartLine",
    "TargetContent",
}
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


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso_from_epoch_ms(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    except (OSError, OverflowError, ValueError):
        return None


def iso_from_mtime(path: Path) -> str | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return None


def stable_hash(text: str, length: int | None = None) -> str:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return digest if length is None else digest[:length]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def relpath(path: Path | str) -> str:
    p = Path(path)
    try:
        return "~/" + str(p.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    obj["_line"] = line_no
                    yield obj
    except OSError:
        return


def json_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(json_text(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("text", "content", "message", "input", "prompt", "description"):
            if key in value:
                out.extend(json_text(value[key]))
        return out
    return []


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


def agy_outcome_text_from_spans(spans: list[str], *, limit: int = 50000) -> str:
    signal_re = re.compile(
        r"(RESOURCE_EXHAUSTED|quota|error|failed|completed|finished|verified|passed|"
        r"Task id|CommandLine|toolAction|toolSummary|git |pytest|npm |pnpm |"
        r"Log: file://|pull/|commit|\\.md\\b|\\.json\\b|\\.py\\b|\\.ts\\b|\\.tsx\\b)",
        re.I,
    )
    selected = [span for span in spans if signal_re.search(span)]
    if not selected:
        selected = [span for span in spans if len(span) <= 4000][:3]
    text = "\n\n".join(selected)
    return text[:limit]


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


def classify_prompt(text: str) -> dict[str, bool]:
    return {
        "has_scope": bool(SCOPE_RE.search(text)),
        "has_predicate": bool(PREDICATE_RE.search(text)),
        "has_receipt_request": bool(RECEIPT_RE.search(text)),
        "mentions_gate": bool(GATE_RE.search(text)),
        "broad": bool(BROAD_RE.search(text)),
    }


def normalize_task_body(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if stripped.startswith("<session_context>"):
        return "", "session_context"
    if stripped.startswith("# FLAME"):
        positions = [(stripped.find(marker), marker) for marker in TASK_BODY_MARKERS if stripped.find(marker) >= 0]
        if positions:
            pos, marker = min(positions, key=lambda item: item[0])
            body = stripped[pos:]
            if marker.startswith("##"):
                # Keep the marker heading and everything after it.
                return body, "flame_with_task_body"
            return body, "flame_with_task_body"
        return "", "flame_scaffold"
    return stripped, "direct"


def outcome_signals(text: str) -> dict[str, int]:
    return {
        "verification": len(VERIFY_RE.findall(text)),
        "receipts": len(RECEIPT_RE.findall(text)),
        "failures": len(FAIL_RE.findall(text)),
        "done_words": len(DONE_RE.findall(text)),
    }


def clean_changed_path(path: Any) -> str | None:
    if not isinstance(path, str):
        return None
    value = path.strip().strip('"').strip("'")
    if not value or value == "/dev/null":
        return None
    return value


def changed_files_from_patch(text: Any) -> list[str]:
    if not isinstance(text, str) or "*** Begin Patch" not in text:
        return []
    out: list[str] = []
    for match in PATCH_FILE_RE.finditer(text):
        cleaned = clean_changed_path(match.group(1))
        if cleaned:
            out.append(cleaned)
    for match in PATCH_MOVE_RE.finditer(text):
        cleaned = clean_changed_path(match.group(1))
        if cleaned:
            out.append(cleaned)
    return sorted(dict.fromkeys(out))


def parse_tool_arguments(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except ValueError:
        return value
    return parsed


def changed_files_from_tool_payload(value: Any) -> list[str]:
    """Conservatively extract changed-file refs from structured tool payloads."""
    out: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        if not isinstance(obj, dict):
            return
        name = obj.get("name")
        raw_input = obj.get("input")
        arguments = parse_tool_arguments(obj.get("arguments"))
        tool_input = parse_tool_arguments(raw_input)

        if name == "apply_patch":
            if isinstance(tool_input, str):
                out.extend(changed_files_from_patch(tool_input))
            elif isinstance(tool_input, dict):
                out.extend(changed_files_from_patch(tool_input.get("patch")))
            if isinstance(arguments, dict):
                out.extend(changed_files_from_patch(arguments.get("patch")))
            elif isinstance(arguments, str):
                out.extend(changed_files_from_patch(arguments))

        if name in MUTATING_TOOL_NAMES and isinstance(tool_input, dict):
            for key in ("file_path", "path", "notebook_path"):
                cleaned = clean_changed_path(tool_input.get(key))
                if cleaned:
                    out.append(cleaned)

        for key in ("content", "message", "payload"):
            child = obj.get(key)
            if child is not None:
                walk(child)

    walk(value)
    return sorted(dict.fromkeys(out))


def embedded_json_objects(text: Any) -> list[Any]:
    if not isinstance(text, str):
        return []
    decoder = json.JSONDecoder()
    out: list[Any] = []
    starts: set[int] = set()
    for match in re.finditer(r'"TargetFile"', text):
        nearby = [m.start() for m in re.finditer(r"\{", text[: match.start()])]
        starts.update(nearby[-20:])
    for start in sorted(starts):
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        out.append(obj)
    return out


def walk_dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def agy_payload_mutates(obj: dict[str, Any]) -> bool:
    action = str(obj.get("toolAction") or obj.get("ToolAction") or "")
    if AGY_MUTATING_ACTION_RE.search(action):
        return True
    return any(key in obj for key in AGY_MUTATING_PAYLOAD_KEYS)


def changed_files_from_agy_spans(spans: Iterable[str]) -> list[str]:
    out: list[str] = []
    for span in spans:
        if "TargetFile" not in span:
            continue
        for obj in embedded_json_objects(span):
            for item in walk_dicts(obj):
                target = clean_changed_path(item.get("TargetFile"))
                if target and agy_payload_mutates(item):
                    out.append(target)
    return sorted(dict.fromkeys(out))


class Aggregator:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.prompt_events = 0
        self.unique_prompt_hashes: set[str] = set()
        self.unique_task_body_hashes: set[str] = set()
        self.source_counts: Counter[str] = Counter()
        self.agent_counts: Counter[str] = Counter()
        self.body_kind_counts: Counter[str] = Counter()
        self.prompt_bytes_by_agent: Counter[str] = Counter()
        self.outcome_text_bytes = 0
        self.private_paths: set[str] = set()
        self.samples_by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def session(self, agent: str, session_id: str, source: str, path: Path | str | None = None) -> dict[str, Any]:
        key = f"{agent}:{session_id}"
        item = self.sessions.setdefault(
            key,
            {
                "key": key,
                "agent": agent,
                "session_id": session_id,
                "sources": Counter(),
                "paths": set(),
                "cwd": None,
                "title": None,
                "first_ts": None,
                "last_ts": None,
                "prompt_events": 0,
                "unique_prompt_hashes": set(),
                "unique_task_body_hashes": set(),
                "prompt_bytes": 0,
                "task_body_bytes": 0,
                "prompt_flags": Counter(),
                "outcome": Counter(),
                "changed_files": set(),
                "model": None,
                "tokens": Counter(),
                "cost": 0.0,
            },
        )
        item["sources"][source] += 1
        if path is not None:
            item["paths"].add(str(path))
            self.private_paths.add(str(path))
        return item

    def add_prompt(
        self,
        *,
        agent: str,
        source: str,
        session_id: str,
        path: Path | str,
        text: str,
        ts: str | None = None,
        cwd: str | None = None,
        title: str | None = None,
        ordinal: int | None = None,
        surface: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = maybe_decode_wrapped_string(text)
        task_body, body_kind = normalize_task_body(text)
        classified_text = task_body or text
        prompt_hash = stable_hash(text)
        task_body_hash = stable_hash(task_body) if task_body else None
        row = {
            "agent": agent,
            "source": source,
            "session_id": session_id,
            "timestamp": ts,
            "cwd": cwd,
            "title": title,
            "path": str(path),
            "display_path": relpath(path),
            "ordinal": ordinal,
            "surface": surface,
            "prompt_hash": prompt_hash,
            "prompt_bytes": len(text.encode("utf-8", errors="replace")),
            "task_body_hash": task_body_hash,
            "task_body_bytes": len(task_body.encode("utf-8", errors="replace")),
            "body_kind": body_kind,
            "flags": classify_prompt(classified_text),
            "text": text,
        }
        if extra:
            row["extra"] = extra

        session = self.session(agent, session_id, source, path)
        session["prompt_events"] += 1
        session["unique_prompt_hashes"].add(prompt_hash)
        if task_body_hash:
            session["unique_task_body_hashes"].add(task_body_hash)
        session["prompt_bytes"] += row["prompt_bytes"]
        session["task_body_bytes"] += row["task_body_bytes"]
        if cwd and not session["cwd"]:
            session["cwd"] = cwd
        if title and not session["title"]:
            session["title"] = title
        for flag, val in row["flags"].items():
            if val:
                session["prompt_flags"][flag] += 1
        session["prompt_flags"][f"body_kind:{body_kind}"] += 1
        for key in ("first_ts", "last_ts"):
            if ts and (session[key] is None or (key == "first_ts" and ts < session[key]) or (key == "last_ts" and ts > session[key])):
                session[key] = ts

        self.prompt_events += 1
        self.unique_prompt_hashes.add(prompt_hash)
        if task_body_hash:
            self.unique_task_body_hashes.add(task_body_hash)
        self.source_counts[source] += 1
        self.agent_counts[agent] += 1
        self.body_kind_counts[body_kind] += 1
        self.prompt_bytes_by_agent[agent] += row["prompt_bytes"]
        if len(self.samples_by_agent[agent]) < 5:
            self.samples_by_agent[agent].append(
                {
                    "session_id": session_id,
                    "timestamp": ts,
                    "prompt_hash": prompt_hash[:16],
                    "bytes": row["prompt_bytes"],
                    "task_body_bytes": row["task_body_bytes"],
                    "body_kind": body_kind,
                    "flags": row["flags"],
                    "display_path": row["display_path"],
                }
            )
        return row

    def add_outcome_text(
        self,
        *,
        agent: str,
        source: str,
        session_id: str,
        path: Path | str,
        text: str,
        ts: str | None = None,
        changed_files: Iterable[str] = (),
    ) -> None:
        if not text:
            return
        session = self.session(agent, session_id, source, path)
        signals = outcome_signals(text)
        session["outcome"].update(signals)
        for changed in changed_files:
            if changed:
                session["changed_files"].add(changed)
        if ts and (session["last_ts"] is None or ts > session["last_ts"]):
            session["last_ts"] = ts
        self.outcome_text_bytes += len(text.encode("utf-8", errors="replace"))

    def add_session_metadata(
        self,
        *,
        agent: str,
        source: str,
        session_id: str,
        path: Path | str,
        cwd: str | None = None,
        title: str | None = None,
        model: str | None = None,
        tokens: dict[str, int] | None = None,
        cost: float | None = None,
        changed_files: Iterable[str] = (),
        ts: str | None = None,
    ) -> None:
        session = self.session(agent, session_id, source, path)
        if cwd and not session["cwd"]:
            session["cwd"] = cwd
        if title and not session["title"]:
            session["title"] = title
        if model and not session["model"]:
            session["model"] = model
        if tokens:
            session["tokens"].update({k: int(v or 0) for k, v in tokens.items()})
        if cost:
            session["cost"] = float(session["cost"]) + float(cost)
        for changed in changed_files:
            if changed:
                session["changed_files"].add(changed)
        if ts and (session["last_ts"] is None or ts > session["last_ts"]):
            session["last_ts"] = ts

    def finalize_sessions(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in self.sessions.values():
            prompt_events = int(item["prompt_events"])
            changed = sorted(item["changed_files"])
            outcome = Counter(item["outcome"])
            flags = Counter(item["prompt_flags"])
            ideal_gaps: list[str] = []
            if prompt_events:
                if flags["broad"] >= 10:
                    ideal_gaps.append("repeated broad/invariant prompt pressure")
                if flags["broad"] and not flags["has_scope"]:
                    ideal_gaps.append("prompt broad without concrete owner scope")
                if not flags["has_predicate"]:
                    ideal_gaps.append("prompt missing executable predicate")
                if not flags["has_receipt_request"]:
                    ideal_gaps.append("prompt missing expected receipt/artifact")
            if prompt_events and outcome["verification"] == 0:
                ideal_gaps.append("session outcome lacks verification signal")
            if prompt_events and outcome["receipts"] == 0 and not changed:
                ideal_gaps.append("session outcome lacks durable receipt signal")
            if prompt_events and outcome["failures"] > outcome["done_words"]:
                ideal_gaps.append("failure/blocker language outweighs done language")
            if prompt_events and not changed and outcome["verification"] == 0 and outcome["receipts"] == 0:
                ideal_gaps.append("likely no-op or unrecorded work")

            score = (
                flags["broad"] * 3
                + (1 if not flags["has_predicate"] and prompt_events else 0) * 4
                + (1 if not flags["has_receipt_request"] and prompt_events else 0) * 4
                + (1 if outcome["verification"] == 0 and prompt_events else 0) * 5
                + (1 if outcome["receipts"] == 0 and not changed and prompt_events else 0) * 5
                + min(outcome["failures"], 10)
            )
            rows.append(
                {
                    "key": item["key"],
                    "agent": item["agent"],
                    "session_id": item["session_id"],
                    "title": item["title"],
                    "cwd": item["cwd"],
                    "first_ts": item["first_ts"],
                    "last_ts": item["last_ts"],
                    "sources": dict(item["sources"]),
                    "paths": sorted(relpath(p) for p in item["paths"]),
                    "prompt_events": prompt_events,
                    "unique_prompts": len(item["unique_prompt_hashes"]),
                    "unique_task_bodies": len(item["unique_task_body_hashes"]),
                    "prompt_bytes": item["prompt_bytes"],
                    "task_body_bytes": item["task_body_bytes"],
                    "prompt_flags": dict(flags),
                    "outcome": dict(outcome),
                    "changed_files": changed[:100],
                    "changed_file_count": len(changed),
                    "model": item["model"],
                    "tokens": dict(item["tokens"]),
                    "cost": item["cost"],
                    "ideal_gaps": ideal_gaps,
                    "risk_score": score,
                }
            )
        rows.sort(key=lambda r: (r["risk_score"], r["prompt_events"], r.get("last_ts") or ""), reverse=True)
        return rows


def extract_codex(agg: Aggregator, writer: Any) -> None:
    paths = sorted(CODEX_SESSIONS.rglob("*.jsonl")) if CODEX_SESSIONS.exists() else []
    if CODEX_HISTORY.exists():
        paths.append(CODEX_HISTORY)
    for path in paths:
        session_id = path.stem
        cwd = None
        for obj in read_jsonl(path):
            typ = obj.get("type")
            ts = obj.get("timestamp")
            payload = obj.get("payload")
            if typ == "session_meta" and isinstance(payload, dict):
                session_id = str(payload.get("id") or payload.get("session_id") or session_id)
                cwd = payload.get("cwd") or cwd
                model = payload.get("model") or payload.get("model_slug") or payload.get("model_provider")
                agg.add_session_metadata(
                    agent="codex",
                    source="codex-sessions",
                    session_id=session_id,
                    path=path,
                    cwd=cwd,
                    model=str(model) if model else None,
                    ts=ts,
                )
                continue
            if typ == "turn_context" and isinstance(payload, dict):
                cwd = payload.get("cwd") or cwd
                agg.add_session_metadata(
                    agent="codex",
                    source="codex-sessions",
                    session_id=session_id,
                    path=path,
                    cwd=cwd,
                    model=str(payload.get("model")) if payload.get("model") else None,
                    ts=ts,
                )
                continue
            if path == CODEX_HISTORY:
                if isinstance(obj.get("text"), str):
                    row = agg.add_prompt(
                        agent="codex",
                        source="codex-history",
                        session_id=str(obj.get("session_id") or session_id),
                        path=path,
                        text=obj["text"],
                        ts=ts,
                        cwd=cwd,
                        ordinal=obj.get("_line"),
                        surface="history",
                    )
                    writer.write(json.dumps(row, ensure_ascii=False) + "\n")
                continue
            if typ == "event_msg" and isinstance(payload, dict) and payload.get("type") == "user_message":
                text = payload.get("message")
                if isinstance(text, str) and text.strip():
                    row = agg.add_prompt(
                        agent="codex",
                        source="codex-sessions",
                        session_id=session_id,
                        path=path,
                        text=text,
                        ts=ts,
                        cwd=cwd,
                        ordinal=obj.get("_line"),
                        surface="event_msg.user_message",
                    )
                    writer.write(json.dumps(row, ensure_ascii=False) + "\n")
            elif typ == "response_item" and isinstance(payload, dict):
                if payload.get("type") == "message" and payload.get("role") == "user":
                    texts = json_text(payload.get("content"))
                    for text in texts:
                        row = agg.add_prompt(
                            agent="codex",
                            source="codex-sessions",
                            session_id=session_id,
                            path=path,
                            text=text,
                            ts=ts,
                            cwd=cwd,
                            ordinal=obj.get("_line"),
                            surface="response_item.user",
                        )
                        writer.write(json.dumps(row, ensure_ascii=False) + "\n")
                elif payload.get("type") == "message" and payload.get("role") in ("assistant", "tool"):
                    agg.add_outcome_text(
                        agent="codex",
                        source="codex-sessions",
                        session_id=session_id,
                        path=path,
                        text="\n".join(json_text(payload.get("content"))),
                        ts=ts,
                        changed_files=changed_files_from_tool_payload(payload),
                    )
                elif payload.get("type") in ("function_call_output", "function_call", "custom_tool_call"):
                    agg.add_outcome_text(
                        agent="codex",
                        source="codex-sessions",
                        session_id=session_id,
                        path=path,
                        text=json.dumps(payload, ensure_ascii=False)[:20000],
                        ts=ts,
                        changed_files=changed_files_from_tool_payload(payload),
                    )


def extract_claude(agg: Aggregator, writer: Any) -> None:
    paths = sorted(CLAUDE_PROJECTS.rglob("*.jsonl")) if CLAUDE_PROJECTS.exists() else []
    if CLAUDE_TASKS.exists():
        paths.extend(sorted(CLAUDE_TASKS.rglob("*.json")))
    for path in paths:
        if path.suffix == ".json":
            try:
                obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            records = [obj] if isinstance(obj, dict) else obj if isinstance(obj, list) else []
        else:
            records = list(read_jsonl(path))
        session_id = path.stem
        cwd = None
        for obj in records:
            if not isinstance(obj, dict):
                continue
            ts = obj.get("timestamp") or obj.get("created_at") or obj.get("updated_at")
            session_id = str(obj.get("sessionId") or obj.get("session_id") or session_id)
            cwd = obj.get("cwd") or cwd
            if obj.get("type") == "queue-operation" and obj.get("operation") == "enqueue":
                for text in json_text(obj.get("content")):
                    row = agg.add_prompt(
                        agent="claude",
                        source="claude-projects" if path.suffix == ".jsonl" else "claude-tasks",
                        session_id=session_id,
                        path=path,
                        text=text,
                        ts=ts,
                        cwd=cwd,
                        ordinal=obj.get("_line"),
                        surface="queue.enqueue",
                    )
                    writer.write(json.dumps(row, ensure_ascii=False) + "\n")
            elif obj.get("type") == "last-prompt":
                for text in json_text(obj.get("lastPrompt")):
                    row = agg.add_prompt(
                        agent="claude",
                        source="claude-projects" if path.suffix == ".jsonl" else "claude-tasks",
                        session_id=session_id,
                        path=path,
                        text=text,
                        ts=ts,
                        cwd=cwd,
                        ordinal=obj.get("_line"),
                        surface="last-prompt",
                    )
                    writer.write(json.dumps(row, ensure_ascii=False) + "\n")
            elif obj.get("type") == "user":
                msg = obj.get("message")
                if isinstance(msg, dict) and msg.get("role") not in (None, "user"):
                    continue
                for text in json_text(msg):
                    row = agg.add_prompt(
                        agent="claude",
                        source="claude-projects" if path.suffix == ".jsonl" else "claude-tasks",
                        session_id=session_id,
                        path=path,
                        text=text,
                        ts=ts,
                        cwd=cwd,
                        ordinal=obj.get("_line"),
                        surface="message.user",
                    )
                    writer.write(json.dumps(row, ensure_ascii=False) + "\n")
            elif obj.get("type") == "assistant":
                agg.add_outcome_text(
                    agent="claude",
                    source="claude-projects" if path.suffix == ".jsonl" else "claude-tasks",
                    session_id=session_id,
                    path=path,
                    text="\n".join(json_text(obj.get("message")) + json_text(obj.get("content"))),
                    ts=ts,
                    changed_files=changed_files_from_tool_payload(obj.get("message")),
                )
            elif obj.get("type") == "tool_result":
                agg.add_outcome_text(
                    agent="claude",
                    source="claude-projects" if path.suffix == ".jsonl" else "claude-tasks",
                    session_id=session_id,
                    path=path,
                    text="\n".join(json_text(obj)),
                    ts=ts,
                )


def extract_opencode(agg: Aggregator, writer: Any) -> None:
    if not OPENCODE_DB.exists():
        return
    try:
        con = sqlite3.connect(f"file:{OPENCODE_DB}?immutable=1", uri=True)
    except sqlite3.Error:
        return
    con.row_factory = sqlite3.Row
    try:
        sessions = con.execute(
            "SELECT id, title, directory, time_created, time_updated, summary_files, summary_additions, "
            "summary_deletions, cost, tokens_input, tokens_output, tokens_reasoning, model "
            "FROM session ORDER BY time_created, id"
        ).fetchall()
    except sqlite3.Error:
        con.close()
        return
    for s in sessions:
        sid = str(s["id"])
        model = s["model"]
        changed_files: list[str] = []
        try:
            diffs = json.loads(s["summary_diffs"]) if "summary_diffs" in s.keys() and s["summary_diffs"] else None
        except (TypeError, ValueError):
            diffs = None
        if isinstance(diffs, list):
            changed_files.extend(str(x) for x in diffs[:200])
        agg.add_session_metadata(
            agent="opencode",
            source="opencode-db",
            session_id=sid,
            path=OPENCODE_DB,
            cwd=s["directory"],
            title=s["title"],
            model=model,
            tokens={
                "input": s["tokens_input"],
                "output": s["tokens_output"],
                "reasoning": s["tokens_reasoning"],
            },
            cost=s["cost"],
            changed_files=changed_files,
            ts=iso_from_epoch_ms(s["time_updated"]),
        )
        try:
            msgs = con.execute(
                "SELECT id, time_created, data FROM message WHERE session_id=? ORDER BY time_created, id",
                (sid,),
            ).fetchall()
            pmap: dict[str, list[sqlite3.Row]] = defaultdict(list)
            for p in con.execute(
                "SELECT message_id, time_created, data FROM part WHERE session_id=? ORDER BY time_created, id",
                (sid,),
            ):
                pmap[p["message_id"]].append(p)
        except sqlite3.Error:
            continue
        for idx, m in enumerate(msgs):
            try:
                md = json.loads(m["data"]) if m["data"] else {}
            except (TypeError, ValueError):
                md = {}
            role = md.get("role")
            ts = iso_from_epoch_ms(m["time_created"])
            parts: list[str] = []
            patches: list[str] = []
            for p in pmap.get(m["id"], []):
                try:
                    pd = json.loads(p["data"]) if p["data"] else {}
                except (TypeError, ValueError):
                    continue
                if not isinstance(pd, dict):
                    continue
                typ = pd.get("type")
                if typ in ("text", "reasoning", "compaction"):
                    text = pd.get("text") or pd.get("summary")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
                elif typ == "tool":
                    parts.append(json.dumps(pd, ensure_ascii=False)[:20000])
                elif typ == "patch":
                    files = pd.get("files")
                    if isinstance(files, list):
                        patches.extend(str(x) for x in files)
                    parts.append(json.dumps(pd, ensure_ascii=False)[:20000])
                elif typ == "subtask":
                    prompt = pd.get("prompt") or pd.get("description")
                    if isinstance(prompt, str) and prompt.strip():
                        parts.append(prompt)
            text = "\n\n".join(parts)
            if role == "user" and text.strip():
                row = agg.add_prompt(
                    agent="opencode",
                    source="opencode-db",
                    session_id=sid,
                    path=OPENCODE_DB,
                    text=text,
                    ts=ts,
                    cwd=s["directory"],
                    title=s["title"],
                    ordinal=idx,
                    surface="message.user.parts",
                )
                writer.write(json.dumps(row, ensure_ascii=False) + "\n")
            elif text.strip():
                agg.add_outcome_text(
                    agent="opencode",
                    source="opencode-db",
                    session_id=sid,
                    path=OPENCODE_DB,
                    text=text,
                    ts=ts,
                    changed_files=patches,
                )
    con.close()


def extract_gemini_tmp_agy(agg: Aggregator, writer: Any) -> None:
    if not GEMINI_TMP.exists():
        return
    paths = sorted(GEMINI_TMP.glob("capfill-agy-*/chats/*.jsonl"))
    paths.extend(sorted(GEMINI_TMP.glob("*agy*/chats/*.jsonl")))
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        session_id = path.stem
        cwd = None
        for obj in read_jsonl(path):
            if "sessionId" in obj:
                session_id = str(obj.get("sessionId") or session_id)
            records: list[dict[str, Any]] = []
            if obj.get("type") in ("user", "assistant", "model"):
                records.append(obj)
            set_obj = obj.get("$set")
            if isinstance(set_obj, dict) and isinstance(set_obj.get("messages"), list):
                records.extend(x for x in set_obj["messages"] if isinstance(x, dict))
            for rec in records:
                typ = rec.get("type")
                ts = rec.get("timestamp")
                texts = json_text(rec.get("content"))
                if not texts:
                    continue
                text = "\n\n".join(texts)
                if text.startswith("<session_context>"):
                    # Still a prompt event, but record the workspace as cwd when possible.
                    m = re.search(r"- \*\*Workspace Directories:\*\*\n\s+- ([^\n]+)", text)
                    if m:
                        cwd = m.group(1).strip()
                if typ == "user":
                    row = agg.add_prompt(
                        agent="agy",
                        source="gemini-tmp-agy",
                        session_id=session_id,
                        path=path,
                        text=text,
                        ts=ts,
                        cwd=cwd,
                        ordinal=rec.get("_line"),
                        surface="gemini-cli.user",
                    )
                    writer.write(json.dumps(row, ensure_ascii=False) + "\n")
                else:
                    agg.add_outcome_text(
                        agent="agy",
                        source="gemini-tmp-agy",
                        session_id=session_id,
                        path=path,
                        text=text,
                        ts=ts,
                    )


def extract_agy_cli_history(agg: Aggregator, writer: Any) -> None:
    if not AGY_CLI_HISTORY.exists():
        return
    for ordinal, obj in enumerate(read_jsonl(AGY_CLI_HISTORY), 1):
        text = obj.get("display")
        if not isinstance(text, str) or not text.strip():
            continue
        session_id = str(obj.get("conversationId") or f"history-{ordinal}")
        row = agg.add_prompt(
            agent="agy",
            source="agy-cli-history",
            session_id=session_id,
            path=AGY_CLI_HISTORY,
            text=text,
            ts=iso_from_epoch_ms(obj.get("timestamp")),
            cwd=obj.get("workspace"),
            ordinal=ordinal,
            surface=f"agy-cli.history.{obj.get('type') or 'prompt'}",
        )
        writer.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_agy_cli_conversations(agg: Aggregator, writer: Any) -> None:
    if not AGY_CLI_CONVERSATIONS.exists():
        return
    for path in sorted(AGY_CLI_CONVERSATIONS.glob("*.db")):
        sid = path.stem
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
        ts = iso_from_mtime(path)
        agg.add_session_metadata(agent="agy", source="agy-cli-conversations", session_id=sid, path=path, ts=ts)
        for row in rows:
            spans: list[str] = []
            for column in ("step_payload", "metadata", "task_details", "error_details", "render_info"):
                spans.extend(blob_text_spans(row[column]))
            if int(row["step_type"]) == 14:
                prompt = agy_prompt_from_spans(spans)
                if prompt:
                    record = agg.add_prompt(
                        agent="agy",
                        source="agy-cli-conversations",
                        session_id=sid,
                        path=path,
                        text=prompt,
                        ts=ts,
                        ordinal=row["idx"],
                        surface="agy-cli.steps.type14",
                    )
                    writer.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                outcome_text = agy_outcome_text_from_spans(spans)
                if outcome_text.strip():
                    agg.add_outcome_text(
                        agent="agy",
                        source="agy-cli-conversations",
                        session_id=sid,
                        path=path,
                        text=outcome_text,
                        ts=ts,
                        changed_files=changed_files_from_agy_spans(spans),
                    )
        con.close()


def count_file_tree(root: Path) -> tuple[int, int]:
    count = 0
    size = 0
    if not root.exists():
        return count, size
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        count += 1
        try:
            size += path.stat().st_size
        except OSError:
            pass
    return count, size


def sqlite_item_table_summary(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": relpath(path),
        "items": 0,
        "chat_or_prompt_keys": [],
        "largest_key": None,
        "largest_bytes": 0,
    }
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        out["error"] = "open_failed"
        return out
    try:
        rows = con.execute("SELECT key, length(value) AS bytes FROM ItemTable").fetchall()
    except sqlite3.Error:
        con.close()
        out["error"] = "query_failed"
        return out
    con.close()
    out["items"] = len(rows)
    key_re = re.compile(r"(chat|prompt|conversation|trajectory|agent|antigravity)", re.I)
    for key, value_bytes in rows:
        if int(value_bytes or 0) > int(out["largest_bytes"] or 0):
            out["largest_key"] = key
            out["largest_bytes"] = int(value_bytes or 0)
        if key_re.search(str(key)):
            out["chat_or_prompt_keys"].append({"key": str(key), "bytes": int(value_bytes or 0)})
    out["chat_or_prompt_keys"] = sorted(
        out["chat_or_prompt_keys"], key=lambda item: (-int(item["bytes"]), item["key"])
    )[:20]
    return out


def antigravity_ide_state_summary() -> dict[str, Any]:
    ide_convo_count, ide_convo_bytes = count_file_tree(ANTIGRAVITY_IDE_HOME / "conversations")
    native_convo_count, native_convo_bytes = count_file_tree(ANTIGRAVITY_HOME / "conversations")
    vscdbs = (
        sorted((ANTIGRAVITY_IDE_SUPPORT / "User").rglob("state.vscdb"))
        if (ANTIGRAVITY_IDE_SUPPORT / "User").exists()
        else []
    )
    state_dbs = [sqlite_item_table_summary(path) for path in vscdbs]

    chat_migration_zero = 0
    trajectory_store_lines = 0
    log_count = 0
    if ANTIGRAVITY_IDE_SUPPORT.exists():
        for path in ANTIGRAVITY_IDE_SUPPORT.rglob("*.log"):
            log_count += 1
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chat_migration_zero += len(re.findall(r"ChatSessionStore: Migrating 0 chat sessions", text))
            trajectory_store_lines += len(re.findall(r"Creating trajectory store manager", text))

    prompt_like_key_count = sum(len(item.get("chat_or_prompt_keys") or []) for item in state_dbs)
    return {
        "ide_conversation_files": ide_convo_count,
        "ide_conversation_bytes": ide_convo_bytes,
        "native_conversation_files": native_convo_count,
        "native_conversation_bytes": native_convo_bytes,
        "state_db_count": len(state_dbs),
        "state_db_items": sum(int(item.get("items") or 0) for item in state_dbs),
        "prompt_like_key_count": prompt_like_key_count,
        "state_db_prompt_like_keys": state_dbs,
        "log_files": log_count,
        "chat_migration_zero_lines": chat_migration_zero,
        "trajectory_store_lines": trajectory_store_lines,
    }


def antigravity_inventory() -> dict[str, Any]:
    files = []
    for path in (ANTIGRAVITY_STATE, ANTIGRAVITY_SUMMARIES, AGY_CLI_HISTORY, AGY_CLI_SUMMARIES):
        if path.exists():
            files.append({"path": str(path), "display_path": relpath(path), "bytes": path.stat().st_size})
    conversation_dbs = list(AGY_CLI_CONVERSATIONS.glob("*.db")) if AGY_CLI_CONVERSATIONS.exists() else []
    conversation_db_bytes = 0
    for path in conversation_dbs:
        try:
            conversation_db_bytes += path.stat().st_size
        except OSError:
            pass
    implicit_pbs = list(AGY_CLI_IMPLICIT.glob("*.pb")) if AGY_CLI_IMPLICIT.exists() else []
    implicit_pb_bytes = 0
    implicit_pb_text_spans = 0
    for path in implicit_pbs:
        try:
            implicit_pb_bytes += path.stat().st_size
            implicit_pb_text_spans += len(blob_text_spans(path.read_bytes(), min_len=20))
        except OSError:
            pass
    ide_state = antigravity_ide_state_summary()
    support_roots = [
        ANTIGRAVITY_IDE_SUPPORT,
        ANTIGRAVITY_APP_SUPPORT,
        HOME / ".gemini" / "antigravity-cli",
    ]
    support_count = 0
    support_bytes = 0
    for root in support_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                support_count += 1
                try:
                    support_bytes += path.stat().st_size
                except OSError:
                    pass
    return {
        "known_state_files": files,
        "agy_cli_conversation_dbs": len(conversation_dbs),
        "agy_cli_conversation_db_bytes": conversation_db_bytes,
        "agy_cli_implicit_pbs": len(implicit_pbs),
        "agy_cli_implicit_pb_bytes": implicit_pb_bytes,
        "agy_cli_implicit_pb_text_spans": implicit_pb_text_spans,
        "ide_state": ide_state,
        "support_file_count": support_count,
        "support_bytes": support_bytes,
        "note": "Agy CLI history and per-conversation SQLite prompt bodies are decoded. Antigravity IDE conversation directories are empty on this host; IDE state DBs and logs were checked for prompt/session stores and did not add first-class prompt events.",
    }


def summarize_agents(sessions: list[dict[str, Any]], agg: Aggregator) -> dict[str, Any]:
    by_agent: dict[str, dict[str, Any]] = {}
    for agent in sorted({s["agent"] for s in sessions} | set(agg.agent_counts)):
        agent_sessions = [s for s in sessions if s["agent"] == agent]
        by_agent[agent] = {
            "sessions": len(agent_sessions),
            "prompt_events": sum(s["prompt_events"] for s in agent_sessions),
            "session_unique_prompts_sum": sum(s["unique_prompts"] for s in agent_sessions),
            "session_unique_task_bodies_sum": sum(s["unique_task_bodies"] for s in agent_sessions),
            "prompt_bytes": sum(s["prompt_bytes"] for s in agent_sessions),
            "task_body_bytes": sum(s["task_body_bytes"] for s in agent_sessions),
            "sessions_with_verification": sum(1 for s in agent_sessions if s["outcome"].get("verification", 0) > 0),
            "sessions_with_receipts": sum(
                1 for s in agent_sessions if s["outcome"].get("receipts", 0) > 0 or s["changed_file_count"] > 0
            ),
            "sessions_with_structured_changes": sum(1 for s in agent_sessions if s.get("changed_file_count", 0) > 0),
            "structured_change_refs": sum(int(s.get("changed_file_count") or 0) for s in agent_sessions),
            "likely_noop_or_unrecorded": sum(
                1 for s in agent_sessions if "likely no-op or unrecorded work" in s["ideal_gaps"]
            ),
            "top_gaps": Counter(gap for s in agent_sessions for gap in s["ideal_gaps"]).most_common(8),
            "body_kinds": dict(
                sum(
                    (
                        Counter(
                            {
                                key.removeprefix("body_kind:"): value
                                for key, value in (s.get("prompt_flags") or {}).items()
                                if key.startswith("body_kind:")
                            }
                        )
                        for s in agent_sessions
                    ),
                    Counter(),
                )
            ),
            "tokens": dict(sum((Counter(s.get("tokens") or {}) for s in agent_sessions), Counter())),
            "cost": sum(float(s.get("cost") or 0.0) for s in agent_sessions),
        }
    return by_agent


def render_markdown(snapshot: dict[str, Any]) -> str:
    generated = snapshot["generated_at"]
    counts = snapshot["counts"]
    agent_summary = snapshot["agents"]
    top_sessions = snapshot["top_sessions"]
    private = snapshot["private_outputs"]
    antigravity = snapshot["antigravity_inventory"]

    lines: list[str] = [
        "# Agent Session Full-Stack Review",
        "",
        f"Generated: `{generated}`",
        "",
        "## Scope",
        "",
        "- Prompt layer first: every extracted prompt event is stored verbatim in the private cartridge.",
        "- Session layer second: sessions are scored against ideal-form requirements and observed outcome signals.",
        "- Tracked output is redacted and receipt-oriented; raw prompt text remains process input under `.limen-private/`.",
        "",
        "## Private Prompt Corpus",
        "",
        f"- Verbatim prompt events: `{private['verbatim_prompts']}`",
        f"- Structured review: `{private['structured_review']}`",
        f"- Prompt events extracted: `{counts['prompt_events']}`",
        f"- Unique prompt hashes: `{counts['unique_prompt_hashes']}`",
        f"- Unique normalized task-body hashes: `{counts['unique_task_body_hashes']}`",
        f"- Sessions reviewed: `{counts['sessions']}`",
        f"- Outcome text scanned: `{counts['outcome_text_bytes']}` bytes",
        "",
        "## Agent Coverage",
        "",
        "| Agent | Sessions | Prompt events | Prompt bytes | Task-body bytes | Verified sessions | Receipt sessions | Likely no-op/unrecorded |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for agent, item in sorted(agent_summary.items()):
        lines.append(
            f"| `{agent}` | {item['sessions']} | {item['prompt_events']} | {item['prompt_bytes']} | "
            f"{item['task_body_bytes']} | {item['sessions_with_verification']} | "
            f"{item['sessions_with_receipts']} | {item['likely_noop_or_unrecorded']} |"
        )

    lines.extend(
        [
            "",
            "## Work Surface Coverage",
            "",
            "| Agent | Structured change sessions | Structured change refs | Input tokens | Output tokens | Reasoning tokens | Cost |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for agent, item in sorted(agent_summary.items()):
        tokens = item.get("tokens") or {}
        lines.append(
            f"| `{agent}` | {item['sessions_with_structured_changes']} | {item['structured_change_refs']} | "
            f"{int(tokens.get('input') or 0)} | {int(tokens.get('output') or 0)} | "
            f"{int(tokens.get('reasoning') or 0)} | {item['cost']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Structured change refs are native or structured tool-payload surfaces, not inferred code diffs. In this local corpus OpenCode exposes native SQLite diffs; Codex and Claude add conservative patch/edit/write tool paths; Agy adds conservative CLI `TargetFile` tool paths when present.",
        ]
    )

    lines.extend(
        [
            "",
            "## Prompt Body Mix",
            "",
            "| Body kind | Prompt events |",
            "|---|---:|",
        ]
    )
    for kind, count in sorted(snapshot["body_kind_counts"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{kind}` | {count} |")

    lines.extend(
        [
            "",
            "## Source Coverage",
            "",
            "| Source | Prompt events |",
            "|---|---:|",
        ]
    )
    for source, count in sorted(snapshot["source_counts"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{source}` | {count} |")

    total_unverified = sum(
        item["sessions"] - item["sessions_with_verification"] for item in agent_summary.values()
    )
    total_unreceipted = sum(
        item["sessions"] - item["sessions_with_receipts"] for item in agent_summary.values()
    )
    total_likely_noop = sum(item["likely_noop_or_unrecorded"] for item in agent_summary.values())
    flame_events = snapshot["body_kind_counts"].get("flame_scaffold", 0) + snapshot["body_kind_counts"].get(
        "flame_with_task_body", 0
    )

    lines.extend(
        [
            "",
            "## Ideal-Form Diff Rules",
            "",
            "Each session is compared to this ideal form:",
            "",
            "- Prompt names concrete owner scope: repo/path/task/lane.",
            "- Prompt names an executable predicate or acceptance condition.",
            "- Prompt names the expected durable receipt: changed path, commit, PR, artifact, or blocker record.",
            "- Prompt separates reversible execution from human-gated outward/irreversible action.",
            "- Session outcome records verification and a durable receipt, or a precise blocker.",
            "",
            "## Ask-vs-Done Diff",
            "",
            "- Asked for every prompt verbatim: done in the private prompt corpus with hashes in the tracked report.",
            "- Asked for Codex, Claude, Agy/Antigravity, and OpenCode: covered Codex session/history JSONL, Claude project/task JSONL, OpenCode SQLite, Agy CLI history/conversation SQLite, and Agy/Gemini capfill JSONL; native Antigravity IDE state is inventoried but not fully decoded.",
            "- Asked for prompt layer first and session layer second: prompt events are normalized into raw prompt hashes plus task-body hashes, then sessions are scored against ideal-form outcome rules.",
            "- Asked for the diff between the ask and actual work: tracked at session level through missing scope, predicate, receipt, gate handling, verification, changed-file, token, and blocker signals.",
            "- Asked for a full work review: this pass is the corpus-wide receipt/outcome review; line-level code review should be driven next from the highest-risk session list rather than attempted as an unbounded manual sweep.",
            "",
            "## What Broke",
            "",
            f"- `{total_unverified}` sessions with prompts had no verification signal in the reviewed outcome text.",
            f"- `{total_unreceipted}` sessions had no durable receipt signal or changed-file receipt.",
            f"- `{total_likely_noop}` sessions look like no-op or unrecorded work because prompts exist but the outcome surface has no verification/receipt/change signal.",
            f"- `{flame_events}` prompt events carried FLAME scaffolding; the task body is now separated, but older ledger views overcounted repeated invariant prompt mass as fresh work.",
            "- Structured changed-file data is still uneven by agent: OpenCode exposes SQLite diffs, Codex and Claude expose conservative patch/edit/write tool paths, and Agy exposes conservative CLI `TargetFile` tool paths when present.",
            "- OpenCode had many sessions that only become trustworthy when its DB-backed token clock and receipt handshake are present; session rows alone are not enough.",
            "- Antigravity IDE has no first-class prompt/session records on this host; provider quota is still not represented as a native receipt surface.",
            "",
            "## Highest-Risk Session Diffs",
            "",
            "| Rank | Agent | Session | Prompt events | Risk | Gaps | Paths |",
            "|---:|---|---|---:|---:|---|---|",
        ]
    )
    for i, session in enumerate(top_sessions[:30], 1):
        gaps = "; ".join(session["ideal_gaps"][:4]) or "none"
        paths = "<br>".join(session["paths"][:2])
        lines.append(
            f"| {i} | `{session['agent']}` | `{session['session_id']}` | {session['prompt_events']} | "
            f"{session['risk_score']} | {gaps} | {paths} |"
        )

    lines.extend(
        [
            "",
            "## Findings",
            "",
            "1. Codex, Claude, OpenCode, and Agy CLI prompt stores are now covered by the refreshed Limen prompt ledger and this full-stack review. The old prompt ledger undercounted OpenCode's SQLite store and Agy CLI/capfill sources; this pass closes that local gap for the four requested agents.",
            "2. Repeated fleet prompts carry a large invariant preamble before narrow work. That makes the prompt layer expensive and blurs the ideal diff: many sessions look like they were asked to preserve the whole organism when the real task was a narrow repo predicate.",
            "3. Broad autonomy language and closeout language are fighting each other. The ideal form should require a named owner scope and receipt before any lane gets a broad prompt.",
            "4. OpenCode has many recent sessions with no summary diffs and no token accounting in the session row; those need a live clock/receipt handshake or they read as no-op/unrecorded work even when the model saw a prompt.",
            "5. Agy provider quota remains a weak surface: this review now decodes Agy CLI history and per-conversation SQLite prompts, while the native Antigravity IDE stores checked here contain no prompt/session records.",
            "",
            "## Agent Notes",
            "",
        ]
    )
    for agent, item in sorted(agent_summary.items()):
        gaps = ", ".join(f"{name} ({count})" for name, count in item["top_gaps"][:5]) or "none"
        lines.append(f"- `{agent}`: top gaps: {gaps}.")

    lines.extend(
        [
            "",
            "## Antigravity/Agy Native Surface",
            "",
            f"- Known native state files: `{len(antigravity['known_state_files'])}`.",
            f"- Agy CLI conversation DBs decoded: `{antigravity['agy_cli_conversation_dbs']}` files, `{antigravity['agy_cli_conversation_db_bytes']}` bytes.",
            f"- Agy CLI implicit protobuf files inventoried: `{antigravity['agy_cli_implicit_pbs']}` files, `{antigravity['agy_cli_implicit_pb_bytes']}` bytes, `{antigravity['agy_cli_implicit_pb_text_spans']}` printable text spans.",
            f"- Antigravity IDE conversation dirs checked: `.gemini/antigravity-ide/conversations` has `{antigravity['ide_state']['ide_conversation_files']}` files; `.gemini/antigravity/conversations` has `{antigravity['ide_state']['native_conversation_files']}` files.",
            f"- Antigravity IDE state DBs checked: `{antigravity['ide_state']['state_db_count']}` DBs, `{antigravity['ide_state']['state_db_items']}` keys, `{antigravity['ide_state']['prompt_like_key_count']}` chat/prompt/trajectory-like keys.",
            f"- Antigravity IDE log evidence: `{antigravity['ide_state']['chat_migration_zero_lines']}` zero-chat-session migration lines and `{antigravity['ide_state']['trajectory_store_lines']}` trajectory-store startup lines across `{antigravity['ide_state']['log_files']}` log files.",
            f"- Local support files inventoried: `{antigravity['support_file_count']}` files, `{antigravity['support_bytes']}` bytes.",
            f"- Coverage note: {antigravity['note']}",
            "",
            "## Next Repairs",
            "",
            "1. Re-check native Antigravity IDE only after a run creates non-empty `.gemini/antigravity-ide/conversations` or `.gemini/antigravity/conversations`; current host state has no IDE prompt store to decode.",
            "2. Add a native Agy provider clock or explicit quota receipt. The existing board-run clock is not equivalent to provider quota exhaustion.",
            "3. Require lane packets to include `owner_scope`, `predicate`, `expected_receipt`, and `gate_class` fields before dispatch to OpenCode/Agy/Claude/Jules.",
            "4. Flag sessions with `prompt_events > 0` and no verification/receipt as failed-unrecorded until a receipt or blocker is written.",
            "5. Use the top-risk session list as the queue for deeper code-diff review, starting with broad Claude sessions and no-receipt OpenCode/Agy sessions.",
            "",
            "## Commands",
            "",
            "- Refresh this review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`",
            "- Inspect raw prompts locally: `less .limen-private/session-corpus/full-stack-review/verbatim-prompts.jsonl`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_snapshot() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    agg = Aggregator()
    with PRIVATE_PROMPTS.open("w", encoding="utf-8") as writer:
        extract_codex(agg, writer)
        extract_claude(agg, writer)
        extract_opencode(agg, writer)
        extract_gemini_tmp_agy(agg, writer)
        extract_agy_cli_history(agg, writer)
        extract_agy_cli_conversations(agg, writer)
    sessions = agg.finalize_sessions()
    snapshot = {
        "generated_at": now_iso(),
        "counts": {
            "prompt_events": agg.prompt_events,
            "unique_prompt_hashes": len(agg.unique_prompt_hashes),
            "unique_task_body_hashes": len(agg.unique_task_body_hashes),
            "sessions": len(sessions),
            "outcome_text_bytes": agg.outcome_text_bytes,
        },
        "source_counts": dict(agg.source_counts),
        "body_kind_counts": dict(agg.body_kind_counts),
        "agent_prompt_counts": dict(agg.agent_counts),
        "agents": summarize_agents(sessions, agg),
        "top_sessions": sessions[:200],
        "sessions": sessions,
        "private_outputs": {
            "verbatim_prompts": str(PRIVATE_PROMPTS.relative_to(ROOT)) if PRIVATE_PROMPTS.is_relative_to(ROOT) else str(PRIVATE_PROMPTS),
            "structured_review": str(PRIVATE_REVIEW.relative_to(ROOT)) if PRIVATE_REVIEW.is_relative_to(ROOT) else str(PRIVATE_REVIEW),
        },
        "antigravity_inventory": antigravity_inventory(),
    }
    PRIVATE_REVIEW.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write tracked markdown report")
    parser.add_argument("--json", action="store_true", help="print private structured review path and counts")
    args = parser.parse_args(argv)

    snapshot = build_snapshot()
    if args.write:
        DOC_PATH.write_text(render_markdown(snapshot), encoding="utf-8")
    if args.json or not args.write:
        print(json.dumps({"counts": snapshot["counts"], "private_review": str(PRIVATE_REVIEW), "doc": str(DOC_PATH)}, indent=2))
    else:
        print(
            "agent-session-full-stack-review: "
            f"{snapshot['counts']['prompt_events']} prompts, "
            f"{snapshot['counts']['sessions']} sessions; wrote {DOC_PATH}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
