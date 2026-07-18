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

    # Refuse to render a degraded profile: the headline facts must be present, and the calendar
    # must have loaded (else heatmap/snake/streak would be empty). A failed run keeps the prior
    # good commit — never overwrite a good profile with a broken one.
    required = ["ecosystem_public_repos", "ecosystem_original_repos", "contributions_last_year"]
    missing = [k for k in required if facts.get(k) is None]
    if missing:
        print(f"profile-visuals: missing critical facts {missing} — refusing to render", file=sys.stderr)
        return 2
    if not facts.calendar_days:
        print("profile-visuals: contribution calendar unavailable — refusing to render "
              "(heatmap/snake/streak would be empty)", file=sys.stderr)
        return 2

    for name, render in ASSETS.items():
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
