"""Shared constants for the record-keeper covenant.

TABVLARIVS is the sole writer of the testament surfaces (the memory dir + `tasks.yaml`).
This module is the checked source of truth other sessions read: the registry loader, the
out-of-repo memory-dir resolver (mirrored EXACTLY from `scripts/evocator.py`), and the
covenant-doc path. `scripts/check-covenant.py` and the tests import from here so the
derivation lives in one place.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
COVENANT_REGISTRY = ROOT / "institutio" / "governance" / "covenant.yaml"
COVENANT_DOC = "docs/record-keeper-covenant.md"

# Files that may legitimately write the memory surface — everything else is a violation
# (check D). memoria.py is the engine, memory-ticket.py the submit CLI, tabularius-organ.py
# the drain, covenant-attribution.py the beat sensor; covenant.py + check-covenant.py touch
# the paths only to reason about them.
MEMORY_WRITER_ALLOWLIST = (
    "cli/src/limen/memoria.py",
    "scripts/memory-ticket.py",
    "scripts/tabularius-organ.py",
    "scripts/covenant-attribution.py",
    "scripts/covenant.py",
    "scripts/check-covenant.py",
)
# Read-only summoners: tolerated unless they gain a write call on a memory path (check D).
MEMORY_READONLY_TOLERATED = (
    "scripts/evocator.py",
    "scripts/session-orient.py",
)


def load_covenant(registry: Path = COVENANT_REGISTRY) -> dict:
    """Parse the covenant registry YAML into a plain dict."""
    return yaml.safe_load(registry.read_text(encoding="utf-8")) or {}


def resolve_memory_dir(root: Path = ROOT) -> Path:
    """Resolve the out-of-repo memory dir, EXACTLY as evocator.py derives it.

    LIMEN_MEMORY_DIR overrides; otherwise
    ~/.claude/projects/<workspace-slug>/memory, where the slug is the workspace path
    with `/` replaced by `-`. `root` is unused in the default derivation (the memory dir
    lives outside the repo) but kept for signature symmetry with the in-repo resolvers.
    """
    workspace = Path(os.environ.get("LIMEN_WORKDIR", Path.home() / "Workspace" / "limen")).expanduser()
    default = Path.home() / ".claude" / "projects" / str(workspace).replace("/", "-") / "memory"
    return Path(os.environ.get("LIMEN_MEMORY_DIR", default))


def covenant_entries(registry: Path = COVENANT_REGISTRY) -> dict:
    """The `covenants:` mapping (name -> entry)."""
    return (load_covenant(registry).get("covenants") or {})
