"""The storage boundary — the ONE writer, honoring the keeper discipline.

The codebase splits *evidence* from *derived state* (cf. ``censor/precedents.jsonl``
vs ``docs/github-estate-ledger.json``):

  * **Evidence** is append-only JSONL — one immutable JSON object per line, UTC ISO
    timestamp, ``sort_keys`` so a row is byte-stable. Never rewritten, never deleted
    (the spec's "no silent mutation").
  * **Derived state** is a whole-file JSON regenerated each run (``*-latest.json``),
    plus an append-only dated *snapshot line* so history is never lost even though the
    latest file is overwritten. Re-running on identical inputs must reproduce a
    byte-identical latest file (the idempotent fixed point the doctor asserts).

Writes are best-effort: observability must never break the beat (GITVS's rule).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import config


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _path(name: str) -> Path:
    return config.data_dir() / name


def append_jsonl(name: str, row: dict) -> None:
    """Append one immutable evidence row (adds ``ts`` if absent)."""
    row = dict(row)
    row.setdefault("ts", _utc_now())
    line = json.dumps(row, sort_keys=True, ensure_ascii=False)
    try:
        with _path(name).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:  # never break the beat over a write
        print(f"[observatory] note: append {name} skipped ({str(e)[:80]})")


def read_jsonl(name: str) -> list[dict]:
    """Read an evidence log back (skips blank/corrupt lines). Empty when absent."""
    path = _path(name)
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return rows
    return rows


def _atomic_write(path: Path, text: str) -> None:
    """temp-file + ``os.replace`` so a reader never sees a half-written file."""
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_latest(name: str, obj: Any) -> None:
    """Regenerate a whole-file derived doc deterministically (sorted keys)."""
    try:
        _atomic_write(_path(name), json.dumps(obj, indent=2, sort_keys=True) + "\n")
    except Exception as e:
        print(f"[observatory] note: write {name} skipped ({str(e)[:80]})")


def read_latest(name: str, default: Any = None) -> Any:
    """Read back a regenerated ``*-latest.json`` doc (``default`` when absent/corrupt)."""
    try:
        return json.loads(_path(name).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_text(name: str, text: str) -> None:
    """Regenerate a human-face artifact (e.g. ``brief-latest.md``)."""
    try:
        _atomic_write(_path(name), text)
    except Exception as e:
        print(f"[observatory] note: write {name} skipped ({str(e)[:80]})")


def snapshot_line(name: str, obj: dict) -> None:
    """Append a dated snapshot of a derived doc so overwriting ``-latest`` loses no history."""
    append_jsonl(name, {"snapshot": obj})


def stamp(obj: dict) -> None:
    """Write the last-run STAMP (mirror ``logs/gitvs.json``)."""
    write_latest("observatory.json", {**obj, "ts": _utc_now()})
