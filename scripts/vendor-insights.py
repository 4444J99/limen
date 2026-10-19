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

`cat-session --max-chars` bounds the excerpt body for the codex, gemini and opencode readers:
the message that crosses the cap is clipped, then a truncation marker follows. Codex rollouts
open with harness-injected context (developer blocks, project-doc, AGENTS.md and app-page
markup); that context is named with its size and omitted so the cap is spent on the conversation.

Archived codex rollouts (`.jsonl.zst`) are read through the stdlib zstd (Python 3.14+) or the zstd
binary; with neither, or on a corrupt frame, the reader raises instead of rendering an empty
session (limen#3083).

`render` draws the page of Claude Code's built-in /insights report (at-a-glance, nav, stats row,
then work / usage / wins / friction / features / patterns / horizon, fun ending, coverage and
verification). narrative.json takes the full /insights shape or the older thin shape (see
`_normalize_narrative`); a section renders only when its narrative key is present, and the
deterministic facet charts sit under the section they belong to or in a Facet Aggregates block.

Exit codes: 0 ok · 1 error · 2 missing prerequisite (e.g. render before facets exist).
All vendor stores are opened STRICTLY read-only (SQLite via file:...?mode=ro).
"""

from __future__ import annotations

import argparse
import contextlib
import html
import importlib.util
import io
import json
import re
import shutil
import sqlite3
import subprocess
import os
import sys
from collections import Counter
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


def _clip_chunk(chunk: str, total: int, max_chars: int) -> str:
    """The part of `chunk` that still fits the budget. A reader that appends a whole message and
    tests the cap afterwards overshoots by that message's full length (measured 2026-10-18:
    --max-chars 1200 returned 55.8 KB for codex, and 1500 returned 12.5 KB for gemini), so the
    message that crosses the cap is clipped instead. Used by the codex, gemini and opencode
    readers; the other readers still test the cap after appending."""
    return chunk[: max(max_chars - total, 0)]


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


def _zstd_module():
    """Python 3.14+ ships zstd in the stdlib. Older interpreters (the gate rail prefers 3.13) get None."""
    try:
        from compression import zstd
    except ImportError:
        return None
    return zstd


def _zstd_binary() -> str | None:
    return shutil.which("zstd")


class _ZstdCliLines:
    """Lines of a .zst file streamed through the zstd binary. Running to EOF with a non-zero exit is a
    corrupt frame and raises; the caller stopping early (the char cap) is not an error."""

    def __init__(self, path: Path, exe: str):
        self.path = path
        self.proc = subprocess.Popen([exe, "-dc", "--", str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.text = io.TextIOWrapper(self.proc.stdout, encoding="utf-8", errors="replace")

    def __iter__(self):
        yield from self.text
        if self.proc.wait() != 0:
            raise RuntimeError(f"zstd could not decompress {self.path.name} (exit {self.proc.returncode})")

    def close(self) -> None:
        self.text.close()
        self.proc.kill()
        self.proc.wait()


@contextlib.contextmanager
def _open_rollout(p: Path):
    """The lines of a codex rollout. A `.jsonl.zst` rollout (codex compresses old sessions into
    archived_sessions/) streams through a decompressor: the stdlib on Python 3.14+, else the zstd binary.
    With neither, or on a corrupt frame, this raises RuntimeError - a compressed session must never read
    as an empty one (limen#3083)."""
    if not p.name.endswith(".zst"):
        with p.open(encoding="utf-8", errors="replace") as fh:
            yield fh
        return
    zstd = _zstd_module()
    if zstd is not None:
        try:
            with zstd.open(p, "rt", encoding="utf-8", errors="replace") as fh:
                yield fh
        except zstd.ZstdError as exc:
            raise RuntimeError(f"zstd could not decompress {p.name}: {exc}") from exc
        return
    exe = _zstd_binary()
    if exe is None:
        raise RuntimeError(
            f"{p.name} is zstd-compressed and no decompressor is available (need Python 3.14+ or the zstd binary)"
        )
    stream = _ZstdCliLines(p, exe)
    try:
        yield stream
    finally:
        stream.close()


def _codex_session_files(mod, sid: str) -> list[Path]:
    """All rollout files of a logical session, oldest first (resumes share the
    parent session_id in session_meta, but each file's NAME carries its own id —
    so match on the session_meta field, falling back to the filename). Compressed
    `.jsonl.zst` rollouts count: codex archives old sessions that way. If nothing
    matches while a compressed file could not be inspected, that is an error, never
    'not found' (limen#3083)."""
    matches: list[Path] = []
    uninspected: list[Path] = []
    for root in _codex_roots(mod):
        for p in root.rglob("rollout-*.jsonl*"):
            if not p.name.endswith((".jsonl", ".jsonl.zst")):
                continue
            if sid in p.name:
                matches.append(p)
                continue
            try:
                with _open_rollout(p) as fh:
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
            except RuntimeError:
                uninspected.append(p)  # a compressed file whose header we could not read
    if not matches and uninspected:
        raise RuntimeError(
            f"{len(uninspected)} compressed rollout(s) could not be inspected (no zstd decompressor, or a corrupt "
            f"frame), so session {sid} cannot be reported as not found"
        )
    return sorted(matches, key=lambda p: p.name)


# Codex prepends harness-injected context to every rollout: `developer` blocks, the `project-doc`
# role, and user-role messages carrying AGENTS.md / app-page / environment markup. Measured over the
# 68 readable rollouts of the 2026-10-18 index, the first operator turn began a median 67,627 chars
# in, and beyond the 60,000 default cap in 40 of them, so a bounded read returned no operator speech.
# These messages are named with their size and omitted, never silently dropped.
_CODEX_INJECTED_ROLES = frozenset({"developer", "project-doc"})
_CODEX_INJECTED_USER_PREFIXES = (
    "# AGENTS.md instructions",
    "<external_codex_apps_open_page>",
    "<codex_internal_context",
    "<environment_context>",
)


def _codex_injected(role, body: str) -> bool:
    if role in _CODEX_INJECTED_ROLES:
        return True
    return role == "user" and body.lstrip().startswith(_CODEX_INJECTED_USER_PREFIXES)


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
        with _open_rollout(match) as fh:
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
                        role = payload.get("role")
                        body = "\n".join(texts)
                        if _codex_injected(role, body):
                            chunk = f"[omitted harness-injected {role} message: {len(body)} chars]\n"
                        else:
                            chunk = f"--- {role} ---\n{body}\n"
                elif pt == "function_call":
                    chunk = f"[tool: {payload.get('name')}]\n"
                if chunk:
                    chunk = _clip_chunk(chunk, total, max_chars)
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
        u = a = t = errors = 0
        error_codes: set[str] = set()
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
                        elif typ == "session.error":
                            # A turn that dies at the model call leaves no assistant
                            # message; without this count a failing lane reads as idle.
                            errors += 1
                            if isinstance(data.get("errorCode"), str):
                                error_codes.add(data["errorCode"])
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
                extra={"errors": errors, "error_codes": sorted(error_codes)},
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
    event_types: dict[str, int] = {}
    with events.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            typ = rec.get("type")
            data = rec.get("data") or {}
            if isinstance(typ, str):
                event_types[typ] = event_types.get(typ, 0) + 1
            chunk = None
            if typ == "user.message":
                chunk = f"--- user ({(rec.get('timestamp') or '')[:19]}) ---\n{data.get('content') or ''}\n"
            elif typ == "assistant.message":
                body = data.get("content") or ""
                tools = "".join(
                    f"[tool: {tr.get('name')}]\n" for tr in data.get("toolRequests") or [] if isinstance(tr, dict)
                )
                chunk = f"--- assistant ({(rec.get('timestamp') or '')[:19]}) ---\n{body}\n{tools}"
            elif typ == "session.error":
                # Structured fields only: the free-text message can carry request ids.
                fields = ", ".join(
                    f"{k}={data[k]}" for k in ("errorType", "statusCode", "errorCode") if data.get(k) is not None
                )
                chunk = f"[session error ({(rec.get('timestamp') or '')[:19]}): {fields or 'unspecified'}]\n"
            if chunk:
                out.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    out.append("[... truncated at max-chars ...]\n")
                    break
    if not out and event_types:
        # Launched, configured and shut down with no conversation: report the
        # lifecycle honestly instead of returning None ("session not found").
        shape = ", ".join(f"{k}×{v}" for k, v in sorted(event_types.items()))
        return f"[lifecycle-only session: no conversational events; event types {shape}]\n"
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: opencode — opencode.db.
#
# TWO schemas, and reading the wrong one reports a FALSE ZERO (observed
# 2026-10-17: the legacy tables held nothing after 2026-10-01, so a 14-day window
# over them returned 0 sessions for a lane with 196 live ones).
#   v1: session / message(data.role) / part(data.type)
#   v2: session_v2 / session_message(type column, data.content[]) — what
#       opencode >= 2.x actually writes.
# The store MOVED too: the legacy ~/.local/share path keeps history while live
# sessions land per-workspace under .agent-runtime. Both are walked via the
# shared resolver, so a lane is never reported silent because its store moved.
# ---------------------------------------------------------------------------


def _opencode_mode(cur) -> str:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_v2'")
    return "v2" if cur.fetchone() else "v1"


def _opencode_counts(cur, mode: str, sid: str) -> tuple[int, int, int, int]:
    """(user_msgs, assistant_msgs, tool_calls, approx_bytes) for one session."""
    if mode == "v2":
        cur.execute("SELECT COUNT(*) FROM session_message WHERE session_id = ? AND type = 'user'", (sid,))
        u = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM session_message WHERE session_id = ? AND type = 'assistant'", (sid,))
        a = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COUNT(*) FROM session_message, json_each(session_message.data, '$.content') "
            "WHERE session_message.session_id = ? AND json_extract(json_each.value, '$.type') = 'tool'",
            (sid,),
        )
        t = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COALESCE(SUM(LENGTH(data)), 0) FROM session_message WHERE session_id = ?", (sid,))
        return u, a, t, int(cur.fetchone()[0] or 0)
    cur.execute(
        "SELECT COUNT(*) FROM message WHERE session_id = ? AND json_extract(data, '$.role') = 'user'", (sid,)
    )
    u = int(cur.fetchone()[0] or 0)
    cur.execute(
        "SELECT COUNT(*) FROM message WHERE session_id = ? AND json_extract(data, '$.role') = 'assistant'", (sid,)
    )
    a = int(cur.fetchone()[0] or 0)
    cur.execute(
        "SELECT COUNT(*) FROM part WHERE session_id = ? AND json_extract(data, '$.type') = 'tool'", (sid,)
    )
    t = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COALESCE(SUM(LENGTH(data)), 0) FROM part WHERE session_id = ?", (sid,))
    return u, a, t, int(cur.fetchone()[0] or 0)


def _index_opencode(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    stores = mod.opencode_estate_stores()
    if not stores:
        return IndexResult([], 0, "absent", notes=["no opencode.db found (legacy path + .agent-runtime globs)"])
    window_ms = int(window_start.timestamp() * 1000)
    # Union across stores, deduped by session id keeping the later update, so a
    # session present in two stores counts once and never as two.
    best: dict[str, dict] = {}
    notes: list[str] = []
    for db in stores:
        try:
            con = _ro_connect(db)
            cur = con.cursor()
            mode = _opencode_mode(cur)
            table = "session_v2" if mode == "v2" else "session"
            cur.execute(
                f"SELECT id, directory, title, model, time_created, time_updated FROM {table} "
                "WHERE MAX(COALESCE(time_created, 0), COALESCE(time_updated, 0)) >= ?",
                (window_ms,),
            )
            rows = cur.fetchall()
            notes.append(f"{mode} schema: {len(rows)} in-window sessions from {db}")
            for row in rows:
                started = _iso(datetime.fromtimestamp((row["time_created"] or 0) / 1000, tz=timezone.utc))
                ended = _iso(datetime.fromtimestamp((row["time_updated"] or 0) / 1000, tz=timezone.utc))
                model = None
                try:
                    mj = json.loads(row["model"]) if row["model"] else {}
                    if isinstance(mj, dict):
                        model = mj.get("modelID") or mj.get("id")
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass
                prev = best.get(row["id"])
                if prev is not None and (prev["ended_at"] or "") >= ended:
                    continue
                best[row["id"]] = {
                    "sid": row["id"],
                    "started_at": started,
                    "ended_at": ended,
                    "cwd": row["directory"],
                    "title": row["title"],
                    "models": [model] if model else [],
                    "_mode": mode,
                }
            con.close()
        except sqlite3.Error as e:
            notes.append(f"store unreadable ({type(e).__name__}): {db}")

    total = len(best)
    ordered = sorted(best.values(), key=lambda r: r["ended_at"] or "", reverse=True)[:max_sessions]
    sessions = []
    for rec in ordered:
        try:
            db = next(s for s in stores if _opencode_in_store(s, rec))
        except StopIteration:
            db = stores[0]
        try:
            con = _ro_connect(db)
            u, a, t, size = _opencode_counts(con.cursor(), rec["_mode"], rec["sid"])
            con.close()
        except sqlite3.Error:
            u = a = t = size = 0
        sessions.append(
            _mk(
                rec["sid"],
                rec["started_at"],
                rec["ended_at"],
                rec["cwd"],
                u,
                a,
                t,
                rec["models"],
                size,
                {"title": rec["title"], "schema": rec["_mode"]},
            )
        )
    return IndexResult(sessions, total, "time_updated (time_created fallback)", notes=notes)


def _opencode_in_store(db: Path, rec: dict) -> bool:
    """True when `rec`'s session id exists in this store."""
    try:
        con = _ro_connect(db)
        cur = con.cursor()
        table = "session_v2" if rec["_mode"] == "v2" else "session"
        cur.execute(f"SELECT 1 FROM {table} WHERE id = ? LIMIT 1", (rec["sid"],))
        found = cur.fetchone() is not None
        con.close()
        return found
    except sqlite3.Error:
        return False


def _cat_opencode(mod, sid: str, max_chars: int) -> str | None:
    for db in mod.opencode_estate_stores():
        out, mode, con = [], "v1", None
        try:
            con = _ro_connect(db)
            cur = con.cursor()
            mode = _opencode_mode(cur)
            if mode == "v2":
                cur.execute("SELECT id, type, data FROM session_message WHERE session_id = ? ORDER BY time_created", (sid,))
                rows = cur.fetchall()
                if not rows:
                    con.close()
                    continue
                for r in rows:
                    try:
                        data = json.loads(r["data"])
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                    texts = []
                    top_text = data.get("text")
                    if isinstance(top_text, str) and top_text.strip():
                        # v2 keeps user, synthetic and system text at the TOP LEVEL of data, not in
                        # `content` blocks, so a content-only walk dropped every operator turn
                        # (206 user messages across 59 sessions, measured 2026-10-18). `system` rows
                        # are harness-injected instruction diffs (median 2.5 KB, max 74 KB), and a `synthetic`
                        # row wrapped in <system-reminder> is the harness talking, not a shell command the
                        # operator ran: both are named and omitted.
                        if r["type"] == "system" or (
                            r["type"] == "synthetic" and top_text.lstrip().startswith("<system-reminder>")
                        ):
                            texts.append(f"[omitted harness-injected {r['type']} message: {len(top_text)} chars]")
                        else:
                            texts.append(top_text)
                    for blk in data.get("content") or []:
                        if not isinstance(blk, dict):
                            continue
                        if blk.get("type") in ("text", "reasoning") and isinstance(blk.get("text"), str):
                            texts.append(blk["text"])
                        elif blk.get("type") == "tool":
                            texts.append(f"[tool: {blk.get('name')}]")
                    if not texts:
                        continue
                    chunk = f"--- {r['type']} ---\n" + "\n".join(texts) + "\n"
                    out.append(chunk)
            else:
                cur.execute("SELECT id, data FROM message WHERE session_id = ? ORDER BY time_created", (sid,))
                messages = cur.fetchall()
                if not messages:
                    con.close()
                    continue
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
        except sqlite3.Error:
            continue
        finally:
            if con is not None:
                try:
                    con.close()
                except sqlite3.Error:
                    pass
        if out:
            body, total = [], 0
            for chunk in out:
                chunk = _clip_chunk(chunk, total, max_chars)
                body.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    body.append("[... truncated at max-chars ...]\n")
                    break
            return "".join(body)
    return None


# ---------------------------------------------------------------------------
# Adapter: antigravity (agy) — conversations/<uuid>.db (steps table; protobuf
# blobs) + history.jsonl (clean user-prompt spine: display, timestamp ms,
# workspace, conversationId). Older conversation DBs rotate away while
# history.jsonl remembers — counts state this honestly.
# step_type map (empirical, NOT authoritative): 14=task init, 15=assistant
# turn wrapper, 132=tool call (field 5 → 4: 2=tool name, 3=JSON args; the
# send_message tool carries the outward assistant text in args.Message),
# 5/17/8/9/25/7=legacy tool results. Re-measured 2026-10-17: 132 is the generic
# tool call, not send_message — reading every 132 as a message hid the lane's
# tool work and counted it as assistant output. Unknown types are counted as
# other_steps, never dropped silently.
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
        total_steps = n_assistant = n_tool = size = 0
        if blob is not None:
            try:
                size = blob.stat().st_size
                con = _ro_connect(blob)
                cur = con.cursor()
                cur.execute("SELECT step_type, step_payload FROM steps")
                for row in cur:
                    total_steps += 1
                    _chunk, kind = _agy_step_chunk(row["step_type"], row["step_payload"])
                    n_assistant += kind == "assistant"
                    n_tool += kind == "tool"
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
        # assistant msgs = send_message calls; tool calls = every other decoded
        # call plus legacy tool-result steps; the remainder is other_steps.
        sessions.append(
            _mk(
                cid,
                h.get("first_ts"),
                ended,
                cwd,
                h.get("count", 0),
                n_assistant,
                n_tool,
                [],
                size,
                extra={
                    "step_count": step_count,
                    "other_steps": total_steps - n_assistant - n_tool,
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


def _pb_fields(buf: bytes):
    """Yield (field_no, value) for one protobuf message level; ValueError on malformed wire data.

    Varints yield ints; length-delimited fields yield bytes; fixed-width fields yield
    their raw bytes. Groups (wire types 3/4) are obsolete and treated as malformed.
    """

    def varint(i: int) -> tuple[int, int]:
        shift = val = 0
        while True:
            if i >= len(buf) or shift > 63:
                raise ValueError("truncated varint")
            c = buf[i]
            i += 1
            val |= (c & 0x7F) << shift
            if not c & 0x80:
                return val, i
            shift += 7

    i = 0
    while i < len(buf):
        key, i = varint(i)
        fn, wt = key >> 3, key & 7
        if fn == 0:
            raise ValueError("field number 0")
        if wt == 0:
            val, i = varint(i)
            yield fn, val
        elif wt in (1, 5):
            width = 8 if wt == 1 else 4
            if i + width > len(buf):
                raise ValueError("truncated fixed field")
            yield fn, buf[i : i + width]
            i += width
        elif wt == 2:
            ln, i = varint(i)
            if i + ln > len(buf):
                raise ValueError("truncated length-delimited field")
            yield fn, buf[i : i + ln]
            i += ln
        else:
            raise ValueError(f"unsupported wire type {wt}")


def _pb_first(buf: bytes | None, fn: int) -> bytes | None:
    """First length-delimited value of field `fn`, or None."""
    for f, val in _pb_fields(buf or b""):
        if f == fn and isinstance(val, bytes):
            return val
    return None


def _agy_tool_call(payload: bytes) -> tuple[str, dict] | None:
    """Decode a type-132 step into (tool_name, args); None when the payload predates this shape."""
    try:
        header = _pb_first(_pb_first(payload, 5), 4)
        name = _pb_first(header, 2)
        raw_args = _pb_first(header, 3)
        if not name or raw_args is None:
            return None
        args = json.loads(raw_args.decode("utf-8"))
        return name.decode("utf-8"), args if isinstance(args, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return None


def _agy_step_chunk(step_type: int, payload: bytes) -> tuple[str | None, str]:
    """Render one step for cat-session: (chunk, kind) with kind in assistant|tool|other."""
    if step_type == 132:
        call = _agy_tool_call(payload)
        if call is None:
            msg = _agy_scrape_blob(payload, ("Message",))
            return (f"--- assistant (send_message) ---\n{msg}\n", "assistant") if msg else (None, "other")
        name, args = call
        if name == "send_message" and isinstance(args.get("Message"), str):
            return f"--- assistant (send_message) ---\n{args['Message']}\n", "assistant"
        summary = args.get("toolSummary")
        label = " ".join(summary.split())[:200] if isinstance(summary, str) else ""
        return (f"[tool: {name} — {label}]\n" if label else f"[tool: {name}]\n"), "tool"
    if step_type in _AGY_TOOL_TYPES:
        return f"[tool: {_AGY_TOOL_TYPES[step_type]}]\n", "tool"
    return None, "other"


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
        step_types: dict[int, int] = {}
        rendered = 0
        for row in cur.fetchall():
            st = row["step_type"]
            step_types[st] = step_types.get(st, 0) + 1
            chunk, _kind = _agy_step_chunk(st, row["step_payload"])
            if chunk:
                rendered += 1
                out.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    out.append("[... truncated at max-chars ...]\n")
                    break
        con.close()
        if step_types and not rendered:
            # A readable DB whose steps all decode to nothing is a coverage fact,
            # not a missing session — say so instead of returning None.
            shape = ", ".join(f"{k}×{v}" for k, v in sorted(step_types.items()))
            out.append(f"[antigravity conversation {sid}: no decodable messages or tool calls; step types {shape}]\n")
    except sqlite3.Error:
        pass
    return "".join(out) or None


# ---------------------------------------------------------------------------
# Adapter: gemini — ~/.gemini/tmp/<slug>/chats/session-*.jsonl (header line +
# message lines, type user|gemini). cwd from the sibling .project_root file.
# ---------------------------------------------------------------------------


def _gemini_messages(path: Path) -> tuple[dict | None, list[dict]]:
    """Return (header, messages) from BOTH gemini on-disk shapes.

    Older files write one flat JSON object per line (type user|gemini). Newer files
    write a header line then `{"$set": {"messages": [...]}}` envelopes. Envelopes are
    FOLDED, not summed: a later `$set` replaces the list while `$push`/`$append`
    extend it, and real files carry ~2.5 `$set` envelopes each, so naive summing
    triple-counts. Reading only the flat shape made every newer session count as
    zero messages (observed 2026-10-17) — a silent undercount that reads as absence.
    """
    header: dict | None = None
    flat: list[dict] = []
    enveloped: list[dict] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if header is None and rec.get("sessionId"):
                    header = rec
                    continue
                if rec.get("type") in ("user", "gemini"):
                    flat.append(rec)
                    continue
                for key, payload in rec.items():
                    if not key.startswith("$") or not isinstance(payload, dict):
                        continue
                    msgs = payload.get("messages")
                    if not isinstance(msgs, list):
                        continue
                    kept = [m for m in msgs if isinstance(m, dict) and m.get("type") in ("user", "gemini")]
                    if key == "$set":
                        enveloped = kept
                    else:  # $push / $append / $add — extend
                        enveloped.extend(kept)
    except OSError:
        return None, []
    return header, (flat or enveloped)


def _index_gemini(mod, window_start: datetime, max_sessions: int) -> IndexResult:
    roots = mod.gemini_estate_roots()
    if not roots:
        return IndexResult([], 0, "absent", notes=["no gemini tmp root found (legacy + .agent-runtime globs)"])
    candidates = []
    order_keys: dict[str, int] = {}
    for p in (q for root in roots for q in root.glob("*/chats/session-*.jsonl")):
        # The header's own lastUpdated decides the window: a file touched later
        # (copied, synced, re-indexed) must not admit an older conversation.
        dt, key = _gemini_header_time(p), "header lastUpdated/startTime"
        if dt is None:
            dt, key = _mtime(p), "file mtime"
        if dt is not None and dt >= window_start:
            candidates.append((dt.timestamp(), p))
            order_keys[key] = order_keys.get(key, 0) + 1
    kept, total, _capped = _rank(candidates, max_sessions)
    # Identity: the header sessionId stays the key whenever it is unique, so the
    # stable identity single-id files depend on is preserved. It is NOT unique in
    # this estate (observed 2026-10-17: three distinct files all carried
    # "skills-list-session", which collapsed three sessions into one), so on
    # collision the file stem — one JSONL per session — is used instead.
    parsed: dict[Path, tuple] = {}
    header_ids: Counter = Counter()
    for p in kept:
        header, messages = _gemini_messages(p)
        hid = (header or {}).get("sessionId")
        header_ids[hid] += 1
        parsed[p] = (header, messages, hid)
    sessions = []
    for p in kept:
        mts = (_mtime(p) or _now()).timestamp()
        header, messages, header_sid = parsed[p]
        sid = header_sid if (header_sid and header_ids[header_sid] == 1) else p.stem
        started = (header or {}).get("startTime")
        ended = (header or {}).get("lastUpdated")
        u = g = t = 0
        models: set[str] = set()
        for rec in messages:
            if rec.get("type") == "user":
                u += 1
            elif rec.get("type") == "gemini":
                g += 1
                if isinstance(rec.get("model"), str):
                    models.add(rec["model"])
                t += len(rec.get("toolCalls") or [])
        cwd = None
        pr = p.parent.parent / ".project_root"
        if pr.exists():
            try:
                cwd = pr.read_text(encoding="utf-8").strip() or None
            except OSError:
                pass
        ended = ended or _iso(datetime.fromtimestamp(mts, tz=timezone.utc))
        # `sid` is the header id when unique, else the file stem (see above). The
        # header value is always kept as evidence so a collision stays visible.
        sessions.append(
            _mk(
                sid,
                started,
                ended,
                cwd,
                u,
                g,
                t,
                models,
                p.stat().st_size,
                {"session_id_header": header_sid} if header_sid else None,
            )
        )
    return IndexResult(
        sessions,
        total,
        "header lastUpdated → startTime → file mtime",
        notes=[
            "gemini's store logs user prompts; assistant replies are frequently not captured — "
            "treat zero assistant_msgs as a store limitation, not silence"
        ],
        extra={"order_key_coverage": order_keys},
    )


def _gemini_header_time(p: Path) -> datetime | None:
    """lastUpdated (else startTime) from a gemini session file's header line."""
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            header = json.loads(fh.readline() or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(header, dict):
        return None
    for field in ("lastUpdated", "startTime"):
        val = header.get(field)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            except ValueError:
                continue
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _cat_gemini(mod, sid: str, max_chars: int) -> str | None:
    roots = mod.gemini_estate_roots()
    if not roots:
        return None
    all_sessions = [q for root in roots for q in root.glob("*/chats/session-*.jsonl")]
    match = None
    for p in all_sessions:
        if sid in p.name:
            match = p
            break
    if match is None:
        # Fall back to matching the header's sessionId.
        for p in all_sessions:
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
    _header, messages = _gemini_messages(match)
    for rec in messages:
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
            chunk = _clip_chunk(chunk, total, max_chars)
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
        "helpfulness": {},
    }
    for f in facets:
        oc = f.get("outcome") or "unclear"
        agg["outcomes"][oc] = agg["outcomes"].get(oc, 0) + 1
        hp = f.get("agent_helpfulness") or f.get("claude_helpfulness")
        if isinstance(hp, str) and hp.strip():
            agg["helpfulness"][hp] = agg["helpfulness"].get(hp, 0) + 1
        st = f.get("session_type") or "unknown"
        agg["session_types"][st] = agg["session_types"].get(st, 0) + 1
        for k, v in (f.get("friction_counts") or {}).items():
            agg["friction_counts"][k] = agg["friction_counts"].get(k, 0) + _as_count(v)
        for k, v in (f.get("user_satisfaction_counts") or {}).items():
            agg["satisfaction_counts"][k] = agg["satisfaction_counts"].get(k, 0) + _as_count(v)
        for k, v in (f.get("goal_categories") or {}).items():
            agg["goal_categories"][k] = agg["goal_categories"].get(k, 0) + _as_count(v)
    return agg


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_VENDOR_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "copilot": "Copilot",
    "opencode": "OpenCode",
    "antigravity": "Antigravity",
    "gemini": "Gemini CLI",
}
_BAR_LIMIT = 8


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _s(v) -> str:
    """Prose-safe text for a narrative field. A missing value is "" (never the literal
    None/undefined), and a list of strings reads as paragraphs."""
    if v is None or isinstance(v, bool):
        return ""
    if isinstance(v, (str, int, float)):
        return str(v).strip()
    if isinstance(v, list):
        return "\n\n".join(t for t in (_s(x) for x in v) if t)
    return ""


def _bold(escaped: str) -> str:
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def _inline(v) -> str:
    """Escape FIRST, then turn **bold** into <strong>, so the only markup in the output is ours.
    Blank-line paragraph breaks become <br><br> for fields that live inside a card."""
    return re.sub(r"\n\s*\n", "<br><br>", _bold(_esc(_s(v))))


def _prose(v) -> str:
    """Blank-line separated paragraphs, escaped, **bold** converted: the .narrative body."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", _s(v)) if p.strip()]
    return "".join(f"<p>{_bold(_esc(p))}</p>" for p in paras)


def _attr(text: str) -> str:
    """An attribute value that survives a round trip: quotes escaped, newlines kept as &#10;."""
    return html.escape(text, quote=True).replace("\n", "&#10;")


def _pretty(key) -> str:
    return str(key).replace("_", " ").strip().title()


def _items(v) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _texts(v) -> list[str]:
    seq = v if isinstance(v, list) else [v]
    return [t for t in (_s(x) for x in seq) if t]


def _vendor_label(vendor: str) -> str:
    return _VENDOR_LABELS.get(vendor) or str(vendor).replace("-", " ").replace("_", " ").title()


def _normalize_narrative(raw) -> dict:
    """Map either narrative.json shape onto the one the renderer draws.

    The thin shape (tldr, areas, interaction_style string, friction list, suggestions list of
    {title, detail}) predates the full /insights shape (project_areas, interaction_style{narrative,
    key_pattern}, what_works, friction_analysis, suggestions{claude_md_additions, features_to_try,
    usage_patterns}, on_the_horizon, fun_ending, verification); both must keep rendering, so each key
    is read by its TYPE rather than by which shape the file claims to be."""
    n = raw if isinstance(raw, dict) else {}

    def d(v) -> dict:
        return v if isinstance(v, dict) else {}

    pa = n.get("project_areas")
    areas = _items(pa.get("areas") if isinstance(pa, dict) else pa) or _items(n.get("areas"))

    ist = n.get("interaction_style")
    style = {
        "narrative": _s(d(ist).get("narrative") if isinstance(ist, dict) else ist),
        "key_pattern": _s(d(ist).get("key_pattern")),
    }

    ww = d(n.get("what_works"))
    fa = n.get("friction_analysis")
    fa = fa if isinstance(fa, (dict, list)) else n.get("friction")
    friction = {
        "intro": _s(d(fa).get("intro")),
        "categories": _items(fa.get("categories") if isinstance(fa, dict) else fa),
    }

    sg = n.get("suggestions")
    if isinstance(sg, dict):
        claude_md = _items(sg.get("claude_md_additions"))
        features = _items(sg.get("features_to_try"))
        patterns = _items(sg.get("usage_patterns"))
    else:
        claude_md, features = [], []
        patterns = [{"title": i.get("title"), "detail": i.get("detail")} for i in _items(sg)]

    hz = d(n.get("on_the_horizon"))
    ver = n.get("verification")
    ver = ver if isinstance(ver, dict) else {"summary": ver}
    glance = d(n.get("at_a_glance"))
    return {
        "tldr": _s(n.get("tldr")),
        "glance": {k: _s(glance.get(k)) for k in ("whats_working", "whats_hindering", "quick_wins", "ambitious_workflows")},
        "areas": areas,
        "style": style,
        "wins": {"intro": _s(ww.get("intro")), "items": _items(ww.get("impressive_workflows"))},
        "friction": friction,
        "claude_md": claude_md,
        "features": features,
        "patterns": patterns,
        "horizon": {"intro": _s(hz.get("intro")), "items": _items(hz.get("opportunities"))},
        "fun": {"headline": _s(d(n.get("fun_ending")).get("headline")), "detail": _s(d(n.get("fun_ending")).get("detail"))},
        "coverage_notes": _texts(n.get("coverage_notes")),
        "verification": {
            "summary": _s(ver.get("summary")),
            "rounds": _s(ver.get("rounds")),
            "issues_found": _s(ver.get("issues_found")),
            "issues_fixed": _s(ver.get("issues_fixed")),
            "residuals": _texts(ver.get("residuals")),
        },
    }


# ---- deterministic charts (the built-in report's bar-row markup, drawn from index + facets) ----


def _bar_card(title: str, counts: dict, color: str, *, limit: int | None = _BAR_LIMIT, ordered=False, pretty=True) -> str:
    items = [(k, v) for k, v in counts.items() if v]
    if not items:
        return ""
    if not ordered:
        items.sort(key=lambda kv: (-kv[1], str(kv[0])))
    shown = items[:limit] if limit else items
    top = max(v for _, v in shown) or 1
    rows = "".join(
        '<div class="bar-row">'
        f'<div class="bar-label" title="{_attr(k)}">{_esc(_pretty(k) if pretty else k)}</div>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{round(v / top * 100, 1)}%;background:{color}"></div></div>'
        f'<div class="bar-value">{v}</div></div>'
        for k, v in shown
    )
    hidden = len(items) - len(shown)
    if hidden > 0:
        rows += f'<div class="empty">+{hidden} more not shown</div>'
    return f'<div class="chart-card"><div class="chart-title">{_esc(title)}</div>{rows}</div>'


def _charts_row(cards: list[str]) -> str:
    cards = [c for c in cards if c]
    return "".join(f'<div class="charts-row">{"".join(cards[i : i + 2])}</div>' for i in range(0, len(cards), 2))


# ---- narrative sections (ids, order and class names mirror the built-in /insights report) ----


def _sec_work(areas: list[dict]) -> str:
    if not areas:
        return ""
    cards = []
    for a in areas:
        count = _s(a.get("session_count"))
        if re.fullmatch(r"~?\d[\d,]*", count):
            count += " sessions"
        badge = f'<span class="area-count">{_esc(count)}</span>' if count else ""
        cards.append(
            '<div class="project-area"><div class="area-header">'
            f'<span class="area-name">{_esc(_s(a.get("name")))}</span>{badge}</div>'
            f'<div class="area-desc">{_inline(a.get("description"))}</div></div>'
        )
    return f'<h2 id="section-work">What You Work On</h2><div class="project-areas">{"".join(cards)}</div>'


def _sec_usage(style: dict, label: str) -> str:
    if not (style["narrative"] or style["key_pattern"]):
        return ""
    key = (
        f'<div class="key-insight"><strong>Key pattern:</strong> {_inline(style["key_pattern"])}</div>'
        if style["key_pattern"]
        else ""
    )
    return (
        f'<h2 id="section-usage">How You Use {_esc(label)}</h2>'
        f'<div class="narrative">{_prose(style["narrative"])}{key}</div>'
    )


def _intro(text: str) -> str:
    return f'<p class="section-intro">{_inline(text)}</p>' if text else ""


def _sec_wins(wins: dict) -> str:
    cards = [
        '<div class="big-win">'
        f'<div class="big-win-title">{_esc(_s(w.get("title")))}</div>'
        f'<div class="big-win-desc">{_inline(w.get("description"))}</div></div>'
        for w in wins["items"]
    ]
    if not cards:
        return ""
    return (
        '<h2 id="section-wins">Impressive Things You Did</h2>'
        f'{_intro(wins["intro"])}<div class="big-wins">{"".join(cards)}</div>'
    )


def _sec_friction(friction: dict) -> str:
    cats = []
    for c in friction["categories"]:
        examples = "".join(f"<li>{_inline(e)}</li>" for e in _texts(c.get("examples")))
        ul = f'<ul class="friction-examples">{examples}</ul>' if examples else ""
        cats.append(
            '<div class="friction-category">'
            f'<div class="friction-title">{_esc(_s(c.get("category")))}</div>'
            f'<div class="friction-desc">{_inline(c.get("description"))}</div>{ul}</div>'
        )
    if not cats:
        return ""
    return (
        '<h2 id="section-friction">Where Things Go Wrong</h2>'
        f'{_intro(friction["intro"])}<div class="friction-categories">{"".join(cats)}</div>'
    )


def _copy_row(code_cls: str, text: str) -> str:
    """A literal code block plus the Copy button copyText() reads (previousElementSibling)."""
    open_tag = f'<code class="{code_cls}">' if code_cls else "<code>"
    return f'{open_tag}{_esc(text)}</code><button class="copy-btn" onclick="copyText(this)">Copy</button>'


def _sec_features(claude_md: list[dict], features: list[dict], label: str) -> str:
    md_rows = [c for c in claude_md if _s(c.get("addition"))]
    cards = [f for f in features if _s(f.get("feature"))]
    if not (md_rows or cards):
        return ""
    out = [f'<h2 id="section-features">Existing {_esc(label)} Features to Try</h2>']
    if md_rows:
        items = []
        for i, c in enumerate(md_rows):
            addition, scaffold, why = _s(c.get("addition")), _s(c.get("prompt_scaffold")), _s(c.get("why"))
            payload = f"{scaffold}\n\n{addition}" if scaffold else addition
            why_html = f'<div class="cmd-why">{_inline(why)}</div>' if why else ""
            items.append(
                '<div class="claude-md-item">'
                f'<input type="checkbox" id="cmd-{i}" class="cmd-checkbox" checked data-text="{_attr(payload)}">'
                f'<label for="cmd-{i}"><code class="cmd-code">{_esc(addition)}</code>'
                f'<button class="copy-btn" onclick="copyCmdItem({i})">Copy</button></label>{why_html}</div>'
            )
        out.append(
            '<div class="claude-md-section"><h3>Suggested Instruction-File Additions</h3>'
            '<p style="font-size: 12px; color: #64748b; margin-bottom: 12px;">'
            f"Just copy this into {_esc(label)} to add it to your instruction file.</p>"
            '<div class="claude-md-actions"><button class="copy-all-btn" onclick="copyAllCheckedClaudeMd()">'
            f'Copy All Checked</button></div>{"".join(items)}</div>'
        )
    if cards:
        feats = []
        for f in cards:
            why = _s(f.get("why_for_you"))
            code = _s(f.get("example_code"))
            feats.append(
                '<div class="feature-card">'
                f'<div class="feature-title">{_esc(_s(f.get("feature")))}</div>'
                + (f'<div class="feature-oneliner">{_inline(f.get("one_liner"))}</div>' if _s(f.get("one_liner")) else "")
                + (f'<div class="feature-why"><strong>Why for you:</strong> {_inline(why)}</div>' if why else "")
                + (
                    '<div class="feature-examples"><div class="feature-example"><div class="example-code-row">'
                    f'{_copy_row("example-code", code)}</div></div></div>'
                    if code
                    else ""
                )
                + "</div>"
            )
        hint = (
            f"Just copy this into {_esc(label)} and it'll set it up for you."
            if any(_s(f.get("example_code")) for f in cards)
            else ""
        )
        hint_html = f'<p style="font-size: 13px; color: #64748b; margin-bottom: 12px;">{hint}</p>' if hint else ""
        out.append(f'{hint_html}<div class="features-section">{"".join(feats)}</div>')
    return "".join(out)


def _sec_patterns(patterns: list[dict], label: str) -> str:
    cards = []
    for p in patterns:
        title = _s(p.get("title"))
        if not title:
            continue
        prompt = _s(p.get("copyable_prompt"))
        summary = _s(p.get("suggestion"))
        detail = _s(p.get("detail"))
        cards.append(
            '<div class="pattern-card">'
            f'<div class="pattern-title">{_esc(title)}</div>'
            + (f'<div class="pattern-summary">{_inline(summary)}</div>' if summary else "")
            + (f'<div class="pattern-detail">{_inline(detail)}</div>' if detail else "")
            + (
                '<div class="copyable-prompt-section">'
                f'<div class="prompt-label">Paste into {_esc(label)}:</div>'
                f'<div class="copyable-prompt-row">{_copy_row("copyable-prompt", prompt)}</div></div>'
                if prompt
                else ""
            )
            + "</div>"
        )
    if not cards:
        return ""
    hint = (
        f"Just copy this into {_esc(label)} and it'll walk you through it."
        if any(_s(p.get("copyable_prompt")) for p in patterns)
        else ""
    )
    hint_html = f'<p style="font-size: 13px; color: #64748b; margin-bottom: 12px;">{hint}</p>' if hint else ""
    return f'<h2 id="section-patterns">New Ways to Use {_esc(label)}</h2>{hint_html}<div class="patterns-section">{"".join(cards)}</div>'


def _sec_horizon(horizon: dict, label: str) -> str:
    cards = []
    for o in horizon["items"]:
        title = _s(o.get("title"))
        if not title:
            continue
        possible, how, prompt = _s(o.get("whats_possible")), _s(o.get("how_to_try")), _s(o.get("copyable_prompt"))
        cards.append(
            '<div class="horizon-card">'
            f'<div class="horizon-title">{_esc(title)}</div>'
            + (f'<div class="horizon-possible">{_inline(possible)}</div>' if possible else "")
            + (f'<div class="horizon-tip"><strong>Getting started:</strong> {_inline(how)}</div>' if how else "")
            + (
                f'<div class="pattern-prompt"><div class="prompt-label">Paste into {_esc(label)}:</div>'
                f'{_copy_row("", prompt)}</div>'
                if prompt
                else ""
            )
            + "</div>"
        )
    if not cards:
        return ""
    return f'<h2 id="section-horizon">On the Horizon</h2>{_intro(horizon["intro"])}<div class="horizon-section">{"".join(cards)}</div>'


def _sec_fun(fun: dict) -> str:
    headline, detail = fun["headline"], fun["detail"]
    if not (headline or detail):
        return ""
    quoted = headline if headline[:1] in ('"', "“") else f'"{headline}"'
    head_html = f'<div class="fun-headline">{_esc(quoted)}</div>' if headline else ""
    detail_html = f'<div class="fun-detail">{_inline(detail)}</div>' if detail else ""
    return f'<div class="fun-ending">{head_html}{detail_html}</div>'


def _sec_coverage(notes: list[str], ver: dict) -> str:
    body = ""
    if notes:
        lis = "".join(f"<li>{_inline(n)}</li>" for n in notes)
        body += f'<div class="prompt-label">Coverage notes</div><ul class="friction-examples" style="margin-bottom: 16px;">{lis}</ul>'
    counts = [
        f"{label}: {ver[k]}"
        for k, label in (("rounds", "Verification rounds"), ("issues_found", "Issues found"), ("issues_fixed", "Issues fixed"))
        if ver[k]
    ]
    if ver["summary"] or counts or ver["residuals"]:
        body += '<div class="prompt-label">Verification</div>'
        if ver["summary"]:
            body += f'<p class="section-intro" style="margin-bottom: 8px;">{_inline(ver["summary"])}</p>'
        if counts:
            body += f'<p class="section-intro" style="margin-bottom: 8px;">{_esc(" | ".join(counts))}</p>'
        if ver["residuals"]:
            lis = "".join(f"<li>{_inline(r)}</li>" for r in ver["residuals"])
            body += (
                '<div class="prompt-label" style="margin-top: 12px;">Residuals</div>'
                f'<ul class="friction-examples" style="margin-bottom: 16px;">{lis}</ul>'
            )
    if not body:
        return ""
    return (
        '<div class="collapsible-section" id="section-coverage">'
        '<div class="collapsible-header open" onclick="toggleCollapsible(this)">'
        '<span class="collapsible-arrow">&#9654;</span><h3>Coverage and verification</h3></div>'
        f'<div class="collapsible-content open">{body}</div></div>'
    )


_REPORT_CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; color: #334155; line-height: 1.65; padding: 48px 24px; }
    .container { max-width: 800px; margin: 0 auto; }
    h1 { font-size: 32px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }
    h2 { font-size: 20px; font-weight: 600; color: #0f172a; margin-top: 48px; margin-bottom: 16px; }
    .subtitle { color: #64748b; font-size: 15px; margin-bottom: 8px; }
    .subtitle:last-of-type { margin-bottom: 32px; }
    .container p + p { margin-top: 8px; }
    .nav-toc { display: flex; flex-wrap: wrap; gap: 8px; margin: 24px 0 32px 0; padding: 16px; background: white; border-radius: 8px; border: 1px solid #e2e8f0; }
    .nav-toc a { font-size: 12px; color: #64748b; text-decoration: none; padding: 6px 12px; border-radius: 6px; background: #f1f5f9; transition: all 0.15s; }
    .nav-toc a:hover { background: #e2e8f0; color: #334155; }
    .stats-row { display: flex; gap: 24px; margin-bottom: 40px; padding: 20px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap; }
    .stat { text-align: center; }
    .stat[title] { cursor: help; }
    .stat-value { font-size: 24px; font-weight: 700; color: #0f172a; }
    .stat-label { font-size: 11px; color: #64748b; text-transform: uppercase; }
    .at-a-glance { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #f59e0b; border-radius: 12px; padding: 20px 24px; margin-bottom: 32px; }
    .glance-title { font-size: 16px; font-weight: 700; color: #92400e; margin-bottom: 16px; }
    .glance-sections { display: flex; flex-direction: column; gap: 12px; }
    .glance-section { font-size: 14px; color: #78350f; line-height: 1.6; }
    .glance-section strong { color: #92400e; }
    .see-more { color: #b45309; text-decoration: none; font-size: 13px; white-space: nowrap; }
    .see-more:hover { text-decoration: underline; }
    .project-areas { display: flex; flex-direction: column; gap: 12px; margin-bottom: 32px; }
    .project-area { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
    .area-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .area-name { font-weight: 600; font-size: 15px; color: #0f172a; }
    .area-count { font-size: 12px; color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 4px; }
    .area-desc { font-size: 14px; color: #475569; line-height: 1.5; }
    .narrative { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 24px; }
    .narrative p { margin-bottom: 12px; font-size: 14px; color: #475569; line-height: 1.7; }
    .narrative p + p { margin-top: 0; }
    .key-insight { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 12px 16px; margin-top: 12px; font-size: 14px; color: #166534; }
    .section-intro { font-size: 14px; color: #64748b; margin-bottom: 16px; }
    .big-wins { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
    .big-win { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; }
    .big-win-title { font-weight: 600; font-size: 15px; color: #166534; margin-bottom: 8px; }
    .big-win-desc { font-size: 14px; color: #15803d; line-height: 1.5; }
    .friction-categories { display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px; }
    .friction-category { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 16px; }
    .friction-title { font-weight: 600; font-size: 15px; color: #991b1b; margin-bottom: 6px; }
    .friction-desc { font-size: 13px; color: #7f1d1d; margin-bottom: 10px; }
    .friction-examples { margin: 0 0 0 20px; font-size: 13px; color: #334155; }
    .friction-examples li { margin-bottom: 4px; }
    .claude-md-section { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
    .claude-md-section h3 { font-size: 14px; font-weight: 600; color: #1e40af; margin: 0 0 12px 0; }
    .claude-md-actions { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #dbeafe; }
    .copy-all-btn { background: #2563eb; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-size: 12px; cursor: pointer; font-weight: 500; transition: all 0.2s; }
    .copy-all-btn:hover { background: #1d4ed8; }
    .copy-all-btn.copied { background: #16a34a; }
    .claude-md-item { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; padding: 10px 0; border-bottom: 1px solid #dbeafe; }
    .claude-md-item:last-child { border-bottom: none; }
    .cmd-checkbox { margin-top: 2px; }
    .cmd-code { background: white; padding: 8px 12px; border-radius: 4px; font-size: 12px; color: #1e40af; border: 1px solid #bfdbfe; font-family: monospace; display: block; white-space: pre-wrap; word-break: break-word; flex: 1; }
    .cmd-why { font-size: 12px; color: #64748b; width: 100%; padding-left: 24px; margin-top: 4px; }
    .features-section, .patterns-section { display: flex; flex-direction: column; gap: 12px; margin: 16px 0; }
    .feature-card { background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 16px; }
    .pattern-card { background: #f0f9ff; border: 1px solid #7dd3fc; border-radius: 8px; padding: 16px; }
    .feature-title, .pattern-title { font-weight: 600; font-size: 15px; color: #0f172a; margin-bottom: 6px; }
    .feature-oneliner { font-size: 14px; color: #475569; margin-bottom: 8px; }
    .pattern-summary { font-size: 14px; color: #475569; margin-bottom: 8px; }
    .feature-why, .pattern-detail { font-size: 13px; color: #334155; line-height: 1.5; }
    .feature-examples { margin-top: 12px; }
    .feature-example { padding: 8px 0; border-top: 1px solid #d1fae5; }
    .feature-example:first-child { border-top: none; }
    .example-code-row { display: flex; align-items: flex-start; gap: 8px; }
    .example-code { flex: 1; background: #f1f5f9; padding: 8px 12px; border-radius: 4px; font-family: monospace; font-size: 12px; color: #334155; overflow-x: auto; white-space: pre-wrap; }
    .copyable-prompt-section { margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0; }
    .copyable-prompt-row { display: flex; align-items: flex-start; gap: 8px; }
    .copyable-prompt { flex: 1; background: #f8fafc; padding: 10px 12px; border-radius: 4px; font-family: monospace; font-size: 12px; color: #334155; border: 1px solid #e2e8f0; white-space: pre-wrap; line-height: 1.5; }
    .pattern-prompt { background: #f8fafc; padding: 12px; border-radius: 6px; margin-top: 12px; border: 1px solid #e2e8f0; }
    .pattern-prompt code { font-family: monospace; font-size: 12px; color: #334155; display: block; white-space: pre-wrap; margin-bottom: 8px; }
    .prompt-label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: #64748b; margin-bottom: 6px; }
    .copy-btn { background: #e2e8f0; border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer; color: #475569; flex-shrink: 0; }
    .copy-btn:hover { background: #cbd5e1; }
    .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 24px 0; }
    .chart-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
    .chart-title { font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 12px; }
    .bar-row { display: flex; align-items: center; margin-bottom: 6px; }
    .bar-label { width: 100px; font-size: 11px; color: #475569; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar-track { flex: 1; height: 6px; background: #f1f5f9; border-radius: 3px; margin: 0 8px; }
    .bar-fill { height: 100%; border-radius: 3px; }
    .bar-value { width: 28px; font-size: 11px; font-weight: 500; color: #64748b; text-align: right; }
    .empty { color: #94a3b8; font-size: 13px; }
    .horizon-section { display: flex; flex-direction: column; gap: 16px; }
    .horizon-card { background: linear-gradient(135deg, #faf5ff 0%, #f5f3ff 100%); border: 1px solid #c4b5fd; border-radius: 8px; padding: 16px; }
    .horizon-title { font-weight: 600; font-size: 15px; color: #5b21b6; margin-bottom: 8px; }
    .horizon-possible { font-size: 14px; color: #334155; margin-bottom: 10px; line-height: 1.5; }
    .horizon-tip { font-size: 13px; color: #6b21a8; background: rgba(255,255,255,0.6); padding: 8px 12px; border-radius: 4px; }
    .fun-ending { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #fbbf24; border-radius: 12px; padding: 24px; margin-top: 40px; text-align: center; }
    .fun-headline { font-size: 18px; font-weight: 600; color: #78350f; margin-bottom: 8px; }
    .fun-detail { font-size: 14px; color: #92400e; }
    .collapsible-section { margin-top: 32px; }
    .collapsible-header { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 12px 0; border-bottom: 1px solid #e2e8f0; }
    .collapsible-header h3 { margin: 0; font-size: 14px; font-weight: 600; color: #475569; }
    .collapsible-arrow { font-size: 12px; color: #94a3b8; transition: transform 0.2s; }
    .collapsible-content { display: none; padding-top: 16px; }
    .collapsible-content.open { display: block; }
    .collapsible-header.open .collapsible-arrow { transform: rotate(90deg); }
    @media (max-width: 640px) { .charts-row { grid-template-columns: 1fr; } .stats-row { justify-content: center; } }
"""

_JS_TOGGLE = """
    function toggleCollapsible(header) {
      header.classList.toggle('open');
      header.nextElementSibling.classList.toggle('open');
    }
"""
_JS_COPY = """
    function copyText(btn) {
      navigator.clipboard.writeText(btn.previousElementSibling.textContent).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
      });
    }
"""
_JS_COPY_CMD = """
    function copyCmdItem(idx) {
      const checkbox = document.getElementById('cmd-' + idx);
      if (!checkbox) return;
      navigator.clipboard.writeText(checkbox.dataset.text).then(() => {
        const btn = checkbox.nextElementSibling.querySelector('.copy-btn');
        if (btn) { btn.textContent = 'Copied!'; setTimeout(() => { btn.textContent = 'Copy'; }, 2000); }
      });
    }
    function copyAllCheckedClaudeMd() {
      const texts = [];
      document.querySelectorAll('.cmd-checkbox:checked').forEach(cb => { if (cb.dataset.text) { texts.push(cb.dataset.text); } });
      const btn = document.querySelector('.copy-all-btn');
      navigator.clipboard.writeText(texts.join('\\n')).then(() => {
        if (!btn) return;
        btn.textContent = 'Copied ' + texts.length + ' items!';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = 'Copy All Checked'; btn.classList.remove('copied'); }, 2000);
      });
    }
"""

_GLANCE_LINKS = (
    ("whats_working", "What's working:", "section-wins", "Impressive Things You Did"),
    ("whats_hindering", "What's hindering you:", "section-friction", "Where Things Go Wrong"),
    ("quick_wins", "Quick wins to try:", "section-features", "Features to Try"),
    ("ambitious_workflows", "Ambitious workflows:", "section-horizon", "On the Horizon"),
)
_NAV_LABELS = {
    "section-work": "What You Work On",
    "section-usage": "How You Use {label}",
    "section-wins": "Impressive Things",
    "section-friction": "Where Things Go Wrong",
    "section-features": "Features to Try",
    "section-patterns": "New Usage Patterns",
    "section-horizon": "On the Horizon",
    "section-aggregates": "Facet Aggregates",
    "section-coverage": "Coverage",
}


def _stat(value: str, label: str, title: str) -> str:
    title_attr = f' title="{_attr(title)}"' if title else ""
    return (
        f'<div class="stat"{title_attr}>'
        f'<div class="stat-value">{_esc(value)}</div><div class="stat-label">{_esc(label)}</div></div>'
    )


def _coverage_notes(index: dict, facets: list[dict], narrative_notes: list[str], absent: list[str]) -> list[str]:
    """The deterministic half of the coverage notes. No silent caps: name what was NOT covered."""
    imeta = index.get("meta") or {}
    n_sessions = len(index.get("sessions", []))
    notes = list(narrative_notes)
    if imeta.get("capped"):
        notes.append(
            f"Index cap: {imeta.get('shown', n_sessions)} of {imeta.get('total_in_window', '?')} in-window sessions were "
            f"indexed (--max-sessions); those not shown are the OLDEST by {imeta.get('order_key') or 'the index order key'}."
        )
    for adapter_note in imeta.get("notes") or []:
        notes.append(f"Store note: {adapter_note}")
    churn = imeta.get("capsule_churn") or {}
    if churn.get("mean_files_per_session", 0) > 1.0:
        notes.append(
            f"Capsule churn: {churn.get('logical_sessions', '?')} logical sessions span {churn.get('files_total', '?')} "
            f"rollout files (mean {churn['mean_files_per_session']}, max {churn.get('max_files_in_one_session', '?')} in one)."
        )
    unfaceted = n_sessions - len(facets)
    if unfaceted > 0:
        notes.append(f"{unfaceted} of {n_sessions} indexed sessions were not faceted (sampling cap).")
    if absent:
        notes.append("Narrative sections absent: " + ", ".join(absent) + ".")
    return notes


def _render_html(vendor: str, index: dict, facets: list[dict], narrative: dict) -> str:
    """Render the report in the shape of Claude Code's built-in /insights page: at-a-glance, nav,
    stats row, then work / usage / wins / friction / features / patterns / horizon, the fun ending and a
    coverage-and-verification block. Narrative sections render only when the narrative has them (a
    section id is never emitted for an empty body, and a nav or see-more link is only emitted for a
    section that rendered); the deterministic facet charts sit under the section they belong to, or in
    a Facet Aggregates block when that section has no narrative."""
    agg = _aggregate_facets(facets)
    nar = _normalize_narrative(narrative)
    label = _vendor_label(vendor)
    sessions = index.get("sessions", [])
    n_sessions = len(sessions)
    tool_calls = sum(s.get("tool_calls", 0) for s in sessions)
    user_msgs = sum(s.get("user_msgs", 0) for s in sessions)
    models = Counter(m for s in sessions for m in s.get("models", []))
    started = Counter(
        s["started_at"][:10] for s in sessions if isinstance(s.get("started_at"), str) and len(s["started_at"]) >= 10
    )
    window = index.get("window", {})
    imeta = index.get("meta") or {}
    if imeta.get("capped"):
        indexed_phrase = (
            f"{imeta.get('shown', n_sessions)} of {imeta.get('total_in_window', '?')} in-window sessions indexed"
        )
    else:
        indexed_phrase = f"{n_sessions} sessions indexed"

    cards = {
        "work": [
            _bar_card("What You Wanted", agg["goal_categories"], "#2563eb"),
            _bar_card("Session Types", agg["session_types"], "#8b5cf6"),
        ],
        "usage": [
            _bar_card("Sessions per Day", dict(sorted(started.items())), "#6366f1", limit=None, ordered=True, pretty=False),
            _bar_card("Models", dict(models), "#0891b2", pretty=False),
        ],
        "wins": [
            _bar_card("Outcomes", agg["outcomes"], "#8b5cf6"),
            _bar_card("Helpfulness (model-estimated)", agg["helpfulness"], "#16a34a"),
        ],
        "friction": [
            _bar_card("Friction Types", agg["friction_counts"], "#dc2626"),
            _bar_card("Inferred Satisfaction (model-estimated)", agg["satisfaction_counts"], "#eab308"),
        ],
    }
    bodies = [
        ("section-work", "work", _sec_work(nar["areas"])),
        ("section-usage", "usage", _sec_usage(nar["style"], label)),
        ("section-wins", "wins", _sec_wins(nar["wins"])),
        ("section-friction", "friction", _sec_friction(nar["friction"])),
        ("section-features", None, _sec_features(nar["claude_md"], nar["features"], label)),
        ("section-patterns", None, _sec_patterns(nar["patterns"], label)),
        ("section-horizon", None, _sec_horizon(nar["horizon"], label)),
    ]
    sections: list[tuple[str, str]] = []
    orphans: list[str] = []
    for sid, card_key, body in bodies:
        if body:
            sections.append((sid, body + (_charts_row(cards[card_key]) if card_key else "")))
        elif card_key:
            orphans.extend(cards[card_key])
    orphan_html = _charts_row(orphans)
    if orphan_html:
        sections.append(("section-aggregates", f'<h2 id="section-aggregates">Facet Aggregates (deterministic)</h2>{orphan_html}'))

    glance = nar["glance"]
    rendered = {sid for sid, _ in sections}
    glance_rows = ""
    for key, title, target, link_text in _GLANCE_LINKS:
        if glance[key]:
            link = f' <a href="#{target}" class="see-more">{_esc(link_text)} →</a>' if target in rendered else ""
            glance_rows += f'<div class="glance-section"><strong>{_esc(title)}</strong> {_inline(glance[key])}{link}</div>'
    glance_html = (
        f'<div class="at-a-glance"><div class="glance-title">At a Glance</div><div class="glance-sections">{glance_rows}</div></div>'
        if glance_rows
        else ""
    )

    absent = [
        name
        for name, present in (
            ("at_a_glance", bool(glance_rows)),
            ("project_areas", bool(nar["areas"])),
            ("interaction_style", bool(nar["style"]["narrative"])),
            ("what_works", bool(nar["wins"]["items"])),
            ("friction_analysis", bool(nar["friction"]["categories"])),
            ("suggestions", bool(nar["claude_md"] or nar["features"] or nar["patterns"])),
            ("on_the_horizon", bool(nar["horizon"]["items"])),
        )
        if not present
    ]
    notes = _coverage_notes(index, facets, nar["coverage_notes"], absent)
    coverage_html = _sec_coverage(notes, nar["verification"])
    if coverage_html:
        rendered.add("section-coverage")

    nav_ids = [sid for sid, _ in sections] + (["section-coverage"] if coverage_html else [])
    nav = "".join(f'<a href="#{sid}">{_esc(_NAV_LABELS[sid].format(label=label))}</a>' for sid in nav_ids)
    active_days = len(started)
    stat_title = f"{len(facets)} faceted of {n_sessions} indexed" + (
        f" ({imeta.get('total_in_window', '?')} in window)" if imeta.get("capped") else ""
    )
    stats = [
        (f"{n_sessions:,}", "Sessions", stat_title),
        (f"{user_msgs:,}", "User msgs", ""),
        (f"{tool_calls:,}", "Tool calls", ""),
        (f"{active_days:,}", "Active days", ""),
        (f"{user_msgs / active_days:,.1f}" if active_days else "—", "Msgs/Day", ""),
    ]
    stats_html = "".join(_stat(v, lbl, t) for v, lbl, t in stats)

    body = "".join(chunk for _, chunk in sections)
    fun_html = _sec_fun(nar["fun"])
    tldr_html = f'<div class="narrative" id="section-tldr">{_prose(nar["tldr"])}</div>' if nar["tldr"] else ""
    scripts = (
        (_JS_TOGGLE if coverage_html else "")
        + (_JS_COPY if 'onclick="copyText(this)"' in body else "")
        + (_JS_COPY_CMD if "copyCmdItem(" in body else "")
    )
    script_html = f"<script>{scripts}</script>" if scripts else ""
    models_line = ", ".join(sorted(models)) or "—"
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_esc(label)} Insights</title><style>{_REPORT_CSS}</style></head><body><div class="container">'
        f"<h1>{_esc(label)} Insights</h1>"
        f'<p class="subtitle">{user_msgs:,} user messages across {_esc(indexed_phrase)} · {len(facets)} faceted | '
        f"{_esc((window.get('start') or '?')[:10])} to {_esc((window.get('end') or '?')[:10])}</p>"
        f'<p class="subtitle">Models: {_esc(models_line)}</p>'
        f"{tldr_html}{glance_html}"
        f'<nav class="nav-toc">{nav}</nav>'
        f'<div class="stats-row">{stats_html}</div>'
        f"{body}{fun_html}{coverage_html}"
        f'<p class="empty" style="margin-top: 32px;">Generated {_iso()} by scripts/vendor-insights.py '
        "(mechanical half of /vendor-insights).</p>"
        f"</div>{script_html}</body></html>"
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
    try:
        text = CATTERS[vendor](mod, sid, max_chars)
    except RuntimeError as exc:  # e.g. a compressed rollout with no decompressor: loud, never an empty render
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
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
