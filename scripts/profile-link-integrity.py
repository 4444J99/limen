#!/usr/bin/env python3
"""Profile/public-face link-integrity predicate.

The public profile rots silently: hardcoded links point at repos that get
renamed or flipped private, so a visitor hits a 404 while the owner sees a
working (authenticated) link. This is the executable predicate for "no dead or
private-to-public links on the public face" — exit 0 iff every outbound link on
every profile surface resolves for an anonymous visitor.

It catches three rot classes:
  * dead        — the URL returns >=400 to an anonymous GET.
  * private     — a github.com/<owner>/<repo> link whose repo is private (200
                  to the authenticated owner via `gh`, 404 to the public).
  * (reported)  — known-HOLD hosts (e.g. a vanity domain mid-cutover) and
                  bot-walled hosts (LinkedIn 999) are listed, never failed.

Usage:
  python3 scripts/profile-link-integrity.py            # human report + exit code
  python3 scripts/profile-link-integrity.py --json     # machine JSON
Exit 0 iff no dead/private links. Wire into the beat like worktree-debt.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request

SURFACES = [
    "https://raw.githubusercontent.com/4444J99/4444J99/main/README.md",
    "https://organvm.github.io/portfolio/",
    "https://organvm.github.io/portfolio/directory/",
    "https://organvm.github.io/portfolio/resume/",
]
# Hosts that legitimately do not resolve for an anonymous crawler and must NOT
# fail the gate: intentional HOLDs (vanity cutover) + bot-walled hosts.
HOLD_HOSTS = {"4444j99.dev", "www.4444j99.dev"}
BOT_WALLED = {"www.linkedin.com", "linkedin.com"}
SKIP_SUFFIX = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".css", ".js", ".ico")
UA = {"User-Agent": "Mozilla/5.0 (profile-link-integrity)"}
GH_RE = re.compile(r"^https?://github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)/?$")


def fetch(url: str, timeout: int = 20) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def repo_is_public(owner: str, repo: str) -> bool | None:
    """True/False via gh; None if gh can't answer (offline/unauth)."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".visibility"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() == "public"


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return (m.group(1) if m else "").lower()


def collect_links() -> tuple[set[str], dict[str, int | None]]:
    links: set[str] = set()
    surface_status: dict[str, int | None] = {}
    for s in SURFACES:
        code, body = fetch(s)
        surface_status[s] = code
        for raw in re.findall(r"https?://[^\s\"'<>)\]]+", body):
            u = raw.rstrip(".,);'\"")
            if "shields.io" in u or u.lower().endswith(SKIP_SUFFIX):
                continue
            links.add(u)
    return links, surface_status


def classify(url: str) -> tuple[str, str]:
    """Return (verdict, detail). verdict in dead|private|hold|bot|ok."""
    host = host_of(url)
    if host in HOLD_HOSTS:
        return "hold", "intentional HOLD host"
    if host in BOT_WALLED:
        return "bot", "bot-walled host (not a real failure)"
    m = GH_RE.match(url)
    if m:
        pub = repo_is_public(m.group(1), m.group(2))
        if pub is False:
            return "private", f"{m.group(1)}/{m.group(2)} is private → 404 to the public"
        if pub is True:
            return "ok", "public repo"
        # gh couldn't answer → fall through to HTTP check
    code, _ = fetch(url, 15)
    if code is None or code >= 400:
        return "dead", f"HTTP {code}"
    return "ok", f"HTTP {code}"


def main() -> int:
    as_json = "--json" in sys.argv
    links, surface_status = collect_links()
    results: dict[str, list[dict[str, str]]] = {"dead": [], "private": [], "hold": [], "bot": [], "ok": []}
    ordered = sorted(links)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for url, (verdict, detail) in zip(ordered, ex.map(classify, ordered)):
            results[verdict].append({"url": url, "detail": detail})

    broken = results["dead"] + results["private"]
    unreachable_surface = [s for s, c in surface_status.items() if c is None or c >= 400]
    payload = {
        "surfaces_scanned": len(SURFACES),
        "unreachable_surfaces": unreachable_surface,
        "links_checked": len(links),
        "dead": results["dead"],
        "private_to_public": results["private"],
        "hold": results["hold"],
        "bot_walled": results["bot"],
        "ok_count": len(results["ok"]),
        "clean": not broken and not unreachable_surface,
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"profile-link-integrity: {len(links)} links across {len(SURFACES)} surfaces")
        print(
            f"  ok={len(results['ok'])}  dead={len(results['dead'])}  private-to-public={len(results['private'])}"
            f"  hold={len(results['hold'])}  bot-walled={len(results['bot'])}"
        )
        for b in broken:
            print(f"  BROKEN {b['url']} — {b['detail']}")
        for s in unreachable_surface:
            print(f"  SURFACE UNREACHABLE {s}")
        for h in results["hold"]:
            print(f"  (hold, not failed) {h['url']}")
        print("CLEAN" if payload["clean"] else "DEFECTS PRESENT")
    return 0 if payload["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
