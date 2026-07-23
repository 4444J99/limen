"""CONTINUITY — don't forget (CKO).

When a session overflows context a second time, the *automatic* continuation can
hand off a degenerate ~200-char summary stub and the thread looks lost. It isn't:
the raw turns survive in ``~/.claude/projects/*/*.jsonl`` and the last good manual
``/compact`` is persisted as a row with ``isCompactSummary=true``. This organ
makes the by-hand recovery automatic: on a degenerate handoff it reconstructs the
thread from the transcript and writes it where the next session can find it.

All parsing is pure + tested; the per-beat scan is best-effort and fail-open.
"""

from __future__ import annotations

import glob as _glob
import json
import os
from pathlib import Path

from . import params


def parse_rows(path: str | Path) -> list[dict]:
    """Parse a Claude Code transcript (one JSON object per line); skip bad lines."""
    rows: list[dict] = []
    try:
        text = Path(path).read_text(errors="replace")
    except Exception:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _row_text(row: dict) -> tuple[str, str] | None:
    """Extract (role, text) from a transcript row, or None if it carries no text."""
    msg = row.get("message")
    role = None
    content = None
    if isinstance(msg, dict):
        role = msg.get("role")
        content = msg.get("content")
    role = role or row.get("type") or "?"

    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    texts.append(str(block["text"]))
                elif block.get("type") == "tool_use":
                    texts.append(f"[tool_use: {block.get('name', '?')}]")
                elif block.get("type") == "tool_result":
                    texts.append("[tool_result]")
            elif isinstance(block, str):
                texts.append(block)
    elif isinstance(row.get("summary"), str):
        texts.append(row["summary"])

    text = "\n".join(t for t in texts if t).strip()
    return (str(role), text) if text else None


def _summary_text(row: dict) -> str | None:
    if row.get("isCompactSummary") or row.get("type") == "summary":
        rt = _row_text(row)
        if rt:
            return rt[1]
        if isinstance(row.get("summary"), str) and row["summary"].strip():
            return row["summary"].strip()
    return None


def last_compact_summary(rows: list[dict]) -> str | None:
    """The most recent compact/handoff summary text in the transcript."""
    for row in reversed(rows):
        s = _summary_text(row)
        if s is not None:
            return s
    return None


def is_degenerate(summary: str | None, min_chars: int) -> bool:
    """A handoff summary shorter than ``min_chars`` is degenerate (this session got 200)."""
    return summary is not None and len(summary.strip()) < min_chars


def reconstruct(rows: list[dict], min_chars: int, max_chars: int = 60000) -> str:
    """Rebuild the thread: the last *good* (non-degenerate) summary as the base,
    then every intact turn that followed it."""
    base_idx: int | None = None
    base_text = ""
    for i, row in enumerate(rows):
        s = _summary_text(row)
        if s is not None and len(s.strip()) >= min_chars:
            base_idx, base_text = i, s.strip()

    parts: list[str] = []
    if base_text:
        parts.append("# Recovered base summary (last good /compact)\n\n" + base_text)
    start = (base_idx + 1) if base_idx is not None else 0
    tail = []
    for row in rows[start:]:
        rt = _row_text(row)
        if rt and not _summary_text(row):
            tail.append(f"## {rt[0]}\n\n{rt[1]}")
    if tail:
        parts.append("# Thread since the last good summary\n\n" + "\n\n".join(tail))
    out = "\n\n".join(parts).strip()
    return out[:max_chars]


def _transcripts(pattern: str) -> list[Path]:
    expanded = os.path.expanduser(pattern)
    paths = [Path(p) for p in _glob.glob(expanded)]
    return sorted((p for p in paths if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)


def _out_dir() -> Path:
    root = params._repo_root() or Path(os.environ.get("LIMEN_ROOT", ".")).expanduser()
    d = root / "logs" / "vigilia"
    d.mkdir(parents=True, exist_ok=True)
    return d


def beat() -> dict:
    """Per-beat scan: if the latest transcript's handoff is degenerate, write a
    reconstruction. Best-effort, fail-open."""
    pattern = params.get("CONTINUITY_TRANSCRIPT_GLOB", "~/.claude/projects/*/*.jsonl")
    min_chars = params.get("CONTINUITY_MIN_SUMMARY_CHARS", 400, cast=int)
    result: dict = {"organ": "continuity", "min_chars": min_chars}
    try:
        paths = _transcripts(pattern)
    except Exception as exc:
        return {**result, "status": "scan-error", "error": str(exc)[:200]}
    if not paths:
        return {**result, "status": "no-transcripts"}

    latest = paths[0]
    rows = parse_rows(latest)
    summary = last_compact_summary(rows)
    degenerate = is_degenerate(summary, min_chars)
    result.update(
        {
            "transcript": str(latest),
            "rows": len(rows),
            "summary_chars": len(summary or ""),
            "degenerate": degenerate,
        }
    )
    if degenerate:
        try:
            recon = reconstruct(rows, min_chars)
            out_path = _out_dir() / f"continuity-{latest.stem}.md"
            out_path.write_text(recon)
            result["reconstruction"] = str(out_path)
            result["reconstruction_chars"] = len(recon)
            result["status"] = "reconstructed"
        except Exception as exc:
            result["status"] = "reconstruct-error"
            result["error"] = str(exc)[:200]
    else:
        result["status"] = "ok"
    return result
