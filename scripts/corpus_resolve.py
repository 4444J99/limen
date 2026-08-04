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

2026-07-31 — the same defect recurred, by a third route, and two fail-opens hid it:

  1. The store moved AGAIN (to `.limen-private/session-corpus/local-memory`, inside
     the checkout but gitignored). No candidate knew, so nothing resolved.
  2. `corpus_home()` then fell back to the last candidate's PARENT — the repo root,
     which is precisely what item 1 of the history above says this module fixed.
  3. With CCE unimportable, `corpus_ids()` returned `[]`, so `undeclared_corpora()`
     swept a repo root against an EMPTY declared set and reported `apps`, `cli`,
     `docs`, `scripts` and `web` as conversation corpora — a green check over zero
     conversation data, 319 MB of real corpus unread.

The structural fix is that the CORPORA registry (`institutio/governance/corpora.yaml`)
is now the id and store authority, with CCE supplementing it. A registry the repo owns
cannot become unimportable, and relocating a store is one registry line. CCE remains a
source of ids so a corpus it declares and the registry has not yet caught up on is
still reachable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The CORPORA registry — the declared-data authority for ids and store roots.
CORPORA_REGISTRY = REPO_ROOT / "institutio" / "governance" / "corpora.yaml"

# Directory name of the registered corpus store, a sibling of the live checkout.
CORPUS_STORE_DIRNAME = "_conversations-private"

# The CCE checkout is known by two names in the wild; try both, in both places.
CCE_DIRNAMES = ("conversation-corpus-check", "conversation-corpus-engine")

# Any two of these under a path prove it is the limen checkout, not a corpus store.
REPO_MARKER_DIRS = ("scripts", "cli", "web", "organs", "institutio")


def load_registry() -> dict:
    """The CORPORA registry as a dict, or {} when it cannot be read.

    Never raises: a resolver that dies on a malformed registry takes every
    consumer down with it. An unreadable registry degrades to CCE-only, which is
    the pre-registry behaviour.
    """
    try:
        import yaml  # imported lazily so the module stays importable without PyYAML
    except ImportError:
        return {}
    try:
        return yaml.safe_load(CORPORA_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def registry_corpus_ids(doc: dict | None = None) -> list[str]:
    """Corpus ids the registry declares, plus any drifted `cce_id` aliases.

    The alias matters: `perplexity-local-session-memory` on disk is
    `perplexity-history-memory` to CCE, and a consumer that constructs a path
    from the declared id alone misses the directory entirely.
    """
    reg = doc if doc is not None else load_registry()
    ids: list[str] = []
    for cid, row in (reg.get("corpora") or {}).items():
        if cid not in ids:
            ids.append(cid)
        alias = (row or {}).get("cce_id")
        if alias and alias not in ids:
            ids.append(alias)
    return ids


def registry_store_roots(doc: dict | None = None) -> list[Path]:
    """Every store root the registry declares, expanded, in declaration order."""
    reg = doc if doc is not None else load_registry()
    roots: list[Path] = []
    for store in (reg.get("stores") or {}).values():
        root = (store or {}).get("root")
        if root:
            roots.append(Path(str(root)).expanduser())
    return roots


def _is_repo_checkout(path: Path) -> bool:
    """True when `path` is the limen checkout rather than a corpus store."""
    return sum(1 for name in REPO_MARKER_DIRS if (path / name).is_dir()) >= 2


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

    # Registry-declared store roots outrank the conventions below them: relocating
    # a store is a `corpora.yaml` edit, not a code change.
    candidates.extend(registry_store_roots())

    root = live_root()
    candidates.append(root.parent / CORPUS_STORE_DIRNAME)
    candidates.append(root / "source-drop")

    seen: set[Path] = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def corpus_home() -> Path:
    """First candidate that actually contains corpus directories.

    Never returns the repo checkout. The old fallback took the last candidate's
    PARENT — `<repo>/source-drop`.parent is the repo root, the exact defect this
    module's docstring says it fixed, reintroduced through the unpopulated path.
    A repo root reaching `undeclared_corpora()` reports `docs` and `scripts` as
    corpora and paints a green check over no data at all.

    When nothing resolves, fall back to the last candidate ITSELF: a path that
    does not exist, so every sweep below stays empty while callers still have a
    concrete location to name in the error.
    """
    for candidate in corpus_home_candidates():
        if _is_repo_checkout(candidate):
            continue
        if candidate.is_dir() and any(p.is_dir() for p in candidate.iterdir()):
            return candidate
    return corpus_home_candidates()[-1]


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
    """Every declared corpus id — registry first, CCE supplementing.

    The registry leads because the repo owns it and it cannot become
    unimportable; CCE still contributes so a corpus it declares before the
    registry catches up stays reachable. Returning [] now means BOTH sources are
    empty, which is a real finding rather than one missing package.
    """
    ids: list[str] = list(registry_corpus_ids())
    cfg = provider_config if provider_config is not None else import_provider_config()
    if not cfg:
        return ids
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
    if not declared:
        # An empty declared set does not mean every directory on disk is an
        # undeclared corpus — it means BOTH the registry and CCE failed to load.
        # Sweeping here is what turned `docs/` and `scripts/` into corpora and
        # reported a populated corpus while nothing had been read.
        return []
    if _is_repo_checkout(base):
        # Belt to the corpus_home() suspender: an explicit LIMEN_CORPUS_ROOT can
        # still point at the checkout, and no sweep of it is ever meaningful.
        return []
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
