#!/usr/bin/env python3
"""Preserve OpenCode's local SQLite history into the private prompt corpus.

The OpenCode database is protected agent state: it can contain raw prompts,
messages, paths, and project details. This tool writes a tracked, counts-only
receipt and private artifacts under .limen-private / external archive storage.
It never deletes the source database.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()
DB_PATH = Path(os.environ.get("LIMEN_OPENCODE_DB", HOME / ".local/share/opencode/opencode.db")).expanduser()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_BASE = PRIVATE_ROOT / "lifecycle" / "opencode-db-intake"
ARCHIVE_BASE = Path(
    os.environ.get("LIMEN_OPENCODE_DB_ARCHIVE_ROOT", "/Volumes/Archive4T/limen-private/opencode-db-intake")
).expanduser()
DOC_PATH = ROOT / "docs" / "opencode-db-corpus-intake.md"
LOG_PATH = ROOT / "logs" / "opencode-db-corpus-intake.jsonl"

COUNT_TABLES = (
    "session",
    "message",
    "part",
    "session_message",
    "session_input",
    "event",
    "project",
    "workspace",
)


def relpath(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        try:
            return str(resolved.relative_to(ROOT))
        except ValueError:
            return str(resolved)


def fmt_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def safe_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def table_count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        row = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
    except sqlite3.Error:
        return None
    return int(row[0]) if row else None


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    except sqlite3.Error:
        return []
    return [str(row[1]) for row in rows]


def integrity_check(path: Path) -> str:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "missing"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def db_pragmas(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for name in ("page_count", "page_size", "freelist_count", "schema_version"):
        try:
            row = conn.execute(f"PRAGMA {name}").fetchone()
        except sqlite3.Error:
            row = None
        if row is not None:
            out[name] = int(row[0])
    return out


def session_rollups(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    rollups: dict[str, dict[str, int]] = {}
    for key, table in (
        ("message_count", "message"),
        ("part_count", "part"),
        ("session_message_count", "session_message"),
    ):
        try:
            rows = conn.execute(f'SELECT session_id, count(*) FROM "{table}" GROUP BY session_id').fetchall()
        except sqlite3.Error:
            rows = []
        for session_id, count in rows:
            rollups.setdefault(str(session_id), {})[key] = int(count)
    return rollups


def export_session_index(conn: sqlite3.Connection, out_path: Path) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rollups = session_rollups(conn)
    columns = table_columns(conn, "session")
    allowed = [
        column
        for column in (
            "id",
            "project_id",
            "parent_id",
            "slug",
            "directory",
            "title",
            "version",
            "summary_additions",
            "summary_deletions",
            "summary_files",
            "permission",
            "time_created",
            "time_updated",
            "time_archived",
            "workspace_id",
            "path",
            "agent",
            "model",
            "cost",
            "tokens_input",
            "tokens_output",
            "tokens_reasoning",
            "tokens_cache_read",
            "tokens_cache_write",
        )
        if column in columns
    ]
    if not allowed:
        out_path.write_bytes(b"")
        return {"path": relpath(out_path), "rows": 0, "bytes": 0, "sha256": sha256_file(out_path)}

    # NB: build the quoted-column list outside the f-string — a nested f-string containing
    # backslash escapes is a SyntaxError before Python 3.12 (breaks the python-311 CI job).
    quoted_columns = ", ".join(f'"{column}"' for column in allowed)
    query = f'SELECT {quoted_columns} FROM "session" ORDER BY time_updated DESC'
    rows = 0
    with gzip.open(out_path, "wt", encoding="utf-8") as fh:
        for row in conn.execute(query):
            record = dict(zip(allowed, row))
            counts = rollups.get(str(record.get("id")), {})
            record.update(
                {
                    "message_count": counts.get("message_count", 0),
                    "part_count": counts.get("part_count", 0),
                    "session_message_count": counts.get("session_message_count", 0),
                }
            )
            fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            rows += 1
    return {"path": relpath(out_path), "rows": rows, "bytes": out_path.stat().st_size, "sha256": sha256_file(out_path)}


def backup_database(source: Path, dest: Path, *, hash_archive: bool) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
        with sqlite3.connect(str(dest)) as dst:
            src.backup(dst)
    check = integrity_check(dest)
    stat = dest.stat()
    result: dict[str, Any] = {
        "path": relpath(dest),
        "bytes": stat.st_size,
        "size": fmt_bytes(stat.st_size),
        "integrity_check": check,
    }
    if hash_archive:
        result["sha256"] = sha256_file(dest)
    return result


def build_snapshot(*, archive: bool, hash_archive: bool, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or safe_run_id()
    if not DB_PATH.exists():
        return {
            "schema": "limen.opencode_db_corpus_intake.v1",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "blocked",
            "blocker": f"database missing: {relpath(DB_PATH)}",
            "source": {"path": relpath(DB_PATH), "exists": False},
        }

    source_stat = DB_PATH.stat()
    with connect_readonly(DB_PATH) as conn:
        source_integrity = integrity_check(DB_PATH)
        table_counts = {table: table_count(conn, table) for table in COUNT_TABLES}
        pragmas = db_pragmas(conn)
        session_bounds = conn.execute(
            "SELECT min(time_created), max(time_updated), round(sum(cost),4), "
            "sum(tokens_input), sum(tokens_output), sum(tokens_reasoning), "
            "sum(tokens_cache_read), sum(tokens_cache_write) FROM session"
        ).fetchone()
        private_dir = PRIVATE_BASE / run_id
        session_index = export_session_index(conn, private_dir / "session-index.jsonl.gz")

    archive_result: dict[str, Any] | None = None
    archive_status = "not_requested"
    if archive:
        if not ARCHIVE_BASE.parent.exists() or not os.access(ARCHIVE_BASE.parent, os.W_OK):
            archive_status = "blocked_archive_unavailable"
            archive_result = {"error": f"archive parent unavailable or not writable: {relpath(ARCHIVE_BASE.parent)}"}
        else:
            archive_path = ARCHIVE_BASE / run_id / "opencode.db"
            archive_result = backup_database(DB_PATH, archive_path, hash_archive=hash_archive)
            archive_status = "verified" if archive_result.get("integrity_check") == "ok" else "failed_integrity"

    status = "archived_private_intake" if archive_status == "verified" else "indexed_private_intake"
    if source_integrity != "ok" or archive_status.startswith("blocked") or archive_status == "failed_integrity":
        status = "blocked"

    return {
        "schema": "limen.opencode_db_corpus_intake.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id,
        "status": status,
        "source": {
            "path": relpath(DB_PATH),
            "exists": True,
            "bytes": source_stat.st_size,
            "size": fmt_bytes(source_stat.st_size),
            "mtime": int(source_stat.st_mtime),
            "integrity_check": source_integrity,
            "pragmas": pragmas,
        },
        "table_counts": table_counts,
        "session_bounds": {
            "first_time_created": session_bounds[0],
            "last_time_updated": session_bounds[1],
            "cost_sum": session_bounds[2],
            "tokens_input": session_bounds[3],
            "tokens_output": session_bounds[4],
            "tokens_reasoning": session_bounds[5],
            "tokens_cache_read": session_bounds[6],
            "tokens_cache_write": session_bounds[7],
        },
        "private_session_index": session_index,
        "archive": archive_result,
        "archive_status": archive_status,
        "retention_decision": {
            "local_db_deleted": False,
            "decision": "retain_source_until_vendor_retention_decision",
            "gate": "do not delete source database outright; a future retention action must reference this intake receipt and prove restore/readback first",
        },
    }


def render(snapshot: dict[str, Any]) -> str:
    source = snapshot.get("source") or {}
    counts = snapshot.get("table_counts") if isinstance(snapshot.get("table_counts"), dict) else {}
    archive = snapshot.get("archive") if isinstance(snapshot.get("archive"), dict) else None
    index = snapshot.get("private_session_index") if isinstance(snapshot.get("private_session_index"), dict) else {}
    lines = [
        "# OpenCode DB Corpus Intake",
        "",
        f"Generated: `{snapshot.get('generated_at')}`",
        f"Status: `{snapshot.get('status')}`",
        f"Run ID: `{snapshot.get('run_id', 'none')}`",
        "",
        "## Source",
        "",
        f"- Path: `{source.get('path')}`.",
        f"- Size: `{source.get('size', 'unknown')}`.",
        f"- Integrity check: `{source.get('integrity_check', 'unknown')}`.",
        "",
        "## Private Intake",
        "",
        f"- Session index: `{index.get('path', 'none')}`.",
        f"- Session rows indexed: `{index.get('rows', 0)}`.",
        f"- Session index SHA-256: `{index.get('sha256', 'none')}`.",
        "",
        "## External Archive",
        "",
        f"- Archive status: `{snapshot.get('archive_status')}`.",
    ]
    if archive:
        lines.extend(
            [
                f"- Archive path: `{archive.get('path', 'none')}`.",
                f"- Archive size: `{archive.get('size', 'unknown')}`.",
                f"- Archive integrity check: `{archive.get('integrity_check', 'unknown')}`.",
            ]
        )
        if archive.get("sha256"):
            lines.append(f"- Archive SHA-256: `{archive.get('sha256')}`.")
        if archive.get("error"):
            lines.append(f"- Archive error: `{archive.get('error')}`.")
    lines += [
        "",
        "## Table Counts",
        "",
        "| Table | Rows |",
        "|---|---:|",
    ]
    for table in COUNT_TABLES:
        lines.append(f"| `{table}` | `{counts.get(table, 0)}` |")
    lines += [
        "",
        "## Retention Gate",
        "",
        "- The tracked receipt is counts-only; raw OpenCode prompt/message content stays private.",
        "- The local database was not deleted.",
        "- Any future local deletion or move must reference this intake receipt, prove archive readback, and record the retention decision.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any]) -> None:
    run_id = str(snapshot.get("run_id") or safe_run_id())
    private_dir = PRIVATE_BASE / run_id
    private_dir.mkdir(parents=True, exist_ok=True)
    private_manifest = private_dir / "manifest.json"
    manifest_payload = {**snapshot, "private_manifest": {"path": relpath(private_manifest)}}
    private_manifest.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    snapshot["private_manifest"] = {"path": relpath(private_manifest), "sha256": sha256_file(private_manifest)}

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(render(snapshot), encoding="utf-8")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "generated_at": snapshot.get("generated_at"),
                    "run_id": snapshot.get("run_id"),
                    "status": snapshot.get("status"),
                    "source_size": (snapshot.get("source") or {}).get("size"),
                    "archive_status": snapshot.get("archive_status"),
                    "private_manifest": snapshot.get("private_manifest"),
                },
                sort_keys=True,
            )
            + "\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Record OpenCode DB private corpus intake.")
    parser.add_argument("--write", action="store_true", help="write tracked doc and private manifest")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--archive", action="store_true", help="write a verified SQLite backup to external archive")
    parser.add_argument(
        "--hash-archive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="compute SHA-256 for archived DB when --archive is used",
    )
    args = parser.parse_args()

    snapshot = build_snapshot(archive=args.archive, hash_archive=args.hash_archive)
    if args.write:
        write_outputs(snapshot)
    if args.json or not args.write:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(
            f"opencode-db-corpus-intake: {snapshot.get('status')} "
            f"source={(snapshot.get('source') or {}).get('size')} archive={snapshot.get('archive_status')}"
        )
    return 0 if snapshot.get("status") != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
