#!/usr/bin/env python3
"""contributions-organ.py — SPECVLVM, the contributions mirror (the OSPO organ's face).

Doctrine: we contribute OUTWARD to study other projects' wiring and improve INWARD; community
standing and name recognition are byproducts of genuine value, never the objective. This is the
public proof mirror PLAN-06 owner packet 04 left unowned — limen is the named owner surface
(docs/current-session-fanout/PLAN-06-contrib-mirror.md). It consumes hub-ledger outputs ONLY
(never raw sessions or private archaeology), renders contribution outcomes as proof categories
(merged / open / no-PR / closed / protocol-due / post-close), and redacts local paths and private
notes before anything touches the surface.

Offline on the beat: reads the local hub checkout (LIMEN_CONTRIB_LEDGER) or the committed cache;
a `gh api` cache refresh runs ONLY with --refresh or LIMEN_CONTRIB_REFRESH=1. When every source is
absent it renders its own staleness receipt instead of pretending — an honest mirror shows its
dust — and still exits 0 (fail-open, never gates the beat). The organ NEVER sends: no comments,
bumps, PRs, or posts; outbound stays the human's hand.

  python3 scripts/contributions-organ.py            # render MIRROR.md + logs/contributions.json
  python3 scripts/contributions-organ.py --refresh  # also refresh the ledger cache from GitHub (read-only API)
  python3 scripts/contributions-organ.py --check    # predicate: committed mirror matches a fresh render (exit 0 <=> current)

The mirror body is deterministic (stamped from source metadata, not the clock), so re-runs against
unchanged sources are byte-identical — the idempotent fixed point the closeout discipline demands.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
HUB_LEDGER = Path(os.environ.get("LIMEN_CONTRIB_LEDGER", HOME / "Workspace" / "organvm" / "contrib" / "LEDGER.yaml"))
HUB_REPO = os.environ.get("LIMEN_CONTRIB_HUB_REPO", "organvm/contrib")
BACKFLOW = Path(
    os.environ.get(
        "LIMEN_BACKFLOW_MANIFEST", HOME / "Workspace" / "organvm-corpvs-testamentvm" / "backflow-manifest.yaml"
    )
)
ORGAN_HOME = ROOT / "organs" / "contributions"
CACHE = ORGAN_HOME / "ledger-cache.json"
MIRROR = ORGAN_HOME / "MIRROR.md"
SIGNAL = ROOT / "logs" / "contributions.json"

# PLAN-06 proof categories, in render order.
CATEGORIES = ("merged", "open", "no-PR", "closed", "protocol-due", "post-close")


def _category(status: str) -> str:
    s = status.lower().strip().replace("_", "-")
    if s == "merged":
        return "merged"
    if s in {"closed", "rejected"}:
        return "closed"
    if s in {"post-close", "postclose"}:
        return "post-close"
    if s in {"protocol-due", "needs-bump", "stale", "needs-response"}:
        return "protocol-due"
    if s in {"no-pr", "nopr", "workspace", "scouted", "none", "planned"}:
        return "no-PR"
    return "open"  # open / draft / waiting-on-maintainer / unknown


def _public(value: Any) -> str:
    """Redaction gate: only short public strings reach the surface; local paths never do."""
    text = str(value or "").strip()
    if not text or "/Users/" in text or text.startswith(("~", "/")):
        return ""
    return text.replace("|", "\\|")


def _ledger_items(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict):
        return []
    items = obj.get("contributions") or obj.get("items") or obj.get("prs") or []
    if isinstance(items, dict):
        items = list(items.values())
    return [i for i in items if isinstance(i, dict)]


def _normalize(item: dict[str, Any]) -> tuple[str, str, str, str]:
    """One hub-ledger item -> (repo, title, url, proof category). Speaks both the refresh-ledger
    contract (upstream_repo/pr_state/pr_title/upstream_pr) and the generic repo/status/title one;
    `workspace` and `notes` never pass this gate."""
    repo = _public(item.get("upstream_repo") or item.get("repo") or item.get("name") or item.get("id") or "")
    title = _public(item.get("pr_title") or item.get("title"))
    pr = item.get("upstream_pr")
    url = _public(item.get("url") or (f"https://github.com/{repo}/pull/{pr}" if repo and pr else ""))
    status = str(item.get("pr_state") or item.get("status") or item.get("state") or "").strip()
    if item.get("pr_merged_at"):
        status = "merged"
    elif not status and not pr:
        status = "no-PR"
    return repo, title, url, _category(status or "open")


def load_sources() -> tuple[list[dict[str, Any]], str, str]:
    """Return (items, source-name, as-of stamp). Local hub checkout wins; else committed cache; else absent."""
    if HUB_LEDGER.exists():
        try:
            obj = yaml.safe_load(HUB_LEDGER.read_text()) or {}
            stamp = dt.datetime.fromtimestamp(HUB_LEDGER.stat().st_mtime, dt.UTC).strftime("%Y-%m-%d")
            return _ledger_items(obj), "local hub checkout", stamp
        except Exception:
            pass
    if CACHE.exists():
        try:
            obj = json.loads(CACHE.read_text())
            return _ledger_items(obj), "committed cache", str(obj.get("fetched") or "unknown")
        except Exception:
            pass
    return [], "absent", ""


def refresh_cache() -> bool:
    """Pull the hub LEDGER.yaml via the read-only GitHub contents API into the committed cache."""
    try:
        raw = subprocess.run(
            ["gh", "api", f"repos/{HUB_REPO}/contents/LEDGER.yaml", "--jq", ".content"],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
            check=True,
        ).stdout
        obj = yaml.safe_load(base64.b64decode(raw)) or {}
        items = _ledger_items(obj)
        if not items:
            print(f"refresh: {HUB_REPO} LEDGER.yaml has no contribution items; cache left untouched")
            return False
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
            "source": f"{HUB_REPO}/LEDGER.yaml",
            "contributions": items,
        }
        CACHE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"refresh: cached {len(items)} item(s) from {HUB_REPO}")
        return True
    except Exception as exc:  # fail-open: the beat never hangs on GitHub
        print(f"refresh: unavailable ({type(exc).__name__}); mirror will render from existing sources")
        return False


def backflow_tally() -> dict[str, int]:
    """Optional inward-lens tally: signals routed per receiving organ. Absent manifest -> {}."""
    if not BACKFLOW.exists():
        return {}
    try:
        obj = yaml.safe_load(BACKFLOW.read_text()) or {}
    except Exception:
        return {}
    signals = obj.get("signals") or obj.get("entries") or obj.get("backflow") or []
    if isinstance(signals, dict):
        signals = list(signals.values())
    tally: dict[str, int] = {}
    for sig in signals:
        if isinstance(sig, dict):
            organ = _public(sig.get("organ") or sig.get("target") or "unrouted") or "unrouted"
            tally[organ] = tally.get(organ, 0) + 1
    return tally


def render(items: list[dict[str, Any]], source: str, as_of: str, flow: dict[str, int]) -> str:
    counts = dict.fromkeys(CATEGORIES, 0)
    rows: list[tuple[str, str, str, str]] = []
    for item in items:
        row = _normalize(item)
        counts[row[3]] += 1
        rows.append(row)
    rows.sort(key=lambda r: (CATEGORIES.index(r[3]), r[0]))

    lines = [
        "# SPECVLVM — the contributions mirror",
        "",
        "> Outward to learn inward: each upstream is a lens on wiring worth absorbing; community and",
        "> name recognition accrue as byproducts of genuine value. Rendered by",
        "> `scripts/contributions-organ.py` from hub-ledger outputs only (PLAN-06 owner packet 04 —",
        "> limen is the owner surface). **Nothing here sends** — every outbound act is the human's hand.",
        "",
    ]
    if source == "absent":
        lines += [
            "## Staleness receipt",
            "",
            "The hub ledger is unreachable: the local hub checkout is absent and no cache has been",
            f"fetched yet. Restore the `{HUB_REPO}` checkout or run with `--refresh` (PLAN-06 owner",
            "packet 01 tracks the hub-side repair). An honest mirror shows its dust — counts below",
            "are empty, not zero-by-achievement.",
            "",
        ]
    else:
        lines += [f"_Source: {source} (as of {as_of}) · {len(rows)} tracked contribution(s)_", ""]
    lines += ["## Proof", "", "| " + " | ".join(CATEGORIES) + " |", "|" + "---|" * len(CATEGORIES)]
    lines += ["| " + " | ".join(str(counts[c]) for c in CATEGORIES) + " |", ""]
    if rows:
        lines += ["| upstream | contribution | ref | proof |", "|---|---|---|---|"]
        lines += [f"| {r or '—'} | {t or '—'} | {u or '—'} | {c} |" for r, t, u, c in rows]
        lines += [""]
    lines += ["## Backflow (the inward product)", ""]
    if flow:
        lines += [f"- **{organ}** — {n} signal(s) routed inward" for organ, n in sorted(flow.items())]
    else:
        lines += ["- backflow manifest not readable from this host — the tally renders where it is."]
    lines += [
        "",
        "## The estate this mirror reflects",
        "",
        f"- Hub: `{HUB_REPO}` (generated LEDGER; state surface)",
        "- Engines: `organvm_engine.contrib` (A) + `contrib_engine/` in orchestration-start-here (B)",
        "- Workspaces: the `contrib--*` tracking repos, one per upstream",
        "- Charter: `organs/contributions/CHARTER.md` · Kernel: `organs/contributions/KERNEL.md`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="SPECVLVM — render the contributions mirror")
    ap.add_argument("--refresh", action="store_true", help="refresh the ledger cache from GitHub first (read-only)")
    ap.add_argument("--check", action="store_true", help="exit 0 iff the committed mirror matches a fresh render")
    args = ap.parse_args()

    if args.refresh or os.environ.get("LIMEN_CONTRIB_REFRESH") == "1":
        refresh_cache()

    items, source, as_of = load_sources()
    body = render(items, source, as_of, backflow_tally())

    if args.check:
        current = MIRROR.read_text() if MIRROR.exists() else ""
        if current == body:
            print(f"mirror current ({source}; {len(items)} item(s))")
            return 0
        print("mirror STALE: re-run scripts/contributions-organ.py to re-render")
        return 1

    ORGAN_HOME.mkdir(parents=True, exist_ok=True)
    changed = not MIRROR.exists() or MIRROR.read_text() != body
    if changed:
        MIRROR.write_text(body)
    SIGNAL.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    for item in items:
        counts[_normalize(item)[3]] += 1
    SIGNAL.write_text(
        json.dumps(
            {
                "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "organ": "contributions",
                "source": source,
                "as_of": as_of,
                "stale": source == "absent",
                "total": len(items),
                "counts": counts,
                "mirror": "organs/contributions/MIRROR.md",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"mirror {'re-rendered' if changed else 'unchanged'} ({source}; {len(items)} item(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
