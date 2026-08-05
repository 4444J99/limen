"""Offline unit tests for the 4444J99 profile engine (scripts/_profile.py).

All tests are hermetic — no GitHub API calls. Follows/READMEs and Facts are synthetic; the
harvest injects a fake readme_fetcher. Mirrors the importlib load pattern of the other
scripts/ tests, with a sys.modules registration required by dataclasses under importlib.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import xml.dom.minidom
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "_profile.py"


def load():
    spec = importlib.util.spec_from_file_location("_profile", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_profile"] = mod  # dataclasses need the module registered when loaded via importlib
    spec.loader.exec_module(mod)
    return mod


P = load()


def synthetic_facts():
    f = P.Facts(login="4444J99", name="Test Builder")
    for k, v in {
        "ecosystem_public_repos": 238,
        "ecosystem_original_repos": 209,
        "ecosystem_stars": 61,
        "contributions_last_year": 29696,
        "current_streak_days": 63,
        "active_days_last_year": 273,
        "member_since": "2016",
    }.items():
        f.put(P.Fact(k, v, "live-public-gh-api", f"gh api ... {k}"))
    f.languages = Counter({"Python": 85, "TypeScript": 42, "JavaScript": 14, "Shell": 9})
    # 371 days ending today, last 63 all active (for the streak test)
    today = dt.date(2026, 7, 17)
    days = []
    for i in range(371):
        d = today - dt.timedelta(days=370 - i)
        ago = (today - d).days
        # exactly the last 63 days active; day-63-ago is 0 so the streak is deterministically 63
        count = 5 if ago < 63 else (0 if ago == 63 else (2 if i % 3 else 0))
        days.append({"date": d.isoformat(), "weekday": d.weekday(), "contributionCount": count})
    f.calendar_days = days
    return f


# --- technique detection + harvest -----------------------------------------


def test_detect_techniques_finds_widgets_and_native():
    readme = (
        "![typing](https://readme-typing-svg.demolab.com/?lines=hi)\n"
        "<details><summary>more</summary>x</details>\n"
        "![stats](https://github-readme-stats.vercel.app/api?username=x)\n"
        "```mermaid\ngraph LR\n```\n"
    )
    found = set(P.detect_techniques(readme))
    assert {"typing_header", "collapsible", "stats_card", "mermaid"} <= found


def test_harvest_ranks_by_adoption_and_flags_self_host():
    follows = ["a", "b", "c", "d"]
    readmes = {
        "a": "![](https://img.shields.io/badge/x-y)",
        "b": "![](https://img.shields.io/badge/x-y) <details></details>",
        "c": "![](https://readme-typing-svg.demolab.com/x)",
        "d": None,  # no profile readme
    }
    digest = P.harvest_following("4444J99", followers=follows, readme_fetcher=lambda who: readmes.get(who))
    assert digest["following_scanned"] == 4
    assert digest["profiles_with_readme"] == 3
    techs = {t["technique"]: t for t in digest["techniques"]}
    assert techs["shields_badges"]["count"] == 2  # a + b
    assert techs["shields_badges"]["rendered_asset"] == "badges.svg"
    assert techs["shields_badges"]["we_self_host"] is True
    # ranked by count desc
    assert digest["techniques"][0]["technique"] == "shields_badges"


# --- streak -----------------------------------------------------------------


def test_current_streak_counts_trailing_active_days():
    f = synthetic_facts()
    assert P.current_streak(f.calendar_days, today=dt.date(2026, 7, 17)) == 63


def test_current_streak_holds_when_today_empty_but_yesterday_active():
    today = dt.date(2026, 7, 17)
    days = [
        {"date": (today - dt.timedelta(days=2)).isoformat(), "weekday": 0, "contributionCount": 4},
        {"date": (today - dt.timedelta(days=1)).isoformat(), "weekday": 1, "contributionCount": 3},
        {"date": today.isoformat(), "weekday": 2, "contributionCount": 0},
    ]
    assert P.current_streak(days, today=today) == 2


# --- provability predicate --------------------------------------------------


def test_readme_number_tokens_ignores_dates_but_catches_stats():
    text = "Generated 2026-07-17T21:45:39Z with 29,696 contributions and 3399 tests and 5 formats."
    toks = P.readme_number_tokens(text)
    assert "29696" in toks and "3399" in toks
    assert "2026" not in toks and "5" not in toks


def test_verify_readme_clean_passes():
    f = synthetic_facts()
    manifest = f.manifest()
    readme = "238 public repos, 29,696 contributions. ![](./assets/stats-card.svg)"
    assert P.verify_readme(readme, manifest) == []


def test_verify_readme_flags_all_violations():
    f = synthetic_facts()
    manifest = f.manifest()
    bad = "Top-tier creative technologist. 987654 stars. ![](https://github-readme-stats.vercel.app/api?username=x)"
    problems = P.verify_readme(bad, manifest)
    joined = " ".join(problems)
    assert "nothing-phrase" in joined
    assert "unprovable number" in joined
    assert "widget host" in joined or "non-local image" in joined


# --- rendering (well-formed SVG) -------------------------------------------


def test_all_renderers_emit_wellformed_svg():
    f = synthetic_facts()
    renderers = [
        P.render_stats_card,
        P.render_languages,
        P.render_heatmap,
        P.render_streak,
        P.render_trophies,
        P.render_badges,
        P.render_snake,
    ]
    for render in renderers:
        svg = render(f)
        xml.dom.minidom.parseString(svg)  # raises if malformed
        assert svg.startswith("<svg")
    header = P.render_typing_header(["line one", "line two"])
    xml.dom.minidom.parseString(header)


def test_manifest_shape_and_attest_tags():
    f = synthetic_facts()
    m = f.manifest()
    assert m["display_name"] == "Test Builder"
    assert m["login"] == "4444J99"
    assert m["stats"]["ecosystem_public_repos"]["value"] == 238
    assert m["stats"]["ecosystem_public_repos"]["attest"] == "api"
    assert "source_query" in m["stats"]["ecosystem_public_repos"]


def test_text_on_contrast_picks_dark_for_light():
    assert P._text_on("#f1e05a") == "#0d1117"  # JavaScript yellow -> dark text
    assert P._text_on("#3572A5") == "#ffffff"  # Python blue -> light text
