#!/usr/bin/env python3
"""Inventory local session/corpus material from Limen without committing raw private data.

This is the Limen control-plane view over the already-built corpus organs:

* session-meta: producer for redacted, deduped, multi-provider atoms
* knowledge-corpus: distilled corpus faces and THE ONE
* conversation-corpus-engine: product/research engine for corpus promotion
* .limen-private/session-corpus: ignored local cartridge for raw/private manifests and,
  when explicitly requested, content-addressed object copies

Default behavior is read-only. Use --write to refresh the tracked ledger plus an ignored
private inventory. Use --materialize with --write to copy the last N days of raw local
session files into the ignored object store.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
HOME = Path.home()
WORKSPACE = ROOT.parent
DOC_PATH = ROOT / "docs" / "session-corpus-ledger.md"
LOG_PATH = ROOT / "logs" / "session-corpus-ledger.json"
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INVENTORY = PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"

LOCAL_SOURCES = [
    ("codex-sessions", HOME / ".codex" / "sessions", ("*",)),
    ("codex-history", HOME / ".codex", ("history.jsonl",)),
    ("codex-attachments", HOME / ".codex" / "attachments", ("*",)),
    ("codex-goals-state", HOME / ".codex", ("goals_*.sqlite*", "state_*.sqlite*")),
    ("codex-app-sqlite", HOME / ".codex" / "sqlite", ("*.db", "*.sqlite", "*.db-*", "*.sqlite-*")),
    ("codex-shell-snapshots", HOME / ".codex" / "shell_snapshots", ("*",)),
    ("claude-projects", HOME / ".claude" / "projects", ("*",)),
    ("claude-usage-session-meta", HOME / ".claude" / "usage-data" / "session-meta", ("*",)),
    ("claude-usage-facets", HOME / ".claude" / "usage-data" / "facets", ("*",)),
    ("claude-tasks", HOME / ".claude" / "tasks", ("*",)),
    ("claude-plans", HOME / ".claude" / "plans", ("*",)),
    ("claude-file-history", HOME / ".claude" / "file-history", ("*",)),
    (
        "chatgpt-desktop-app-support",
        HOME / "Library" / "Application Support" / "com.openai.chat",
        ("*.data", "*.json", "*.jsonl", "*.md", "*.txt"),
    ),
    (
        "chatgpt-atlas-app-support",
        HOME / "Library" / "Application Support" / "OpenAI" / "ChatGPT Atlas",
        ("*.data", "*.json", "*.jsonl", "*.md", "*.txt"),
    ),
    (
        "claude-desktop-indexeddb",
        HOME / "Library" / "Application Support" / "Claude" / "IndexedDB",
        ("*.ldb", "*.log", "*.sqlite", "*.db", "*.json", "*.jsonl"),
    ),
    (
        "gemini-desktop-stores",
        HOME / "Library" / "Application Support" / "com.google.GeminiMacOS",
        (
            "*.data",
            "*.json",
            "*.jsonl",
            "*.ldb",
            "*.log",
            "*.sqlite",
            "*.db",
            "*.store",
            "*.store-*",
            "*.md",
            "*.txt",
        ),
    ),
    (
        "perplexity-desktop-stores",
        HOME / "Library" / "Application Support" / "ai.perplexity.macv3",
        ("*.data", "*.json", "*.jsonl", "*.ldb", "*.log", "*.sqlite", "*.db", "*.plist", "*.md", "*.txt"),
    ),
]

EXTERNAL_SOURCE_PREFIX = "external-session"
EXTERNAL_PATTERNS = (
    "*.data",
    "*.json",
    "*.jsonl",
    "*.md",
    "*.txt",
    "*.log",
    "*.sqlite",
    "*.sqlite-*",
    "*.db",
    "*.db-*",
    "*.csv",
    "*.yaml",
    "*.yml",
)
EXTERNAL_SKIP_DIRS = {
    ".Trash",
    ".Spotlight-V100",
    ".TemporaryItems",
    ".Trashes",
    ".fseventsd",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".next",
    ".turbo",
    "dist",
    "build",
    "target",
    "DerivedData",
    "Library",
}

ORGANS = [
    {
        "name": "session-meta",
        "role": "producer: redacted, deduped multi-provider atoms",
        "path": WORKSPACE / "session-meta",
    },
    {
        "name": "knowledge-corpus",
        "role": "distillation target: collection, reduced faces, THE ONE",
        "path": WORKSPACE / "knowledge-corpus",
    },
    {
        "name": "conversation-corpus-engine",
        "role": "product/research engine: provider import and corpus promotion",
        "path": WORKSPACE / "conversation-corpus-engine",
    },
]


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


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return val if val > 0 else default


def external_session_sources() -> list[tuple[str, Path, tuple[str, ...]]]:
    raw = os.environ.get("LIMEN_EXTERNAL_SESSION_ROOTS", "")
    roots = [part for part in raw.split(os.pathsep) if part.strip()]
    sources: list[tuple[str, Path, tuple[str, ...]]] = []
    for idx, part in enumerate(roots, start=1):
        root = Path(part.strip()).expanduser()
        name = root.name or f"root-{idx}"
        sources.append((f"{EXTERNAL_SOURCE_PREFIX}:{name}", root, EXTERNAL_PATTERNS))
    return sources


def local_sources() -> list[tuple[str, Path, tuple[str, ...]]]:
    return [*LOCAL_SOURCES, *external_session_sources()]


def is_external_source(source: str) -> bool:
    return source.startswith(f"{EXTERNAL_SOURCE_PREFIX}:")


def external_match(path: Path, patterns: tuple[str, ...]) -> bool:
    name = path.name.lower()
    return any(fnmatch.fnmatch(name, pattern.lower()) for pattern in patterns)


def external_candidates(root: Path, patterns: tuple[str, ...]) -> tuple[list[Path], dict[str, Any]]:
    max_files = env_positive_int("LIMEN_EXTERNAL_SESSION_MAX_FILES_PER_ROOT", 2000)
    max_dirs = env_positive_int("LIMEN_EXTERNAL_SESSION_MAX_DIRS_PER_ROOT", 5000)
    max_depth = env_positive_int("LIMEN_EXTERNAL_SESSION_MAX_DEPTH", 5)
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        resolved = root.expanduser()
    limit = {
        "root": relpath(resolved),
        "max_files": max_files,
        "max_dirs": max_dirs,
        "max_depth": max_depth,
        "dirs_seen": 0,
        "candidate_files": 0,
        "truncated": False,
        "reason": None,
    }
    if not resolved.exists():
        limit["reason"] = "missing-root"
        return [], limit
    if resolved.is_file():
        candidates = [resolved] if external_match(resolved, patterns) else []
        limit["candidate_files"] = len(candidates)
        return candidates, limit

    candidates: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(resolved):
        current = Path(dirpath)
        limit["dirs_seen"] += 1
        try:
            depth = len(current.relative_to(resolved).parts)
        except ValueError:
            depth = 0
        if limit["dirs_seen"] >= max_dirs:
            limit["truncated"] = True
            limit["reason"] = "dir-cap"
            dirnames[:] = []
        else:
            dirnames[:] = sorted(
                name for name in dirnames if name not in EXTERNAL_SKIP_DIRS and not name.endswith(".noindex")
            )
            if depth >= max_depth:
                dirnames[:] = []

        for filename in sorted(filenames):
            path = current / filename
            if not external_match(path, patterns):
                continue
            candidates.append(path)
            if len(candidates) >= max_files:
                limit["candidate_files"] = len(candidates)
                limit["truncated"] = True
                limit["reason"] = "file-cap"
                return candidates, limit

    limit["candidate_files"] = len(candidates)
    return candidates, limit


def source_candidates(
    source: str,
    root: Path,
    patterns: tuple[str, ...],
) -> tuple[list[Path], dict[str, Any] | None]:
    if is_external_source(source):
        return external_candidates(root, patterns)
    if not root.exists():
        return [], None
    if root.is_file():
        return [root], None
    return [path for pattern in patterns for path in root.rglob(pattern)], None


def scan_local_files(days: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cutoff = None if days is None else dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
    rows: list[dict[str, Any]] = []
    scan_limits: list[dict[str, Any]] = []
    for source, root, patterns in local_sources():
        seen: set[Path] = set()
        candidates, scan_limit = source_candidates(source, root, patterns)
        source_files = 0
        source_bytes = 0
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
                    "root": str(root),
                    "path": str(path),
                    "display_path": relpath(path),
                    "size": st.st_size,
                    "mtime": iso_from_ts(st.st_mtime),
                }
            )
            source_files += 1
            source_bytes += st.st_size
        if scan_limit:
            scan_limit["source"] = source
            scan_limit["accepted_files"] = source_files
            scan_limit["accepted_bytes"] = source_bytes
            scan_limits.append(scan_limit)
    rows.sort(key=lambda r: (r["mtime"] or "", r["source"], r["path"]), reverse=True)
    return rows, scan_limits


def iter_local_files(days: int | None) -> list[dict[str, Any]]:
    rows, _scan_limits = scan_local_files(days)
    return rows


def summarize_local(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        root = row.get("root")
        if root is None:
            root = next(root for name, root, _ in local_sources() if name == row["source"])
        item = by_source.setdefault(
            row["source"],
            {
                "source": row["source"],
                "root": relpath(Path(root)),
                "files": 0,
                "bytes": 0,
                "newest": None,
            },
        )
        item["files"] += 1
        item["bytes"] += int(row["size"])
        if item["newest"] is None or (row["mtime"] or "") > item["newest"]:
            item["newest"] = row["mtime"]
    return sorted(by_source.values(), key=lambda r: (-r["bytes"], r["source"]))


def missing_local_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    present = {str(row.get("source")) for row in rows}
    missing: list[dict[str, Any]] = []
    for source, root, _patterns in local_sources():
        if is_external_source(source) or source in present:
            continue
        expanded = root.expanduser()
        reason = "missing-root"
        try:
            if expanded.exists():
                reason = "no-matching-files"
        except OSError:
            reason = "unreadable-root"
        missing.append({"source": source, "root": relpath(expanded), "reason": reason})
    return missing


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def materialize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    objects = PRIVATE_ROOT / "objects"
    copied = 0
    already = 0
    bytes_copied = 0
    failed: list[dict[str, str]] = []
    for row in rows:
        path = Path(row["path"])
        try:
            digest = sha256_file(path)
            dest = objects / digest[:2] / digest
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                already += 1
            else:
                shutil.copy2(path, dest)
                copied += 1
                bytes_copied += int(row["size"])
            row["sha256"] = digest
            row["object"] = str(dest.relative_to(PRIVATE_ROOT))
        except OSError as exc:
            failed.append({"path": row["display_path"], "error": str(exc)})
    object_files = [p for p in objects.rglob("*") if p.is_file()] if objects.is_dir() else []
    object_bytes = 0
    for path in object_files:
        try:
            object_bytes += path.stat().st_size
        except OSError:
            pass
    return {
        "objects_root": str(objects),
        "copied": copied,
        "already_present": already,
        "bytes_copied": bytes_copied,
        "object_count": len(object_files),
        "object_bytes": object_bytes,
        "failed": failed,
    }


def object_store_snapshot() -> dict[str, Any]:
    objects = PRIVATE_ROOT / "objects"
    files = [path for path in objects.rglob("*") if path.is_file()] if objects.is_dir() else []
    total = 0
    newest = None
    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        total += st.st_size
        mtime = iso_from_ts(st.st_mtime)
        if newest is None or (mtime or "") > newest:
            newest = mtime
    return {
        "present": objects.is_dir(),
        "root": str(objects),
        "object_count": len(files),
        "object_bytes": total,
        "newest": newest,
    }


def git_status(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists() and not (path / ".git").is_file():
        return {"present": path.exists(), "git": False, "summary": "not a git repo"}
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "status", "--short", "--branch"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"present": True, "git": True, "summary": f"status unavailable: {exc}"}
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    branch = lines[0] if lines else "unknown"
    dirty = [ln for ln in lines[1:] if ln.strip()]
    return {
        "present": True,
        "git": True,
        "summary": branch,
        "dirty_entries": len(dirty),
        "dirty": bool(dirty),
    }


def count_jsonl(path: Path, *, source_counts: bool = False) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "path": str(path)}
    count = 0
    by_source: dict[str, int] = {}
    latest_mtime = iso_from_ts(path.stat().st_mtime)
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            count += 1
            if source_counts:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                src = obj.get("source") or "unknown"
                by_source[src] = by_source.get(src, 0) + 1
    out: dict[str, Any] = {"present": True, "path": str(path), "lines": count, "mtime": latest_mtime}
    if source_counts:
        out["by_source"] = dict(sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0])))
    return out


def substrate_snapshot() -> dict[str, Any]:
    sm = WORKSPACE / "session-meta"
    kc = WORKSPACE / "knowledge-corpus"
    one = kc / "00-THE-ONE.md"
    reduced = kc / "reduced"
    return {
        "organs": [{**organ, "path": str(organ["path"]), "git": git_status(organ["path"])} for organ in ORGANS],
        "session_meta": {
            "manifest": count_jsonl(sm / "ingest" / "manifest.jsonl", source_counts=True),
            "atoms": count_jsonl(sm / "ingest" / "atoms.jsonl", source_counts=False),
        },
        "knowledge_corpus": {
            "the_one_present": one.is_file(),
            "the_one_mtime": iso_from_ts(one.stat().st_mtime) if one.is_file() else None,
            "reduced_faces": len(list(reduced.glob("*.md"))) if reduced.is_dir() else 0,
        },
        "limen": {
            "quicken": str(ROOT / "scripts" / "quicken.py"),
            "codex_quicken": str(ROOT / "scripts" / "codex-quicken.py"),
            "corpus_converge": str(ROOT / "scripts" / "corpus-converge.py"),
            "ingest_coverage": str(ROOT / "scripts" / "ingest-coverage.py"),
        },
        "quicken": quicken_snapshot(),
        "codex_quicken": codex_quicken_snapshot(),
    }


def quicken_snapshot() -> dict[str, Any]:
    path = ROOT / "logs" / "session-lifecycle.jsonl"
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
                    event = json.loads(line)
                except ValueError:
                    continue
                if "sessions" in event:
                    last = event
    except OSError:
        return {"present": False, "path": str(path)}
    if not last:
        return {"present": False, "path": str(path)}
    sessions = int(last.get("sessions", 0) or 0)
    stalled = len(last.get("stalled") or [])
    alive = len(last.get("alive") or [])
    done = len(last.get("done") or [])
    closed = max(0, sessions - stalled - alive - done)
    return {
        "present": True,
        "path": str(path),
        "ts": iso_from_ts(float(last.get("ts") or 0)),
        "sessions": sessions,
        "stalled": stalled,
        "alive": alive,
        "done": done,
        "closed": closed,
        "reaped": len(last.get("reaped") or []),
    }


def codex_quicken_snapshot() -> dict[str, Any]:
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
    except OSError:
        return {"present": False, "path": str(path)}
    if not last:
        return {"present": False, "path": str(path)}
    return {
        "present": True,
        "path": str(path),
        "ts": iso_from_ts(float(last.get("ts") or 0)),
        "sessions": int(last.get("session_count", 0) or 0),
        "by_state": last.get("by_state") or {},
        "by_family": last.get("by_family") or {},
    }


def screenshot_snapshot() -> dict[str, Any]:
    root = PRIVATE_ROOT / "screenshots"
    if not root.is_dir():
        return {"present": False, "root": str(root), "files": 0, "bytes": 0}
    files = sorted(path for path in root.rglob("*.png") if path.is_file())
    total = 0
    newest = None
    batches: dict[str, int] = {}
    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        total += st.st_size
        mtime = iso_from_ts(st.st_mtime)
        if newest is None or (mtime or "") > newest:
            newest = mtime
        try:
            batch = str(path.parent.relative_to(root))
        except ValueError:
            batch = "."
        batches[batch] = batches.get(batch, 0) + 1
    return {
        "present": True,
        "root": str(root),
        "files": len(files),
        "bytes": total,
        "newest": newest,
        "batches": dict(sorted(batches.items())),
    }


def infer_roadblocks(snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    roadblocks: list[str] = []
    organs = {o["name"]: o for o in snapshot["organs"]}
    sm_git = organs.get("session-meta", {}).get("git", {})
    if sm_git.get("dirty") or ("behind" in sm_git.get("summary", "")):
        roadblocks.append(
            "session-meta is not clean/in-sync; do not mutate it from Limen until its existing "
            "dirty and divergent work is preserved or merged."
        )
    for name, organ in organs.items():
        if name == "session-meta":
            continue
        git = organ.get("git", {})
        if git.get("dirty"):
            roadblocks.append(
                f"{name} has {git.get('dirty_entries', 0)} dirty entries; record or preserve that "
                "owner-state before treating the corpus substrate as fully clean."
            )
    if rows:
        roadblocks.append(
            "Local Claude/Codex app stores are live private data; screenshots are only UI evidence. "
            "Canonical ingestion must come from the filesystem stores, not from the screenshots."
        )
    atoms = snapshot["session_meta"]["atoms"]
    if not atoms.get("present"):
        roadblocks.append("session-meta atoms.jsonl is missing, so corpus-converge has no atom substrate.")
    manifest = snapshot["session_meta"]["manifest"]
    if manifest.get("present"):
        try:
            mt = dt.datetime.fromisoformat(str(manifest["mtime"]).replace("Z", "+00:00"))
            age = dt.datetime.now(dt.timezone.utc) - mt
            if age.total_seconds() > 2 * 86400:
                roadblocks.append("session-meta manifest is stale by more than two days.")
        except (TypeError, ValueError):
            pass
    if not snapshot.get("quicken", {}).get("present"):
        roadblocks.append(
            "Claude has a lifecycle organ (`scripts/quicken.py`), but no recent journal was found; "
            "refresh it before treating Claude FleetView lifecycle as current."
        )
    if not snapshot.get("codex_quicken", {}).get("present"):
        roadblocks.append(
            "Codex has a lifecycle classifier (`scripts/codex-quicken.py`), but no journal was found; "
            "run it before relying on Codex app history as typed lifecycle coverage."
        )
    return roadblocks


def render_markdown(
    snapshot: dict[str, Any], rows: list[dict[str, Any]], args: argparse.Namespace, mat: dict[str, Any] | None
) -> str:
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    local = summarize_local(rows)
    total_files = sum(int(r["files"]) for r in local)
    total_bytes = sum(int(r["bytes"]) for r in local)
    lines = [
        "# Session Corpus Ledger",
        "",
        f"Generated: `{generated}`",
        f"Horizon: `{('all local history' if args.days is None else f'last {args.days} days')}`",
        "",
        "## Canonical Decision",
        "",
        "- Limen is the control plane and visible ledger for session/corpus lifecycle.",
        "- `session-meta` remains the producer for redacted, deduped, multi-provider atoms.",
        "- `knowledge-corpus` remains the distillation target consumed by `corpus-converge.py`.",
        "- `prompt-lifecycle-ledger.py` is the redacted crosswalk from local prompts/sessions to "
        "worktrees, tasks, GitHub receipts, and cloud probes.",
        "- Raw personal/session data is private local material. It belongs under "
        "`./.limen-private/session-corpus/` when materialized, never in public Git history.",
        "- The app screenshots are coverage hints, not canonical input. Canonical input is the local "
        "Claude/Codex/session-meta filesystem state.",
        "- External/archive roots are opt-in through `LIMEN_EXTERNAL_SESSION_ROOTS`; they are bounded "
        "inventory inputs, not deletion targets.",
        "",
        "## Local Session Sources",
        "",
        f"Total seen: `{total_files}` files, `{fmt_bytes(total_bytes)}`.",
        "",
        "| Source | Root | Files | Size | Newest |",
        "|---|---:|---:|---:|---|",
    ]
    for item in local:
        lines.append(
            f"| `{item['source']}` | `{item['root']}` | {item['files']} | "
            f"{fmt_bytes(int(item['bytes']))} | `{item['newest'] or 'n/a'}` |"
        )
    if not local:
        lines.append("| none | n/a | 0 | 0 B | n/a |")

    missing_sources = missing_local_sources(rows)
    if missing_sources:
        lines += [
            "",
            "## Missing Local App Sources",
            "",
            "These are known local app/store adapters with no matched files in this scan. This is a "
            "coverage signal only; roots are not deletion targets.",
            "",
            "| Source | Root | Reason |",
            "|---|---|---|",
        ]
        for item in missing_sources:
            lines.append(f"| `{item['source']}` | `{item['root']}` | `{item['reason']}` |")

    scan_limits = snapshot.get("scan_limits") or []
    if scan_limits:
        lines += [
            "",
            "## External Scan Bounds",
            "",
            "| Source | Root | Accepted | Size | Dirs Seen | Caps | Truncated |",
            "|---|---|---:|---:|---:|---|---|",
        ]
        for item in scan_limits:
            caps = f"files {item.get('max_files')}, dirs {item.get('max_dirs')}, depth {item.get('max_depth')}"
            truncated = item.get("reason") if item.get("truncated") else "no"
            lines.append(
                f"| `{item.get('source')}` | `{item.get('root')}` | "
                f"{item.get('accepted_files', 0)} | "
                f"{fmt_bytes(int(item.get('accepted_bytes', 0)))} | "
                f"{item.get('dirs_seen', 0)} | `{caps}` | `{truncated}` |"
            )

    lines += [
        "",
        "## Existing Organs",
        "",
        "| Organ | Role | Path | Git state |",
        "|---|---|---|---|",
    ]
    for organ in snapshot["organs"]:
        git = organ["git"]
        dirty = ""
        if git.get("dirty_entries"):
            dirty = f"; {git['dirty_entries']} dirty entries"
        lines.append(
            f"| `{organ['name']}` | {organ['role']} | `{relpath(Path(organ['path']))}` | "
            f"`{git.get('summary', 'unknown')}{dirty}` |"
        )

    manifest = snapshot["session_meta"]["manifest"]
    atoms = snapshot["session_meta"]["atoms"]
    kc = snapshot["knowledge_corpus"]
    lines += [
        "",
        "## Substrate Counts",
        "",
        f"- `session-meta/ingest/manifest.jsonl`: "
        f"{manifest.get('lines', 0):,} records, mtime `{manifest.get('mtime', 'missing')}`.",
        f"- `session-meta/ingest/atoms.jsonl`: "
        f"{atoms.get('lines', 0):,} atoms, mtime `{atoms.get('mtime', 'missing')}`.",
        f"- `knowledge-corpus`: `{kc['reduced_faces']}` reduced faces; "
        f"`00-THE-ONE.md` present: `{kc['the_one_present']}`.",
    ]
    if manifest.get("by_source"):
        top = list(manifest["by_source"].items())[:8]
        lines.append("- Top manifest sources: " + ", ".join(f"`{src}` {count:,}" for src, count in top) + ".")

    q = snapshot.get("quicken", {})
    lines += [
        "",
        "## Session Lifecycle",
        "",
    ]
    if q.get("present"):
        lines += [
            f"- Last `quicken.py` journal: `{q.get('ts')}`.",
            f"- Claude FleetView sessions classified: `{q.get('sessions', 0)}` total; "
            f"`{q.get('stalled', 0)}` stalled, `{q.get('closed', 0)}` closed, "
            f"`{q.get('alive', 0)}` alive, `{q.get('done', 0)}` done.",
            f"- Reaped worktrees in that pass: `{q.get('reaped', 0)}`.",
        ]
    else:
        lines.append("- No `quicken.py` journal found yet.")
    cq = snapshot.get("codex_quicken", {})
    if cq.get("present"):
        states = ", ".join(f"`{state}` {count}" for state, count in sorted((cq.get("by_state") or {}).items()))
        families = ", ".join(
            f"`{family}` {count}"
            for family, count in sorted((cq.get("by_family") or {}).items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        )
        lines += [
            f"- Last `codex-quicken.py` journal: `{cq.get('ts')}`.",
            f"- Codex sessions classified: `{cq.get('sessions', 0)}` total{'; ' + states if states else ''}.",
            f"- Top Codex lifecycle families: {families or 'none'}.",
        ]
    else:
        lines.append("- No `codex-quicken.py` journal found yet.")

    lines += [
        "",
        "## Private Cartridge",
        "",
        f"- Private root: `{relpath(PRIVATE_ROOT)}`.",
        f"- Private inventory: `{relpath(PRIVATE_INVENTORY)}`.",
        "- `.limen-private/` is ignored by Git; it is the local raw/private landing zone.",
    ]
    if mat:
        lines.append(
            f"- Materialized objects this run: copied `{mat['copied']}`, already present "
            f"`{mat['already_present']}`, bytes copied `{fmt_bytes(int(mat['bytes_copied']))}`."
        )
        lines.append(
            f"- Private object store now holds `{mat.get('object_count', 0)}` unique objects, "
            f"`{fmt_bytes(int(mat.get('object_bytes', 0)))}`."
        )
        if mat["failed"]:
            lines.append(f"- Materialization failures: `{len(mat['failed'])}`.")
    else:
        lines.append("- Raw object materialization was not requested on this run.")
        object_store = snapshot.get("object_store", {})
        if object_store.get("object_count"):
            lines.append(
                f"- Private object store currently holds `{object_store.get('object_count', 0)}` "
                f"unique objects, `{fmt_bytes(int(object_store.get('object_bytes', 0)))}`."
            )

    screenshots = snapshot.get("private_screenshots", {})
    if screenshots.get("files"):
        batch_bits = ", ".join(f"`{batch}` {count}" for batch, count in screenshots.get("batches", {}).items())
        lines += [
            f"- Private screenshot evidence: `{screenshots['files']}` PNG artifacts, "
            f"`{fmt_bytes(int(screenshots.get('bytes', 0)))}`, newest `{screenshots.get('newest')}`.",
            f"- Screenshot batches: {batch_bits or 'none'}.",
        ]
    else:
        lines.append("- Private screenshot evidence: none recorded yet.")

    screenshot_receipts = sorted((ROOT / "docs").glob("session-screenshot-intake-*.md"))
    drain_queues = sorted((ROOT / "docs").glob("session-lifecycle-drain-queue-*.md"))
    blocker_receipts = sorted((ROOT / "docs").glob("session-lifecycle-blockers.md"))
    attack_paths = sorted((ROOT / "docs").glob("session-attack-paths.md"))
    priority_maps = sorted((ROOT / "docs").glob("prompt-priority-map.md"))
    atom_ledgers = sorted((ROOT / "docs").glob("prompt-atom-ledger.md"))
    batch_review_ledgers = sorted((ROOT / "docs").glob("prompt-batch-review-ledger.md"))
    packet_ledgers = sorted((ROOT / "docs").glob("prompt-packet-ledger.md"))
    packet_resolution_receipts = sorted((ROOT / "docs").glob("prompt-packet-resolution-receipts.json"))
    capability_receipts = sorted((ROOT / "docs").glob("capability-substrate-ledger.md"))
    if (
        screenshot_receipts
        or drain_queues
        or blocker_receipts
        or attack_paths
        or priority_maps
        or atom_ledgers
        or batch_review_ledgers
        or packet_ledgers
        or packet_resolution_receipts
        or capability_receipts
    ):
        lines += [
            "",
            "## Tracked Intake Receipts",
            "",
        ]
        for path in screenshot_receipts:
            lines.append(f"- Screenshot intake: `{path.relative_to(ROOT)}`.")
        for path in drain_queues:
            lines.append(f"- Session lifecycle drain queue: `{path.relative_to(ROOT)}`.")
        for path in blocker_receipts:
            lines.append(f"- Session lifecycle blockers: `{path.relative_to(ROOT)}`.")
        for path in attack_paths:
            lines.append(f"- Session attack paths: `{path.relative_to(ROOT)}`.")
        for path in priority_maps:
            lines.append(f"- Prompt priority map: `{path.relative_to(ROOT)}`.")
        for path in atom_ledgers:
            lines.append(f"- Canonical ask-atom control ledger: `{path.relative_to(ROOT)}`.")
        for path in batch_review_ledgers:
            lines.append(f"- Prompt batch review ledger: `{path.relative_to(ROOT)}`.")
        for path in packet_ledgers:
            lines.append(f"- Prompt packet ledger: `{path.relative_to(ROOT)}`.")
        for path in packet_resolution_receipts:
            lines.append(f"- Prompt packet resolution receipts: `{path.relative_to(ROOT)}`.")
        for path in capability_receipts:
            lines.append(f"- Capability substrate ledger: `{path.relative_to(ROOT)}`.")

    lines += [
        "",
        "## Roadblocks And Potholes",
        "",
    ]
    for rb in infer_roadblocks(snapshot, rows):
        lines.append(f"- {rb}")

    lines += [
        "",
        "## Commands",
        "",
        "- Refresh the visible all-history ledger: `python3 scripts/session-corpus-ledger.py --write --all`",
        "- Refresh a bounded ledger: `python3 scripts/session-corpus-ledger.py --write --days 7`",
        "- Absorb raw local objects into the ignored cartridge: "
        "`python3 scripts/session-corpus-ledger.py --write --all --materialize`",
        "- Refresh local/remote/cloud prompt lifecycle: `python3 scripts/prompt-lifecycle-ledger.py --write --all`",
        "- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`",
        "- Refresh parked blockers: `python3 scripts/session-blockers-ledger.py --write`",
        "- Refresh ranked attack paths: `python3 scripts/session-attack-paths.py --write`",
        "- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`",
        "- Refresh prompt ask atoms: `python3 scripts/prompt-atom-ledger.py --scan --write`",
        "- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`",
        "- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`",
        "- Rebuild session-meta atoms after preserving its dirty work: "
        "`cd ~/Workspace/session-meta && ./ingest/refresh-atoms.sh`",
        "- Refresh Limen coverage view: `python3 scripts/ingest-coverage.py`",
        "- Classify Codex app/session lifecycle: `python3 scripts/codex-quicken.py --all --apply`",
        "",
    ]
    return "\n".join(lines)


def build_snapshot(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    rows, scan_limits = scan_local_files(args.days)
    mat = materialize(rows) if args.materialize else None
    snapshot = substrate_snapshot()
    snapshot["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    snapshot["horizon_days"] = args.days
    snapshot["local_summary"] = summarize_local(rows)
    snapshot["scan_limits"] = scan_limits
    snapshot["private_root"] = str(PRIVATE_ROOT)
    snapshot["materialization"] = mat
    snapshot["object_store"] = object_store_snapshot()
    snapshot["private_screenshots"] = screenshot_snapshot()
    return snapshot, rows, mat


def write_outputs(snapshot: dict[str, Any], rows: list[dict[str, Any]], markdown: str) -> None:
    DOC_PATH.write_text(markdown)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps({**snapshot, "local_files": rows}, indent=2))
    PRIVATE_INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INVENTORY.write_text(json.dumps({**snapshot, "local_files": rows}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the Limen session/corpus lifecycle ledger.")
    parser.add_argument("--days", type=int, default=None, help="local app-store horizon to inventory")
    parser.add_argument("--all", action="store_true", help="inventory all local app-store history")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private inventory")
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="copy raw local files into the ignored content-addressed object store",
    )
    args = parser.parse_args()
    if args.all:
        args.days = None
    if args.days is not None and args.days <= 0:
        args.days = None
    if args.materialize and not args.write:
        parser.error("--materialize requires --write")

    snapshot, rows, mat = build_snapshot(args)
    markdown = render_markdown(snapshot, rows, args, mat)
    if args.write:
        write_outputs(snapshot, rows, markdown)
    else:
        print(markdown)
    total = sum(int(r["files"]) for r in snapshot["local_summary"])
    size = sum(int(r["bytes"]) for r in snapshot["local_summary"])
    horizon = "all history" if args.days is None else f"{args.days}d"
    msg = f"session-corpus-ledger: {total} files, {fmt_bytes(size)} over {horizon}"
    if mat:
        msg += f"; materialized copied={mat['copied']} already={mat['already_present']}"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
