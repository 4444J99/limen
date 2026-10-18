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
import shlex
import stat
from collections.abc import Mapping
from pathlib import Path

from limen.conduct.client import BrokerUnavailable

URL_KEY = "LIMEN_CONDUCT_URL"
TOKEN_KEY = "LIMEN_CONDUCT_TOKEN"
UNSAFE = "conduct environment cache must be a user-owned mode-600 regular file"
INCOMPLETE = "conduct environment cache does not define LIMEN_CONDUCT_URL and LIMEN_CONDUCT_TOKEN"


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


def read_conduct_credentials(environ: Mapping[str, str] | None = None) -> tuple[str, str] | None:
    """``(url, token)`` from the cache; None when no cache exists; BrokerUnavailable with a named reason otherwise."""
    path = cache_path(environ)
    if not path.exists() and not path.is_symlink():
        return None
    if not ownership_ok(path):
        raise BrokerUnavailable(UNSAFE)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise BrokerUnavailable(UNSAFE) from None
    found = parse_assignments(text, frozenset({URL_KEY, TOKEN_KEY}))
    if URL_KEY not in found or TOKEN_KEY not in found:
        raise BrokerUnavailable(INCOMPLETE)
    return found[URL_KEY], found[TOKEN_KEY]


def complete_from_cache(endpoint: str, credential: str) -> tuple[str, str]:
    """Fill whichever of the endpoint and credential the environment left empty; explicit values win."""
    cached = read_conduct_credentials()
    if cached is None:
        return endpoint, credential
    return endpoint or cached[0], credential or cached[1]
