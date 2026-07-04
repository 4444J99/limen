#!/usr/bin/env python3
"""Classify local Codex sessions into lifecycle families without committing raw chat text.

Claude has `scripts/quicken.py`: it can inspect FleetView sessions, classify stalled work,
and hang the irreducible human residue. Codex session files do not have the same task sidecar,
so this organ is deliberately narrower:

* read local `~/.codex/sessions/**/*.jsonl` and `~/.codex/history.jsonl`;
* classify sessions by lifecycle state and work family;
* write only counts, hashes, and routing labels to tracked docs;
* write the redacted per-session index to `.limen-private/`.

This is an intake/classifier, not an executor. It does not resume sessions, dispatch work,
edit tasks.yaml, delete files, push, merge, or touch credentials.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
SESSIONS = HOME / ".codex" / "sessions"
HISTORY = HOME / ".codex" / "history.jsonl"
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
JOURNAL = ROOT / "logs" / "codex-session-lifecycle.jsonl"
DIGEST_OUT = ROOT / "docs" / "CODEX-SESSION-LIFECYCLE.md"


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


STALE_MIN = positive_int_env("LIMEN_CODEX_QUICKEN_STALE_MIN", 20)

FAMILIES: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        "auth_credentials",
        re.compile(r"\b(auth|login|sign ?in|oauth|secret|credential|api[ _-]?key|token|password)\b", re.I),
        "credential workstream",
        "park unless a scoped task explicitly requires the account action",
    ),
    (
        "session_lifecycle",
        re.compile(
            r"\b(session|handoff|closeout|lifecycle|sprawl|drain|receipt|intake|goal|conductor|"
            r"autopoietic|autopoiesis|alchemy)\b",
            re.I,
        ),
        "limen control plane",
        "fold into session and prompt lifecycle ledgers",
    ),
    (
        "convergence_corpus",
        re.compile(
            r"\b(convergence|corpus|knowledge graph|knowledge[- ]corpus|session[- ]meta|atoms?|"
            r"studium|canon|memory|prompt)\b",
            re.I,
        ),
        "corpus organs",
        "route through session-meta, knowledge-corpus, and corpus-converge receipts",
    ),
    (
        "worktree_lifecycle",
        re.compile(r"\b(worktree|dirty|untracked|unpushed|merged|branch|\.limen-worktrees)\b", re.I),
        "worktree lifecycle",
        "preserve branch or owner receipt before cleanup",
    ),
    (
        "github_review",
        re.compile(r"\b(github|pull request|\bpr\b|issue|review|merge|closed as|not planned)\b", re.I),
        "repo owner",
        "map issue or PR to owner receipt before further review",
    ),
    (
        "technical_debt_ci",
        re.compile(r"\b(technical debt|typecheck|tsc|pytest|test|ci|build|verify|probe|worker)\b", re.I),
        "repo predicate",
        "run the narrow predicate and preserve failures as owner blockers",
    ),
    (
        "agent_coordination",
        re.compile(r"\b(jules|agy|gemini|opencode|claude|codex|dispatch|async|subagent)\b", re.I),
        "agent router",
        "packetize only bounded, non-secret work for other agents",
    ),
    (
        "product_surface",
        re.compile(
            r"\b(revenue|bounty|portfolio|scraper|invisible ledger|mail|automation|chess|media|"
            r"product|customer|landing)\b",
            re.I,
        ),
        "product repo",
        "route to the owning product surface after corpus receipt",
    ),
]


def stable_hash(text: str, length: int = 20) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def iso_from_ts(ts: float | None) -> str | None:
    if not ts:
        return None
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat(timespec="seconds")


def parse_ts(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        return ts if math.isfinite(ts) else None
    try:
        ts = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (OverflowError, ValueError):
        return None
    return ts if math.isfinite(ts) else None


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
                    rows.append(obj)
    except OSError:
        return []
    return rows


def iter_session_files(days: int | None) -> list[Path]:
    cutoff = None if days is None else time.time() - days * 86400
    files: list[Path] = []
    if SESSIONS.is_dir():
        for path in SESSIONS.rglob("*.jsonl"):
            try:
                mtime = path.stat().st_mtime
                if cutoff is None or mtime >= cutoff:
                    files.append(path)
            except OSError:
                continue
    def mtime_or_zero(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    files.sort(key=mtime_or_zero, reverse=True)
    return files


def prompt_texts(obj: dict[str, Any]) -> list[str]:
    payload = obj.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "user_message":
            return text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))
        if payload.get("type") == "message" and payload.get("role") == "user":
            return text_from_content(payload.get("content"))
    return []


def classify_family(text: str) -> dict[str, str]:
    for family, rx, owner, route in FAMILIES:
        if rx.search(text):
            return {"family": family, "owner": owner, "route": route}
    return {
        "family": "uncategorized",
        "owner": "needs classifier",
        "route": "inspect privately, then add a family or owner receipt",
    }


def classify_state(
    *,
    now: float,
    mtime: float,
    last_user_ts: float | None,
    last_complete_ts: float | None,
    last_abort_ts: float | None,
    family: str,
) -> str:
    idle_min = (now - mtime) / 60.0
    if idle_min < STALE_MIN:
        return "ALIVE"
    if family == "auth_credentials" and (last_complete_ts is None or (last_user_ts or 0) > last_complete_ts):
        return "PARKED"
    if last_user_ts and (last_complete_ts is None or last_user_ts > last_complete_ts):
        return "STALLED"
    if last_abort_ts and (last_complete_ts is None or last_abort_ts > last_complete_ts):
        return "STALLED"
    if last_complete_ts:
        return "CLOSED"
    return "CLOSED"


def summarize_session(path: Path, now: float) -> dict[str, Any] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    records = read_jsonl(path)
    if not records:
        return None

    session_id = path.stem
    cwd: str | None = None
    event_count = 0
    prompts: list[str] = []
    prompt_hashes: list[str] = []
    first_ts: float | None = None
    last_ts: float | None = None
    last_user_ts: float | None = None
    last_complete_ts: float | None = None
    last_abort_ts: float | None = None

    for obj in records:
        event_count += 1
        ts = parse_ts(obj.get("timestamp"))
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)

        typ = obj.get("type")
        payload = obj.get("payload")
        ptype = payload.get("type") if isinstance(payload, dict) else None
        if typ == "session_meta" and isinstance(payload, dict):
            if payload.get("session_id"):
                session_id = str(payload["session_id"])
            if payload.get("cwd"):
                cwd = str(payload["cwd"])
        if typ == "turn_context" and isinstance(payload, dict) and payload.get("cwd"):
            cwd = str(payload["cwd"])
        if ptype == "user_message":
            last_user_ts = ts or last_user_ts
        if ptype == "task_complete":
            last_complete_ts = ts or last_complete_ts
        if ptype == "turn_aborted":
            last_abort_ts = ts or last_abort_ts
        for text in prompt_texts(obj):
            prompts.append(text)
            prompt_hashes.append(hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest())

    family = classify_family("\n".join(prompts))
    state = classify_state(
        now=now,
        mtime=st.st_mtime,
        last_user_ts=last_user_ts,
        last_complete_ts=last_complete_ts,
        last_abort_ts=last_abort_ts,
        family=family["family"],
    )
    prompt_bytes = sum(len(p.encode("utf-8", errors="replace")) for p in prompts)
    return {
        "session_key": stable_hash(f"codex:{session_id}:{path}", 24),
        "session_id_hash": stable_hash(session_id, 24),
        "path": str(path),
        "display_path": relpath(path),
        "cwd_hash": stable_hash(cwd, 24) if cwd else None,
        "cwd_repo_hint": Path(cwd).name if cwd else None,
        "mtime": iso_from_ts(st.st_mtime),
        "first_event": iso_from_ts(first_ts),
        "last_event": iso_from_ts(last_ts),
        "event_count": event_count,
        "prompt_event_count": len(prompts),
        "prompt_bytes": prompt_bytes,
        "first_prompt_hash": prompt_hashes[0] if prompt_hashes else None,
        "last_prompt_hash": prompt_hashes[-1] if prompt_hashes else None,
        "family": family["family"],
        "owner": family["owner"],
        "route": family["route"],
        "state": state,
    }


def summarize_history(days: int | None) -> dict[str, Any]:
    if not HISTORY.is_file():
        return {"present": False, "path": str(HISTORY), "events": 0}
    cutoff = None if days is None else time.time() - days * 86400
    events = 0
    prompt_hashes: list[str] = []
    by_session: Counter[str] = Counter()
    for obj in read_jsonl(HISTORY):
        ts = parse_ts(obj.get("ts"))
        if cutoff is not None and ts is not None and ts < cutoff:
            continue
        text = obj.get("text")
        if isinstance(text, str) and text.strip():
            events += 1
            prompt_hashes.append(hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest())
        sid = obj.get("session_id")
        if sid:
            by_session[stable_hash(str(sid), 24)] += 1
    return {
        "present": True,
        "path": str(HISTORY),
        "events": events,
        "sessions": len(by_session),
        "first_prompt_hash": prompt_hashes[0] if prompt_hashes else None,
        "last_prompt_hash": prompt_hashes[-1] if prompt_hashes else None,
    }


def build_snapshot(days: int | None) -> dict[str, Any]:
    now = time.time()
    sessions = [
        row
        for path in iter_session_files(days)
        if (row := summarize_session(path, now)) is not None
    ]
    by_state = Counter(row["state"] for row in sessions)
    by_family = Counter(row["family"] for row in sessions)
    family_state: dict[str, Counter[str]] = defaultdict(Counter)
    family_bytes: Counter[str] = Counter()
    family_prompts: Counter[str] = Counter()
    family_routes: dict[str, dict[str, str]] = {}
    for row in sessions:
        family_state[row["family"]][row["state"]] += 1
        family_bytes[row["family"]] += int(row["prompt_bytes"])
        family_prompts[row["family"]] += int(row["prompt_event_count"])
        family_routes[row["family"]] = {"owner": row["owner"], "route": row["route"]}

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "horizon_days": days,
        "stale_min": STALE_MIN,
        "sessions": sessions,
        "session_count": len(sessions),
        "history": summarize_history(days),
        "by_state": dict(sorted(by_state.items())),
        "by_family": dict(sorted(by_family.items())),
        "families": [
            {
                "family": family,
                "sessions": by_family[family],
                "states": dict(sorted(family_state[family].items())),
                "prompt_events": family_prompts[family],
                "prompt_bytes": family_bytes[family],
                **family_routes.get(family, {"owner": "unknown", "route": "unknown"}),
            }
            for family in sorted(by_family, key=lambda f: (-by_family[f], f))
        ],
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    horizon = "all local history" if snapshot["horizon_days"] is None else f"last {snapshot['horizon_days']} days"
    lines = [
        "# Codex Session Lifecycle",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Horizon: `{horizon}`",
        "",
        "## Canonical Decision",
        "",
        "- Codex app/session history is lifecycle material, not disposable chat residue.",
        "- Tracked output stays counts-only and route-oriented; raw prompts remain in local Codex stores and ignored private cartridge indexes.",
        "- This classifier does not execute, delete, dispatch, push, merge, or solve credentials.",
        "- Auth, login, key, token, password, and credential sessions are parked into the credential workstream unless directly scoped.",
        "",
        "## State Summary",
        "",
        f"- Codex session files classified: `{snapshot['session_count']}`.",
    ]
    hist = snapshot.get("history", {})
    if hist.get("present"):
        lines.append(
            f"- Codex prompt history events indexed: `{hist.get('events', 0)}` across "
            f"`{hist.get('sessions', 0)}` session ids."
        )
    else:
        lines.append("- Codex prompt history file was not present.")

    if snapshot.get("by_state"):
        lines.append(
            "- States: "
            + ", ".join(f"`{state}` {count}" for state, count in snapshot["by_state"].items())
            + "."
        )
    else:
        lines.append("- States: none.")

    lines += [
        "",
        "## Family Routes",
        "",
        "| Family | Sessions | States | Prompt Events | Owner | Route |",
        "|---|---:|---|---:|---|---|",
    ]
    for family in snapshot["families"]:
        states = ", ".join(f"`{state}` {count}" for state, count in family["states"].items()) or "none"
        lines.append(
            f"| `{family['family']}` | {family['sessions']} | {states} | "
            f"{family['prompt_events']} | {family['owner']} | {family['route']} |"
        )
    if not snapshot["families"]:
        lines.append("| none | 0 | none | 0 | n/a | n/a |")

    lines += [
        "",
        "## Lifecycle Rules",
        "",
        "- `ALIVE`: recently moving; do not interfere.",
        "- `STALLED`: a user prompt appears newer than any recorded Codex task completion.",
        "- `CLOSED`: Codex recorded task completion or no newer prompt is waiting.",
        "- `PARKED`: credential/auth/login material; hung for a separate credential workstream.",
        "",
        "## Commands",
        "",
        "- Preview all history: `python3 scripts/codex-quicken.py --all`",
        "- Write the digest, journal, and private index: `python3 scripts/codex-quicken.py --all --apply`",
        "- Bounded preview: `python3 scripts/codex-quicken.py --days 14`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DIGEST_OUT.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_OUT.write_text(markdown, encoding="utf-8")
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    journal_record = {
        "ts": int(time.time()),
        "generated_at": snapshot["generated_at"],
        "horizon_days": snapshot["horizon_days"],
        "session_count": snapshot["session_count"],
        "by_state": snapshot["by_state"],
        "by_family": snapshot["by_family"],
    }
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(journal_record, sort_keys=True) + "\n")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify Codex local sessions into lifecycle families.")
    parser.add_argument("--days", type=int, default=14, help="session horizon to scan")
    parser.add_argument("--all", action="store_true", help="scan all local Codex session history")
    parser.add_argument("--apply", action="store_true", help="write docs, journal, and ignored private index")
    args = parser.parse_args()
    days = None if args.all or args.days <= 0 else args.days

    snapshot = build_snapshot(days)
    markdown = render_markdown(snapshot)
    if args.apply:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    horizon = "all history" if days is None else f"{days}d"
    msg = f"codex-quicken: {snapshot['session_count']} sessions over {horizon}"
    if args.apply:
        msg += f"; wrote {DIGEST_OUT}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
