#!/usr/bin/env python3
"""traffic-collect.py — the "is anyone SEEING this?" signal for the public face.

GitHub's traffic API (/traffic/views|clones|popular/referrers|popular/paths) is the ONLY real
visibility signal it exposes, and nothing in the estate touched it. This collects it for the
value-repos (+ the profile repo) and appends a dated snapshot per repo to
logs/observatory/traffic.jsonl — the "seen" stage of the conversion funnel (scripts/conversion-funnel.py)
and the prevalence signal OBSERVATORY was missing. Read-only; requires push access to each repo
(the traffic API 403s otherwise — recorded, never fatal).

    python scripts/traffic-collect.py                 # value-repos.json + 4444J99/4444J99
    python scripts/traffic-collect.py --repos organvm/limen
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "logs" / "observatory" / "traffic.jsonl"
PROFILE_REPO = "4444J99/4444J99"


def _today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def gh_json(path: str, *, timeout: int = 45):
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True,
                          timeout=timeout, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "gh failed").strip().splitlines()[-1][:200])
    return json.loads(proc.stdout or "null")


def value_repos() -> list[str]:
    data = json.loads((ROOT / "value-repos.json").read_text(encoding="utf-8"))
    out = []
    for e in data.get("repos", []):
        out.append(e if isinstance(e, str) else e.get("repo"))
    return [r for r in out if r]


def collect_repo(repo: str) -> dict:
    """One repo's traffic snapshot. Partial failures degrade to nulls, never abort the run."""
    def _try(path, pick):
        try:
            return pick(gh_json(path))
        except Exception as exc:
            return {"_error": str(exc)}

    views = _try(f"repos/{repo}/traffic/views",
                 lambda d: {"count": d.get("count", 0), "uniques": d.get("uniques", 0)})
    clones = _try(f"repos/{repo}/traffic/clones",
                  lambda d: {"count": d.get("count", 0), "uniques": d.get("uniques", 0)})
    referrers = _try(f"repos/{repo}/traffic/popular/referrers",
                     lambda d: [{"referrer": r.get("referrer"), "count": r.get("count"),
                                 "uniques": r.get("uniques")} for r in (d or [])[:10]])
    paths = _try(f"repos/{repo}/traffic/popular/paths",
                 lambda d: [{"path": p.get("path"), "count": p.get("count"),
                             "uniques": p.get("uniques")} for p in (d or [])[:10]])
    return {
        "repo": repo,
        "date": _today(),
        "fetched_at": _now(),
        "window_days": 14,
        "views": views,
        "clones": clones,
        "referrers": referrers,
        "top_paths": paths,
        "source": f"gh api repos/{repo}/traffic/*",
    }


def _existing_keys(ledger: Path) -> set[tuple[str, str]]:
    if not ledger.exists():
        return set()
    keys = set()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            keys.add((r.get("repo"), r.get("date")))
        except Exception:
            continue
    return keys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect GitHub traffic for the value-repos + profile.")
    ap.add_argument("--repos", nargs="*", help="explicit repo list; default = value-repos.json + profile")
    ap.add_argument("--out", type=Path, default=LEDGER)
    args = ap.parse_args(argv)

    repos = args.repos or (value_repos() + [PROFILE_REPO])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    already = _existing_keys(args.out)

    written = skipped = errored = 0
    total_views = total_view_uniques = 0
    with args.out.open("a", encoding="utf-8") as fh:
        for repo in repos:
            if (repo, _today()) in already:
                skipped += 1
                continue
            snap = collect_repo(repo)
            fh.write(json.dumps(snap) + "\n")
            v = snap["views"]
            if isinstance(v, dict) and "_error" in v:
                errored += 1
            else:
                total_views += int(v.get("count", 0) or 0)
                total_view_uniques += int(v.get("uniques", 0) or 0)
            written += 1

    print(f"traffic-collect: {written} snapshots ({skipped} already today, {errored} traffic-403/err) -> {args.out}")
    print(f"  total repo-page views (14d): {total_views} · unique visitors: {total_view_uniques} across {written} repos")
    if written and total_view_uniques < 50:
        print("  ⚠ visibility is near-zero — the conversion bottleneck is almost certainly DISCOVERY "
              "(see scripts/conversion-funnel.py).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
