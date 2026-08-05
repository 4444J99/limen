"""OBSERVATORY configuration — one accessor, no hardcoded thresholds.

Every name/window/limit the organ uses is a declared parameter in
``institutio/governance/parameters.yaml`` (``OBSERVATORY_*``), read through the
same single accessor VIGILIA uses (:mod:`limen.vigilia.params`) so the two organs
share one panel and one precedence rule (env > panel default > in-code default).

The organ also *reads* three existing in-repo registries as ground truth — it
never duplicates them:

  * ``value-repos.json``          — time-to-dollar hero ordering
  * ``revenue-ladder.json``       — per-repo outcome class (stage / whose_hand)
  * ``docs/github-estate-ledger.json`` — GITVS's observed estate (our repo list)

All readers fail-open: a missing/corrupt registry yields an empty structure so the
beat degrades rather than crashes (the sibling-organ contract).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from limen.vigilia import params


def get(key: str, default: Any, cast: Optional[Callable[[Any], Any]] = None) -> Any:
    """Resolve an ``OBSERVATORY_*`` parameter (passthrough to the shared panel)."""
    return params.get(key, default, cast)


def repo_root() -> Path:
    """The limen checkout root (``$LIMEN_ROOT`` or the panel-bearing ancestor)."""
    root = params._repo_root()
    if root:
        return root
    return Path(os.environ.get("LIMEN_ROOT", ".")).expanduser()


def data_dir() -> Path:
    """``logs/observatory/`` — created on demand; the organ's whole footprint."""
    d = repo_root() / "logs" / "observatory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(rel: str, default: Any) -> Any:
    path = repo_root() / rel
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def value_repos() -> list[str]:
    """Hero-ordering SSOT. Fail-CLOSED to ``[]`` — an empty hero list means the
    organ proposes no experiment rather than inventing a target."""
    data = _read_json("value-repos.json", {})
    repos = data.get("repos") if isinstance(data, dict) else None
    return [str(r) for r in repos] if isinstance(repos, list) else []


def revenue_ladder() -> dict:
    """Outcome-class inputs (stage / whose_hand / first_dollar_path). Fail-open."""
    data = _read_json("revenue-ladder.json", {})
    return data if isinstance(data, dict) else {}


def estate_ledger() -> dict:
    """GITVS's observed estate ledger — the source of 'our repos'. Fail-open."""
    data = _read_json("docs/github-estate-ledger.json", {})
    return data if isinstance(data, dict) else {}


def competitor_seeds() -> list[str]:
    """Curated ``owner/repo`` competitor list (comma-separated param). May be empty."""
    raw = str(get("OBSERVATORY_COMPETITOR_SEEDS", "") or "")
    return [s.strip() for s in raw.split(",") if s.strip()]
