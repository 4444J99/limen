"""The ONLY shell-out boundary in OBSERVATORY.

Copies GITVS's proven ``gh`` idiom (``scripts/gitvs.py``): a cascade token
(App → PAT → gh keyring) and thin subprocess wrappers that **fail OPEN** — offline
or with ``gh`` absent they return ``returncode 1`` and never raise, so a network
fault degrades the beat to SKIP instead of crashing it.

Every reader here returns plain Python (list/dict/str/None); parsing lives at the
boundary so the analytical modules stay pure and hermetically testable (they
monkeypatch this one module).

Trending has no official API, so :func:`search_repos` approximates GitHub Trending
via the search API with a recency + star sort (tunable through the
``OBSERVATORY_TRENDING_QUERY`` parameter).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import config


def _root() -> Path:
    return config.repo_root()


def token() -> str | None:
    """Mint a token via the shared ``gh-app-token.sh`` cascade. None when exhausted."""
    if os.environ.get("LIMEN_OFFLINE"):
        return None
    script = _root() / "scripts" / "gh-app-token.sh"
    if not script.exists():
        return None
    try:
        r = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=45)
    except Exception:
        return None
    tok = (r.stdout or "").strip()
    return tok if r.returncode == 0 and tok else None


def gh(args: list[str], tok: str | None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a ``gh`` command with the cascade token exported. Fails OPEN, never raises."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    env = {**os.environ}
    if tok:
        env["GH_TOKEN"] = tok
        env["GITHUB_TOKEN"] = tok
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as e:  # fail open
        return subprocess.CompletedProcess(args, 1, "", str(e))


def gh_json(args: list[str], tok: str | None, timeout: int = 60, default=None):
    """``gh(...)`` + ``json.loads(stdout)``; the declared ``default`` on any failure."""
    r = gh(args, tok, timeout)
    if r.returncode != 0 or not (r.stdout or "").strip():
        return default
    try:
        return json.loads(r.stdout)
    except Exception:
        return default


def online(tok: str | None) -> bool:
    """True iff a live ``gh`` read is possible (not offline, gh present, token or keyring)."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return False
    return True


def search_repos(query: str, tok: str | None, *, sort: str = "stars", per_page: int = 30) -> list[dict]:
    """Approximate Trending / competitor discovery via the search API. Fail-open ``[]``."""
    per_page = max(1, min(int(per_page), 100))
    endpoint = f"/search/repositories?q={query}&sort={sort}&order=desc&per_page={per_page}"
    items = gh_json(["api", endpoint, "--jq", ".items"], tok, default=[])
    return items if isinstance(items, list) else []


def repo(owner_repo: str, tok: str | None) -> dict | None:
    """``GET /repos/{owner}/{repo}`` — the single metadata call per snapshot."""
    data = gh_json(["api", f"/repos/{owner_repo}"], tok, default=None)
    return data if isinstance(data, dict) else None


def readme_markdown(owner_repo: str, tok: str | None) -> str | None:
    """The raw README markdown (Accept: raw). None when unavailable."""
    r = gh(
        ["api", f"/repos/{owner_repo}/readme", "-H", "Accept: application/vnd.github.raw+json"],
        tok,
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    return r.stdout


def releases(owner_repo: str, tok: str | None) -> list[dict]:
    """Release list — feeds the release-maturity matching variable. Fail-open ``[]``."""
    data = gh_json(["api", f"/repos/{owner_repo}/releases?per_page=10"], tok, default=[])
    return data if isinstance(data, list) else []


def rate_headroom_pct(tok: str | None) -> int | None:
    """Core rate-limit headroom as a percent (0-100), or None when unknown."""
    data = gh_json(["api", "/rate_limit", "--jq", ".resources.core"], tok, default=None)
    if not isinstance(data, dict):
        return None
    limit = data.get("limit") or 0
    remaining = data.get("remaining")
    if not limit or remaining is None:
        return None
    return int(round(100 * remaining / limit))
