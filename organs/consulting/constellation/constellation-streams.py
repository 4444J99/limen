#!/usr/bin/env python3
"""
constellation-streams — where the streams overlap, and what the estate is hiding.

The atlas renders the register as declared. This renders the register against
*reality*: it sweeps the live GitHub estate, matches every repository to the
lanes it plausibly belongs to using the register's own keyword lists, and
surfaces five things the declared view cannot show.

  claimed     a repo the register names for a lane — confirmed present in the
              estate, or MISSING, which is drift worth knowing about.

  unclaimed   a repo that matches a lane's keywords but no lane declares it.
              These are the buried ones: work that already exists in the estate
              and belongs to somebody's stream without being wired to it.

  crossings   one repo matching the lanes of two or more DIFFERENT people. The
              literal overlap between streams — shared engines, shared shapes.

  parallels   two people's lanes sharing keyword vocabulary. The register says
              john-m and john-f occupy one space; this derives every such pair
              mechanically, including the ones nobody wrote down.

  echoes      separate repositories that are different ANGLES on one idea —
              cve-watch and vulnpulse are two takes on vulnerability intel, not
              copies of each other. Grouped by the rare vocabulary they share,
              so the estate's own words cluster it and no taxonomy is authored.

Plus `twins`: repositories whose names collapse to the same base — legacy
copies, per-org forks, and play/demo splits. Where echoes find one idea built
twice, twins find one repository named twice.

Nothing here is authoritative. Every match is EVIDENCE for the demand review,
never a registration — the register's own review-before-rails rule. Confirm a
candidate by adding it to registry.yaml; the page then shows it as claimed.

Usage:
  organs/consulting/constellation/constellation-streams.py --refresh   # re-sweep the estate
  organs/consulting/constellation/constellation-streams.py             # render from cache
  organs/consulting/constellation/constellation-streams.py --public-safe --out p.html
  organs/consulting/constellation/constellation-streams.py --json      # findings as data
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REGISTRY = HERE / "registry.yaml"
STYLESHEET = HERE / "atlas.css"
CENSUS = REPO_ROOT / "logs" / "constellation" / "estate-census.json"
DEFAULT_OUT = REPO_ROOT / "logs" / "constellation" / "streams.html"

# Every org the estate spans. Enumerated, not guessed — an empty org is fine and
# recorded, so a repo that lands there later is picked up by the next sweep.
ORGS = [
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
    "4444J99",
]

# Repos that can never be a collaborator lane: vendor mirrors, contribution
# trackers, per-org scaffolding, GitHub Pages copies, superprojects. Matched
# against the bare repo name. Keeping these out is what stops "python-sdk" and
# "docs" from landing in somebody's stream.
EXCLUDE_PATTERNS = [
    r"^contrib--",
    r"^dot-github--",
    r"^pages--",
    r"^org-dotgithub$",
    r"^\.github$",
    r"--superproject$",
    r"\.github\.io$",
    r"^(docs?|doc|ops|contrib|skills|gens|mesh|personal|prima|core-engine)$",
    r"^(python|typescript|client|performance|sdk)-sdk$",
    r"^sdk-python$",
    r"^(camel|hive|k6|gait|iwf|langgraph|fastmcp|fastapi_mcp|guarddog|dbt-mcp|agentkit)$",
    r"^(anthropic-sdk-python|openai-agents-python|pydantic-ai|blender-mcp|a2a-python)$",
    r"^(dbt-databricks|dagster-sdlc|github-stars|ipapi-py|summarize_recent_commit)$",
    r"^session-stone-",
    r"^process-environment-enactment",
]

# Shared-weight floor for linking two repos into an echo family. Tuned against
# the live estate: BELOW this, transitive closure fuses everything into one blob
# that the size cap then discards, so a lower floor yields FEWER families, not
# more. At 11.0 the families are tight and legible.
ECHO_FLOOR = 11.0

# Tokens too generic to carry a stream. Derived vocabulary is only as good as
# what it refuses to count.
STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "of",
    "for",
    "to",
    "in",
    "on",
    "or",
    "with",
    "by",
    "app",
    "apps",
    "system",
    "systems",
    "platform",
    "engine",
    "tool",
    "tools",
    "ai",
    "web",
    "site",
    "page",
    "data",
    "new",
    "my",
    "os",
}


def _display_name(slug: str) -> str:
    parts = slug.split("-")
    out = [parts[0].capitalize()]
    for p in parts[1:]:
        out.append(f"{p.upper()}." if len(p) == 1 else p.capitalize())
    return " ".join(out)


def _excluded(name: str) -> bool:
    return any(re.search(p, name, re.IGNORECASE) for p in EXCLUDE_PATTERNS)


# ── census ──────────────────────────────────────────────────────────────────


def sweep_estate() -> dict[str, Any]:
    """Enumerate every repo across every declared org via gh."""
    repos: list[dict[str, Any]] = []
    per_org: dict[str, int] = {}
    for org in ORGS:
        proc = subprocess.run(
            [
                "gh",
                "repo",
                "list",
                org,
                "--limit",
                "1000",
                "--json",
                "nameWithOwner,description,visibility,isArchived,pushedAt,repositoryTopics",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"  warn: {org} unreadable ({proc.stderr.strip().splitlines()[:1]})", file=sys.stderr)
            per_org[org] = 0
            continue
        rows = json.loads(proc.stdout or "[]")
        for r in rows:
            r["topics"] = [t["name"] for t in (r.get("repositoryTopics") or [])]
            r.pop("repositoryTopics", None)
            r["name"] = r["nameWithOwner"].split("/", 1)[1]
        repos.extend(rows)
        per_org[org] = len(rows)
        print(f"  {org}: {len(rows)}", file=sys.stderr)

    return {
        "swept_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "orgs": per_org,
        "repos": repos,
    }


def load_census(*, refresh: bool) -> dict[str, Any]:
    if refresh or not CENSUS.is_file():
        if not refresh:
            print(f"no census at {CENSUS} — sweeping", file=sys.stderr)
        census = sweep_estate()
        CENSUS.parent.mkdir(parents=True, exist_ok=True)
        CENSUS.write_text(json.dumps(census, indent=2), encoding="utf-8")
        return census
    return json.loads(CENSUS.read_text(encoding="utf-8"))


# ── matching ────────────────────────────────────────────────────────────────


def _haystack(repo: dict[str, Any]) -> str:
    parts = [
        repo["name"].replace("--", " ").replace("-", " ").replace("_", " "),
        repo.get("description") or "",
        " ".join(repo.get("topics") or []),
    ]
    return re.sub(r"\s+", " ", " ".join(parts).lower())


def _has_word(hay: str, word: str) -> bool:
    """Word-boundary match, tolerant of a trailing plural on either side.

    The register writes lanes in the singular ("party game"); repositories
    describe themselves in the plural ("parlor/party games"). Without this the
    two never meet, and the most obvious matches in the estate go unfound.
    """
    stem = re.escape(word[:-1] if len(word) > 3 and word.endswith("s") else word)
    return re.search(rf"\b{stem}(?:s|es)?\b", hay) is not None


def score(repo: dict[str, Any], keywords: list[str]) -> tuple[int, list[str]]:
    """Score a repo against one lane's keywords.

    A multi-word keyword whose every word is present is a STRONG signal (3).
    A lone word is WEAK (1) — enough words make a case, one never does.
    """
    hay = _haystack(repo)
    total = 0
    hits: list[str] = []
    for kw in keywords:
        k = str(kw).lower().strip()
        if not k:
            continue
        words = [w for w in re.split(r"[^a-z0-9]+", k) if w and w not in STOPWORDS]
        if not words:
            continue
        if all(_has_word(hay, w) for w in words):
            total += 3 if len(words) > 1 else 1
            hits.append(k)
    return total, hits


def confidence(points: int, hits: list[str]) -> str:
    """Grade purely on effective points — never on how the keyword was written.

    A keyword's SHAPE lies: "ai audit" looks like a phrase but "ai" is a
    stopword, so matching it proves only that the word "audit" appeared. Scoring
    already encodes that (a real multi-word hit is worth 3, a lone word 1), so
    the grade reads points and nothing else.
    """
    del hits  # deliberately unused — see above
    if points >= 3:
        return "likely"
    if points == 2:
        return "possible"
    return "weak"


# ── analysis ────────────────────────────────────────────────────────────────


def analyse(registry: dict[str, Any], census: dict[str, Any]) -> dict[str, Any]:
    people = registry.get("people", [])
    repos = [r for r in census.get("repos", []) if not _excluded(r["name"])]
    by_full = {r["nameWithOwner"]: r for r in census.get("repos", [])}

    # every repo the register already names, anywhere
    declared: set[str] = set()
    for p in people:
        for proj in p.get("projects") or []:
            if proj.get("repo"):
                declared.add(str(proj["repo"]))
            for rel in proj.get("related_repos") or []:
                declared.add(str(rel))

    lanes: list[dict[str, Any]] = []
    for p in people:
        for proj in p.get("projects") or []:
            lanes.append(
                {
                    "slug": p["slug"],
                    "person": _display_name(p["slug"]),
                    "tier": p.get("tier"),
                    "project": proj.get("name"),
                    "stage": proj.get("stage"),
                    "keywords": [str(k) for k in (proj.get("keywords") or [])],
                    "declared": ([str(proj["repo"])] if proj.get("repo") else [])
                    + [str(r) for r in (proj.get("related_repos") or [])],
                }
            )

    # ── claimed: does each declared repo actually exist? ──
    claimed = []
    for lane in lanes:
        for full in lane["declared"]:
            row = by_full.get(full)
            claimed.append(
                {
                    "lane": lane,
                    "repo": full,
                    "present": row is not None,
                    "visibility": (row or {}).get("visibility"),
                    "archived": (row or {}).get("isArchived"),
                    "pushed": (row or {}).get("pushedAt"),
                    "description": (row or {}).get("description"),
                }
            )

    # ── unclaimed: matches a lane, declared by nobody ──
    matches: dict[str, list[dict[str, Any]]] = defaultdict(list)  # repo -> lane matches
    for repo in repos:
        if repo["nameWithOwner"] in declared:
            continue
        for lane in lanes:
            pts, hits = score(repo, lane["keywords"])
            conf = confidence(pts, hits)
            if conf in ("likely", "possible"):
                matches[repo["nameWithOwner"]].append({"lane": lane, "points": pts, "hits": hits, "confidence": conf})

    unclaimed_by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for full, ms in matches.items():
        best = max(ms, key=lambda m: m["points"])
        repo = by_full[full]
        unclaimed_by_slug[best["lane"]["slug"]].append(
            {
                "repo": full,
                "name": repo["name"],
                "description": repo.get("description"),
                "visibility": repo.get("visibility"),
                "archived": repo.get("isArchived"),
                "pushed": repo.get("pushedAt"),
                "lane": best["lane"],
                "hits": best["hits"],
                "points": best["points"],
                "confidence": best["confidence"],
                "also": sorted({m["lane"]["slug"] for m in ms} - {best["lane"]["slug"]}),
            }
        )
    for v in unclaimed_by_slug.values():
        v.sort(key=lambda x: (-x["points"], x["name"]))

    # ── crossings: one repo, two or more people ──
    crossings = []
    for full, ms in matches.items():
        slugs = sorted({m["lane"]["slug"] for m in ms})
        if len(slugs) < 2:
            continue
        repo = by_full[full]
        crossings.append(
            {
                "repo": full,
                "name": repo["name"],
                "description": repo.get("description"),
                "visibility": repo.get("visibility"),
                "people": [_display_name(s) for s in slugs],
                "slugs": slugs,
                "lanes": sorted({f"{m['lane']['slug']}/{m['lane']['project']}" for m in ms}),
                "points": max(m["points"] for m in ms),
            }
        )
    crossings.sort(key=lambda c: (-len(c["slugs"]), -c["points"], c["name"]))

    # ── parallels: lanes of different people sharing vocabulary ──
    def toks(lane: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        for kw in lane["keywords"]:
            for w in re.split(r"[^a-z0-9]+", kw.lower()):
                if w and w not in STOPWORDS and len(w) > 2:
                    out.add(w)
        return out

    # A token shared by many lanes is vocabulary; one shared by exactly two is a
    # tie. Weighting by that rarity is what lets a single well-chosen word
    # ("audit") outrank a common one ("social") instead of being thrown away.
    lane_df: dict[str, int] = defaultdict(int)
    for lane in lanes:
        for t in toks(lane):
            lane_df[t] += 1

    parallels = []
    for a, b in combinations(lanes, 2):
        if a["slug"] == b["slug"]:
            continue
        shared = toks(a) & toks(b)
        if shared:
            rarity = sum(1 / lane_df[t] for t in shared)
            parallels.append(
                {
                    "a": a,
                    "b": b,
                    # Ties break on the token itself: a sort keyed only on a
                    # score inherits set-iteration order, which differs per
                    # process, and the page would churn on every run.
                    "shared": sorted(shared, key=lambda t: (lane_df[t], t)),
                    "weight": len(shared),
                    "rarity": round(rarity, 3),
                    "kind": "strong" if len(shared) >= 2 else "faint",
                }
            )
    parallels.sort(
        key=lambda p: (
            -p["weight"],
            -p["rarity"],
            p["a"]["slug"],
            str(p["a"]["project"]),
            p["b"]["slug"],
            str(p["b"]["project"]),
        )
    )

    # ── echoes: different repos circling the same idea ──
    echoes = find_echoes(repos)

    # ── blind spots: what this page structurally cannot see ──
    blind = blind_spots(census, {p["slug"] for p in people})

    # ── twins: names that collapse to the same base ──
    def base(name: str) -> str:
        n = re.sub(r"--(4444j99|a-organvm-legacy|legacy|copy)$", "", name, flags=re.IGNORECASE)
        n = re.sub(r"-(play|demo|sanitized)$", "", n, flags=re.IGNORECASE)
        return n.lower()

    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in census.get("repos", []):
        if _excluded(r["name"]):
            continue
        families[base(r["name"])].append(r)
    twins = [{"base": k, "repos": sorted(v, key=lambda r: r["name"])} for k, v in families.items() if len(v) > 1]
    twins.sort(key=lambda t: t["base"])

    return {
        "swept_at": census.get("swept_at"),
        "orgs": census.get("orgs", {}),
        "total_repos": len(census.get("repos", [])),
        "considered": len(repos),
        "lanes": lanes,
        "claimed": claimed,
        "unclaimed": dict(unclaimed_by_slug),
        "crossings": crossings,
        "parallels": parallels,
        "echoes": echoes,
        "twins": twins,
        "blind": blind,
    }


# ── blind spots ─────────────────────────────────────────────────────────────
#
# A page that silently omits what it cannot see reads as complete when it is
# not. Keyword matching is blind to a repo that never describes itself, a `gh`
# sweep is blind to a repo with no remote, and the whole surface is blind to a
# person the register never registered — no matter how thoroughly they are
# documented elsewhere. Each of those is counted here rather than left absent.


def _people_elsewhere(registered: set[str]) -> list[dict[str, str]]:
    """People documented in another registry but absent from the register."""
    found: dict[str, str] = {}

    for engagements in (
        REPO_ROOT / "organs" / "social" / "engagements",
        REPO_ROOT / "organs" / "consulting" / "engagements",
    ):
        if not engagements.is_dir():
            continue
        for path in sorted(engagements.glob("*.yaml")):
            slug = path.stem
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            name = str(((doc.get("member") or {}) if isinstance(doc, dict) else {}).get("name", ""))
            # Template files carry {{PLACEHOLDER}} members — not a real person.
            if "{{" in name or not name:
                continue
            if slug not in registered:
                found.setdefault(slug, f"{engagements.parent.name} engagement")

    people_index = Path.home() / ".config" / "ai-context" / "people.yaml"
    if people_index.is_file():
        try:
            rows = yaml.safe_load(people_index.read_text(encoding="utf-8")) or []
        except yaml.YAMLError:
            rows = []
        for row in rows if isinstance(rows, list) else []:
            raw = str(row.get("name", "")).strip()
            if not raw:
                continue
            slug = raw.split()[0].lower()
            if slug not in registered:
                found.setdefault(slug, "people index")

    return [{"slug": s, "where": w} for s, w in sorted(found.items())]


def _remoteless_repos() -> list[str]:
    """Sibling working trees with no remote — invisible to any gh sweep."""
    out: list[str] = []
    # Resolve the LIVE checkout, not this working tree: run from a worktree,
    # REPO_ROOT.parent is .claude/worktrees and the real siblings are missed.
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    live = Path(common.stdout.strip()).parent if common.returncode == 0 else REPO_ROOT
    workspace = live.parent
    if not workspace.is_dir():
        return out
    for child in sorted(workspace.iterdir()):
        if not (child / ".git").exists():
            continue
        remotes = subprocess.run(["git", "remote"], capture_output=True, text=True, cwd=child, check=False)
        if remotes.returncode == 0 and not remotes.stdout.strip():
            out.append(child.name)
    return out


def blind_spots(census: dict[str, Any], registered: set[str]) -> dict[str, Any]:
    """Blind-spot inventories, each row carrying visibility.

    Visibility travels with the name because these lists are the one place a
    private repository can reach a rendered page WITHOUT going through the
    matcher — they enumerate what was never matched, and "never matched"
    includes everything private. The renderer filters them under --public-safe.
    """
    all_repos = census.get("repos", [])

    def row(r: dict[str, Any]) -> dict[str, str]:
        return {"name": r["name"], "visibility": r.get("visibility", "PUBLIC")}

    undescribed = sorted(
        (row(r) for r in all_repos if not (r.get("description") or "").strip() and not _excluded(r["name"])),
        key=lambda r: r["name"],
    )
    excluded = sorted((row(r) for r in all_repos if _excluded(r["name"])), key=lambda r: r["name"])
    return {
        "undescribed": undescribed,
        "excluded": excluded,
        "people_elsewhere": _people_elsewhere(registered),
        # Local working trees. These carry no GitHub visibility, and their bare
        # names are self-describing (a litigation store announces itself), so
        # the renderer publishes only the count.
        "remoteless": _remoteless_repos(),
    }


# ── echo detection ──────────────────────────────────────────────────────────
#
# Twins catch a repo copied under another name. Echoes catch something harder:
# separate repos that are different ANGLES on one idea — vulnpulse / cve-watch /
# bountyscope are three takes on vulnerability intelligence, not copies.
#
# Method: treat each repo's name + description + topics as a document, weight
# every token by inverse document frequency so estate-wide words ("organvm",
# "engine") count for nothing and rare shared ones ("cve", "spiral") count for a
# lot, then link any pair whose shared weight clears a floor and transitively
# close those links into families. No taxonomy is hand-authored — the vocabulary
# the estate actually uses is what does the grouping.


def _tokens(repo: dict[str, Any]) -> set[str]:
    # Name + description only. Topic tags are applied estate-wide in bulk
    # ("b2c", "commerce", "organ-iii"), so including them groups repos by
    # their filing category rather than by what they actually are.
    raw = " ".join(
        [
            repo["name"].replace("--", " ").replace("-", " ").replace("_", " "),
            repo.get("description") or "",
        ]
    ).lower()
    out: set[str] = set()
    for w in re.split(r"[^a-z0-9]+", raw):
        if len(w) < 3 or w in STOPWORDS or w.isdigit():
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)  # crude singularisation
    return out


def find_echoes(
    repos: list[dict[str, Any]], *, floor: float = ECHO_FLOOR, max_family: int = 14
) -> list[dict[str, Any]]:
    import math

    docs = {r["nameWithOwner"]: _tokens(r) for r in repos}
    docs = {k: v for k, v in docs.items() if len(v) >= 3}
    n = len(docs)
    if n < 2:
        return []

    df: dict[str, int] = defaultdict(int)
    for toks in docs.values():
        for t in toks:
            df[t] += 1

    # A token shared by nobody cannot group; one shared by a quarter of the
    # estate is vocabulary, not signal.
    ceiling = max(3, int(n * 0.12))
    idf = {t: math.log(n / c) for t, c in df.items() if 2 <= c <= ceiling}

    keys = list(docs)
    edges: list[tuple[float, str, str, list[str]]] = []
    for i, a in enumerate(keys):
        ta = docs[a] & idf.keys()
        if not ta:
            continue
        for b in keys[i + 1 :]:
            shared = ta & docs[b]
            if len(shared) < 2:
                continue
            weight = sum(idf[t] for t in shared)
            if weight >= floor:
                edges.append((weight, a, b, sorted(shared, key=lambda t: (-idf[t], t))))

    # transitive closure over the surviving links
    parent: dict[str, str] = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _w, a, b, _s in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    groups: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        groups[find(k)].append(k)

    # Transitive closure lets a chain A–B–C–D fuse repos that share nothing:
    # only the middle links are real. Prune to the 2-core — in any family above
    # a pair, every member must link to at least two others — which dissolves
    # chains while leaving genuine clusters (where everything interlinks) whole.
    def two_core(members: list[str]) -> list[str]:
        live = set(members)
        while len(live) > 2:
            degree = dict.fromkeys(live, 0)
            for _w, a, b, _s in edges:
                if a in live and b in live:
                    degree[a] += 1
                    degree[b] += 1
            weak = {m for m, d in degree.items() if d < 2}
            if not weak:
                break
            live -= weak
        return sorted(live)

    by_full = {r["nameWithOwner"]: r for r in repos}
    families = []
    for raw_members in groups.values():
        if len(raw_members) < 2:
            continue
        members = two_core(raw_members) if len(raw_members) > 2 else raw_members
        if not (2 <= len(members) <= max_family):
            continue
        inner = [e for e in edges if e[1] in members and e[2] in members]
        if not inner:
            continue
        theme: dict[str, float] = defaultdict(float)
        for w, _a, _b, shared in inner:
            for t in shared:
                theme[t] += idf[t]
        families.append(
            {
                "theme": [t for t, _ in sorted(theme.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
                "strength": round(sum(e[0] for e in inner) / max(len(inner), 1), 1),
                "repos": sorted(
                    (
                        {
                            "name": by_full[m]["name"],
                            "full": m,
                            "description": by_full[m].get("description"),
                            "visibility": by_full[m].get("visibility"),
                            "archived": by_full[m].get("isArchived"),
                        }
                        for m in members
                    ),
                    key=lambda r: r["name"],
                ),
            }
        )
    families.sort(key=lambda fam: (-len(fam["repos"]), -fam["strength"], fam["repos"][0]["name"]))
    return families


# ── rendering ───────────────────────────────────────────────────────────────

E = html.escape

EXTRA_CSS = """
/* ── streams-only ─────────────────────────────────────────── */
.block { display: flex; flex-direction: column; gap: 16px; }
.block-head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
  padding-bottom: 8px; border-bottom: 2px solid var(--ink); }
.block-head h2 { font-family: var(--display); font-size: 21px; font-weight: 600; margin: 0; }
.block-head .gloss { color: var(--ink-muted); font-size: 13.5px; flex: 1 1 24ch; }
.block-head .count { font-family: var(--mono); font-size: 11px; color: var(--ink-faint);
  font-variant-numeric: tabular-nums; }

.rows { display: flex; flex-direction: column; gap: 10px; }

.row {
  display: grid; grid-template-columns: minmax(150px, 190px) 1fr; gap: 18px;
  background: var(--surface); border: 1px solid var(--rule); border-left: 3px solid var(--stripe, var(--rule));
  border-radius: 3px; padding: 11px 13px; box-shadow: var(--shadow);
}
.row .lhs { display: flex; flex-direction: column; gap: 3px; }
.row .who { font-family: var(--display); font-size: 17px; font-weight: 600; line-height: 1.15; }
.row .lane-name { font-family: var(--mono); font-size: 10.5px; color: var(--ink-faint); }
.row .rhs { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.row .repo-name { font-family: var(--mono); font-size: 13px; font-weight: 600; word-break: break-all; }
.row .desc { font-size: 12.5px; color: var(--ink-muted); line-height: 1.45; }
.row .meta { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }

.stripe-likely   { --stripe: var(--inbuild); }
.stripe-possible { --stripe: var(--idea); }
.stripe-missing  { --stripe: var(--dormant); }
.stripe-ok       { --stripe: var(--shipped); }

.cross { display: flex; flex-direction: column; gap: 7px; background: var(--surface);
  border: 1px solid var(--rule); border-radius: 3px; padding: 12px 14px; box-shadow: var(--shadow); }
.cross .names { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
.cross .names .p { font-family: var(--display); font-size: 16px; font-weight: 600; }
.cross .names .x { color: var(--accent); font-family: var(--mono); font-size: 12px; }
.cross .repo-name { font-family: var(--mono); font-size: 12.5px; font-weight: 600; word-break: break-all; }
.cross .desc { font-size: 12.5px; color: var(--ink-muted); line-height: 1.45; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }

.par { display: grid; grid-template-columns: 1fr auto 1fr; gap: 12px; align-items: center;
  background: var(--surface); border: 1px solid var(--rule); border-radius: 3px;
  padding: 10px 13px; box-shadow: var(--shadow); }
.par .side { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.par .side.r { text-align: right; }
.par .side .p { font-family: var(--display); font-size: 16px; font-weight: 600; }
.par .side .l { font-family: var(--mono); font-size: 10.5px; color: var(--ink-faint); }
.par .link { display: flex; flex-direction: column; align-items: center; gap: 3px; }
.par .link .bar { height: 2px; background: var(--accent); border-radius: 1px; }
.par .link .n { font-family: var(--mono); font-size: 9.5px; color: var(--accent);
  letter-spacing: .06em; text-transform: uppercase; white-space: nowrap; }
.par .shared { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 4px; }
.par.faint { border-style: dashed; }
.par.faint .link .bar { background: var(--ink-faint); }
.par.faint .link .n { color: var(--ink-faint); }
.par.faint .side .p { color: var(--ink-muted); font-weight: 500; }

.echo { background: var(--surface); border: 1px solid var(--rule); border-radius: 3px;
  padding: 12px 14px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 8px; }
.echo-head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  padding-bottom: 7px; border-bottom: 1px solid var(--rule-soft); }
.echo-head .n { font-family: var(--mono); font-size: 10px; letter-spacing: .08em;
  text-transform: uppercase; color: var(--accent); white-space: nowrap; }
.echo-row { display: flex; flex-direction: column; gap: 2px; padding-left: 10px;
  border-left: 2px solid var(--accent-dim); }
.echo-row .repo-name { font-family: var(--mono); font-size: 12px; font-weight: 600; word-break: break-all; }
.echo-row .desc { font-size: 12px; color: var(--ink-muted); line-height: 1.4; }

.twin { background: var(--surface); border: 1px solid var(--rule); border-radius: 3px;
  padding: 10px 13px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 5px; }
.twin .b { font-family: var(--mono); font-size: 12px; font-weight: 600; }
.twin ul { list-style: none; display: flex; flex-direction: column; gap: 2px; }
.twin li { font-family: var(--mono); font-size: 11px; color: var(--ink-muted); word-break: break-all; }

.blinds { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.blind { background: var(--surface); border: 1px solid var(--rule); border-radius: 3px;
  padding: 12px 14px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 6px;
  border-left: 3px solid var(--ink-faint); }
.blind.loud { border-left-color: var(--dormant); }
.blind .bt { font-family: var(--body); font-size: 14px; font-weight: 650; line-height: 1.25; }
.blind .bw { font-size: 12.5px; color: var(--ink-muted); line-height: 1.45; }
.blind .bn { font-family: var(--display); font-size: 24px; line-height: 1;
  font-variant-numeric: tabular-nums; color: var(--dormant); }
.blind .bn.ok { color: var(--shipped); font-family: var(--mono); font-size: 12px; }
.blind:not(.loud) .bn { color: var(--ink-faint); }

.caveat { border: 1px solid var(--inbuild); border-radius: 3px; padding: 12px 15px;
  font-size: 13px; color: var(--ink-muted); line-height: 1.55; }
.caveat strong { color: var(--ink); }

@media (max-width: 640px) {
  .row { grid-template-columns: 1fr; gap: 10px; }
  .par { grid-template-columns: 1fr; }
  .par .side.r { text-align: left; }
}
"""


def _pill(text: str, cls: str = "quiet") -> str:
    return f'<span class="pill {cls}">{E(text)}</span>'


def _vis_pill(repo: dict[str, Any]) -> str:
    bits = []
    if repo.get("visibility") == "PRIVATE":
        bits.append(_pill("private", "warn"))
    if repo.get("archived"):
        bits.append(_pill("archived", "off"))
    return "".join(bits)


def render(f: dict[str, Any], *, public_safe: bool) -> str:
    css = STYLESHEET.read_text(encoding="utf-8") + EXTRA_CSS

    def keep(repo_row: dict[str, Any]) -> bool:
        return not (public_safe and repo_row.get("visibility") == "PRIVATE")

    # ── figures ──
    unclaimed_rows = [r for rows in f["unclaimed"].values() for r in rows if keep(r)]
    likely = [r for r in unclaimed_rows if r["confidence"] == "likely"]
    missing = [c for c in f["claimed"] if not c["present"]]
    figures = [
        (f["total_repos"], "repos swept"),
        (f["considered"], "candidate repos"),
        (len(f["lanes"]), "registered lanes"),
        (len(likely), "likely unclaimed"),
        (len(f["crossings"]), "stream crossings"),
        (len(f["echoes"]), "echo families"),
    ]
    figures_html = "".join(
        f'<div class="figure"><span class="n">{n}</span><span class="k">{E(k)}</span></div>' for n, k in figures
    )

    # ── claimed ──
    claimed_rows = ""
    for c in sorted(f["claimed"], key=lambda c: (c["present"], c["lane"]["slug"])):
        if public_safe and c.get("visibility") == "PRIVATE":
            continue
        lane = c["lane"]
        stripe = "stripe-ok" if c["present"] else "stripe-missing"
        state = _pill("present", "on") if c["present"] else _pill("not in estate", "off")
        desc = c.get("description") or ("" if c["present"] else "declared by the register, absent from every swept org")
        claimed_rows += (
            f'<div class="row {stripe}"><div class="lhs">'
            f'<span class="who">{E(lane["person"])}</span>'
            f'<span class="lane-name">{E(str(lane["project"]))}</span></div>'
            f'<div class="rhs"><span class="repo-name">{E(c["repo"])}</span>'
            f'<span class="desc">{E(desc)}</span>'
            f'<span class="meta">{state}{_vis_pill(c)}</span></div></div>'
        )

    # ── unclaimed ──
    unclaimed_html = ""
    for slug in sorted(f["unclaimed"], key=lambda s: -len([r for r in f["unclaimed"][s] if keep(r)])):
        rows = [r for r in f["unclaimed"][slug] if keep(r)]
        if not rows:
            continue
        person = rows[0]["lane"]["person"]
        body = ""
        for r in rows:
            hits = "".join(f'<span class="key">{E(h)}</span>' for h in r["hits"][:4])
            also = ""
            if r["also"]:
                also = _pill("also " + ", ".join(_display_name(s) for s in r["also"]), "mark")
            body += (
                f'<div class="row stripe-{r["confidence"]}"><div class="lhs">'
                f'<span class="who">{E(person)}</span>'
                f'<span class="lane-name">{E(str(r["lane"]["project"]))}</span></div>'
                f'<div class="rhs"><span class="repo-name">{E(r["name"])}</span>'
                f'<span class="desc">{E((r.get("description") or "no description")[:190])}</span>'
                f'<span class="meta">{_pill(r["confidence"], "warn" if r["confidence"] == "likely" else "quiet")}'
                f"{_vis_pill(r)}{also}{hits}</span></div></div>"
            )
        unclaimed_html += body

    # ── crossings ──
    cross_html = ""
    for c in f["crossings"]:
        if public_safe and c.get("visibility") == "PRIVATE":
            continue
        names = '<span class="x">×</span>'.join(f'<span class="p">{E(p)}</span>' for p in c["people"])
        lanes = "".join(f'<span class="key">{E(x)}</span>' for x in c["lanes"])
        cross_html += (
            f'<div class="cross"><div class="names">{names}</div>'
            f'<span class="repo-name">{E(c["name"])}</span>'
            f'<span class="desc">{E((c.get("description") or "no description")[:180])}</span>'
            f'<div class="keys">{lanes}</div></div>'
        )

    # ── parallels ──
    par_html = ""
    top = f["parallels"][:16]
    maxw = max((p["weight"] for p in top), default=1)
    for p in top:
        width = 26 + round(46 * p["weight"] / maxw)
        shared = "".join(f'<span class="key">{E(s)}</span>' for s in p["shared"][:8])
        par_html += (
            f'<div class="par {"faint" if p["kind"] == "faint" else ""}">'
            f'<div class="side"><span class="p">{E(p["a"]["person"])}</span>'
            f'<span class="l">{E(str(p["a"]["project"]))}</span></div>'
            f'<div class="link"><span class="n">{p["weight"]} shared'
            f"{'' if p['kind'] == 'strong' else ' · faint'}</span>"
            f'<span class="bar" style="width: {width}px"></span></div>'
            f'<div class="side r"><span class="p">{E(p["b"]["person"])}</span>'
            f'<span class="l">{E(str(p["b"]["project"]))}</span></div>'
            f'<div class="shared">{shared}</div></div>'
        )

    # ── echoes ──
    echo_html = ""
    echo_families = 0
    for fam in f["echoes"]:
        rows = [r for r in fam["repos"] if not (public_safe and r.get("visibility") == "PRIVATE")]
        if len(rows) < 2:
            continue
        echo_families += 1
        theme = "".join(f'<span class="key">{E(t)}</span>' for t in fam["theme"])
        items = ""
        for r in rows:
            marks = ""
            if r.get("visibility") == "PRIVATE":
                marks += _pill("private", "warn")
            if r.get("archived"):
                marks += _pill("archived", "off")
            items += (
                f'<div class="echo-row"><span class="repo-name">{E(r["name"])}</span>'
                f'<span class="desc">{E((r.get("description") or "no description")[:150])}</span>'
                f"{f'<span class=meta>{marks}</span>' if marks else ''}</div>"
            )
        echo_html += (
            f'<div class="echo"><div class="echo-head">'
            f'<span class="n">{len(rows)} angles</span><div class="keys">{theme}</div></div>'
            f"{items}</div>"
        )

    # ── twins ──
    twin_html = ""
    for t in f["twins"]:
        rows = [r for r in t["repos"] if not (public_safe and r.get("visibility") == "PRIVATE")]
        if len(rows) < 2:
            continue
        items = "".join(
            f"<li>{E(r['name'])}{' · private' if r.get('visibility') == 'PRIVATE' else ''}"
            f"{' · archived' if r.get('isArchived') else ''}</li>"
            for r in rows
        )
        twin_html += f'<div class="twin"><span class="b">{E(t["base"])}</span><ul>{items}</ul></div>'

    # ── blind spots ──
    blind = f["blind"]

    def _blind_card(title: str, why: str, items: list[str], *, tone: str = "") -> str:
        if not items:
            return (
                f'<div class="blind"><span class="bt">{E(title)}</span>'
                f'<span class="bw">{E(why)}</span>'
                '<span class="bn ok">none</span></div>'
            )
        shown = "".join(f'<span class="key">{E(i)}</span>' for i in items[:18])
        more = f'<span class="key">+{len(items) - 18} more</span>' if len(items) > 18 else ""
        return (
            f'<div class="blind {tone}"><span class="bt">{E(title)}</span>'
            f'<span class="bw">{E(why)}</span>'
            f'<span class="bn">{len(items)}</span>'
            f'<div class="keys">{shown}{more}</div></div>'
        )

    def visible(rows: list[dict[str, str]]) -> tuple[list[str], int]:
        """Names safe to print, plus how many were withheld as private."""
        if public_safe:
            shown = [r["name"] for r in rows if r["visibility"] != "PRIVATE"]
            return shown, len(rows) - len(shown)
        return [r["name"] for r in rows], 0

    def withheld(n: int) -> str:
        return f" {n} private repositories are counted but not named." if n else ""

    undesc, undesc_priv = visible(blind["undescribed"])
    excl, excl_priv = visible(blind["excluded"])
    # Local trees have no GitHub visibility and self-describing names, so under
    # public-safe they are counted only — never listed.
    remoteless = [] if public_safe else blind["remoteless"]

    blind_html = (
        _blind_card(
            "People documented elsewhere but never registered",
            "They have an engagement record or a people-index entry, so nothing on either page "
            "shows them. The register — not the sweep — is the gap.",
            [f"{p['slug']} ({p['where']})" for p in blind["people_elsewhere"]],
            tone="loud",
        )
        + _blind_card(
            "Repositories with no description",
            "Matching reads name + description. A repo that never says what it is cannot be "
            "matched to anyone's lane, however obviously it belongs to one." + withheld(undesc_priv),
            undesc,
            tone="loud",
        )
        + _blind_card(
            "Working trees with no remote",
            "A gh sweep enumerates remotes. Local-only repositories are invisible to it by "
            "construction — no threshold change reaches them."
            + (f" {len(blind['remoteless'])} found; names withheld." if public_safe and blind["remoteless"] else ""),
            remoteless,
        )
        + _blind_card(
            "Excluded by pattern",
            "Vendor mirrors, contribution trackers, per-org scaffolding, Pages copies and "
            "superprojects. Deliberate, but a judgment call worth re-reading." + withheld(excl_priv),
            excl,
        )
    )

    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    swept = f.get("swept_at") or "unknown"
    mode = "public repos only" if public_safe else "full estate incl. private"
    orgs_line = ", ".join(f"{k} {v}" for k, v in f["orgs"].items() if v)

    return f"""<title>Constellation Streams — overlaps and parallels</title>
<style>{css}</style>
<div class="sheet">
  <header class="masthead">
    <div class="eyebrow">
      <span>Constellation Streams</span><span class="sep">/</span>
      <span>estate swept {E(swept)}</span><span class="sep">/</span>
      <span>{E(mode)}</span><span class="sep">/</span>
      <span>{E(stamp)}</span>
    </div>
    <h1>Where the streams overlap, and what the estate was hiding</h1>
    <p class="standfirst">
      The atlas shows the register as written. This shows it against the actual
      GitHub estate — <strong>{f["total_repos"]} repositories</strong> swept across every org, matched
      to lanes by the register's own keywords. It surfaces the repos that already
      exist inside somebody's stream without being wired to it, the repos that sit
      in <strong>two</strong> streams at once, the lanes that are quietly the same shape — and
      the places the estate has <strong>built the same idea more than once</strong> from a
      different angle.
    </p>
    <div class="caveat">
      <strong>Every match below is evidence, not a registration.</strong> Keyword matching
      proposes; the demand review disposes. Confirm a candidate by adding it to
      <code>registry.yaml</code> — it then appears here as claimed, and on the atlas as a lane.
      Nothing on this page has been written back to the register.
    </div>
  </header>

  <div class="figures">{figures_html}</div>

  <section class="block">
    <div class="block-head"><h2>Claimed</h2>
      <span class="gloss">Repos the register names, checked against the live estate.</span>
      <span class="count">{len(f["claimed"])} declared / {len(missing)} missing</span></div>
    <div class="rows">{claimed_rows}</div>
  </section>

  <section class="block">
    <div class="block-head"><h2>Unclaimed</h2>
      <span class="gloss">Already in the estate, matching a lane, declared by nobody.</span>
      <span class="count">{len(unclaimed_rows)} candidates / {len(likely)} likely</span></div>
    <div class="rows">{unclaimed_html}</div>
  </section>

  <section class="block">
    <div class="block-head"><h2>Crossings</h2>
      <span class="gloss">One repository sitting in two or more people's streams.</span>
      <span class="count">{len(f["crossings"])} repos</span></div>
    <div class="grid2">{cross_html}</div>
  </section>

  <section class="block">
    <div class="block-head"><h2>Parallels</h2>
      <span class="gloss">Lanes belonging to different people that share vocabulary — the same
      shape recurring across unrelated friendships.</span>
      <span class="count">top {len(top)} of {len(f["parallels"])}</span></div>
    <div class="rows">{par_html}</div>
  </section>

  <section class="block">
    <div class="block-head"><h2>Echoes</h2>
      <span class="gloss">Separate repositories that are different <em>angles on the same idea</em> —
      grouped by the vocabulary they share, not by name. This is where the estate repeats itself.</span>
      <span class="count">{echo_families} families</span></div>
    <div class="grid2">{echo_html}</div>
  </section>

  <section class="block">
    <div class="block-head"><h2>Twins</h2>
      <span class="gloss">Names that collapse to one base — legacy copies, per-org forks, play
      splits. Estate mess that makes any count of "what exists" wrong.</span>
      <span class="count">{len(f["twins"])} families</span></div>
    <div class="grid2">{twin_html}</div>
  </section>

  <section class="block">
    <div class="block-head"><h2>Blind spots</h2>
      <span class="gloss">What this page structurally cannot see. Counted, so an absence never
      reads as an all-clear.</span>
      <span class="count">{len(blind["people_elsewhere"])} people / {len(blind["undescribed"])} repos unmatched</span></div>
    <div class="blinds">{blind_html}</div>
  </section>

  <p class="colophon">
    Generated by <code>organs/consulting/constellation/constellation-streams.py</code> from
    <code>registry.yaml</code> and a live <code>gh</code> sweep of {E(orgs_line)}.
    Re-run with <code>--refresh</code> to re-sweep. Matching is mechanical: a multi-word keyword
    whose every word appears is a strong signal, a lone word is weak, and vendor mirrors,
    contribution trackers, and per-org scaffolding are excluded by pattern.
  </p>
</div>
"""


# ── entrypoint ──────────────────────────────────────────────────────────────


# ── private atom evidence (never published) ─────────────────────────────────
#
# The drained brainstorm estate carries per-thread semantic atoms in the
# PRIVATE corpus store. Scoring their statements against the register's lane
# keywords yields the same kind of evidence the unclaimed-repo sweep produces —
# but the material is conversation-derived, so it renders ONLY to a local page
# under logs/ (gitignored) and is never part of the published surface:
# publish-constellation.py runs the generators in public mode without this
# flag, and the standing rule is that atom content never enters the public
# tree. Evidence, never registration — a human confirms by editing
# registry.yaml, exactly as with unclaimed repos.

_ATOMS_PAGE_OUT = REPO_ROOT / "logs" / "constellation" / "streams-atoms-private.html"
_ATOM_EXTRACT_RE = re.compile(r"^---\n(.*?)\n---\n.*?## SEMANTIC ATOMS\s*\n+```yaml\n(.*?)```", re.DOTALL)


def _extracts_root() -> Path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import corpus_resolve  # the one resolver — no second copy of the store root

    return corpus_resolve.corpus_home() / "brainstorm-extracts"


def atoms_evidence(registry: dict[str, Any]) -> dict[str, Any]:
    """Score every drained atom statement against every lane's keywords."""
    root = _extracts_root()
    lanes: list[dict[str, Any]] = []
    for person in registry.get("people") or []:
        for proj in person.get("projects") or []:
            lanes.append(
                {
                    "slug": person.get("slug"),
                    "project": proj.get("name"),
                    "keywords": proj.get("keywords") or [],
                }
            )
    matched: dict[str, list[dict[str, Any]]] = defaultdict(list)
    n_files = n_atoms = 0
    for path in sorted(root.glob("*/threads/*.md")):
        m = _ATOM_EXTRACT_RE.match(path.read_text(encoding="utf-8"))
        if not m:
            continue
        n_files += 1
        try:
            front = yaml.safe_load(m.group(1)) or {}
            block = yaml.safe_load(m.group(2)) or {}
        except yaml.YAMLError:
            continue
        stream = str(front.get("stream") or "")
        for atom in block.get("atoms") or []:
            statement = str(atom.get("statement") or "").strip()
            if not statement:
                continue
            n_atoms += 1
            pseudo = {"name": stream, "description": statement, "topics": [str(atom.get("kind") or "")]}
            best: dict[str, Any] | None = None
            for lane in lanes:
                pts, hits = score(pseudo, lane["keywords"])
                grade = confidence(pts, hits)
                if grade in ("likely", "possible") and (best is None or pts > best["points"]):
                    best = {"lane": lane, "points": pts, "hits": hits, "confidence": grade}
            if best:
                matched[best["lane"]["slug"]].append(
                    {
                        "project": best["lane"]["project"],
                        "stream": stream,
                        "atom_id": atom.get("id"),
                        "kind": atom.get("kind"),
                        "statement": statement,
                        "confidence": best["confidence"],
                        "hits": best["hits"],
                    }
                )
    for rows in matched.values():
        rows.sort(key=lambda r: (r["confidence"] != "likely", r["stream"], str(r["atom_id"])))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": n_files,
        "atoms": n_atoms,
        "matched": dict(sorted(matched.items())),
    }


def render_atoms_page(ev: dict[str, Any]) -> str:
    css = STYLESHEET.read_text(encoding="utf-8") if STYLESHEET.is_file() else ""
    total = sum(len(v) for v in ev["matched"].values())
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        "<title>Atom evidence — PRIVATE</title>",
        f"<style>{css}</style>",
        "<h1>Atom evidence (private — never published)</h1>",
        (
            f"<p class='meta'>generated {html.escape(ev['generated_at'])} · "
            f"{ev['files']} extracts · {ev['atoms']} atoms scanned · {total} matched. "
            "Every match is EVIDENCE for the demand review, never a registration — "
            "confirm a candidate by adding it to registry.yaml.</p>"
        ),
    ]
    for slug, rows in ev["matched"].items():
        parts.append(f"<h2>{html.escape(str(slug))}</h2><ul>")
        for r in rows:
            parts.append(
                "<li>"
                f"<strong>{html.escape(str(r['confidence']))}</strong> "
                f"[{html.escape(str(r['kind']))}] {html.escape(str(r['statement']))} "
                f"<em>— stream {html.escape(str(r['stream']))}, lane {html.escape(str(r['project']))}, "
                f"hits: {html.escape(', '.join(r['hits']))}</em>"
                "</li>"
            )
        parts.append("</ul>")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-sweep the live estate before rendering")
    ap.add_argument("--public-safe", action="store_true", help="omit private repositories entirely")
    ap.add_argument("--out", type=Path, default=None, help=f"output path (default {DEFAULT_OUT})")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON instead of a page")
    ap.add_argument("--open", action="store_true", help="open the rendered page")
    ap.add_argument(
        "--atoms-evidence",
        action="store_true",
        help="render the PRIVATE atom-evidence page from the drained brainstorm estate (never published)",
    )
    args = ap.parse_args()

    if not REGISTRY.is_file():
        print(f"ERROR: register not found at {REGISTRY}", file=sys.stderr)
        return 2
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}

    if args.atoms_evidence:
        if args.public_safe:
            print("ERROR: --atoms-evidence is private-only; refuse --public-safe", file=sys.stderr)
            return 2
        ev = atoms_evidence(registry)
        if args.json:
            print(json.dumps(ev, indent=2, default=str))
            return 0
        out = (args.out or _ATOMS_PAGE_OUT).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_atoms_page(ev), encoding="utf-8")
        total = sum(len(v) for v in ev["matched"].values())
        print(
            f"wrote {out}  ({ev['atoms']} atoms scanned / {total} matched into "
            f"{len(ev['matched'])} lanes) — PRIVATE, never published"
        )
        return 0

    census = load_census(refresh=args.refresh)
    findings = analyse(registry, census)

    if args.json:
        print(json.dumps(findings, indent=2, default=str))
        return 0

    out = (args.out or DEFAULT_OUT).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(findings, public_safe=args.public_safe), encoding="utf-8")

    likely = sum(1 for rows in findings["unclaimed"].values() for r in rows if r["confidence"] == "likely")
    print(
        f"wrote {out}  ({findings['total_repos']} repos swept / {likely} likely unclaimed / "
        f"{len(findings['crossings'])} crossings / {len(findings['parallels'])} parallels)"
    )
    if args.open:
        subprocess.run(["open", str(out)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
