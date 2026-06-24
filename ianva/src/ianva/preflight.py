"""Per-upstream reachability preflight — the agy/antigravity login-flap lesson.

That incident: a lane misread a transient network failure as "not logged in" and spawned a
browser per beat. The root fix was a per-beat DNS+TCP:443 preflight that skips unreachable
hosts instead of treating them as auth failures. ianva fronts many remote upstreams, so it
inherits the same guard: a remote upstream that fails a cheap reachability check is marked
DOWN for this beat (and surfaced), never re-auth'd.
"""
from __future__ import annotations

import socket
from urllib.parse import urlparse


def reachable(host: str, port: int = 443, timeout: float = 2.0) -> bool:
    """Cheap DNS + TCP connect check. No auth, no request body."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for family, socktype, proto, _canon, sockaddr in infos:
        try:
            with socket.socket(family, socktype, proto) as s:
                s.settimeout(timeout)
                if s.connect_ex(sockaddr) == 0:
                    return True
        except OSError:
            continue
    return False


def url_reachable(url: str, timeout: float = 2.0) -> bool:
    p = urlparse(url)
    if not p.hostname:
        return False
    port = p.port or (443 if p.scheme == "https" else 80)
    return reachable(p.hostname, port, timeout)


def unreachable(upstreams, timeout: float = 2.0) -> list[str]:
    """Names of remote (http/sse) upstreams that are unreachable right now. stdio upstreams
    are always considered reachable (local process spawn)."""
    down: list[str] = []
    for u in upstreams:
        url = getattr(u, "url", None)
        if not url:
            continue  # stdio upstream — nothing to preflight
        if not url_reachable(url, timeout):
            down.append(getattr(u, "name", url))
    return down
