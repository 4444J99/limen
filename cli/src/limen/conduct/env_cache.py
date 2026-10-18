"""Broker credentials from the organ-owned cache, for callers whose shell cannot source it.

``~/.limen.env`` is written by the credential organ (``scripts/creds-hydrate.py``). An isolated agent
shell may not source a file, so ``session-closeout --check`` read the broker as unavailable even though
the credential exists (issue 2966). This reads exactly the two keys the broker client needs. It parses
and never executes the file, never prints a value, and never writes the values into the process
environment, where a child process such as ``gh`` would inherit them.

The ownership predicate is the one ``workstream_hydrate_conduct_environment`` applies in
``scripts/lib/workstream-capsule.sh``. That shell function is serialized into ``kickstart.sh`` and must
stay self-contained, so it keeps an inline copy; ``test_conduct_env_cache.py`` holds the two in parity.
"""

from __future__ import annotations

import os
import re
import shlex
import stat
from collections.abc import Mapping
from pathlib import Path

from limen.conduct.client import BrokerUnavailable

URL_KEY = "LIMEN_CONDUCT_URL"
TOKEN_KEY = "LIMEN_CONDUCT_TOKEN"
LANE_TOKEN_PREFIX = TOKEN_KEY + "_"
UNSAFE = "conduct environment cache must be a user-owned mode-600 regular file"
INCOMPLETE = "conduct environment cache does not define LIMEN_CONDUCT_URL and LIMEN_CONDUCT_TOKEN"
LANE_INVALID = "conduct lane must be a lower-case lane id such as opencode or github_actions"
_LANE_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}")


def lane_token_key(lane: str) -> str:
    """``LIMEN_CONDUCT_TOKEN_<LANE>``: the named bearer a lane owns, never the generic one.

    The lane arrives from process environment (``LIMEN_AGENT``), so it is validated against the lane-id
    shape before it names a cache key: a crafted value can select no other entry.
    """
    if not _LANE_ID.fullmatch(lane):
        raise BrokerUnavailable(LANE_INVALID)
    return LANE_TOKEN_PREFIX + lane.upper().replace("-", "_")


def lane_incomplete(lane: str) -> str:
    return f"conduct environment cache does not define {URL_KEY} and {lane_token_key(lane)}"


def cache_path(environ: Mapping[str, str] | None = None) -> Path:
    environ = os.environ if environ is None else environ
    configured = environ.get("LIMEN_CONDUCT_ENV_FILE", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".limen.env"


def ownership_ok(path: Path) -> bool:
    """User-owned, mode 0600, regular, and not a symlink."""
    try:
        info = path.lstat()
    except OSError:
        return False
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        return False
    return info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600


def parse_assignments(text: str, keys: frozenset[str]) -> dict[str, str]:
    """Last assignment wins, as in a sourced shell file. Only ``keys`` are read; nothing is executed."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, separator, value = line.partition("=")
        if not separator or name not in keys:
            continue
        try:
            words = shlex.split(value, posix=True)
        except ValueError:
            continue
        if len(words) == 1 and words[0]:
            found[name] = words[0]
    return found


def lane_credential_present(lane: str, environ: Mapping[str, str] | None = None) -> bool:
    """True when ``lane`` owns a named bearer, in the environment or in a safe cache.

    Never raises and never returns a value: a malformed lane id, an absent or unsafe cache, or a cache
    without the lane's entry is simply "no own credential". Callers that inherit ``LIMEN_AGENT`` from a
    launcher use this to engage lane resolution only for lanes that actually have a bearer of their own,
    leaving every other lane's existing resolution untouched.
    """
    environ = os.environ if environ is None else environ
    try:
        key = lane_token_key(lane)
    except BrokerUnavailable:
        return False
    if environ.get(key, "").strip():
        return True
    path = cache_path(environ)
    if not ownership_ok(path):
        return False
    try:
        return key in parse_assignments(path.read_text(encoding="utf-8"), frozenset({key}))
    except (OSError, UnicodeDecodeError):
        return False


def read_conduct_credentials(
    environ: Mapping[str, str] | None = None, *, lane: str | None = None
) -> tuple[str, str] | None:
    """``(url, token)`` from the cache; None when no cache exists; BrokerUnavailable with a named reason otherwise.

    With ``lane`` the token is that lane's own entry and only that entry is parsed, so the generic bearer
    (the legacy ``codex-direct-legacy`` principal) can never be returned for a lane that did not ask for it.
    """
    token_key = TOKEN_KEY if lane is None else lane_token_key(lane)
    path = cache_path(environ)
    if not path.exists() and not path.is_symlink():
        return None
    if not ownership_ok(path):
        raise BrokerUnavailable(UNSAFE)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise BrokerUnavailable(UNSAFE) from None
    found = parse_assignments(text, frozenset({URL_KEY, token_key}))
    if URL_KEY not in found or token_key not in found:
        raise BrokerUnavailable(INCOMPLETE if lane is None else lane_incomplete(lane))
    return found[URL_KEY], found[token_key]


def complete_from_cache(endpoint: str, credential: str, *, lane: str | None = None) -> tuple[str, str]:
    """Fill whichever of the endpoint and credential the environment left empty; explicit values win."""
    cached = read_conduct_credentials(lane=lane)
    if cached is None:
        return endpoint, credential
    return endpoint or cached[0], credential or cached[1]
