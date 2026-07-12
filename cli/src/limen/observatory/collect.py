"""Collection — winners, competitors, and matched controls → normalized snapshots.

The IO layer of the external-legibility face. It reuses the :mod:`limen.observatory.gh`
boundary (so it inherits fail-open behavior), snapshots each repo into a normalized
record (age, category, archetype, release maturity, public signals, success vector), and
extracts its README surface via :mod:`limen.observatory.surface`. The pure matching lives
in :mod:`limen.observatory.cohort`; this module owns the searches and snapshots.

``run(apply=...)`` is the executive **collect** stage: it gathers a bounded set of winners
+ competitor seeds, snapshots + surfaces each, selects ~k controls per winner, and appends
the evidence (snapshots / surfaces / cohorts) — writing nothing to any public surface.
Everything is fail-open: offline, ``collect`` returns an empty, honest result.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import cohort, config, gh, ledger, surface

# the 8-component success vector — always present, components null until measurable (never faked).
_VECTOR_KEYS = (
    "reach",
    "activation",
    "retention",
    "trust",
    "maintenance",
    "distribution",
    "economic_return",
    "cultural_impact",
)

_CORP_HINTS = ("google", "microsoft", "apple", "alibaba", "meta", "amazon", "nvidia", "openai", "vercel")


def _age_days(created_at: str | None, now: datetime | None = None) -> int | None:
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0, (now - created).days)


def _category(topics: list[str], language: str | None) -> str:
    t = {str(x).lower() for x in (topics or [])}
    if t & {"cli", "developer-tools", "devtools", "sdk", "framework", "library"}:
        return "dev-tool"
    if t & {"machine-learning", "ml", "ai", "llm", "deep-learning"}:
        return "ml"
    if t & {"dataset", "data", "analytics", "database"}:
        return "data"
    if t & {"app", "desktop", "mobile", "web"}:
        return "app"
    if t & {"docs", "documentation", "awesome", "tutorial"}:
        return "docs"
    if language in ("Python", "TypeScript", "JavaScript", "Rust", "Go"):
        return "library"
    return "unknown"


def _owner_archetype(owner: dict) -> str:
    login = str((owner or {}).get("login") or "").lower()
    otype = (owner or {}).get("type")
    if any(h in login for h in _CORP_HINTS):
        return "corporate"
    if otype == "Organization":
        return "team"
    return "solo"


def _release_maturity(releases: list[dict]) -> str:
    if not releases:
        return "none"
    tags = [str(r.get("tag_name") or "") for r in releases]
    if any(r.get("prerelease") for r in releases):
        maturity = "prerelease"
    else:
        maturity = "v0"
    for tag in tags:
        norm = tag.lstrip("vV")
        if norm and not norm.startswith("0.") and norm[0].isdigit() and norm[0] != "0":
            return "v1plus"
    return maturity


def _slug(owner_repo: str) -> str:
    return owner_repo.replace("/", "-")


def snapshot(owner_repo: str, tok, *, role: str, now: datetime | None = None) -> dict | None:
    """One normalized RepoSnapshot (+ its surface record embedded). None when the repo can't be read."""
    meta = gh.repo(owner_repo, tok)
    if not isinstance(meta, dict) or not meta.get("full_name"):
        return None
    owner = meta.get("owner") or {}
    topics = meta.get("topics") or []
    rels = gh.releases(owner_repo, tok)
    readme = gh.readme_markdown(owner_repo, tok) or ""
    feats = surface.extract(readme, meta)
    # P3-CAPTURE — merge live-homepage first-impression features when armed (OBSERVATORY_CAPTURE=1)
    # and the repo declares a homepage. Off by default → README-only, byte-identical to before.
    if config.get("OBSERVATORY_CAPTURE", 0, cast=int):
        home = meta.get("homepage")
        if isinstance(home, str) and home.strip():
            feats = {**feats, **surface.capture_site(home.strip())}
    snap = {
        "schema": "limen.observatory.snapshot.v1",
        "owner_repo": meta["full_name"],
        "role": role,
        "created_at": meta.get("created_at"),
        "age_days": _age_days(meta.get("created_at"), now),
        "language": meta.get("language"),
        "topics": topics,
        "category": _category(topics, meta.get("language")),
        "owner_archetype": _owner_archetype(owner),
        "owner_followers": None,  # a second call; left null in v1 rather than faked
        "release_maturity": _release_maturity(rels),
        "signals": {
            "stars": meta.get("stargazers_count"),
            "forks": meta.get("forks_count"),
            "watchers": meta.get("subscribers_count") or meta.get("watchers_count"),
            "open_issues": meta.get("open_issues_count"),
            "star_signal_only": True,
        },
        "success_vector": {k: None for k in _VECTOR_KEYS},
        "surface": feats,
    }
    return snap


def collect_winners(tok, *, window_days: int, limit: int) -> list[dict]:
    """Approximate Trending (no official API): repos CREATED within the recency window, sorted by
    stars — recent risers. The query is tunable via OBSERVATORY_TRENDING_QUERY. Fail-open []."""
    query = str(config.get("OBSERVATORY_TRENDING_QUERY", "") or "").strip()
    if not query:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).date().isoformat()
        query = f"stars:>50 created:>={cutoff}"  # GitHub search needs an absolute ISO date, not now-Nd
    items = gh.search_repos(query, tok, sort="stars", per_page=max(limit, 10))
    out = []
    for it in items[:limit]:
        name = it.get("full_name")
        if name:
            snap = snapshot(name, tok, role="winner")
            if snap:
                out.append(snap)
    return out


def collect_competitors(tok, seeds: list[str]) -> list[dict]:
    out = []
    for name in seeds:
        snap = snapshot(name, tok, role="competitor")
        if snap:
            out.append(snap)
    return out


def _candidates_for(winner: dict, tok, *, per_winner_search: int) -> list[dict]:
    q = cohort.control_query(winner)
    items = gh.search_repos(q, tok, sort="updated", per_page=per_winner_search)
    cands = []
    for it in items:
        name = it.get("full_name")
        if name and name != winner.get("owner_repo"):
            snap = snapshot(name, tok, role="control")
            if snap:
                cands.append(snap)
    return cands


def run(*, apply: bool = False) -> dict:
    """The executive collect stage: winners + competitors + matched controls → evidence."""
    tok = gh.token()
    if not gh.online(tok):
        report = {"online": False, "winners": 0, "controls": 0, "cohorts": 0}
        ledger.write_latest("collect-latest.json", report)
        return report

    limit = config.get("OBSERVATORY_WINNERS_LIMIT", 3, cast=int)
    window = config.get("OBSERVATORY_TRENDING_WINDOW_DAYS", 30, cast=int)
    k = config.get("OBSERVATORY_CONTROLS_PER_WINNER", 3, cast=int)

    winners = collect_winners(tok, window_days=window, limit=limit)
    competitors = collect_competitors(tok, config.competitor_seeds())

    n_controls = 0
    n_cohorts = 0
    for winner in winners:
        cands = _candidates_for(winner, tok, per_winner_search=30)
        picks = cohort.rank_controls(winner, cands, k)
        control_snaps = {c["owner_repo"]: c for c in cands}
        controls = [control_snaps[p["owner_repo"]] for p in picks if p["owner_repo"] in control_snaps]
        confs = cohort.confounders(winner, controls)
        for snap in [winner, *controls]:
            ledger.append_jsonl("snapshots.jsonl", snap)
            ledger.append_jsonl("surfaces.jsonl", {"owner_repo": snap["owner_repo"], "features": snap["surface"]})
            n_controls += 1 if snap["role"] == "control" else 0
        ledger.append_jsonl(
            "cohorts.jsonl",
            {
                "winner": winner["owner_repo"],
                "match_key": cohort.match_key(winner),
                "controls": picks,
                "undersized": len(picks) < k,
                "confounders": confs,
            },
        )
        n_cohorts += 1

    for snap in competitors:
        ledger.append_jsonl("snapshots.jsonl", snap)

    report = {"online": True, "winners": len(winners), "controls": n_controls, "cohorts": n_cohorts}
    ledger.write_latest("collect-latest.json", report)
    return report
