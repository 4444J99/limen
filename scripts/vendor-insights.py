#!/usr/bin/env python3
"""
vendor-insights.py — the MECHANICAL half of /vendor-insights (cross-vendor /insights).

Claude Code's built-in /insights produces a faceted narrative usage report — but only for
Claude. This organ is the deterministic substrate that lets the /vendor-insights skill
produce the same report for every other agent estate on the host (codex, copilot,
opencode, antigravity/agy, gemini — and claude itself, for parity runs).

Division of labor (the experience-audit ↔ experience-judge twin pattern):
  - THIS SCRIPT (deterministic): enumerate sessions (`index`), hand the model one bounded
    transcript excerpt at a time (`cat-session`), and render the final HTML (`render`).
  - THE SKILL (model-in-the-loop): read excerpts, write per-session facet JSONs (the same
    shape Claude's /insights facets use), aggregate them into narrative.json, then call
    `render`.

Vendor store paths are imported from scripts/insight-cross-vendor-ingest.py
(VENDOR_REGISTRY + claude_estate_roots) — one source of truth; this organ never
re-declares a path. Store shapes were established by direct recon (2026-08-06) and are
noted per adapter; unknown record types are tolerated, never fatal.

Data placement (deliberate, mirrors built-in /insights):
  logs/vendor-insights/<vendor>/index.json           session metadata index (local-only)
  logs/vendor-insights/<vendor>/facets/<sid>.json    per-session facets (skill-written)
  logs/vendor-insights/<vendor>/narrative.json       aggregate narrative (skill-written)
  logs/vendor-insights/<vendor>/report-<ts>.html     the shareable report
  logs/vendor-insights/ is GITIGNORED: reports narrate personal usage, exactly like the
  built-in /insights artifact under .agent-runtime/ — the tracked deliverable is this
  organ + the skill + tests, never the personal data.

Usage:
  python3 scripts/vendor-insights.py list
  python3 scripts/vendor-insights.py index --vendor codex [--window-days 14] [--max-sessions 40]
  python3 scripts/vendor-insights.py cat-session --vendor codex --session <id> [--max-chars 60000]
  python3 scripts/vendor-insights.py render --vendor codex

Exit codes: 0 ok · 1 error · 2 missing prerequisite (e.g. render before facets exist).
All vendor stores are opened STRICTLY read-only (SQLite via file:...?mode=ro).
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sqlite3
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import NamedTuple

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
HOME = Path(os.environ.get("HOME", str(Path.home())))
OUT_ROOT = Path(os.environ.get("LIMEN_VENDOR_INSIGHTS_DIR", LIMEN_ROOT / "logs" / "vendor-insights"))

DEFAULT_WINDOW_DAYS = 14
DEFAULT_MAX_SESSIONS = 40
DEFAULT_MAX_CHARS = 60_000

# ---------------------------------------------------------------------------
# Ingest-organ import — single source of truth for vendor store paths
# ---------------------------------------------------------------------------


def _load_ingest_module():
    ingest_path = Path(__file__).resolve().parent / "insight-cross-vendor-ingest.py"
    spec = importlib.util.spec_from_file_location("insight_cross_vendor_ingest", ingest_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _ro_connect(db_path: Path) -> sqlite3.Connection:
    """Open a vendor SQLite store read-only. Never bare-connect a live store."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


# ---------------------------------------------------------------------------
# Session record shape (every adapter returns these)
# ---------------------------------------------------------------------------
# {
#   "id": str, "started_at": iso, "ended_at": iso | None, "cwd": str | None,
#   "user_msgs": int, "assistant_msgs": int, "tool_calls": int,
#   "models": [str], "approx_bytes": int, ...adapter extras (step_count, rollout_files, ...)
# }


def _mk(sid, started, ended, cwd, u, a, t, models, size, extra: dict | None = None) -> dict:
    rec = {
        "id": str(sid),
        "started_at": started,
        "ended_at": ended,
        "cwd": cwd,
        "user_msgs": int(u),
        "assistant_msgs": int(a),
        "tool_calls": int(t),
        "models": sorted({m for m in models if m}),
        "approx_bytes": int(size),
    }
    if extra:
        rec.update(extra)
    return rec


class IndexResult(NamedTuple):
    """What every _index_* adapter returns.

    A sample is not the corpus: `total_in_window` is the TRUE in-window population
    counted with the same predicate that selected `sessions`, before any cap —
    the renderer and skill surface it so a capped index can never speak in the
    corpus's language (the antigravity 40-of-505 incident, 2026-08-06).
    """

    sessions: list
    total_in_window: int
    order_key: str
    notes: tuple | list = ()
    sources: dict | None = None
    extra: dict | None = None


def _rank(candidates: list[tuple[float, object]], max_sessions: int) -> tuple[list, int, bool]:
    """One shared recency contract: sort by key desc, keep the newest N.

    Returns (kept_items, total_in_window, capped). Every adapter caps through
    here so "most-recent N" has a single definition instead of six copies.
    """
    candidates.sort(key=lambda kv: kv[0], reverse=True)
    total = len(candidates)
    kept = [item for _, item in candidates[:max_sessions]]
    return kept, total, total > max_sessions


# ---------------------------------------------------------------------------
# Adapter: claude — legacy ~/.claude/projects + per-workspace .agent-runtime
# roots (mod.claude_estate_roots). One JSONL per session inside project dirs.
# ---------------------------------------------------------------------------


def _index_claude(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    candidates: list[tuple[float, Path]] = []
    for root in mod.claude_estate_roots():
        for proj_dir in root.iterdir():
            if not proj_dir.is_dir():
                continue
            mt = _mtime(proj_dir)
            if mt is None or mt < window_start:
                continue
            for p in proj_dir.glob("*.jsonl"):
                fmt = _mtime(p)
                if fmt is not None and fmt >= window_start:
                    candidates.append((fmt.timestamp(), p))
    kept, total, _capped = _rank(candidates, max_sessions)
    sessions = []
    for p in kept:
        u = a = t = 0
        first_ts = last_ts = cwd = None
        models: set[str] = set()
        try:
            with p.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = rec.get("timestamp")
                    if isinstance(ts, str):
                        first_ts = first_ts or ts
                        last_ts = ts
                    if cwd is None and isinstance(rec.get("cwd"), str):
                        cwd = rec["cwd"]
                    typ = rec.get("type")
                    if typ == "user":
                        u += 1
                    elif typ == "assistant":
                        a += 1
                        msg = rec.get("message") or {}
                        if isinstance(msg, dict):
                            if isinstance(msg.get("model"), str):
                                models.add(msg["model"])
                            for blk in msg.get("content") or []:
                                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                                    t += 1
            sessions.append(_mk(p.stem, first_ts, last_ts, cwd, u, a, t, models, p.stat().st_size))
        except OSError:
            continue
    return IndexResult(sessions, total, "file mtime")


def _cat_claude(mod, sid: str, max_chars: int) -> str | None:
    match = None
    for root in mod.claude_estate_roots():
        found = list(root.glob(f"*/{sid}.jsonl"))
        if found:
            match = found[0]
            break
    if match is None:
        return None
    out: list[str] = []
    total = 0
    with match.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            typ = rec.get("type")
            if typ not in ("user", "assistant"):
                continue
            msg = rec.get("message") or {}
            content = msg.get("content")
            texts: list[str] = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for blk in content:
                    if not isinstance(blk, dict):
                        continue
                    if blk.get("type") == "text":
                        texts.append(blk.get("text") or "")
                    elif blk.get("type") == "tool_use":
                        texts.append(f"[tool_use: {blk.get('name')}]")
            if not texts:
                continue
            chunk = f"--- {typ} ({(rec.get('timestamp') or '')[:19]}) ---\n" + "\n".join(texts) + "\n"
            out.append(chunk)
            total += len(chunk)
            if total >= max_chars:
                out.append("[... truncated at max-chars ...]\n")
                break
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: codex — ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (+ flat
# archived_sessions/). Line types: session_meta (payload.id/.cwd/.git),
# turn_context (payload.model), response_item (payload.type: message role
# user|assistant | function_call | function_call_output | reasoning).
# Streamed line-by-line — some rollouts run to thousands of lines.
# ---------------------------------------------------------------------------


def _codex_roots(mod) -> list[Path]:
    meta = mod.VENDOR_REGISTRY["codex"]
    roots = [Path(p) for p in meta.get("sessions_roots", [])]
    return [r for r in roots if r.is_dir()]


def _codex_scan_file(p: Path) -> dict:
    sid = cwd = None
    u = a = t = 0
    models: set[str] = set()
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            typ = rec.get("type")
            payload = rec.get("payload") or {}
            if typ == "session_meta":
                sid = payload.get("session_id") or payload.get("id") or sid
                cwd = payload.get("cwd") or cwd
            elif typ == "turn_context":
                if isinstance(payload.get("model"), str):
                    models.add(payload["model"])
            elif typ == "response_item":
                pt = payload.get("type")
                if pt == "message":
                    role = payload.get("role")
                    if role == "user":
                        u += 1
                    elif role == "assistant":
                        a += 1
                elif pt == "function_call":
                    t += 1
    return {"sid": sid, "cwd": cwd, "u": u, "a": a, "t": t, "models": models}


_CODEX_TS_RE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})")


def _codex_started_at(p: Path) -> str | None:
    m = _CODEX_TS_RE.search(p.name)
    if not m:
        return None
    return f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}+00:00"


def _codex_file_sid(p: Path) -> str | None:
    """The logical session id a rollout file belongs to — session_meta sits in the
    first lines; resumes/forks carry the PARENT id here while the filename has
    their own. Reads at most 3 lines (population counting must stay cheap)."""
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 2:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "session_meta":
                    pay = rec.get("payload") or {}
                    return pay.get("session_id") or pay.get("id")
    except OSError:
        pass
    return None


def _index_codex(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    # Resumed/forked codex sessions write a NEW rollout file carrying the PARENT
    # session_meta.session_id (observed live 2026-08-06: one logical session across
    # 9 files). A logical session is the session_id GROUP — aggregate, never drop.
    #
    # Phase 1 groups EVERY in-window file by session id via a 3-line header read,
    # so total_in_window and the capsule-churn metric cover the whole window;
    # phase 2 full-scans only the kept N groups (bounded I/O).
    file_groups: dict[str, list[tuple[float, Path]]] = {}
    for root in _codex_roots(mod):
        for p in root.rglob("rollout-*.jsonl"):
            mt = _mtime(p)
            if mt is None or mt < window_start:
                continue
            sid = _codex_file_sid(p) or p.stem
            file_groups.setdefault(sid, []).append((mt.timestamp(), p))
    churn_counts = [len(files) for files in file_groups.values()]
    capsule_churn = {
        "files_total": sum(churn_counts),
        "logical_sessions": len(churn_counts),
        "mean_files_per_session": round(sum(churn_counts) / len(churn_counts), 2) if churn_counts else 0.0,
        "max_files_in_one_session": max(churn_counts, default=0),
    }
    candidates: list[tuple[float, str]] = [(max(mts for mts, _ in files), sid) for sid, files in file_groups.items()]
    kept_sids, total, _capped = _rank(candidates, max_sessions)
    sessions = []
    for sid in kept_sids:
        g = {"started": None, "ended": "", "cwd": None, "u": 0, "a": 0, "t": 0, "models": set(), "size": 0}
        for mts, p in sorted(file_groups[sid]):
            try:
                scan = _codex_scan_file(p)
                size = p.stat().st_size
            except OSError:
                continue
            started = _codex_started_at(p)
            ended = _iso(datetime.fromtimestamp(mts, tz=timezone.utc))
            g["u"] += scan["u"]
            g["a"] += scan["a"]
            g["t"] += scan["t"]
            g["models"] |= scan["models"]
            g["size"] += size
            g["cwd"] = g["cwd"] or scan["cwd"]
            if started and (g["started"] is None or started < g["started"]):
                g["started"] = started
            if ended > g["ended"]:
                g["ended"] = ended
        sessions.append(
            _mk(
                sid,
                g["started"],
                g["ended"] or None,
                g["cwd"],
                g["u"],
                g["a"],
                g["t"],
                g["models"],
                g["size"],
                extra={"rollout_files": len(file_groups[sid])},
            )
        )
    return IndexResult(
        sessions,
        total,
        "newest rollout-file mtime per logical session",
        extra={"capsule_churn": capsule_churn, "population_count_method": "rollout header scan (3 lines/file)"},
    )


def _codex_session_files(mod, sid: str) -> list[Path]:
    """All rollout files of a logical session, oldest first (resumes share the
    parent session_id in session_meta, but each file's NAME carries its own id —
    so match on the session_meta field, falling back to the filename)."""
    matches: list[Path] = []
    for root in _codex_roots(mod):
        for p in root.rglob("rollout-*.jsonl"):
            if sid in p.name:
                matches.append(p)
                continue
            try:
                with p.open(encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        if i > 2:
                            break
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("type") == "session_meta":
                            pay = rec.get("payload") or {}
                            if sid in (pay.get("session_id"), pay.get("id")):
                                matches.append(p)
                            break
            except OSError:
                continue
    return sorted(matches, key=lambda p: p.name)


def _cat_codex(mod, sid: str, max_chars: int) -> str | None:
    files = _codex_session_files(mod, sid)
    if not files:
        return None
    out: list[str] = []
    total = 0
    for match in files:
        if total >= max_chars:
            break
        if len(files) > 1:
            out.append(f"===== rollout file: {match.name} =====\n")
        with match.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "response_item":
                    continue
                payload = rec.get("payload") or {}
                pt = payload.get("type")
                chunk = None
                if pt == "message":
                    texts = []
                    for blk in payload.get("content") or []:
                        if isinstance(blk, dict) and isinstance(blk.get("text"), str):
                            texts.append(blk["text"])
                    if texts:
                        chunk = f"--- {payload.get('role')} ---\n" + "\n".join(texts) + "\n"
                elif pt == "function_call":
                    chunk = f"[tool: {payload.get('name')}]\n"
                if chunk:
                    out.append(chunk)
                    total += len(chunk)
                    if total >= max_chars:
                        out.append("[... truncated at max-chars ...]\n")
                        break
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: copilot — ~/.copilot/session-state/<sid>/ is authoritative:
# workspace.yaml (flat metadata) + events.jsonl (transcript; absent on stub
# sessions). The top-level session-store.db is a thin cache — not used here.
# ---------------------------------------------------------------------------


def _flat_yaml(path: Path) -> dict:
    """Parse a flat key: value YAML file without a YAML dependency."""
    d: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line.startswith("#") or line[0] in " \t" or ":" not in line:
                continue
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return d


def _copilot_root(mod) -> Path | None:
    meta = mod.VENDOR_REGISTRY["copilot"]
    root = meta.get("session_state_root")
    if root is None:
        return None
    root = Path(root)
    return root if root.is_dir() else None


def _index_copilot(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    root = _copilot_root(mod)
    if root is None:
        return IndexResult([], 0, "absent", notes=["copilot session-state root not found"])
    candidates: list[tuple[float, tuple[Path, dict]]] = []
    for sdir in root.iterdir():
        ws = sdir / "workspace.yaml"
        if not sdir.is_dir() or not ws.exists():
            continue
        meta = _flat_yaml(ws)
        updated = meta.get("updated_at") or ""
        try:
            upd_dt = datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else _mtime(sdir)
        except ValueError:
            upd_dt = _mtime(sdir)
        if upd_dt is None or upd_dt < window_start:
            continue
        candidates.append((upd_dt.timestamp(), (sdir, meta)))
    kept, total, _capped = _rank(candidates, max_sessions)
    sessions = []
    for sdir, meta in kept:
        u = a = t = 0
        models: set[str] = set()
        events = sdir / "events.jsonl"
        size = 0
        if events.exists():
            size = events.stat().st_size
            try:
                with events.open(encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        typ = rec.get("type")
                        data = rec.get("data") or {}
                        if typ == "user.message":
                            u += 1
                        elif typ == "assistant.message":
                            a += 1
                            if isinstance(data.get("model"), str):
                                models.add(data["model"])
                        elif typ == "tool.execution_start":
                            t += 1
                        elif typ == "session.start" and isinstance(data.get("model"), str):
                            models.add(data["model"])
            except OSError:
                pass
        sessions.append(
            _mk(
                meta.get("id") or sdir.name,
                meta.get("created_at"),
                meta.get("updated_at"),
                meta.get("cwd"),
                u,
                a,
                t,
                models,
                size,
            )
        )
    return IndexResult(sessions, total, "workspace.yaml updated_at (dir mtime fallback)")


def _cat_copilot(mod, sid: str, max_chars: int) -> str | None:
    root = _copilot_root(mod)
    if root is None:
        return None
    events = root / sid / "events.jsonl"
    if not events.exists():
        # Stub sessions have metadata but no transcript — report that honestly.
        if (root / sid / "workspace.yaml").exists():
            return "[stub session: workspace.yaml exists but no events.jsonl transcript]\n"
        return None
    out: list[str] = []
    total = 0
    with events.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            typ = rec.get("type")
            data = rec.get("data") or {}
            chunk = None
            if typ == "user.message":
                chunk = f"--- user ({(rec.get('timestamp') or '')[:19]}) ---\n{data.get('content') or ''}\n"
            elif typ == "assistant.message":
                body = data.get("content") or ""
                tools = "".join(
                    f"[tool: {tr.get('name')}]\n" for tr in data.get("toolRequests") or [] if isinstance(tr, dict)
                )
                chunk = f"--- assistant ({(rec.get('timestamp') or '')[:19]}) ---\n{body}\n{tools}"
            if chunk:
                out.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    out.append("[... truncated at max-chars ...]\n")
                    break
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: opencode — opencode.db: session (id, directory, title, model JSON,
# time_created/updated in EPOCH MS), message (data JSON: role), part (data
# JSON: type text|reasoning|tool|...). Tool parts are upserted in place, so
# counting part rows does not double-count status transitions.
# ---------------------------------------------------------------------------


def _index_opencode(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    db = Path(mod.VENDOR_REGISTRY["opencode"]["path"])
    if not db.exists():
        return IndexResult([], 0, "absent", notes=["opencode.db not found"])
    window_ms = int(window_start.timestamp() * 1000)
    sessions = []
    total = 0
    try:
        con = _ro_connect(db)
        cur = con.cursor()
        # A session created before the window but still active inside it is in-window:
        # filter on the LATER of created/updated, order by last activity.
        where = "MAX(COALESCE(time_created, 0), COALESCE(time_updated, 0)) >= ?"
        cur.execute(f"SELECT COUNT(*) FROM session WHERE {where}", (window_ms,))
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT id, directory, title, model, time_created, time_updated FROM session "
            f"WHERE {where} ORDER BY COALESCE(time_updated, time_created) DESC LIMIT ?",
            (window_ms, max_sessions),
        )
        rows = cur.fetchall()
        for row in rows:
            sid = row["id"]
            cur.execute(
                "SELECT COUNT(*) FROM message WHERE session_id = ? AND json_extract(data, '$.role') = 'user'",
                (sid,),
            )
            u = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM message WHERE session_id = ? AND json_extract(data, '$.role') = 'assistant'",
                (sid,),
            )
            a = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM part WHERE session_id = ? AND json_extract(data, '$.type') = 'tool'",
                (sid,),
            )
            t = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COALESCE(SUM(LENGTH(data)), 0) FROM part WHERE session_id = ?", (sid,))
            size = int(cur.fetchone()[0] or 0)
            model = None
            try:
                mj = json.loads(row["model"]) if row["model"] else {}
                model = mj.get("modelID")
            except (json.JSONDecodeError, TypeError):
                pass
            started = _iso(datetime.fromtimestamp((row["time_created"] or 0) / 1000, tz=timezone.utc))
            ended = _iso(datetime.fromtimestamp((row["time_updated"] or 0) / 1000, tz=timezone.utc))
            sessions.append(_mk(sid, started, ended, row["directory"], u, a, t, [model] if model else [], size))
        con.close()
    except sqlite3.Error as e:
        print(f"WARN: opencode sqlite error: {type(e).__name__}", file=sys.stderr)
    return IndexResult(sessions, total, "time_updated (time_created fallback)")


def _cat_opencode(mod, sid: str, max_chars: int) -> str | None:
    db = Path(mod.VENDOR_REGISTRY["opencode"]["path"])
    if not db.exists():
        return None
    out: list[str] = []
    total = 0
    try:
        con = _ro_connect(db)
        cur = con.cursor()
        cur.execute("SELECT id, data FROM message WHERE session_id = ? ORDER BY time_created", (sid,))
        messages = cur.fetchall()
        if not messages:
            con.close()
            return None
        for mrow in messages:
            try:
                mdata = json.loads(mrow["data"])
            except (json.JSONDecodeError, TypeError):
                mdata = {}
            role = mdata.get("role") or "?"
            cur.execute("SELECT data FROM part WHERE message_id = ? ORDER BY time_created", (mrow["id"],))
            texts = []
            for prow in cur.fetchall():
                try:
                    pdata = json.loads(prow["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                ptype = pdata.get("type")
                if ptype in ("text", "reasoning") and isinstance(pdata.get("text"), str):
                    texts.append(pdata["text"])
                elif ptype == "tool":
                    texts.append(f"[tool: {pdata.get('tool')}]")
            if not texts:
                continue
            chunk = f"--- {role} ---\n" + "\n".join(texts) + "\n"
            out.append(chunk)
            total += len(chunk)
            if total >= max_chars:
                out.append("[... truncated at max-chars ...]\n")
                break
        con.close()
    except sqlite3.Error:
        return None
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: antigravity (agy) — conversations/<uuid>.db (steps table; protobuf
# blobs, printable-ASCII scrape only) + history.jsonl (clean user-prompt spine:
# display, timestamp ms, workspace, conversationId). Older conversation DBs
# rotate away while history.jsonl remembers — counts state this honestly.
# step_type map (empirical, NOT authoritative): 14=task init, 15=assistant
# turn wrapper, 132=send_message (outward assistant msg), 5/17/8/9/25/7=tool
# results. Unknown types are counted as tool-ish steps, never dropped silently.
# ---------------------------------------------------------------------------

_AGY_TOOL_TYPES = {
    5: "write_to_file",
    17: "write_to_file",
    8: "view_file",
    9: "list_dir",
    25: "find_by_name",
    7: "grep_search",
}


def _agy_root(mod) -> Path:
    return Path(mod.VENDOR_REGISTRY["antigravity"]["path"])


# Structural columns ONLY — title/preview are conversation CONTENT and never
# leave the store through this organ (PII firewall, mechanically tested).
_AGY_SUMMARY_SQL = (
    "SELECT conversation_id, step_count, last_modified_time, workspace_uris, "
    "killed, not_fully_idle, parent_conversation_id, nesting_depth, "
    "last_user_input_time, last_user_input_step_index FROM conversation_summaries"
)

# The store writes literal year-1 datetimes where it has no value; treating the
# sentinel as a timestamp would rank real work below everything ever recorded.
_AGY_ZERO_TIME = "0001-01-01"


def _agy_parse_time(val) -> datetime | None:
    if not isinstance(val, str) or val.startswith(_AGY_ZERO_TIME):
        return None
    try:
        dt = datetime.fromisoformat(val)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _agy_summaries(mod) -> tuple[dict[str, dict], list[str]]:
    """conversation_id -> structural summary row (no content columns)."""
    db = _agy_root(mod) / "conversation_summaries.db"
    if not db.exists():
        return {}, ["conversation_summaries.db absent"]
    rows: dict[str, dict] = {}
    try:
        con = _ro_connect(db)
        cur = con.cursor()
        cur.execute(_AGY_SUMMARY_SQL)
        for r in cur.fetchall():
            rows[r["conversation_id"]] = dict(r)
        con.close()
    except sqlite3.Error as e:
        return {}, [f"conversation_summaries.db unreadable ({type(e).__name__})"]
    return rows, []


def _agy_history(mod) -> dict[str, dict]:
    """conversationId -> {count, first_ts, last_ts, workspace} from history.jsonl."""
    hist: dict[str, dict] = {}
    hp = _agy_root(mod) / "history.jsonl"
    if not hp.exists():
        return hist
    try:
        for line in hp.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = rec.get("conversationId")
            if not cid:
                continue
            ts = rec.get("timestamp")
            iso = _iso(datetime.fromtimestamp(ts / 1000, tz=timezone.utc)) if isinstance(ts, (int, float)) else None
            slot = hist.setdefault(
                cid, {"count": 0, "first_ts": iso, "last_ts": iso, "workspace": rec.get("workspace")}
            )
            slot["count"] += 1
            if iso:
                slot["first_ts"] = slot["first_ts"] or iso
                slot["last_ts"] = iso
    except OSError:
        pass
    return hist


def _index_antigravity(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    # Three sources describe this estate, and they are nearly DISJOINT (measured
    # 2026-08-06: 506 summary rows, 129 conversation DBs, overlap 5 — blobs prune
    # ~10 days out while summaries persist; history.jsonl remembers longest). The
    # universe is their UNION keyed by conversation_id; each record carries its
    # provenance, and only the kept N ever open a blob DB (bounded I/O).
    summaries, notes = _agy_summaries(mod)
    conv_dir = _agy_root(mod) / "conversations"
    blobs: dict[str, Path] = {p.stem: p for p in conv_dir.glob("*.db")} if conv_dir.is_dir() else {}
    hist = _agy_history(mod)

    candidates: list[tuple[float, str]] = []
    order_keys: dict[str, str] = {}
    for cid in set(summaries) | set(blobs) | set(hist):
        dt = _agy_parse_time((summaries.get(cid) or {}).get("last_modified_time"))
        key = "summaries.last_modified_time"
        if dt is None and cid in blobs:
            dt = _mtime(blobs[cid])
            key = "conversation .db mtime"
        if dt is None:
            key = "history.jsonl last_ts"
            last_ts = (hist.get(cid) or {}).get("last_ts")
            if last_ts:
                try:
                    dt = datetime.fromisoformat(last_ts)
                except ValueError:
                    dt = None
        if dt is None or dt < window_start:
            continue
        candidates.append((dt.timestamp(), cid))
        order_keys[cid] = key

    kept, total, _capped = _rank(candidates, max_sessions)
    coverage: dict[str, int] = {}
    for cid in kept:
        coverage[order_keys[cid]] = coverage.get(order_keys[cid], 0) + 1

    sessions = []
    for cid in kept:
        srow = summaries.get(cid)
        blob = blobs.get(cid)
        h = hist.get(cid, {})
        total_steps = t132 = t14 = size = 0
        if blob is not None:
            try:
                size = blob.stat().st_size
                con = _ro_connect(blob)
                cur = con.cursor()
                cur.execute("SELECT COUNT(*) FROM steps")
                total_steps = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT COUNT(*) FROM steps WHERE step_type = 132")
                t132 = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT COUNT(*) FROM steps WHERE step_type = 14")
                t14 = int(cur.fetchone()[0] or 0)
                con.close()
            except sqlite3.Error:
                blob = None
        step_count = int((srow or {}).get("step_count") or 0) or total_steps
        cwd = h.get("workspace")
        if cwd is None and srow and srow.get("workspace_uris"):
            try:
                uris = json.loads(srow["workspace_uris"])
                if isinstance(uris, list) and uris and isinstance(uris[0], str):
                    cwd = uris[0].removeprefix("file://")
            except json.JSONDecodeError:
                pass
        ended_dt = _agy_parse_time((srow or {}).get("last_modified_time")) or (_mtime(blob) if blob else None)
        ended = _iso(ended_dt) if ended_dt else h.get("last_ts")
        provenance = [
            s
            for s, present in (("summaries", srow is not None), ("blob", blob is not None), ("history", cid in hist))
            if present
        ]
        # user turns come from history.jsonl (the only clean per-message source);
        # assistant msgs = send_message steps; everything else ≈ tool machinery.
        sessions.append(
            _mk(
                cid,
                h.get("first_ts"),
                ended,
                cwd,
                h.get("count", 0),
                t132,
                max(0, total_steps - t132 - t14),
                [],
                size,
                extra={
                    "step_count": step_count,
                    "sources": provenance,
                    "content_depth": "blob" if blob is not None else "summary_only",
                },
            )
        )
    if summaries:
        pruned = len(set(summaries) - set(blobs))
        notes.append(f"{pruned} of {len(summaries)} summarized conversations have no local blob store (pruned)")
    return IndexResult(
        sessions,
        total,
        "summaries.last_modified_time → blob mtime → history last_ts",
        notes=notes,
        sources={
            "summaries_db": len(summaries),
            "conversation_dbs": len(blobs),
            "history_jsonl": len(hist),
            "union": len(set(summaries) | set(blobs) | set(hist)),
        },
        extra={"order_key_coverage": coverage},
    )


def _agy_scrape_blob(blob: bytes, keys: tuple[str, ...]) -> str | None:
    """Best-effort extraction of a JSON value from a protobuf blob via printable runs."""
    for run in re.findall(rb"[ -~]{6,}", blob or b""):
        text = run.decode("ascii", errors="replace")
        start = text.find("{")
        if start < 0:
            continue
        try:
            obj = json.loads(text[start:])
        except json.JSONDecodeError:
            continue
        for k in keys:
            if isinstance(obj.get(k), str):
                return obj[k]
    return None


def _cat_antigravity(mod, sid: str, max_chars: int) -> str | None:
    db = _agy_root(mod) / "conversations" / f"{sid}.db"
    if not db.exists():
        # The blob store prunes ~10 days out; a summaries row proves the session
        # existed. Report the structural facts honestly — never invent content,
        # and never surface the summaries' title/preview (content columns).
        summaries, _ = _agy_summaries(mod)
        srow = summaries.get(sid)
        if srow is None:
            return None
        ws = ""
        try:
            uris = json.loads(srow.get("workspace_uris") or "[]")
            if isinstance(uris, list) and uris and isinstance(uris[0], str):
                ws = uris[0].removeprefix("file://")
        except json.JSONDecodeError:
            pass
        lines = [
            f"[antigravity conversation {sid}: blob store pruned — content not locally readable]\n",
            f"[structural facts: step_count={srow.get('step_count')}, "
            f"last_modified={srow.get('last_modified_time')}, workspace={ws or '?'}]\n",
            "[Antigravity retains conversation blobs ~10 days; the summaries DB persists structure only.]\n",
        ]
        hist = _agy_history(mod)
        h = hist.get(sid)
        if h:
            lines.append(f"[history.jsonl: {h['count']} user prompts, {h.get('first_ts')} → {h.get('last_ts')}]\n")
        return "".join(lines)
    hist = _agy_history(mod)
    out: list[str] = []
    h = hist.get(sid)
    if h:
        out.append(f"[history.jsonl: {h['count']} user prompts, {h.get('first_ts')} → {h.get('last_ts')}]\n")
    # Verbatim user prompts for this conversation, from the clean spine.
    hp = _agy_root(mod) / "history.jsonl"
    if hp.exists():
        try:
            for line in hp.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("conversationId") == sid and isinstance(rec.get("display"), str):
                    out.append(f"--- user ---\n{rec['display']}\n")
        except OSError:
            pass
    total = sum(len(c) for c in out)
    try:
        con = _ro_connect(db)
        cur = con.cursor()
        cur.execute("SELECT idx, step_type, step_payload FROM steps ORDER BY idx")
        for row in cur.fetchall():
            st = row["step_type"]
            chunk = None
            if st == 132:
                msg = _agy_scrape_blob(row["step_payload"], ("Message",))
                if msg:
                    chunk = f"--- assistant (send_message) ---\n{msg}\n"
            elif st in _AGY_TOOL_TYPES:
                chunk = f"[tool: {_AGY_TOOL_TYPES[st]}]\n"
            if chunk:
                out.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    out.append("[... truncated at max-chars ...]\n")
                    break
        con.close()
    except sqlite3.Error:
        pass
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: gemini — ~/.gemini/tmp/<slug>/chats/session-*.jsonl (header line +
# message lines, type user|gemini). cwd from the sibling .project_root file.
# ---------------------------------------------------------------------------


def _index_gemini(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    root = Path(mod.VENDOR_REGISTRY["gemini"]["path"])
    if not root.is_dir():
        return IndexResult([], 0, "absent", notes=["gemini tmp root not found"])
    candidates = []
    for p in root.glob("*/chats/session-*.jsonl"):
        mt = _mtime(p)
        if mt is not None and mt >= window_start:
            candidates.append((mt.timestamp(), p))
    kept, total, _capped = _rank(candidates, max_sessions)
    sessions = []
    for p in kept:
        mts = (_mtime(p) or _now()).timestamp()
        sid = started = ended = None
        u = g = t = 0
        models: set[str] = set()
        try:
            with p.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if sid is None and rec.get("sessionId"):
                        sid = rec.get("sessionId")
                        started = rec.get("startTime")
                        ended = rec.get("lastUpdated")
                        continue
                    typ = rec.get("type")
                    if typ == "user":
                        u += 1
                    elif typ == "gemini":
                        g += 1
                        if isinstance(rec.get("model"), str):
                            models.add(rec["model"])
                        t += len(rec.get("toolCalls") or [])
        except OSError:
            continue
        cwd = None
        pr = p.parent.parent / ".project_root"
        if pr.exists():
            try:
                cwd = pr.read_text(encoding="utf-8").strip() or None
            except OSError:
                pass
        ended = ended or _iso(datetime.fromtimestamp(mts, tz=timezone.utc))
        sessions.append(_mk(sid or p.stem, started, ended, cwd, u, g, t, models, p.stat().st_size))
    return IndexResult(
        sessions,
        total,
        "file mtime",
        notes=[
            "gemini's store logs user prompts; assistant replies are frequently not captured — "
            "treat zero assistant_msgs as a store limitation, not silence"
        ],
    )


def _cat_gemini(mod, sid: str, max_chars: int) -> str | None:
    root = Path(mod.VENDOR_REGISTRY["gemini"]["path"])
    if not root.is_dir():
        return None
    match = None
    for p in root.glob("*/chats/session-*.jsonl"):
        if sid in p.name:
            match = p
            break
    if match is None:
        # Fall back to matching the header's sessionId.
        for p in root.glob("*/chats/session-*.jsonl"):
            try:
                with p.open(encoding="utf-8", errors="replace") as fh:
                    first = fh.readline()
                if json.loads(first).get("sessionId") == sid:
                    match = p
                    break
            except (OSError, json.JSONDecodeError):
                continue
    if match is None:
        return None
    out: list[str] = []
    total = 0
    with match.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            typ = rec.get("type")
            chunk = None
            if typ == "user":
                texts = [b.get("text") or "" for b in rec.get("content") or [] if isinstance(b, dict)]
                if texts:
                    chunk = "--- user ---\n" + "\n".join(texts) + "\n"
            elif typ == "gemini":
                body = rec.get("content") if isinstance(rec.get("content"), str) else ""
                tools = "".join(
                    f"[tool: {tc.get('name')}]\n" for tc in rec.get("toolCalls") or [] if isinstance(tc, dict)
                )
                if body or tools:
                    chunk = f"--- gemini ---\n{body}\n{tools}"
            if chunk:
                out.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    out.append("[... truncated at max-chars ...]\n")
                    break
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: claude-desktop — plan-usage-history.json spine + session-dir counts.
# Conversation content is a server-side mirror (Local Storage LevelDB /
# IndexedDB) that this organ NEVER parses — enforced by sentinel test.
# ---------------------------------------------------------------------------


def _index_claude_desktop(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    meta = mod.VENDOR_REGISTRY["claude-desktop"]
    root = Path(meta["path"])
    if not root.is_dir():
        return IndexResult([], 0, "absent", notes=["Claude Desktop estate not found"])

    candidates: list[tuple[float, tuple[str, Path]]] = []
    for store in meta.get("session_dirs", []):
        d = root / store
        if not d.is_dir():
            continue
        for child in d.iterdir():
            if not child.is_dir():
                continue
            mt = _mtime(child)
            if mt is not None and mt >= window_start:
                candidates.append((mt.timestamp(), (store, child)))
    kept, total, _capped = _rank(candidates, max_sessions)

    sessions = []
    for store, child in kept:
        mt = _mtime(child)
        size = 0
        try:
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
        except OSError:
            pass
        sessions.append(
            _mk(child.name, None, _iso(mt) if mt else None, None, 0, 0, 0, [], size, extra={"store": store})
        )

    plan_usage: dict = {
        "samples_in_window": 0,
        "peak_five_hour_pct": 0,
        "peak_seven_day_pct": 0,
        "saturated_samples": 0,
    }
    usage_path = root / "plan-usage-history.json"
    if usage_path.is_file():
        try:
            doc = json.loads(usage_path.read_text(encoding="utf-8"))
            cutoff_ms = window_start.timestamp() * 1000
            for sample in doc.get("samples") or []:
                if not isinstance(sample, dict) or sample.get("t", 0) < cutoff_ms:
                    continue
                plan_usage["samples_in_window"] += 1
                u = sample.get("u") or {}
                fh = int(u.get("fh") or 0)
                sd = int(u.get("sd") or 0)
                plan_usage["peak_five_hour_pct"] = max(plan_usage["peak_five_hour_pct"], fh)
                plan_usage["peak_seven_day_pct"] = max(plan_usage["peak_seven_day_pct"], sd)
                if fh >= 90 or sd >= 90:
                    plan_usage["saturated_samples"] += 1
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    return IndexResult(
        sessions,
        total,
        "session-dir mtime",
        notes=[
            "Conversation content is a server-side mirror (LevelDB) this organ never parses — "
            "zero message counts are the store contract, not silence",
            "plan-usage spine summarized in meta.plan_usage (five-hour/seven-day utilization %)",
        ],
        extra={"plan_usage": plan_usage},
    )


def _cat_claude_desktop(mod, sid: str, max_chars: int) -> str | None:
    meta = mod.VENDOR_REGISTRY["claude-desktop"]
    root = Path(meta["path"])
    for store in meta.get("session_dirs", []):
        child = root / store / sid
        if child.is_dir():
            lines = [f"[claude-desktop session dir: {store}/{sid}]"]
            for f in sorted(child.rglob("*")):
                if f.is_file():
                    try:
                        st = f.stat()
                    except OSError:
                        continue
                    rel = f.relative_to(child)
                    lines.append(f"  {rel}  {st.st_size}B  mtime {_iso(_mtime(f))}")
            lines.append(
                "[conversation content lives in a server-side mirror (Local Storage LevelDB) "
                "that this organ never parses — structural listing only]"
            )
            return "\n".join(lines)[:max_chars] + "\n"
    return None


# ---------------------------------------------------------------------------
# Adapter: chatgpt-desktop — opaque .data payloads; counts/sizes/mtimes ONLY.
# The payload bytes are never read — enforced by sentinel test.
# ---------------------------------------------------------------------------


def _index_chatgpt_desktop(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    root = Path(mod.VENDOR_REGISTRY["chatgpt-desktop"]["path"])
    if not root.is_dir():
        return IndexResult([], 0, "absent", notes=["ChatGPT.app estate not found"])

    candidates: list[tuple[float, Path]] = []
    for conv_dir in root.glob("conversations-v3-*"):
        if not conv_dir.is_dir():
            continue
        for p in conv_dir.glob("*.data"):
            mt = _mtime(p)
            if mt is not None and mt >= window_start:
                candidates.append((mt.timestamp(), p))
    kept, total, _capped = _rank(candidates, max_sessions)

    sessions = []
    for p in kept:
        mt = _mtime(p)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        sessions.append(_mk(p.stem, None, _iso(mt) if mt else None, None, 0, 0, 0, [], size))
    return IndexResult(
        sessions,
        total,
        "payload-file mtime",
        notes=[
            "Payloads are opaque .data blobs this organ never reads — "
            "zero message counts are the store contract, not silence"
        ],
    )


def _cat_chatgpt_desktop(mod, sid: str, max_chars: int) -> str | None:
    root = Path(mod.VENDOR_REGISTRY["chatgpt-desktop"]["path"])
    if not root.is_dir():
        return None
    for conv_dir in root.glob("conversations-v3-*"):
        p = conv_dir / f"{sid}.data"
        if p.is_file():
            try:
                st = p.stat()
            except OSError:
                return None
            return (
                f"[chatgpt-desktop conversation {sid}]\n"
                f"  payload: {st.st_size}B, mtime {_iso(_mtime(p))}\n"
                "[payload is an opaque .data blob this organ never reads — structural facts only]\n"
            )
    return None


# ---------------------------------------------------------------------------
# Adapter: vscode-copilot-chat (×2 variants) — chatSessions/<sid>.jsonl v3
# delta logs: line 0 is {"kind": 0, "v": {version: 3, sessionId, creationDate,
# requests, ...}}; later lines are patches, counted but never replayed.
# version != 3 degrades to counts-only.
# ---------------------------------------------------------------------------


def _vscode_snapshot(p: Path) -> tuple[dict | None, int]:
    """(v3 snapshot dict or None, patch-line count) for one delta-log file."""
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
            patches = sum(1 for _ in fh)
        head = json.loads(first)
    except (OSError, json.JSONDecodeError):
        return None, 0
    snapshot = head.get("v") if isinstance(head, dict) else None
    if isinstance(snapshot, dict) and snapshot.get("version") == 3:
        return snapshot, patches
    return None, patches


def _index_vscode_chat(mod, window_start: datetime, max_sessions: int, vendor_key: str) -> IndexResult:
    meta = mod.VENDOR_REGISTRY[vendor_key]
    root = Path(meta["path"])
    if not root.is_dir():
        return IndexResult([], 0, "absent", notes=[f"workspaceStorage not found ({meta.get('variant')})"])

    candidates: list[tuple[float, Path]] = []
    for p in root.glob("*/chatSessions/*.jsonl"):
        mt = _mtime(p)
        if mt is not None and mt >= window_start:
            candidates.append((mt.timestamp(), p))
    kept, total, _capped = _rank(candidates, max_sessions)

    sessions = []
    unreadable = 0
    for p in kept:
        mt = _mtime(p)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        snapshot, patches = _vscode_snapshot(p)
        if snapshot is None:
            unreadable += 1
            sessions.append(
                _mk(p.stem, None, _iso(mt) if mt else None, None, 0, 0, 0, [], size, extra={"snapshot": "unreadable"})
            )
            continue
        created = snapshot.get("creationDate")
        if isinstance(created, (int, float)):
            started = _iso(datetime.fromtimestamp(created / 1000, tz=timezone.utc))
        else:
            started = created if isinstance(created, str) else None
        requests = snapshot.get("requests") if isinstance(snapshot.get("requests"), list) else []
        answered = sum(1 for r in requests if isinstance(r, dict) and r.get("response"))
        sessions.append(
            _mk(
                snapshot.get("sessionId") or p.stem,
                started,
                _iso(mt) if mt else None,
                None,
                len(requests),
                answered,
                0,
                [],
                size,
                extra={"patch_lines": patches, "workspace_hash": p.parent.parent.name},
            )
        )
    notes = [
        "v3 delta log: message counts come from the line-0 snapshot only; "
        "patch lines are counted (extra.patch_lines) but never replayed"
    ]
    if unreadable:
        notes.append(f"{unreadable} of {len(kept)} kept sessions not v3-snapshot-readable — counts-only records")
    return IndexResult(sessions, total, "delta-log file mtime", notes=notes)


def _collect_text(node, out: list[str]) -> None:
    """Best-effort text harvest from an undocumented snapshot subtree: every
    string under a key named 'text' — nothing else is assumed about the shape."""
    if isinstance(node, dict):
        for k, val in node.items():
            if k == "text" and isinstance(val, str) and val.strip():
                out.append(val)
            else:
                _collect_text(val, out)
    elif isinstance(node, list):
        for item in node:
            _collect_text(item, out)


def _cat_vscode_chat(mod, sid: str, max_chars: int, vendor_key: str) -> str | None:
    root = Path(mod.VENDOR_REGISTRY[vendor_key]["path"])
    if not root.is_dir():
        return None
    match = None
    for p in root.glob("*/chatSessions/*.jsonl"):
        if sid in p.name:
            match = p
            break
        snapshot, _ = _vscode_snapshot(p)
        if snapshot and snapshot.get("sessionId") == sid:
            match = p
            break
    if match is None:
        return None
    snapshot, patches = _vscode_snapshot(match)
    if snapshot is None:
        try:
            size = match.stat().st_size
        except OSError:
            size = 0
        return (
            f"[vscode-copilot-chat session {sid}: snapshot not v3-readable — "
            f"{size}B, {patches} patch lines, content not extracted]\n"
        )
    out: list[str] = []
    total = 0
    for i, req in enumerate(snapshot.get("requests") or []):
        if not isinstance(req, dict):
            continue
        texts: list[str] = []
        _collect_text(req.get("message"), texts)
        if texts:
            chunk = f"--- user (request {i}) ---\n" + "\n".join(texts) + "\n"
            out.append(chunk)
            total += len(chunk)
        texts = []
        _collect_text(req.get("response"), texts)
        if texts:
            chunk = f"--- assistant (request {i}) ---\n" + "\n".join(texts) + "\n"
            out.append(chunk)
            total += len(chunk)
        if total >= max_chars:
            out.append("[... truncated at max-chars ...]\n")
            break
    out.append(f"[{patches} patch lines not replayed — snapshot content only]\n")
    return "".join(out)


def _index_vscode_chat_stable(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    return _index_vscode_chat(mod, window_start, max_sessions, "vscode-copilot-chat")


def _index_vscode_chat_insiders(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    return _index_vscode_chat(mod, window_start, max_sessions, "vscode-copilot-chat-insiders")


def _cat_vscode_chat_stable(mod, sid: str, max_chars: int) -> str | None:
    return _cat_vscode_chat(mod, sid, max_chars, "vscode-copilot-chat")


def _cat_vscode_chat_insiders(mod, sid: str, max_chars: int) -> str | None:
    return _cat_vscode_chat(mod, sid, max_chars, "vscode-copilot-chat-insiders")


# ---------------------------------------------------------------------------
# Adapter: cline — state-only store, no transcripts exist. The zero message
# counts ARE the finding; cat lists state file names/sizes, never values.
# ---------------------------------------------------------------------------


def _index_cline(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    root = Path(mod.VENDOR_REGISTRY["cline"]["path"])
    workspaces = root / "workspaces"
    if not workspaces.is_dir():
        return IndexResult([], 0, "absent", notes=["cline workspaces directory not found"])

    candidates: list[tuple[float, Path]] = []
    for child in workspaces.iterdir():
        if not child.is_dir():
            continue
        mt = _mtime(child)
        if mt is not None and mt >= window_start:
            candidates.append((mt.timestamp(), child))
    kept, total, _capped = _rank(candidates, max_sessions)

    sessions = []
    for child in kept:
        mt = _mtime(child)
        size = 0
        try:
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
        except OSError:
            pass
        sessions.append(_mk(child.name, None, _iso(mt) if mt else None, None, 0, 0, 0, [], size))
    return IndexResult(
        sessions,
        total,
        "workspace-dir mtime",
        notes=[
            "state-only store: cline keeps workspace state, no transcripts — "
            "the zero message counts are the finding, not a coverage gap"
        ],
    )


def _cat_cline(mod, sid: str, max_chars: int) -> str | None:
    root = Path(mod.VENDOR_REGISTRY["cline"]["path"])
    child = root / "workspaces" / sid
    if not child.is_dir():
        return None
    lines = [f"[cline workspace state: {sid}]"]
    for f in sorted(child.rglob("*")):
        if f.is_file():
            try:
                st = f.stat()
            except OSError:
                continue
            lines.append(f"  {f.relative_to(child)}  {st.st_size}B  mtime {_iso(_mtime(f))}")
    lines.append("[state file VALUES are never echoed — names/sizes/mtimes only; no transcript exists]")
    return "\n".join(lines)[:max_chars] + "\n"


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

INDEXERS = {
    "claude": _index_claude,
    "codex": _index_codex,
    "copilot": _index_copilot,
    "opencode": _index_opencode,
    "antigravity": _index_antigravity,
    "gemini": _index_gemini,
    "claude-desktop": _index_claude_desktop,
    "chatgpt-desktop": _index_chatgpt_desktop,
    "vscode-copilot-chat": _index_vscode_chat_stable,
    "vscode-copilot-chat-insiders": _index_vscode_chat_insiders,
    "cline": _index_cline,
}

CATTERS = {
    "claude": _cat_claude,
    "codex": _cat_codex,
    "copilot": _cat_copilot,
    "opencode": _cat_opencode,
    "antigravity": _cat_antigravity,
    "gemini": _cat_gemini,
    "claude-desktop": _cat_claude_desktop,
    "chatgpt-desktop": _cat_chatgpt_desktop,
    "vscode-copilot-chat": _cat_vscode_chat_stable,
    "vscode-copilot-chat-insiders": _cat_vscode_chat_insiders,
    "cline": _cat_cline,
}

VENDOR_ALIASES = {"agy": "antigravity"}


# ---------------------------------------------------------------------------
# Facet aggregation + HTML renderer
# ---------------------------------------------------------------------------


def _as_count(v) -> int:
    """Tolerant facet-count coercion: a model-written facet must never crash the
    render (a goal_categories value arrived as descriptive prose, 2026-08-06).
    bools/ints/numeric strings count as themselves; other truthy values mean
    'present' (1); falsy/absent means 0."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return 1 if v.strip() else 0
    return 1 if v else 0


def _aggregate_facets(facets: list[dict]) -> dict:
    agg: dict = {
        "n_facets": len(facets),
        "outcomes": {},
        "session_types": {},
        "friction_counts": {},
        "satisfaction_counts": {},
        "goal_categories": {},
    }
    for f in facets:
        oc = f.get("outcome") or "unclear"
        agg["outcomes"][oc] = agg["outcomes"].get(oc, 0) + 1
        st = f.get("session_type") or "unknown"
        agg["session_types"][st] = agg["session_types"].get(st, 0) + 1
        for k, v in (f.get("friction_counts") or {}).items():
            agg["friction_counts"][k] = agg["friction_counts"].get(k, 0) + _as_count(v)
        for k, v in (f.get("user_satisfaction_counts") or {}).items():
            agg["satisfaction_counts"][k] = agg["satisfaction_counts"].get(k, 0) + _as_count(v)
        for k, v in (f.get("goal_categories") or {}).items():
            agg["goal_categories"][k] = agg["goal_categories"].get(k, 0) + _as_count(v)
    return agg


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _dl(d: dict) -> str:
    items = sorted(d.items(), key=lambda kv: -kv[1])
    rows = "".join(f"<tr><td>{_esc(k)}</td><td class='num'>{v}</td></tr>" for k, v in items)
    return rows or "<tr><td colspan='2'>—</td></tr>"


def _render_html(vendor: str, index: dict, facets: list[dict], narrative: dict) -> str:
    agg = _aggregate_facets(facets)
    sessions = index.get("sessions", [])
    n_sessions = len(sessions)
    tool_calls = sum(s.get("tool_calls", 0) for s in sessions)
    user_msgs = sum(s.get("user_msgs", 0) for s in sessions)
    models = sorted({m for s in sessions for m in s.get("models", [])})
    window = index.get("window", {})

    def sec(title: str, body: str) -> str:
        return f"<section><h2>{_esc(title)}</h2>{body}</section>"

    imeta = index.get("meta") or {}
    if imeta.get("capped"):
        indexed_phrase = (
            f"{imeta.get('shown', n_sessions)} of {imeta.get('total_in_window', '?')} in-window sessions indexed"
        )
    else:
        indexed_phrase = f"{n_sessions} sessions indexed"
    parts: list[str] = []
    parts.append(
        f"<header><h1>{_esc(vendor)} · usage insights</h1>"
        f"<p class='meta'>{_esc((window.get('start') or '?')[:10])} → {_esc((window.get('end') or '?')[:10])} · "
        f"{indexed_phrase} · {len(facets)} faceted · "
        f"{user_msgs} user messages · {tool_calls} tool calls · models: {_esc(', '.join(models) or '—')}</p></header>"
    )

    glance = narrative.get("at_a_glance") or {}
    if glance:
        rows = "".join(
            f"<div class='card'><h3>{_esc(t)}</h3><p>{_esc(glance[k])}</p></div>"
            for k, t in (
                ("whats_working", "What's working"),
                ("whats_hindering", "What's hindering"),
                ("quick_wins", "Quick wins"),
                ("ambitious_workflows", "On the horizon"),
            )
            if glance.get(k)
        )
        parts.append(sec("At a glance", f"<div class='cards'>{rows}</div>"))

    if narrative.get("tldr"):
        parts.append(sec("TL;DR", f"<p>{_esc(narrative['tldr'])}</p>"))

    areas = narrative.get("areas") or []
    if areas:
        body = "".join(
            f"<div class='area'><h3>{_esc(a.get('name'))} "
            f"<span class='count'>{_esc(a.get('session_count', '?'))} sessions</span></h3>"
            f"<p>{_esc(a.get('description'))}</p></div>"
            for a in areas
        )
        parts.append(sec("Project areas", body))

    parts.append(
        sec(
            "Facet aggregates (deterministic)",
            "<div class='tables'>"
            f"<table><caption>Outcomes</caption>{_dl(agg['outcomes'])}</table>"
            f"<table><caption>Friction</caption>{_dl(agg['friction_counts'])}</table>"
            f"<table><caption>Satisfaction</caption>{_dl(agg['satisfaction_counts'])}</table>"
            f"<table><caption>Goal categories</caption>{_dl(agg['goal_categories'])}</table>"
            "</div>",
        )
    )

    if narrative.get("interaction_style"):
        parts.append(sec("Interaction style", f"<p>{_esc(narrative['interaction_style'])}</p>"))

    friction = narrative.get("friction") or []
    if friction:
        body = "".join(
            f"<div class='area'><h3>{_esc(f.get('category'))}</h3><p>{_esc(f.get('description'))}</p>"
            + "".join(f"<p class='ex'>· {_esc(e)}</p>" for e in (f.get("examples") or []))
            + "</div>"
            for f in friction
        )
        parts.append(sec("Where things go wrong", body))

    suggestions = narrative.get("suggestions") or []
    if suggestions:
        body = "".join(
            f"<div class='area'><h3>{_esc(s.get('title'))}</h3><p>{_esc(s.get('detail'))}</p></div>"
            for s in suggestions
        )
        parts.append(sec("Suggestions", body))

    # No silent caps: name what was NOT covered.
    missing = [
        k
        for k in ("at_a_glance", "tldr", "areas", "interaction_style", "friction", "suggestions")
        if not narrative.get(k)
    ]
    unfaceted = n_sessions - len(facets)
    notes = list(narrative.get("coverage_notes") or [])
    if imeta.get("capped"):
        notes.append(
            f"Index cap: {imeta.get('shown')} of {imeta.get('total_in_window')} in-window sessions were "
            f"indexed (--max-sessions); those not shown are the OLDEST by {imeta.get('order_key')}."
        )
    for adapter_note in imeta.get("notes") or []:
        notes.append(f"Store note: {adapter_note}")
    churn = imeta.get("capsule_churn") or {}
    if churn.get("mean_files_per_session", 0) > 1.0:
        notes.append(
            f"Capsule churn: {churn['logical_sessions']} logical sessions span {churn['files_total']} rollout "
            f"files (mean {churn['mean_files_per_session']}, max {churn['max_files_in_one_session']} in one)."
        )
    if unfaceted > 0:
        notes.append(f"{unfaceted} of {n_sessions} indexed sessions were not faceted (sampling cap).")
    if missing:
        notes.append("Narrative sections absent: " + ", ".join(missing) + ".")
    if notes:
        parts.append(sec("Coverage notes", "".join(f"<p>{_esc(n)}</p>" for n in notes)))

    css = (
        ":root { color-scheme: light dark; }"
        "body { font: 15px/1.5 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;"
        " margin: 0 auto; max-width: 60rem; padding: 2rem 1.25rem; }"
        "header h1 { margin: 0 0 .25rem; font-size: 1.6rem; }"
        ".meta { color: #777; margin: 0 0 1.5rem; }"
        "section { margin: 1.75rem 0; }"
        "h2 { font-size: 1.15rem; border-bottom: 1px solid #8884; padding-bottom: .3rem; }"
        ".cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: .75rem; }"
        ".card { border: 1px solid #8883; border-radius: .5rem; padding: .75rem 1rem; }"
        ".card h3, .area h3 { margin: .1rem 0 .4rem; font-size: 1rem; }"
        ".count { color: #777; font-weight: normal; font-size: .85rem; }"
        ".ex { color: #777; margin: .15rem 0 .15rem .75rem; font-size: .9rem; }"
        ".tables { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: .75rem; }"
        "table { border-collapse: collapse; width: 100%; font-size: .9rem; }"
        "caption { text-align: left; font-weight: 600; margin-bottom: .25rem; }"
        "td { border-top: 1px solid #8883; padding: .2rem .4rem; }"
        "td.num { text-align: right; font-variant-numeric: tabular-nums; }"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_esc(vendor)} insights</title><style>{css}</style></head><body>"
        + "".join(parts)
        + f"<footer><p class='meta'>Generated {_iso()} by scripts/vendor-insights.py"
        " (mechanical half of /vendor-insights).</p></footer></body></html>"
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _resolve_vendor(name: str) -> str:
    return VENDOR_ALIASES.get(name, name)


def cmd_list(mod) -> int:
    for name, meta in sorted(mod.VENDOR_REGISTRY.items()):
        path = Path(meta["path"])
        live = "live" if path.exists() else "MISSING"
        dormant = " (dormant)" if meta.get("dormant") else ""
        supported = "indexable" if name in INDEXERS else "packet-only"
        print(f"{name:12} {live:8} {supported:12}{dormant}  {path}")
    return 0


def cmd_index_all(mod, window_days: int, max_sessions: int) -> int:
    """Refresh every lane's index, continuing past a failing lane (the beat's rung:
    one broken vendor store must not starve the other ten of fresh indexes)."""
    failures = []
    for vendor in sorted(INDEXERS):
        try:
            rc = cmd_index(mod, vendor, window_days, max_sessions)
        except Exception as exc:  # noqa: BLE001 — a lane failure is data, not a crash
            print(f"ERROR: index --all: '{vendor}' raised {type(exc).__name__}: {exc}", file=sys.stderr)
            rc = 1
        if rc != 0:
            failures.append(vendor)
    if failures:
        print(f"index --all: {len(failures)} lane(s) failed: {', '.join(failures)}", file=sys.stderr)
    return 1 if len(failures) == len(INDEXERS) else 0


def cmd_index(mod, vendor: str, window_days: int, max_sessions: int) -> int:
    vendor = _resolve_vendor(vendor)
    if vendor not in INDEXERS:
        print(f"ERROR: no indexer for vendor '{vendor}' (have: {', '.join(sorted(INDEXERS))})", file=sys.stderr)
        return 1
    window_start = _now() - timedelta(days=window_days)
    result = INDEXERS[vendor](mod, window_start, max_sessions)
    sessions = result.sessions
    sessions.sort(key=lambda s: s.get("started_at") or "", reverse=True)
    meta = {
        "total_in_window": result.total_in_window,
        "shown": len(sessions),
        "capped": result.total_in_window > len(sessions),
        "order_key": result.order_key,
        "notes": list(result.notes),
    }
    if result.sources:
        meta["population_sources"] = result.sources
    if result.extra:
        meta.update(result.extra)
    doc = {
        "vendor": vendor,
        "generated_at": _iso(),
        "window": {"start": _iso(window_start), "end": _iso(), "days": window_days},
        "max_sessions": max_sessions,
        "meta": meta,
        "sessions": sessions,
    }
    out = OUT_ROOT / vendor / "index.json"
    _atomic_write(out, json.dumps(doc, indent=2))
    capnote = f" (of {result.total_in_window} in-window — CAPPED)" if meta["capped"] else ""
    print(f"{out} — {len(sessions)} sessions{capnote}")
    return 0


def cmd_cat(mod, vendor: str, sid: str, max_chars: int) -> int:
    vendor = _resolve_vendor(vendor)
    if vendor not in CATTERS:
        print(f"ERROR: no session reader for vendor '{vendor}'", file=sys.stderr)
        return 1
    text = CATTERS[vendor](mod, sid, max_chars)
    if text is None:
        print(f"ERROR: session '{sid}' not found for vendor '{vendor}'", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


def cmd_render(vendor: str) -> int:
    vendor = _resolve_vendor(vendor)
    vdir = OUT_ROOT / vendor
    index_path = vdir / "index.json"
    if not index_path.exists():
        print(f"ERROR: {index_path} missing — run `index --vendor {vendor}` first", file=sys.stderr)
        return 2
    index = json.loads(index_path.read_text())
    facets = []
    facets_dir = vdir / "facets"
    if facets_dir.is_dir():
        for p in sorted(facets_dir.glob("*.json")):
            try:
                facets.append(json.loads(p.read_text()))
            except (OSError, json.JSONDecodeError):
                print(f"WARN: unreadable facet {p.name}", file=sys.stderr)
    narrative = {}
    npath = vdir / "narrative.json"
    if npath.exists():
        try:
            narrative = json.loads(npath.read_text())
        except (OSError, json.JSONDecodeError):
            print("WARN: narrative.json unreadable — rendering without narrative", file=sys.stderr)
    if not facets and not narrative:
        print(f"ERROR: no facets and no narrative under {vdir} — the skill half hasn't run", file=sys.stderr)
        return 2
    html_text = _render_html(vendor, index, facets, narrative)
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    out = vdir / f"report-{stamp}.html"
    _atomic_write(out, html_text)
    _atomic_write(vdir / "report.html", html_text)
    print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cross-vendor /insights mechanical half")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_idx = sub.add_parser("index")
    group = p_idx.add_mutually_exclusive_group(required=True)
    group.add_argument("--vendor")
    group.add_argument("--all", action="store_true", help="index every lane, continuing past a failing one")
    p_idx.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    p_idx.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    p_cat = sub.add_parser("cat-session")
    p_cat.add_argument("--vendor", required=True)
    p_cat.add_argument("--session", required=True)
    p_cat.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    p_r = sub.add_parser("render")
    p_r.add_argument("--vendor", required=True)
    args = ap.parse_args(argv)

    mod = _load_ingest_module()
    if args.cmd == "list":
        return cmd_list(mod)
    if args.cmd == "index":
        if args.all:
            return cmd_index_all(mod, args.window_days, args.max_sessions)
        return cmd_index(mod, args.vendor, args.window_days, args.max_sessions)
    if args.cmd == "cat-session":
        return cmd_cat(mod, args.vendor, args.session, args.max_chars)
    if args.cmd == "render":
        return cmd_render(args.vendor)
    return 1


if __name__ == "__main__":
    sys.exit(main())
