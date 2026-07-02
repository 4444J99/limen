#!/usr/bin/env python3
"""link-health.py — the organ that handles links.

A dead link on a public identity surface is silent demand-loss: it repels the exact
visitor the front door is built to pull, and no one reports it. Fixing one by hand is a
one-off; this organ makes it a REPEATABLE process. Every cadence it reads the surface
registry (link-surfaces.json), fetches each surface, extracts its outbound links, and
probes each one. A 404 on any tracked surface fails the predicate — the same shape as
`creds-hydrate --verify` (presence is not the predicate; *reachability* is).

When a dead link's host matches a `remap` rule (e.g. the bare `4444j99.github.io` user
site that never had a Pages build -> the working `organvm.github.io`), the organ verifies
the remapped URL is live and prints the exact fix, so detection and repair are one loop.

  python3 scripts/link-health.py              # human report; exit 1 if any dead link
  python3 scripts/link-health.py --verify     # beat form: quiet unless broken, exit 1 on dead
  python3 scripts/link-health.py --json        # machine report to stdout
  python3 scripts/link-health.py --throttle 21600   # no-op if checked within 6h (beat self-throttle)

Anti-waste + fail-open: read-only on the graph (one `gh api` per readme surface, plain HTTP
HEAD elsewhere); decorative badge hosts are ignored so signal stays high; a fetch error on a
SURFACE fails open (skipped, not counted dead) while a 404 on a LINK is the real signal.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
REGISTRY = Path(os.environ.get("LIMEN_LINK_SURFACES", ROOT / "link-surfaces.json"))
STATE_DIR = ROOT / ".limen-private" / "link-health"
STAMP = STATE_DIR / "last.json"

UA = "limen-link-health/1.0 (+https://github.com/organvm/limen)"
TIMEOUT = 8
# markdown [text](url), html href/src="url", and bare http(s) urls.
LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)|(?:href|src)=[\"'](https?://[^\"']+)[\"']|(?<![\"'(=])(https?://[^\s\"'<>)\]]+)")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sh(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, r.stdout


def load_registry() -> dict:
    data = json.loads(REGISTRY.read_text())
    data.setdefault("surfaces", [])
    data.setdefault("remap", [])
    data.setdefault("ignore_hosts", [])
    return data


def fetch_surface(surface: dict) -> tuple[str | None, str | None]:
    """(text, error). text is None on a surface-level failure (fails OPEN — skipped, not dead)."""
    kind = surface.get("type")
    ref = surface.get("ref", "")
    if kind == "github_readme":
        code, out = sh(["gh", "api", f"repos/{ref}/readme", "-H", "Accept: application/vnd.github.raw"])
        if code == 0 and out.strip():
            return out, None
        # fallback: some gh versions ignore the raw Accept header and return JSON with base64 content.
        code2, out2 = sh(["gh", "api", f"repos/{ref}/readme", "--jq", ".content"])
        if code2 == 0 and out2.strip():
            try:
                return base64.b64decode(out2).decode("utf-8", "replace"), None
            except (ValueError, UnicodeDecodeError):
                pass
        return None, f"gh api repos/{ref}/readme failed"
    if kind == "url":
        status, _final, err = probe(ref)
        if status is None:
            return None, f"surface url unreachable: {err}"
        try:
            req = urllib.request.Request(ref, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read(600_000).decode("utf-8", "replace"), None
        except (urllib.error.URLError, socket.timeout, ValueError) as e:
            # the url resolved on probe() but the body read failed — treat the surface itself as the one link.
            return ref, f"body read failed ({e}); checked the surface url only"
    return None, f"unknown surface type: {kind!r}"


def extract_links(text: str, ignore_hosts: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for m in LINK_RE.finditer(text):
        url = m.group(1) or m.group(2) or m.group(3)
        if not url:
            continue
        url = url.rstrip(".,);'\"")
        host = (urlparse(url).hostname or "").lower()
        if any(host == h or host.endswith("." + h) for h in ignore_hosts):
            continue
        seen.setdefault(url, None)
    return list(seen)


def probe(url: str) -> tuple[int | None, str, str | None]:
    """(status, final_url, error). status None => dead (DNS/timeout/refused). HEAD, GET-fallback on 405."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, resp.geturl(), None
        except urllib.error.HTTPError as e:
            if e.code in (403, 405) and method == "HEAD":
                continue  # some servers refuse HEAD — retry as GET
            return e.code, url, None
        except (urllib.error.URLError, socket.timeout, ValueError, ConnectionError) as e:
            return None, url, str(getattr(e, "reason", e))
    return None, url, "unreachable"


def suggest_fix(url: str, remap: list[dict]) -> dict | None:
    host = (urlparse(url).hostname or "").lower()
    for rule in remap:
        if host == rule.get("from_host", "").lower():
            fixed = url.replace(rule["from_host"], rule["to_host"], 1)
            status, _final, _err = probe(fixed)
            return {"to": fixed, "verified_live": status is not None and status < 400,
                    "status": status, "why": rule.get("why", "")}
    return None


# Bot-protection / auth / rate-limit codes mean "I could not verify" — NOT "broken". LinkedIn's
# signature 999, a WAF 403, and 429 rate-limits are unverifiable, so they must never fail the
# predicate (a link organ that cries wolf on every bot-blocked social link gets muted).
BLOCKED_CODES = {401, 403, 429, 999}


def classify(status: int | None) -> str:
    if status is None:
        return "unreachable"  # DNS failure / timeout / refused — treated as broken for an identity surface
    if status in BLOCKED_CODES:
        return "blocked"
    if status >= 400:
        return "dead"  # 404/410/other 4xx/5xx — genuinely broken
    return "ok"


def run(reg: dict) -> dict:
    surfaces_out = []
    total_dead = total_blocked = total_links = 0
    for surface in reg["surfaces"]:
        text, err = fetch_surface(surface)
        entry = {"id": surface.get("id"), "label": surface.get("label"), "ref": surface.get("ref"),
                 "links": [], "dead": [], "blocked": [], "skipped_surface": None}
        if text is None:
            entry["skipped_surface"] = err  # fail OPEN: a surface we can't fetch is not a broken link
            surfaces_out.append(entry)
            continue
        for url in extract_links(text, reg["ignore_hosts"]):
            status, final, perr = probe(url)
            total_links += 1
            kind = classify(status)
            rec = {"url": url, "status": status, "class": kind, "final": final if final != url else None}
            if kind in ("dead", "unreachable"):
                total_dead += 1
                rec["error"] = perr
                fix = suggest_fix(url, reg["remap"])
                if fix:
                    rec["fix"] = fix
                entry["dead"].append(rec)
            elif kind == "blocked":
                total_blocked += 1
                entry["blocked"].append(rec)
            entry["links"].append(rec)
        surfaces_out.append(entry)
    return {"generated_at": now_iso(), "surfaces": surfaces_out,
            "total_links": total_links, "total_dead": total_dead, "total_blocked": total_blocked,
            "ok": total_dead == 0}


def write_stamp(report: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(json.dumps(report, indent=2) + "\n")


def throttled(seconds: int) -> dict | None:
    """Return the cached report if the last run is younger than `seconds`, else None."""
    if seconds <= 0 or not STAMP.exists():
        return None
    try:
        cached = json.loads(STAMP.read_text())
        last = dt.datetime.fromisoformat(cached["generated_at"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    age = (dt.datetime.now(dt.timezone.utc) - last).total_seconds()
    return cached if age < seconds else None


def render(report: dict, verify: bool) -> str:
    if verify and report["ok"]:
        return ""  # beat form is silent when green
    lines = []
    flag = "✓ all links live" if report["ok"] else f"✗ {report['total_dead']} dead link(s)"
    blocked = report.get("total_blocked", 0)
    tail = f", {blocked} blocked/unverifiable" if blocked else ""
    lines.append(f"link-health: {flag}  ({report['total_links']} checked across "
                 f"{len(report['surfaces'])} surfaces{tail})")
    for s in report["surfaces"]:
        if s["skipped_surface"]:
            lines.append(f"  ~ {s['id']}: surface skipped (fail-open) — {s['skipped_surface']}")
            continue
        if not s["dead"]:
            if not verify:
                lines.append(f"  ✓ {s['id']}: {len(s['links'])} links live")
            continue
        lines.append(f"  ✗ {s['id']} — {s['label']}")
        for d in s["dead"]:
            st = d["status"] if d["status"] is not None else f"unreachable ({d.get('error')})"
            lines.append(f"      DEAD [{st}] {d['url']}")
            fix = d.get("fix")
            if fix:
                mark = "verified live" if fix["verified_live"] else f"status {fix['status']}"
                lines.append(f"        -> fix: {fix['to']}  ({mark})")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true", help="beat form: silent when green, exit 1 on any dead link")
    ap.add_argument("--json", action="store_true", help="emit the machine report to stdout")
    ap.add_argument("--throttle", type=int, default=0, metavar="SEC",
                    help="no-op (use cached result) if the last run is younger than SEC (beat self-throttle)")
    args = ap.parse_args()

    cached = throttled(args.throttle)
    report = cached if cached is not None else run(load_registry())
    if cached is None:
        write_stamp(report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        out = render(report, args.verify)
        if out:
            print(out)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
