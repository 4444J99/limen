"""_profile.py — the profile-engine library for the 4444J99 GitHub profile.

WHY THIS EXISTS
---------------
The profile README at github.com/4444J99 carried a "nothing phrase" ("Top-tier
Creative Technologist") and a wall of self-reported numbers that traced to no live
source and contradicted the API (the personal account owns 1 public repo; the work
lives under the organvm orgs). This module makes every number on the profile
*provable*: it is queried live from the GitHub API at generate-time and emitted into
a committed `stats-manifest.json` as {value, basis, source_query, fetched_at} so any
claim is re-derivable. Visuals are rendered as our OWN self-hosted SVGs (no
third-party widget hot-links). A follow-harvester ranks the techniques every followed
account uses, and that ranking prioritises which self-hosted elements we feature.

DESIGN NOTES
------------
* Ground truth is the live API, not the frozen `system-vars` register — this sidesteps
  the three severed CI pipes documented in face-ownership.json and can never drift.
* A number is only a lie when UNBOUND from its basis (face-ownership.json's
  named_variables doctrine). Every fact here carries its `basis`.
* Contribution fields blow GitHub GraphQL's RESOURCE_LIMITS when queried together on a
  high-activity account, so each is fetched in its OWN isolated call (fetch_calendar_total).
* Facts fetch under try/except and degrade to None; the manifest and renderers OMIT a
  missing fact rather than printing a number we could not prove.
* SVG animations use SMIL <animate>, never CSS @keyframes — GitHub's camo image proxy
  preserves the former and strips the latter, which is why committed SMIL SVGs animate
  on a profile but CSS ones do not.

This is an importable helper (leading-underscore convention, cf. scripts/_pr_scan.py);
the thin CLI organs profile-visuals.py / sync-readme.py / follow-harvest-organ.py /
profile-verify.py drive it.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

LOGIN = "4444J99"

# Orgs are DERIVED at run-time from `users/<login>/orgs`; this is only the fallback set
# (public org memberships can be API-flaky). Names are outputs — never the source of truth.
FALLBACK_ORGS = [
    "organvm",
    "organvm-i-theoria",
    "organvm-ii-poiesis",
    "organvm-iii-ergon",
    "organvm-iv-taxis",
    "organvm-v-logos",
    "organvm-vi-koinonia",
    "organvm-vii-kerygma",
    "meta-organvm",
    "a-organvm",
]

# Third-party widget hosts we must NEVER hot-link (the owner wants our own adapted
# versions). profile-verify.py greps the rendered README against this denylist.
THIRD_PARTY_WIDGET_HOSTS = [
    "github-readme-stats",
    "readme-typing-svg",
    "streak-stats",
    "github-profile-trophy",
    "github-readme-streak",
    "capsule-render",
    "activity-graph",
    "readme-stats",
    "demolab.com",
    "herokuapp.com",
    "img.shields.io",
    "skillicons.dev",
    "spotify-github-profile",
]


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# GitHub API client (gh subprocess; auth flows from the environment / gh login)
# ---------------------------------------------------------------------------


class GhError(RuntimeError):
    """A gh invocation failed; callers catch this to degrade a single fact gracefully."""


def _gh(args: list[str], *, timeout: int = 90) -> str:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise GhError(proc.stderr.strip() or proc.stdout.strip() or "gh failed")
    return proc.stdout


def gh_json(path: str, *, paginate: bool = False, timeout: int = 90) -> Any:
    args = ["api", path]
    if paginate:
        args.insert(1, "--paginate")
    return json.loads(_gh(args, timeout=timeout) or "null")


_TRANSIENT = ("resource_limits", "rate limit", "was submitted too quickly", "timed out", "timeout")


def gh_graphql(query: str, *, timeout: int = 90, retries: int = 3, **variables: Any) -> dict[str, Any]:
    """Run a GraphQL query, retrying transient RESOURCE_LIMITS/rate errors — GitHub throws these
    intermittently on high-activity accounts even for a single-field query."""
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F", f"{key}={value}"]
    last: Exception | None = None
    for attempt in range(retries):
        try:
            payload = json.loads(_gh(args, timeout=timeout))
            if payload.get("errors"):
                raise GhError(json.dumps(payload["errors"]))
            return payload.get("data") or {}
        except (GhError, subprocess.TimeoutExpired) as exc:
            last = exc
            if not any(t in str(exc).lower() for t in _TRANSIENT) or attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise last or GhError("gh_graphql failed")


def fetch_calendar_total(login: str = LOGIN) -> int:
    """Last-year contribution total, fetched ALONE so it stays under GraphQL resource limits.
    Load-bearing → extra retries (the resource limit is intermittent, not a rate cap)."""
    q = "query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{totalContributions}}}}"
    data = gh_graphql(q, retries=5, l=login)
    return int(data["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"])


def fetch_calendar_days(login: str = LOGIN) -> list[dict[str, Any]]:
    """The day-by-day contribution calendar (for streak + heatmap). Its own isolated, retried call.
    Slim projection (no color — we grade our own) to stay well under the resource limit."""
    q = (
        "query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{"
        "weeks{contributionDays{contributionCount date weekday}}}}}}"
    )
    data = gh_graphql(q, retries=5, l=login)
    weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [day for week in weeks for day in week["contributionDays"]]


# ---------------------------------------------------------------------------
# Fact collection — every fact bound to a basis + the exact query that proves it
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    key: str
    value: Any
    basis: str  # e.g. "live-public-gh-api", "repo-attested-ci", "curated-registry"
    source_query: str  # the exact gh/graphql call a skeptic can re-run
    attest: str = "api"  # "api" (re-derivable by query) | "repo" (proven by a repo's own CI)


@dataclass
class Facts:
    login: str
    name: str = ""
    generated: str = field(default_factory=_now_iso)
    items: dict[str, Fact] = field(default_factory=dict)
    calendar_days: list[dict[str, Any]] = field(default_factory=list)
    languages: Counter = field(default_factory=Counter)
    public_repos: list[str] = field(default_factory=list)  # "owner/name" of every public ecosystem repo

    def put(self, fact: Fact) -> None:
        self.items[fact.key] = fact

    def get(self, key: str, default: Any = None) -> Any:
        f = self.items.get(key)
        return f.value if f else default

    def manifest(self) -> dict[str, Any]:
        return {
            "display_name": self.name,
            "_doc": (
                "Provability manifest for the 4444J99 profile. Every number rendered on the "
                "README appears here with the exact query that re-derives it. attest=api => "
                "re-run source_query against the live GitHub API; attest=repo => proven by that "
                "repository's own CI. Regenerated by scripts/profile-visuals.py."
            ),
            "login": self.login,
            "generated": self.generated,
            "stats": {
                f.key: {
                    "value": f.value,
                    "basis": f.basis,
                    "source_query": f.source_query,
                    "attest": f.attest,
                }
                for f in self.items.values()
            },
        }


def _try(fn, on_fail=None):
    try:
        return fn()
    except Exception:
        return on_fail


def collect_facts(login: str = LOGIN) -> Facts:
    """Collect every provable profile fact. Each fact degrades to omission on failure."""
    facts = Facts(login=login)

    # --- personal account (users/<login>) ---
    user = _try(lambda: gh_json(f"users/{login}"), {}) or {}
    if user:
        facts.name = str(user.get("name") or login)
        facts.put(
            Fact(
                "personal_public_repos",
                int(user.get("public_repos", 0)),
                "live-public-gh-api",
                f"gh api users/{login} --jq .public_repos",
            )
        )
        facts.put(
            Fact(
                "followers",
                int(user.get("followers", 0)),
                "live-public-gh-api",
                f"gh api users/{login} --jq .followers",
            )
        )
        created = str(user.get("created_at", ""))[:4]
        if created:
            facts.put(Fact("member_since", created, "live-public-gh-api", f"gh api users/{login} --jq .created_at"))

    # --- org ecosystem: derive orgs, aggregate public repos / originals / forks / stars / langs ---
    org_logins = _try(lambda: [o["login"] for o in gh_json(f"users/{login}/orgs")], []) or []
    orgs = sorted(set(org_logins) | set(FALLBACK_ORGS))
    total_public = 0
    originals = 0
    forks = 0
    stars = 0
    langs: Counter = Counter()
    orgs_with_public: set[str] = set()
    public_fullnames: list[str] = []
    for org in orgs:
        meta = _try(lambda org=org: gh_json(f"orgs/{org}"))
        if not meta:
            continue
        pub = int(meta.get("public_repos", 0))
        total_public += pub
        if pub > 0:
            orgs_with_public.add(org)
        repos = (
            _try(
                lambda org=org: gh_json(f"orgs/{org}/repos?type=public&per_page=100", paginate=True),
                [],
            )
            or []
        )
        for r in repos:
            stars += int(r.get("stargazers_count", 0))
            if r.get("full_name"):
                public_fullnames.append(r["full_name"])
            if r.get("fork"):
                forks += 1
            else:
                originals += 1
                if r.get("language"):
                    langs[r["language"]] += 1
    facts.public_repos = sorted(public_fullnames)
    if orgs_with_public:
        orgs_q = f"gh api users/{login}/orgs then sum orgs/<org>.public_repos"
        facts.put(Fact("ecosystem_public_repos", total_public, "live-public-gh-api", orgs_q))
        facts.put(
            Fact(
                "ecosystem_original_repos",
                originals,
                "live-public-gh-api",
                "gh api --paginate orgs/<org>/repos?type=public | count .fork==false",
            )
        )
        facts.put(
            Fact(
                "ecosystem_forks",
                forks,
                "live-public-gh-api",
                "gh api --paginate orgs/<org>/repos?type=public | count .fork==true",
            )
        )
        facts.put(
            Fact(
                "ecosystem_stars",
                stars,
                "live-public-gh-api",
                "gh api --paginate orgs/<org>/repos?type=public | sum .stargazers_count",
            )
        )
        facts.put(
            Fact(
                "ecosystem_orgs",
                len(orgs_with_public),
                "live-public-gh-api",
                f"gh api users/{login}/orgs then count orgs with public_repos>0",
            )
        )
        facts.put(
            Fact(
                "ecosystem_classified_repos",
                sum(langs.values()),
                "live-public-gh-api",
                "count original ecosystem repos with a detected primary language",
            )
        )
        facts.languages = langs

    # --- contributions ---
    # The full contribution fields blow GraphQL's RESOURCE_LIMITS together AND the isolated
    # total call is itself intermittent on this account. But the day-by-day calendar call is
    # reliable, and totalContributions is exactly the sum of those days — so we DERIVE the
    # year total from the calendar we already fetch (one call, robust, same provable source),
    # falling back to the isolated total only when the calendar is unavailable.
    days = _try(lambda: fetch_calendar_days(login), []) or []
    if days:
        facts.calendar_days = days
        total = sum(int(d.get("contributionCount", 0)) for d in days)
        facts.put(
            Fact(
                "contributions_last_year",
                total,
                "live-public-gh-api",
                "sum contributionCalendar day counts (== contributionCalendar.totalContributions)",
            )
        )
        facts.put(
            Fact(
                "current_streak_days",
                current_streak(days),
                "live-public-gh-api",
                "walk contributionCalendar days backward while contributionCount>0",
            )
        )
        active = sum(1 for d in days if d.get("contributionCount", 0) > 0)
        facts.put(
            Fact(
                "active_days_last_year",
                active,
                "live-public-gh-api",
                "count contributionCalendar days with contributionCount>0",
            )
        )
    else:
        total = _try(lambda: fetch_calendar_total(login))
        if total is not None:
            facts.put(
                Fact(
                    "contributions_last_year",
                    int(total),
                    "live-public-gh-api",
                    "gh api graphql contributionsCollection.contributionCalendar.totalContributions",
                )
            )

    return facts


def current_streak(days: list[dict[str, Any]], *, today: dt.date | None = None) -> int:
    """Consecutive days (ending today or yesterday) with >0 contributions."""
    by_date = {d["date"]: int(d.get("contributionCount", 0)) for d in days}
    cursor = today or dt.datetime.now(dt.UTC).date()
    # allow the streak to "hold" if today has no contribution yet but yesterday did
    if by_date.get(cursor.isoformat(), 0) == 0:
        cursor = cursor - dt.timedelta(days=1)
    streak = 0
    while by_date.get(cursor.isoformat(), 0) > 0:
        streak += 1
        cursor -= dt.timedelta(days=1)
    return streak


# ---------------------------------------------------------------------------
# Follow-harvest — detect the signature technique of every followed account
# ---------------------------------------------------------------------------

# name -> (regex, is_third_party_widget, human label). We adapt these into OUR OWN
# self-hosted versions; the widget flag marks the ones people lazily hot-link.
TECHNIQUE_PATTERNS: dict[str, tuple[str, bool, str]] = {
    "typing_header": (r"readme-typing-svg|typing-svg", True, "Animated typing header"),
    "stats_card": (r"github-readme-stats|readme-stats.*api", True, "GitHub stats card"),
    "language_card": (r"top-langs|top-languages", True, "Language breakdown card"),
    "streak": (r"streak-stats|streak_stats|github-readme-streak", True, "Contribution streak"),
    "snake": (r"platane/snk|github-snake|snake\.svg|/snk", True, "Contribution snake animation"),
    "trophies": (r"github-profile-trophy|profile-trophy", True, "Trophy / achievement row"),
    "activity_graph": (r"activity-graph|graph\?username", True, "Activity line graph"),
    "capsule_banner": (r"capsule-render", True, "Capsule/wave banner"),
    "shields_badges": (r"img\.shields\.io|badge/", True, "Shields.io badge row"),
    "skill_icons": (r"skillicons\.dev", True, "Skill-icon row"),
    "mermaid": (r"```mermaid", False, "Mermaid diagram"),
    "collapsible": (r"<details>", False, "Collapsible <details> section"),
    "html_table": (r"<table", False, "HTML table layout"),
    "local_svg_assets": (
        r"(?:src|\]\()\s*[\"']?\.?/?assets?/[^\"')]+\.(?:svg|png)",
        False,
        "Self-hosted local SVG/PNG assets",
    ),
    "ascii_art": (r"[┌┐└┘├┤┬┴─│╭╮╰╯]{3,}", False, "ASCII art / box drawing"),
    "profile_views": (r"profile-views|visitor-badge|komarev", True, "Profile view counter"),
    "wakatime": (r"wakatime|waka-readme", True, "WakaTime coding stats"),
    "now_playing": (r"spotify.*now.*playing|novatorem", True, "Now-playing panel"),
}


def fetch_following(login: str = LOGIN) -> list[str]:
    return [u["login"] for u in (gh_json(f"users/{login}/following", paginate=True) or [])]


def fetch_profile_readme(login: str) -> str | None:
    """The <login>/<login> profile README, or None if the account has no profile repo."""
    try:
        payload = gh_json(f"repos/{login}/{login}/readme")
    except GhError:
        return None
    if not isinstance(payload, dict) or "content" not in payload:
        return None
    try:
        return base64.b64decode(payload["content"]).decode("utf-8", "replace")
    except Exception:
        return None


def detect_techniques(readme_text: str) -> list[str]:
    found = []
    for name, (pattern, _widget, _label) in TECHNIQUE_PATTERNS.items():
        if re.search(pattern, readme_text, re.IGNORECASE):
            found.append(name)
    return found


def harvest_following(
    login: str = LOGIN, *, followers: list[str] | None = None, readme_fetcher=fetch_profile_readme
) -> dict[str, Any]:
    """Scan EVERY followed account (no per-follow prompt), rank techniques by adoption × novelty.

    Returns a digest whose top techniques prioritise which self-hosted elements we render.
    `readme_fetcher` is injectable so tests run offline.
    """
    logins = followers if followers is not None else fetch_following(login)
    scores: dict[str, dict[str, Any]] = {
        name: {"count": 0, "examples": [], "widget": widget, "label": label}
        for name, (_p, widget, label) in TECHNIQUE_PATTERNS.items()
    }
    scanned = with_readme = 0
    for who in logins:
        text = readme_fetcher(who)
        scanned += 1
        if not text:
            continue
        with_readme += 1
        for tech in detect_techniques(text):
            scores[tech]["count"] += 1
            if len(scores[tech]["examples"]) < 4:
                scores[tech]["examples"].append(who)

    total = max(with_readme, 1)
    ranked = []
    for name, s in scores.items():
        if s["count"] == 0:
            continue
        adoption = s["count"] / total
        ranked.append(
            {
                "technique": name,
                "label": s["label"],
                "count": s["count"],
                "adoption_pct": round(adoption * 100, 1),
                "novelty": round((1 - adoption) * 100, 1),
                "is_widget": s["widget"],
                "examples": s["examples"],
                "rendered_asset": RENDERED_ASSET_FOR.get(name),
                "we_self_host": name in RENDERED_ASSET_FOR,
            }
        )
    # rank by adoption first (what the crowd values), novelty as tiebreak
    ranked.sort(key=lambda r: (-r["count"], -r["novelty"], r["technique"]))
    return {
        "_doc": "Techniques harvested across EVERY account 4444J99 follows; top ranks drive which "
        "self-hosted elements the profile features. Generated by follow-harvest-organ.py.",
        "generated": _now_iso(),
        "following_scanned": scanned,
        "profiles_with_readme": with_readme,
        "techniques": ranked,
    }


# Which harvested techniques we ACTUALLY render as our own self-hosted asset (technique -> file).
# Only these may claim "rebuilt as a self-hosted SVG" — keeps the adapted-section honest.
RENDERED_ASSET_FOR = {
    "typing_header": "typing-header.svg",
    "stats_card": "stats-card.svg",
    "language_card": "languages.svg",
    "streak": "streak.svg",
    "snake": "snake.svg",
    "trophies": "trophies.svg",
    "shields_badges": "badges.svg",
    "activity_graph": "heatmap.svg",
}


# ---------------------------------------------------------------------------
# SVG rendering — our own self-hosted assets (SMIL animation only)
# ---------------------------------------------------------------------------

THEME = {
    "bg": "#0d1117",
    "panel": "#161b22",
    "border": "#30363d",
    "text": "#e6edf3",
    "muted": "#8b949e",
    "accent": "#58a6ff",
    "green": "#39d353",
    "green_dim": "#0e4429",
    "gold": "#d29922",
}
LANG_COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "HTML": "#e34c26",
    "Shell": "#89e051",
    "CSS": "#563d7c",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Astro": "#ff5a03",
    "SuperCollider": "#46390b",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "Ruby": "#701516",
    "C": "#555555",
    "Java": "#b07219",
}


def _esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _svg(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" fill="none">\n{body}\n</svg>\n'
    )


def _panel(width: int, height: int) -> str:
    # TRANSPARENT — no background at all. A hardcoded #0d1117 fill only matches GitHub's dark-default
    # theme; on dark-dimmed or light it reads as a stark box in the wrong color. With no fill the
    # element inherits the viewer's ACTUAL canvas, so it's unified on every theme by construction.
    return ""


def _text_on(hex_color: str) -> str:
    """Pick dark or light text for legibility on a colored pill (WCAG-ish luminance)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "#ffffff"
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#0d1117" if lum > 0.6 else "#ffffff"


def _fmt(n: Any) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return _esc(n)
    if n >= 1000:
        return f"{n:,}"
    return str(n)


def render_stats_card(facts: Facts) -> str:
    """Verifiable ecosystem stats — every figure is in stats-manifest.json."""
    rows = [
        ("Public repositories", facts.get("ecosystem_public_repos")),
        ("Original (non-fork)", facts.get("ecosystem_original_repos")),
        ("Contributions · last year", facts.get("contributions_last_year")),
        ("Active days · last year", facts.get("active_days_last_year")),
        ("Current streak (days)", facts.get("current_streak_days")),
        ("Stars across ecosystem", facts.get("ecosystem_stars")),
    ]
    rows = [(label, val) for label, val in rows if val is not None]
    w, pad, line_h, top = 460, 2, 44, 84
    h = top + line_h * len(rows) + 4
    body = [_panel(w, h)]
    body.append(
        f'<text x="{pad}" y="30" fill="{THEME["text"]}" font-family="Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="22" font-weight="800">Verified GitHub statistics</text>'
    )
    body.append(
        f'<text x="{pad}" y="54" fill="{THEME["muted"]}" font-family="Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="12.5">organvm ecosystem · every number re-derivable from stats-manifest.json</text>'
    )
    y = top + 18
    for label, val in rows:
        body.append(
            f'<text x="{pad}" y="{y}" fill="{THEME["muted"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="15">{_esc(label)}</text>'
        )
        body.append(
            f'<text x="{w - pad}" y="{y}" text-anchor="end" fill="{THEME["accent"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="21" '
            f'font-weight="800">{_fmt(val)}</text>'
        )
        y += line_h
    return _svg(w, h, "\n".join(body))


def render_languages(facts: Facts, *, top_n: int = 6) -> str:
    """Language breakdown across original ecosystem repos (primary-language tally).

    Single-accent bars (not per-language rainbow): the name + weight carry identity, the accent
    carries emphasis — GitHub-thematic and striking without the noise of ten saturated hues.
    """
    langs = facts.languages.most_common(top_n)
    total = sum(facts.languages.values()) or 1
    w, pad, top, bar_h, gap = 460, 2, 90, 18, 28
    h = top + (bar_h + gap) * len(langs) - gap + 8
    body = [_panel(w, h)]
    body.append(
        f'<text x="{pad}" y="30" fill="{THEME["text"]}" font-family="Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="22" font-weight="800">Language mix</text>'
    )
    body.append(
        f'<text x="{pad}" y="54" fill="{THEME["muted"]}" font-family="Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="12.5">top {len(langs)} of {total} original repos, by primary language</text>'
    )
    y = top
    bar_w = w - pad * 2
    for name, count in langs:
        frac = count / total
        body.append(
            f'<text x="{pad}" y="{y - 5}" fill="{THEME["text"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="13" font-weight="600">{_esc(name)}</text>'
        )
        body.append(
            f'<text x="{w - pad}" y="{y - 5}" text-anchor="end" fill="{THEME["muted"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="12">{frac * 100:.0f}%</text>'
        )
        body.append(f'<rect x="{pad}" y="{y}" width="{bar_w}" height="{bar_h}" rx="4" fill="rgba(255,255,255,0.07)"/>')
        body.append(
            f'<rect x="{pad}" y="{y}" width="{max(int(bar_w * frac), 6)}" height="{bar_h}" rx="4" '
            f'fill="{THEME["accent"]}"/>'
        )
        y += bar_h + gap
    return _svg(w, h, "\n".join(body))


def render_heatmap(facts: Facts) -> str:
    """52-week contribution calendar as our own SVG (color-graded by intensity)."""
    days = facts.calendar_days
    if not days:
        return _svg(480, 40, _panel(480, 40))
    counts = [d.get("contributionCount", 0) for d in days]
    hi = max(counts) or 1

    def shade(c: int) -> str:
        if c <= 0:
            # translucent white so the empty cell tints WHATEVER canvas is behind it (adapts to any
            # GitHub theme) instead of a fixed dark that clashes off dark-default.
            return "rgba(255,255,255,0.07)"
        t = c / hi
        if t < 0.25:
            return "#0e4429"
        if t < 0.5:
            return "#006d32"
        if t < 0.75:
            return "#26a641"
        return "#39d353"

    cell, gap, pad, top = 11, 3, 4, 54
    # rebuild week columns from weekday
    weeks: list[list[dict]] = []
    col: list[dict] = []
    for d in days:
        col.append(d)
        if d.get("weekday") == 6:
            weeks.append(col)
            col = []
    if col:
        weeks.append(col)
    w = pad * 2 + len(weeks) * (cell + gap)
    h = top + 7 * (cell + gap) + 8
    body = [_panel(w, h)]
    body.append(
        f'<text x="{pad}" y="32" fill="{THEME["text"]}" font-family="Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="22" font-weight="800">Contribution activity · last year</text>'
    )
    for xi, week in enumerate(weeks):
        for d in week:
            wd = d.get("weekday", 0)
            x = pad + xi * (cell + gap)
            y = top + wd * (cell + gap)
            body.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{shade(d.get("contributionCount", 0))}"/>'
            )
    # a single quiet marker sweeps the real grid — the animated signature merged INTO the one
    # titled calendar (so the profile needs no second, redundant snake graph).
    path_pts = []
    for xi in range(len(weeks)):
        rows = range(7) if xi % 2 == 0 else range(6, -1, -1)
        for wd in rows:
            path_pts.append((pad + xi * (cell + gap), top + wd * (cell + gap)))
    if path_pts:
        step = max(1, len(path_pts) // 120)
        pp = path_pts[::step]
        xs = ";".join(f"{p[0]:.0f}" for p in pp)
        ys = ";".join(f"{p[1]:.0f}" for p in pp)
        x0, y0 = pp[0]
        body.append(
            f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{cell}" height="{cell}" rx="2" '
            f'fill="{THEME["accent"]}" opacity="0.85">'
            f'<animate attributeName="x" values="{xs}" dur="12s" repeatCount="indefinite" calcMode="linear"/>'
            f'<animate attributeName="y" values="{ys}" dur="12s" repeatCount="indefinite" calcMode="linear"/>'
            f"</rect>"
        )
    return _svg(w, h, "\n".join(body))


def render_streak(facts: Facts) -> str:
    """Single bold streak/contribution figure card."""
    streak = facts.get("current_streak_days", 0)
    total = facts.get("contributions_last_year")
    w, h = 300, 150
    body = [_panel(w, h)]
    body.append(
        f'<text x="{w / 2}" y="52" text-anchor="middle" fill="{THEME["green"]}" '
        f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="46" font-weight="800">{_fmt(streak)}</text>'
    )
    body.append(
        f'<text x="{w / 2}" y="78" text-anchor="middle" fill="{THEME["muted"]}" '
        f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="13">day contribution streak</text>'
    )
    if total is not None:
        body.append(
            f'<text x="{w / 2}" y="118" text-anchor="middle" fill="{THEME["text"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="15" '
            f'font-weight="600">{_fmt(total)} contributions / year</text>'
        )
    return _svg(w, h, "\n".join(body))


def render_trophies(facts: Facts) -> str:
    """Milestone badges computed from REAL counts (thresholds, not decoration)."""
    trophies = []
    repos = facts.get("ecosystem_public_repos", 0) or 0
    contribs = facts.get("contributions_last_year", 0) or 0
    streak = facts.get("current_streak_days", 0) or 0
    since = facts.get("member_since")
    if repos:
        tier = "S" if repos >= 200 else "A" if repos >= 100 else "B"
        trophies.append((tier, _fmt(repos), "repositories"))
    if contribs:
        tier = "S" if contribs >= 20000 else "A" if contribs >= 5000 else "B"
        trophies.append((tier, _fmt(contribs), "contributions"))
    if streak:
        tier = "S" if streak >= 100 else "A" if streak >= 30 else "B"
        trophies.append((tier, str(streak), "day streak"))
    if since:
        yrs = dt.datetime.now(dt.UTC).year - int(since)
        trophies.append(("A", str(yrs), "years on GitHub"))
    if not trophies:
        return _svg(480, 40, _panel(480, 40))
    cw, gap, pad, top = 138, 12, 24, 76
    w = pad * 2 + len(trophies) * cw + (len(trophies) - 1) * gap
    h, ch = 150, 84
    tier_color = {"S": THEME["gold"], "A": THEME["accent"], "B": THEME["green"]}
    body = [_panel(w, h)]
    body.append(
        f'<text x="{pad}" y="40" fill="{THEME["text"]}" font-family="Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="18" font-weight="700">Milestones</text>'
    )
    x = pad
    for tier, value, unit in trophies:
        cx = x + cw / 2
        body.append(
            f'<rect x="{x}" y="{top - 16}" width="{cw}" height="{ch}" rx="8" fill="{THEME["panel"]}" '
            f'stroke="{THEME["border"]}"/>'
        )
        # the number leads; the tier is a quiet muted tag with a small colored dot
        body.append(
            f'<text x="{cx}" y="{top + 22}" text-anchor="middle" fill="{THEME["text"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="27" font-weight="800">{_esc(value)}</text>'
        )
        body.append(
            f'<text x="{cx}" y="{top + 44}" text-anchor="middle" fill="{THEME["muted"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="12">{_esc(unit)}</text>'
        )
        body.append(f'<circle cx="{x + 16}" cy="{top - 2}" r="3.5" fill="{tier_color[tier]}"/>')
        body.append(
            f'<text x="{x + 25}" y="{top + 2}" fill="{THEME["muted"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="10" font-weight="600">{tier}-tier</text>'
        )
        x += cw + gap
    return _svg(w, h, "\n".join(body))


def render_typing_header(lines: list[str], *, width: int = 760, height: int = 90) -> str:
    """Animated typing header — SMIL only so GitHub's camo proxy keeps it animated."""
    body: list[str] = []  # transparent — inherit the viewer's canvas
    n = max(len(lines), 1)
    # Auto-fit: pick the largest font (<=26px) at which the LONGEST line fits the width with a
    # margin — monospace advance is ~0.6em, so overflow/clipping can't happen (the raw-SVG preview
    # caught a 25px line overrunning a 760px canvas).
    longest = max((len(s) for s in lines), default=1)
    font_size = max(13, min(26, int((width - 48) / (longest * 0.62))))
    per = 3.6  # seconds each line owns within the cycle
    cycle = per * n  # one full loop; every line runs an indefinite dur=cycle animation
    fade = min(0.05, 0.2 / n)  # crossfade fraction of the cycle
    for i, text in enumerate(lines):
        s, e = i / n, (i + 1) / n
        # Crossfading keyframes with NO all-blank gap, and line 0 == 1 at t=0 so the initial
        # (and non-animating) frame always shows a line. Line i rises over [s-fade, s],
        # overlapping the previous line's fall over [s-fade, s] (== its own [e-fade, e]).
        if i == 0:
            pts = [(0.0, 1.0), (e - fade, 1.0), (e, 0.0), (1.0, 0.0)]
        elif i == n - 1:
            pts = [(0.0, 0.0), (s - fade, 0.0), (s, 1.0), (1.0, 1.0)]
        else:
            pts = [(0.0, 0.0), (s - fade, 0.0), (s, 1.0), (e - fade, 1.0), (e, 0.0), (1.0, 0.0)]
        kt, vals = [], []
        for t, v in pts:
            t = min(max(t, 0.0), 1.0)
            if kt and abs(t - kt[-1]) < 1e-6:
                vals[-1] = f"{v:g}"
                continue
            kt.append(t)
            vals.append(f"{v:g}")
        base = "1" if i == 0 else "0"  # a static (non-animating) viewer still sees the first line
        body.append(
            f'<text x="{width / 2}" y="{height / 2 + font_size / 3:.0f}" text-anchor="middle" fill="{THEME["accent"]}" '
            f'font-family="Consolas,Menlo,monospace" font-size="{font_size}" font-weight="700" opacity="{base}">'
            f"{_esc(text)}"
            f'<animate attributeName="opacity" values="{";".join(vals)}" '
            f'keyTimes="{";".join(f"{t:.4f}" for t in kt)}" dur="{cycle}s" '
            f'repeatCount="indefinite" calcMode="linear"/>'
            f"</text>"
        )
    return _svg(width, height, "\n".join(body))


def render_snake(facts: Facts, *, width: int = 760) -> str:
    """OUR OWN contribution 'snake' — a marker traversing the real calendar grid (SMIL).

    Not a fork of platane/snk: a self-hosted SVG that animates a dot sweeping the actual
    contribution cells, dimming each as it 'eats' it. Provable substrate (real calendar),
    self-hosted, camo-safe.
    """
    days = facts.calendar_days
    cell, gap, pad, top = 11, 3, 16, 16
    # rebuild weeks
    weeks: list[list[dict]] = []
    col: list[dict] = []
    for d in days:
        col.append(d)
        if d.get("weekday") == 6:
            weeks.append(col)
            col = []
    if col:
        weeks.append(col)
    if not weeks:
        return _svg(width, 60, _panel(width, 60))
    n_weeks = len(weeks)
    w = pad * 2 + n_weeks * (cell + gap)
    h = top * 2 + 7 * (cell + gap)
    counts = [d.get("contributionCount", 0) for d in days]
    hi = max(counts) or 1

    def shade(c: int) -> str:
        if c <= 0:
            return THEME["panel"]
        t = c / hi
        return "#0e4429" if t < 0.25 else "#006d32" if t < 0.5 else "#26a641" if t < 0.75 else "#39d353"

    body: list[str] = []  # transparent — inherit the viewer's canvas
    # base grid
    cells_xy = []
    for xi, week in enumerate(weeks):
        for d in week:
            wd = d.get("weekday", 0)
            x = pad + xi * (cell + gap)
            y = top + wd * (cell + gap)
            body.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{shade(d.get("contributionCount", 0))}"/>'
            )
            cells_xy.append((x + cell / 2, y + cell / 2))
    # snake path: sweep column by column, serpentine, sampled to keep the SVG light
    path_pts = []
    for xi in range(n_weeks):
        rows = range(7) if xi % 2 == 0 else range(6, -1, -1)
        for wd in rows:
            x = pad + xi * (cell + gap) + cell / 2
            y = top + wd * (cell + gap) + cell / 2
            path_pts.append((x, y))
    step = max(1, len(path_pts) // 120)
    path_pts = path_pts[::step]
    dur = 8.0
    xs = ";".join(f"{p[0]:.0f}" for p in path_pts)
    ys = ";".join(f"{p[1]:.0f}" for p in path_pts)
    body.append(
        f'<rect x="-6" y="-6" width="12" height="12" rx="3" fill="{THEME["accent"]}">'
        f'<animate attributeName="x" values="{xs}" dur="{dur}s" repeatCount="indefinite" '
        f'calcMode="linear"/>'
        f'<animate attributeName="y" values="{ys}" dur="{dur}s" repeatCount="indefinite" '
        f'calcMode="linear"/></rect>'
    )
    return _svg(w, h, "\n".join(body))


def render_badges(facts: Facts, *, top_n: int = 10, width: int = 760) -> str:
    """A self-hosted tech-stack legend row (the most-harvested technique from the follows).

    GitHub-native language chips from the REAL primary-language tally: a neutral panel chip with
    a small language-color dot and a muted label — the quiet legend GitHub itself uses, not a row
    of saturated shields.io pills. Wraps to multiple rows.
    """
    langs = [name for name, _ in facts.languages.most_common(top_n)]
    if not langs:
        return _svg(width, 40, "")
    pad, ph, gap, char_w, dot_pad = 14, 28, 8, 7.4, 30
    x, y = pad, 14
    body = []
    rows = 1
    for name in langs:
        pw = int(len(name) * char_w) + dot_pad + 16
        if x + pw > width - pad:
            x = pad
            y += ph + gap
            rows += 1
        dot = LANG_COLORS.get(name, THEME["accent"])
        body.append(
            f'<rect x="{x}" y="{y}" width="{pw}" height="{ph}" rx="6" '
            f'fill="{THEME["panel"]}" stroke="{THEME["border"]}"/>'
        )
        body.append(f'<circle cx="{x + 15}" cy="{y + ph / 2}" r="5" fill="{dot}"/>')
        body.append(
            f'<text x="{x + dot_pad}" y="{y + ph / 2 + 4}" fill="{THEME["text"]}" '
            f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="13" '
            f'font-weight="500">{_esc(name)}</text>'
        )
        x += pw + gap
    h = 14 + rows * (ph + gap)
    header = ""  # transparent — inherit the viewer's canvas
    return _svg(width, h, header + "\n" + "\n".join(body))


# ---------------------------------------------------------------------------
# Verification predicate — profile-verify.py drives this
# ---------------------------------------------------------------------------


def readme_number_tokens(readme_text: str) -> list[str]:
    """Numbers a reader would treat as a statistical claim: >=4 digits, or with a thousands
    separator. Small counts (a version, '5 formats', '60+ agents') are not statistics; we gate
    the big claims. ISO dates/timestamps are stripped first so a footer date is not read as a stat.
    """
    text = re.sub(r"\d{4}-\d{2}-\d{2}(?:[T ]\S+)?", " ", readme_text)  # drop dates/timestamps
    tokens = []
    for m in re.finditer(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{4,}\b", text):
        tokens.append(m.group(0).replace(",", ""))
    return tokens


def manifest_values(manifest: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for entry in manifest.get("stats", {}).values():
        val = entry.get("value")
        if isinstance(val, int):
            out.add(str(val))
        elif isinstance(val, str) and val.isdigit():
            out.add(val)
    return out


def verify_readme(readme_text: str, manifest: dict[str, Any]) -> list[str]:
    """Return a list of problems; empty ⇒ the README is provable and self-hosted."""
    problems: list[str] = []

    # 1. no third-party widget hot-links
    low = readme_text.lower()
    for host in THIRD_PARTY_WIDGET_HOSTS:
        if host.lower() in low:
            problems.append(f"third-party widget host present: {host}")

    # 2. every image src is a local ./assets file
    for m in re.finditer(r'(?:<img[^>]+src=|!\[[^\]]*\]\()\s*["\']?([^"\')\s>]+)', readme_text):
        src = m.group(1)
        if src.startswith(("http://", "https://")):
            problems.append(f"non-local image src: {src}")

    # 3. every big number is backed by the manifest
    allowed = manifest_values(manifest)
    for tok in readme_number_tokens(readme_text):
        if tok not in allowed:
            problems.append(f"unprovable number in README (not in manifest): {tok}")

    # 4. the nothing-phrase must be gone
    if re.search(r"top[- ]tier creative", low):
        problems.append("banned nothing-phrase present: 'top-tier creative ...'")

    return problems
