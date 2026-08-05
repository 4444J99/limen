"""Streaming Limen adapter for session-meta's physical atoms-store contract."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections.abc import Iterator, Mapping
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


class AtomStreamError(RuntimeError):
    """The selected session-meta atom source is malformed or unreadable."""


def session_meta_root() -> Path:
    configured = os.environ.get("LIMEN_SESSION_META", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / "Workspace" / "session-meta"


def atoms_store_root() -> Path:
    configured = os.environ.get("ATOMS_STORE_ROOT", "").strip()
    return Path(configured).expanduser() if configured else session_meta_root() / "ingest" / "atoms-store"


def legacy_atoms_path() -> Path | None:
    configured = os.environ.get("LIMEN_EXPORT_ATOMS", "").strip()
    return Path(configured).expanduser() if configured else None


def _v2_state_present(store_root: Path) -> bool:
    return any(path.exists() or path.is_symlink() for path in (store_root / "CURRENT", store_root / "generations"))


@lru_cache(maxsize=8)
def _load_owner_module(module_path: str) -> ModuleType:
    path = Path(module_path)
    if path.is_symlink() or not path.is_file():
        raise AtomStreamError("session-meta atoms_store.py is missing or is a symlink")
    name = f"_limen_session_atoms_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AtomStreamError("session-meta atoms-store module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(name, None)
        raise AtomStreamError(f"session-meta atoms-store module failed to load: {exc}") from exc
    return module


def _owner_module() -> ModuleType:
    return _load_owner_module(str(session_meta_root() / "ingest" / "atoms_store.py"))


def _record_mapping(record: object) -> dict[str, Any]:
    if isinstance(record, Mapping):
        value = dict(record)
    elif is_dataclass(record) and not isinstance(record, type):
        value = asdict(record)
    else:
        try:
            value = dict(vars(record))
        except (TypeError, ValueError) as exc:
            raise AtomStreamError("atom reader yielded a non-record value") from exc
    if not isinstance(value.get("text"), str):
        raise AtomStreamError("atom record text is not a string")
    return value


def _iter_legacy(path: Path) -> Iterator[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise AtomStreamError("explicit legacy atoms export is missing or is a symlink")
    try:
        with path.open(encoding="utf-8") as handle:
            for ordinal, line in enumerate(handle):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AtomStreamError(f"legacy atom row {ordinal} is malformed JSON") from exc
                yield _record_mapping(value)
    except OSError as exc:
        raise AtomStreamError("explicit legacy atoms export is unreadable") from exc


def iter_atoms() -> Iterator[dict[str, Any]]:
    """Yield logical AtomRecord rows without materializing the collection.

    A present v2 marker always wins. Any malformed or incomplete v2 state raises;
    the explicit one-release v1 export is considered only when no v2 state exists.
    """

    store_root = atoms_store_root()
    if _v2_state_present(store_root):
        module = _owner_module()
        reader = getattr(module, "iter_collection", None)
        if not callable(reader):
            raise AtomStreamError("session-meta atoms-store reader is unavailable")
        try:
            for record in reader(store_root):
                yield _record_mapping(record)
        except AtomStreamError:
            raise
        except Exception as exc:
            raise AtomStreamError(f"v2 atom store is invalid: {exc}") from exc
        return
    legacy = legacy_atoms_path()
    if legacy is not None:
        yield from _iter_legacy(legacy)


def atoms_summary() -> dict[str, Any]:
    """Count records with bounded memory and identify the selected physical source."""

    store_root = atoms_store_root()
    v2_present = _v2_state_present(store_root)
    legacy = legacy_atoms_path()
    if not v2_present and legacy is None:
        return {
            "present": False,
            "format": None,
            "path": str(store_root),
            "lines": 0,
            "mtime": None,
        }
    count = sum(1 for _record in iter_atoms())
    selected = store_root if v2_present else legacy
    marker = store_root / "CURRENT" if v2_present else selected
    try:
        mtime = marker.stat().st_mtime if marker is not None else None
    except OSError:
        mtime = None
    generation: str | None = None
    if v2_present:
        try:
            generation = (store_root / "CURRENT").read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise AtomStreamError("v2 CURRENT is unreadable after streaming") from exc
    return {
        "present": True,
        "format": "session-meta.atoms-store.v2" if v2_present else "legacy-jsonl-v1",
        "path": str(selected),
        "lines": count,
        "mtime": mtime,
        "generation": generation,
    }


__all__ = [
    "AtomStreamError",
    "atoms_store_root",
    "atoms_summary",
    "iter_atoms",
    "legacy_atoms_path",
    "session_meta_root",
]
