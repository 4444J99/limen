"""Credential discipline — inherited verbatim from the fleet's credential-race fix.

The fleet learned the hard way (anthropics/claude-code#48786, and the 40 stale Keychain
forks this build surfaced) that concurrent processes must NEVER share and concurrently
rotate one interactive OAuth credential. ianva is the single credential authority for the
whole fleet, so it has to get this exactly right or it recreates the flap at the gateway.

Rules encoded here:
  * Secrets come only from ~/.limen.env (loaded via paths.load_limen_env). Never argv/history/log.
  * Token refreshes are SINGLE-WRITER: serialized with an flock so a rotating (single-use)
    refresh token is never double-spent and self-revoked by two racing refreshers.
  * CLAUDE_CODE_OAUTH_TOKEN is never propagated to a child — on macOS it DELETES the global
    Keychain item on exit (anthropics/claude-code#37512), which would knock out a live session.
  * An auth blip in child output triggers exactly ONE self-healing retry (a fresh process
    re-reads the rotated token), distinct from a genuine rate-limit.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re

from . import paths

# Matches the credential-race fix's _AUTH_BLIP_PATTERNS so ianva and dispatch.py agree on
# what "the token rotated under me" looks like.
AUTH_BLIP = re.compile(
    r"not logged in|please run /login|invalid[_ ]grant|oauth[^.]*(expired|invalid|revoked)|"
    r"authentication_error|\b401\b|unauthorized",
    re.IGNORECASE,
)
_RATE_LIMITED = re.compile(r"rate.?limit|429|quota|overloaded|too many requests", re.IGNORECASE)


def is_auth_blip(text: str) -> bool:
    """True when text looks like a credential-rotation race, not a rate limit."""
    t = text or ""
    return bool(AUTH_BLIP.search(t)) and not _RATE_LIMITED.search(t)


@contextlib.contextmanager
def refresh_lock(name: str = "oauth-refresh"):
    """Serialize OAuth refreshes fleet-wide. Only one process refreshes a given upstream's
    token at a time, so single-use rotating refresh tokens are never double-spent."""
    paths.ensure_dirs()
    lockfile = paths.LOCK_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', name)}.lock"
    fd = os.open(lockfile, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def sanitize_child_env(env: dict[str, str] | None = None, *, fleet_claude: bool = True) -> dict[str, str]:
    """Return a copy of env safe to hand to a child process.

    Always strips CLAUDE_CODE_OAUTH_TOKEN. When fleet_claude is set, applies the fleet's
    auth precedence (LIMEN_CLAUDE_AUTH_TOKEN -> ANTHROPIC_AUTH_TOKEN, else LIMEN_CLAUDE_API_KEY
    -> ANTHROPIC_API_KEY) so any claude ianva spawns stays off the interactive Keychain.
    """
    out = dict(env if env is not None else os.environ)
    out.pop("CLAUDE_CODE_OAUTH_TOKEN", None)  # #37512: would wipe the Keychain on exit
    if fleet_claude:
        limen = paths.load_limen_env()
        ftok = limen.get("LIMEN_CLAUDE_AUTH_TOKEN") or os.environ.get("LIMEN_CLAUDE_AUTH_TOKEN")
        fkey = limen.get("LIMEN_CLAUDE_API_KEY") or os.environ.get("LIMEN_CLAUDE_API_KEY")
        if ftok:
            out["ANTHROPIC_AUTH_TOKEN"] = ftok
            out.pop("ANTHROPIC_API_KEY", None)
        elif fkey:
            out["ANTHROPIC_API_KEY"] = fkey
    return out


def have(key: str) -> bool:
    """True if a secret is present in ~/.limen.env or the environment (never reveals it)."""
    return bool(paths.load_limen_env().get(key) or os.environ.get(key))


BEARER_ENV = "IANVA_BEARER_TOKEN"


def bearer_token() -> str | None:
    """The gateway's shared bearer (protects a publicly-exposed endpoint). None = unauthenticated."""
    limen = paths.load_limen_env()
    return limen.get(BEARER_ENV) or os.environ.get(BEARER_ENV) or None


def new_bearer() -> str:
    """A fresh high-entropy bearer to store (via set-credential) before exposing the gateway."""
    import secrets

    return secrets.token_urlsafe(32)
