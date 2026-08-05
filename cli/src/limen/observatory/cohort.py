"""Matched-control selection — the anti-survivorship spine.

Studying only winners produces flattering post-hoc stories. For each winner OBSERVATORY
selects ~3 **controls**: repos in the same niche/age/language/archetype that did *not*
win. "Why they succeeded" then becomes a bounded hypothesis (winner has X, matched
controls lack X), not mythology.

This module is **pure** — it builds match keys, control search queries, ranks candidates
by match distance, and flags confounders. All network/IO (running the search, snapshotting
candidates) is owned by :mod:`limen.observatory.collect`, so cohort logic stays hermetically
testable. Star count is deliberately **excluded** from the match distance: matching on the
outcome would defeat the design.
"""

from __future__ import annotations

_AGE_BUCKETS = ((90, "<3mo"), (180, "3-6mo"), (365, "6-12mo"), (730, "1-2y"))

# weights for match distance (must sum to 1.0); star count is intentionally absent.
_WEIGHTS = {
    "age_bucket": 0.20,
    "category": 0.25,
    "language": 0.20,
    "owner_archetype": 0.20,
    "release_maturity": 0.15,
}


def age_bucket(age_days: int | None) -> str:
    if age_days is None:
        return "unknown"
    for ceiling, label in _AGE_BUCKETS:
        if age_days < ceiling:
            return label
    return ">2y"


def match_key(snapshot: dict) -> dict:
    """The six comparison variables (audience is derived downstream from category)."""
    return {
        "age_bucket": age_bucket(snapshot.get("age_days")),
        "category": snapshot.get("category") or "unknown",
        "language": snapshot.get("language") or "unknown",
        "owner_archetype": snapshot.get("owner_archetype") or "unknown",
        "release_maturity": snapshot.get("release_maturity") or "none",
    }


def control_query(winner: dict) -> str:
    """A GitHub search query for same-niche repos that did NOT win — the honest control band
    is stars strictly below the winner (10..<half the winner's stars)."""
    lang = winner.get("language")
    topics = winner.get("topics") or []
    stars = int(((winner.get("signals") or {}).get("stars")) or 0)
    ceiling = max(10, stars // 2)
    parts = []
    if lang:
        parts.append(f"language:{lang}")
    if topics:
        parts.append(f"topic:{topics[0]}")
    parts.append(f"stars:10..{ceiling}")
    parts.append("sort:updated")
    return " ".join(parts)


def match_distance(winner_key: dict, cand_key: dict) -> float:
    """Weighted disagreement across the match variables (0 = identical, 1 = fully different)."""
    dist = 0.0
    for var, w in _WEIGHTS.items():
        if winner_key.get(var) != cand_key.get(var):
            dist += w
    return round(dist, 4)


def rank_controls(winner: dict, candidates: list[dict], k: int) -> list[dict]:
    """Nearest-k candidates to the winner, excluding the winner/other winners. Fewer than k is
    honest (flag ``undersized`` downstream), never fabricated."""
    wkey = match_key(winner)
    scored = []
    seen = {winner.get("owner_repo")}
    for cand in candidates:
        name = cand.get("owner_repo")
        if not name or name in seen:
            continue
        seen.add(name)
        scored.append({"owner_repo": name, "match_distance": match_distance(wkey, match_key(cand))})
    scored.sort(key=lambda c: (c["match_distance"], c["owner_repo"]))
    return scored[:k]


def confounders(winner: dict, controls: list[dict]) -> list[dict]:
    """Honest flags that DISCOUNT a winner's explanatory strength. Recorded, never hidden."""
    out: list[dict] = []
    wsig = winner.get("signals") or {}
    followers = int(winner.get("owner_followers") or 0)
    archetype = winner.get("owner_archetype")

    if followers >= 5000:
        out.append({"kind": "existing_audience", "evidence": f"owner has ~{followers} followers", "weight": 0.8})
    if archetype in ("corporate", "foundation"):
        out.append({"kind": "corporate_brand", "evidence": f"owner archetype {archetype}", "weight": 0.7})

    # suspected star manipulation: stars wildly out of band vs forks/watchers.
    stars = int(wsig.get("stars") or 0)
    forks = int(wsig.get("forks") or 0)
    watchers = int(wsig.get("watchers") or 0)
    engagement = forks + watchers
    if stars >= 500 and engagement >= 0 and stars > 60 * max(1, engagement):
        out.append(
            {
                "kind": "star_manipulation_suspected",
                "evidence": f"stars {stars} ≫ forks+watchers {engagement}",
                "weight": 0.6,
            }
        )
    return out


def confounder_discount(confs: list[dict]) -> float:
    """Combine confounder weights into a multiplicative discount in (0, 1]. More/stronger
    confounders → a smaller factor → lower explanatory strength."""
    factor = 1.0
    for c in confs or []:
        factor *= 1.0 - min(0.9, float(c.get("weight") or 0.0))
    return round(max(0.05, factor), 4)
