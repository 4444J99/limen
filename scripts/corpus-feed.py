#!/usr/bin/env python3
"""Refresh the multi-provider session corpus feed without exposing raw prompts.

The heartbeat uses this as the named CORPUS_FEED organ. It records only provider
counts/bytes/newest mtimes in Limen, then delegates raw prompt atomization to
session-meta's ingest pipeline. Raw app/session files stay in their source stores
or in the ignored private cartridge; this script writes no raw transcript content
to tracked Limen files.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli" / "src"))

from limen.session_atoms import AtomStreamError, atoms_store_root, atoms_summary  # noqa: E402

HOME = Path.home()
LOGS = ROOT / "logs"
STATE = LOGS / "corpus-feed-state.json"
SESSION_META = Path(os.environ.get("LIMEN_SESSION_META", HOME / "Workspace" / "session-meta")).expanduser()
TIMEOUT = int(os.environ.get("LIMEN_CORPUS_FEED_TIMEOUT", "600"))

PROVIDER_ROOTS = {
    "claude-projects": HOME / ".claude" / "projects",
    "codex-sessions": HOME / ".local" / "share" / "codex" / "sessions",
    "chatgpt-desktop": HOME / "Library" / "Application Support" / "com.openai.chat",
    "gemini-desktop": HOME / "Library" / "Application Support" / "com.google.GeminiMacOS",
    "perplexity-desktop": HOME / "Library" / "Application Support" / "ai.perplexity.macv3",
}


def _iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _tail(text: str, lines: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _source_census() -> dict[str, dict[str, Any]]:
    census: dict[str, dict[str, Any]] = {}
    for source, root in PROVIDER_ROOTS.items():
        item: dict[str, Any] = {
            "present": root.exists(),
            "files": 0,
            "bytes": 0,
            "newest": None,
        }
        if root.is_file():
            try:
                st = root.stat()
            except OSError:
                census[source] = item
                continue
            item["files"] = 1
            item["bytes"] = st.st_size
            item["newest"] = _iso(st.st_mtime)
            census[source] = item
            continue
        if root.is_dir():
            newest_ts: float | None = None
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    st = path.stat()
                except OSError:
                    continue
                item["files"] += 1
                item["bytes"] += st.st_size
                if newest_ts is None or st.st_mtime > newest_ts:
                    newest_ts = st.st_mtime
            item["newest"] = _iso(newest_ts)
        census[source] = item
    return census


def _run_refresh() -> dict[str, Any]:
    if not SESSION_META.is_dir():
        return {"status": "missing_session_meta", "session_meta_present": False}
    refresh = SESSION_META / "ingest" / "refresh-atoms.sh"
    if refresh.exists():
        return _with_store_summary(_run_command(["bash", str(refresh)], cwd=SESSION_META))

    manifest = SESSION_META / "ingest" / "manifest.py"
    atomize = SESSION_META / "ingest" / "atomize.py"
    if not manifest.exists() or not atomize.exists():
        return {"status": "missing_ingest_pipeline", "session_meta_present": True}

    manifest_run = _run_command(
        [
            sys.executable,
            str(manifest),
            "data/session-transcripts",
            "--extra-root",
            f"{HOME}/.claude/projects:claude-projects",
            "--out",
            "ingest/manifest.jsonl",
            "--merge",
        ],
        cwd=SESSION_META,
    )
    if manifest_run["status"] != "pass":
        return {"status": "manifest_failed", "manifest": manifest_run}
    atomize_run = _run_command(
        [
            sys.executable,
            str(atomize),
            "--manifest",
            "ingest/manifest.jsonl",
            "--store-root",
            str(atoms_store_root()),
        ],
        cwd=SESSION_META,
    )
    return _with_store_summary({"status": atomize_run["status"], "manifest": manifest_run, "atomize": atomize_run})


def _with_store_summary(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "pass":
        return result
    try:
        summary = atoms_summary()
    except AtomStreamError as exc:
        return {**result, "status": "store_invalid", "atoms_store_error": str(exc)}
    if not summary["present"]:
        return {**result, "status": "store_missing", "atoms_store": summary}
    return {**result, "atoms_store": summary}


def _run_command(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "elapsed_sec": round(time.monotonic() - started, 3),
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail(exc.stderr or ""),
        }
    except OSError as exc:
        return {"status": "error", "error": str(exc), "elapsed_sec": round(time.monotonic() - started, 3)}
    return {
        "status": "pass" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "elapsed_sec": round(time.monotonic() - started, 3),
        "stdout_tail": _tail(proc.stdout),
        "stderr_tail": _tail(proc.stderr),
    }


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    report = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_meta_present": SESSION_META.is_dir(),
        "source_census": _source_census(),
        "refresh": _run_refresh(),
    }
    STATE.write_text(json.dumps(report, indent=2))
    total_files = sum(int(item.get("files", 0)) for item in report["source_census"].values())
    refresh_status = report["refresh"]["status"]
    print(f"corpus-feed: sources={len(report['source_census'])} files={total_files} refresh={refresh_status}")
    return 0 if refresh_status in {"pass", "missing_session_meta", "missing_ingest_pipeline"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
