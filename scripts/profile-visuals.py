#!/usr/bin/env python3
"""profile-visuals.py — render the self-hosted SVG suite + provability manifest for 4444J99.

Collects the live, provable facts (scripts/_profile.collect_facts) and renders OUR OWN SVGs
(no third-party widget hot-links) into <out>/assets, plus stats-manifest.json — the ledger that
makes every number re-derivable. Driven directly and by .github/workflows/profile.yml.

    python scripts/profile-visuals.py --out _profile-build
    python scripts/profile-visuals.py --out _profile-build --from-facts facts.json   # offline
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _profile as P  # noqa: E402


ASSETS = {
    "typing-header.svg": lambda f: P.render_typing_header([
        "I build production systems that solve expensive problems.",
        "Not demos. Live platforms — tested, deployed, running.",
    ]),
    "stats-card.svg": P.render_stats_card,
    "languages.svg": P.render_languages,
    "heatmap.svg": P.render_heatmap,
    "streak.svg": P.render_streak,
    "trophies.svg": P.render_trophies,
    "badges.svg": P.render_badges,
    "snake.svg": P.render_snake,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render self-hosted profile SVGs + provability manifest.")
    ap.add_argument("--login", default=P.LOGIN)
    ap.add_argument("--out", default=os.environ.get("LIMEN_PROFILE_OUT", "_profile-build"),
                    help="profile build root; assets land in <out>/assets")
    ap.add_argument("--from-facts", type=Path, help="load a cached facts JSON instead of hitting the API (tests/offline)")
    args = ap.parse_args(argv)

    out = Path(args.out)
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    try:
        facts = P.collect_facts(args.login)
    except Exception as exc:  # never partially write a lying profile
        print(f"profile-visuals: fact collection failed: {exc}", file=sys.stderr)
        return 2

    # The headline facts must be present — without them there is no profile to render.
    required = ["ecosystem_public_repos", "ecosystem_original_repos", "contributions_last_year"]
    missing = [k for k in required if facts.get(k) is None]
    if missing:
        print(f"profile-visuals: missing critical facts {missing} — refusing to render", file=sys.stderr)
        return 2

    # Graceful degradation for the contribution calendar. Its day-detail GraphQL intermittently 504s /
    # exceeds resource limits on a high-activity account; treating that as fatal froze the ENTIRE
    # profile for hours (one flaky API blocking stats, languages, chips, milestones, and the README
    # copy alike). When the calendar is missing we PRESERVE the last-good committed calendar assets and
    # backfill their derived stats from the prior manifest, then render everything else fresh — the
    # profile always updates what it can, and can never be frozen whole by one endpoint.
    calendar_assets = {"heatmap.svg", "snake.svg", "streak.svg"}
    calendar_stats = ("current_streak_days", "active_days_last_year")
    calendar_ok = bool(facts.calendar_days)
    if not calendar_ok:
        prior_stats: dict = {}
        try:
            prior_stats = json.loads((assets / "stats-manifest.json").read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            prior_stats = {}
        for key in calendar_stats:
            if facts.get(key) is None and key in prior_stats:
                p = prior_stats[key]
                facts.put(P.Fact(key, p.get("value"), "last-good (calendar API unavailable this run)",
                                 p.get("source_query", ""), p.get("attest", "api")))
        preserved = sorted(n for n in calendar_assets if (assets / n).exists())
        print("profile-visuals: contribution calendar unavailable (API 504/resource-limit) — DEGRADED: "
              f"preserving last-good {preserved}, backfilling {list(calendar_stats)} from prior manifest, "
              "rendering everything else fresh.", file=sys.stderr)

    for name, render in ASSETS.items():
        # when the calendar is down, keep the last-good committed calendar SVG instead of an empty one
        if name in calendar_assets and not calendar_ok and (assets / name).exists():
            continue
        (assets / name).write_text(render(facts), encoding="utf-8")

    manifest = facts.manifest()
    manifest["languages"] = dict(facts.languages.most_common())
    (assets / "stats-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # the public-repo index — sync-readme lists a system only if its repo is verifiably public
    (assets / "public-repos.json").write_text(
        json.dumps({"generated": facts.generated, "public_repos": facts.public_repos}, indent=2),
        encoding="utf-8")

    print(f"profile-visuals: {len(ASSETS)} SVGs + manifest ({len(facts.items)} provable stats) -> {assets}")
    for k, fact in facts.items.items():
        print(f"  {k:28} = {fact.value!s:>10} [{fact.attest}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
