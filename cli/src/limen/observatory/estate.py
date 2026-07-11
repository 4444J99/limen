"""Our own estate — outcome class, activation gap, hero selection.

The other half of the comparison. This module reads *existing* ground-truth registries
(it never invents a new success SSOT): ``value-repos.json`` (time-to-dollar hero ordering)
and ``revenue-ladder.json`` (per-repo stage / whose_hand / first-dollar path). It derives
each repo's **outcome class**, snapshots our own surface for the gap comparison, and picks
the hero — the highest-ranked repo that actually has a transferable gap to close.
"""

from __future__ import annotations

from . import config, gh, surface

# which success-vector component matters most at each product stage (drives expected_value).
_STAGE_COMPONENT = {
    "building": "activation",
    "deploy-ready": "activation",
    "live": "retention",
    "monetized": "economic_return",
}


def our_repos() -> list[str]:
    """The actionable hero-candidate set — the ranked value list (fail-CLOSED to [])."""
    return config.value_repos()


def _ladder_products() -> list[dict]:
    data = config.revenue_ladder()
    products = data.get("products") if isinstance(data, dict) else None
    return products if isinstance(products, list) else []


def outcome_class(owner_repo: str) -> dict:
    """Derive the repo's outcome class from the existing registries (never a new SSOT)."""
    ranked = our_repos()
    value_rank = ranked.index(owner_repo) + 1 if owner_repo in ranked else None
    stage = None
    whose_hand = None
    for p in _ladder_products():
        if p.get("repo") == owner_repo:
            stage = p.get("stage")
            whose_hand = p.get("whose_hand")
            break
    return {
        "repo": owner_repo,
        "value_rank": value_rank,
        "stage": stage,
        "whose_hand": whose_hand,
        "primary_component": _STAGE_COMPONENT.get(stage or "", "activation"),
    }


def our_surface(owner_repo: str, tok) -> dict | None:
    """Extract our own repo's README surface features (role='ours'). None when unreadable."""
    meta = gh.repo(owner_repo, tok)
    if not isinstance(meta, dict):
        return None
    readme = gh.readme_markdown(owner_repo, tok) or ""
    return surface.extract(readme, meta)


def has_feature(features: dict, mechanism: str) -> bool:
    """Whether our surface already exhibits a mechanism (count features count as present when > 0)."""
    val = (features or {}).get(mechanism)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    return bool(val)


def activation_gap(claim: dict, hero_features: dict) -> dict | None:
    """A transferable mechanism the hero LACKS is a gap; one it already has is not."""
    mech = claim.get("mechanism")
    if not isinstance(mech, str):
        return None
    if has_feature(hero_features, mech):
        return None
    return {
        "mechanism": mech,
        "we_have": False,
        "priority": claim.get("priority"),
        "target_component": claim.get("target_component"),
        "claim": claim,
    }


def select_hero(gaps_by_repo: dict[str, list]) -> str | None:
    """The highest value-repos-ranked repo that has at least one gap."""
    for repo in our_repos():  # value-repos.json is already priority-ordered
        if gaps_by_repo.get(repo):
            return repo
    return None
