#!/usr/bin/env python3
"""
corpus_resolve — the one place that knows where the conversation corpora live.

Two consumers needed this and each carried its own copy: `constellation-dossier.py`
and `organs/consulting/constellation/check.py`. Both copies were wrong in the same
two ways, which is what a duplicated capability buys you:

  1. The corpus home was taken as `<live-repo>/source-drop`'s parent — i.e. the
     repo root itself, which contains no corpora. The registered store is a
     SIBLING of the repo (`_conversations-private`), local-only by design.
  2. The CCE package was imported from a path nested inside the repo. The
     checkout is beside the repo, and its directory is named
     `conversation-corpus-check` while the repository is called
     `conversation-corpus-engine`.

Both resolvers below take an ordered candidate list and return the first one that
actually holds something, so a stale convention can never silently outrank a
populated store. Import this module; do not re-derive these paths.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directory name of the registered corpus store, a sibling of the live checkout.
CORPUS_STORE_DIRNAME = "_conversations-private"

# The CCE checkout is known by two names in the wild; try both, in both places.
CCE_DIRNAMES = ("conversation-corpus-check", "conversation-corpus-engine")


def live_root() -> Path:
    """The live checkout's root — worktrees share its untracked estate."""
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return REPO_ROOT
    return Path(result.stdout.strip()).parent


def corpus_home_candidates() -> list[Path]:
    """Ordered places the per-corpus directories may live, most-specific first."""
    candidates: list[Path] = []

    env = os.environ.get("LIMEN_CORPUS_ROOT") or os.environ.get("CCE_SOURCE_DROP_ROOT")
    if env:
        env_path = Path(env).expanduser()
        # CCE_SOURCE_DROP_ROOT names the drop dir; its PARENT holds the corpora.
        candidates.append(env_path.parent if env_path.name == "source-drop" else env_path)

    root = live_root()
    candidates.append(root.parent / CORPUS_STORE_DIRNAME)
    candidates.append(root / "source-drop")
    return candidates


def corpus_home() -> Path:
    """First candidate that actually contains corpus directories.

    Falls back to the last candidate's parent so callers still get a path to
    name in an error message when nothing is populated.
    """
    for candidate in corpus_home_candidates():
        if candidate.is_dir() and any(p.is_dir() for p in candidate.iterdir()):
            return candidate
    return corpus_home_candidates()[-1].parent


def cce_src_roots() -> list[Path]:
    """Every place the `conversation_corpus_engine` package may be checked out."""
    root = live_root()
    return [base / name / "src" for base in (root, root.parent) for name in CCE_DIRNAMES]


def import_provider_config() -> dict | None:
    """Import CCE's PROVIDER_CONFIG, searching every known checkout location.

    Returns None on failure — callers report it; this module never exits.
    """
    for src in cce_src_roots():
        if (src / "conversation_corpus_engine").is_dir():
            if str(src) not in sys.path:
                sys.path.insert(0, str(src))
            break
    try:
        from conversation_corpus_engine.provider_catalog import PROVIDER_CONFIG  # type: ignore
    except Exception:  # noqa: BLE001 — any import failure is the same finding
        return None
    return PROVIDER_CONFIG


def corpus_ids(provider_config: dict | None = None) -> list[str]:
    """Every corpus id CCE declares, in declaration order, de-duplicated."""
    cfg = provider_config if provider_config is not None else import_provider_config()
    if not cfg:
        return []
    ids: list[str] = []
    for entry in cfg.values():
        if not isinstance(entry, dict):
            continue
        for key in ("default_corpus_id", "fallback_corpus_id"):
            value = entry.get(key)
            if value and value not in ids:
                ids.append(value)
    return ids


# Directories under the corpus home that are infrastructure, not corpora.
NON_CORPUS_DIRS = {".git", "federation", "reports", "state", "source-drop"}


def populated_corpora(home: Path | None = None) -> list[Path]:
    """Declared corpus directories that exist and are non-empty."""
    base = home if home is not None else corpus_home()
    found = []
    for cid in corpus_ids():
        candidate = base / cid
        if candidate.is_dir() and any(candidate.iterdir()):
            found.append(candidate)
    return found


def undeclared_corpora(home: Path | None = None) -> list[Path]:
    """Corpus-shaped directories on disk that CCE does not declare.

    This is not hypothetical: the Perplexity store is
    `perplexity-local-session-memory` on disk while CCE's provider catalog
    declares `perplexity-history-memory`. Sweeping declared ids alone drops 89
    files on the floor with no error — the drift has to be surfaced, not
    tolerated.
    """
    base = home if home is not None else corpus_home()
    if not base.is_dir():
        return []
    declared = set(corpus_ids())
    found = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name in NON_CORPUS_DIRS or child.name in declared:
            continue
        if child.name.startswith("."):
            continue
        if any(child.iterdir()):
            found.append(child)
    return found


def populated_corpora_including_undeclared(home: Path | None = None) -> list[Path]:
    """Every non-empty corpus directory, declared or not."""
    base = home if home is not None else corpus_home()
    return populated_corpora(base) + undeclared_corpora(base)


if __name__ == "__main__":
    home = corpus_home()
    print(f"corpus home : {home}")
    print(f"cce package : {'found' if import_provider_config() else 'NOT IMPORTABLE'}")
    ids = corpus_ids()
    print(f"declared ids: {len(ids)}")
    populated = populated_corpora(home)
    print(f"populated   : {len(populated)}")
    for p in populated:
        count = sum(1 for _ in p.rglob("*") if _.is_file())
        print(f"  {p.name:<38} {count:>6} files")
