#!/usr/bin/env python3
"""follow-harvest-organ.py — harvest the signature technique of EVERY account 4444J99 follows.

The owner's rule: "everyone I'm following ... something I want to steal from them — that doesn't
mean ask me per follow, it means figure it out for all of them." So this scans every followed
account's profile README (no human-in-the-loop), detects which README techniques each uses,
ranks them by adoption × novelty, and writes <out>/assets/follow-harvest-digest.json. The top
ranks prioritise which self-hosted elements the profile features — the harvest is the prioritiser
for our own adapted versions, never a hot-link to theirs.

    python scripts/follow-harvest-organ.py --out _profile-build
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _profile as P  # noqa: E402


def render_report(digest: dict) -> str:
    lines = [
        "# Follow-harvest digest",
        "",
        f"Scanned **{digest['following_scanned']}** followed accounts "
        f"({digest['profiles_with_readme']} have a profile README). "
        "Ranked by how many of them use each technique; we rebuild the top ones as our own "
        "self-hosted, no-third-party-widget versions.",
        "",
        "| # | Technique | Follows using it | Novelty | We self-host | Examples |",
        "|--:|-----------|-----------------:|--------:|:------------:|----------|",
    ]
    for i, t in enumerate(digest["techniques"], 1):
        mark = "✅" if t["we_self_host"] else "—"
        ex = ", ".join(f"@{e}" for e in t["examples"][:3])
        lines.append(
            f"| {i} | {t['label']} | {t['count']} ({t['adoption_pct']}%) "
            f"| {t['novelty']}% | {mark} | {ex} |"
        )
    lines.append("")
    lines.append(f"_Generated {digest['generated']} by scripts/follow-harvest-organ.py._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Harvest README techniques across all follows.")
    ap.add_argument("--login", default=P.LOGIN)
    ap.add_argument("--out", default=os.environ.get("LIMEN_PROFILE_OUT", "_profile-build"))
    args = ap.parse_args(argv)

    out = Path(args.out)
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    try:
        digest = P.harvest_following(args.login)
    except Exception as exc:
        print(f"follow-harvest: unavailable: {exc}", file=sys.stderr)
        return 2

    (assets / "follow-harvest-digest.json").write_text(json.dumps(digest, indent=2), encoding="utf-8")
    (assets / "follow-harvest-report.md").write_text(render_report(digest), encoding="utf-8")

    print(f"follow-harvest: scanned {digest['following_scanned']} follows "
          f"({digest['profiles_with_readme']} with README), {len(digest['techniques'])} techniques ranked")
    for t in digest["techniques"][:8]:
        host = "self-host" if t["we_self_host"] else "skip"
        print(f"  {t['count']:>3} {t['label']:36} [{host}] e.g. {', '.join(t['examples'][:2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
