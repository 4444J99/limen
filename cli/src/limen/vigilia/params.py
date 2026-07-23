"""Read the VIGILIA parameter panel (the spine's '100x').

Every name/path/threshold the autonomic organs use is one declared parameter in
``institutio/governance/parameters.yaml`` — with a default and an env override.
This module is the single accessor the organs share, so nothing hardcodes a
threshold. Fail-open: if the panel can't be read, callers still get their own
in-code default (the organ degrades, it never crashes the beat).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, overload

import yaml

_PANEL_REL = ("institutio", "governance", "parameters.yaml")

T = TypeVar("T")


def _repo_root() -> Path | None:
    """Find the repo root that contains the parameter panel.

    Prefer ``$LIMEN_ROOT`` (the daemon sets it); otherwise walk up from this file.
    """
    env = os.environ.get("LIMEN_ROOT")
    if env:
        p = Path(env).expanduser()
        if (p.joinpath(*_PANEL_REL)).exists():
            return p
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent.joinpath(*_PANEL_REL)).exists():
            return parent
    if env:
        return Path(env).expanduser()
    return None


def panel_path() -> Path | None:
    root = _repo_root()
    return root.joinpath(*_PANEL_REL) if root else None


def _load_panel() -> dict[str, object]:
    path = panel_path()
    if not path or not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            return {}
        params = data.get("parameters", {})
        return params if isinstance(params, dict) else {}
    except Exception:
        return {}


@overload
def get(key: str, default: T, cast: None = None) -> T | str: ...


@overload
def get(key: str, default: T, cast: Callable[[Any], T]) -> T: ...


@overload
def get(key: str, default: None = None, cast: None = None) -> object | None: ...


def get(key: str, default: object = None, cast: Callable[[Any], object] | None = None) -> object:
    """Resolve a parameter.

    Precedence: env override (the param's declared ``env``, falling back to the
    key itself) > the panel's ``default`` > the caller's ``default``.
    """
    spec = _load_panel().get(key)
    env_name = key
    panel_default: object = None
    if isinstance(spec, dict):
        env_name = str(spec.get("env") or key)
        panel_default = spec.get("default")

    raw: object = os.environ.get(env_name)
    if raw is None:
        raw = panel_default
    if raw is None:
        raw = default

    if cast is not None and raw is not None:
        try:
            return cast(raw)
        except (TypeError, ValueError):
            return default
    return raw
