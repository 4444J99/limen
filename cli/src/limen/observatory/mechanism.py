"""Success-mechanism observation + transferability scoring.

A *mechanism* is a surface feature a winner HAS that its matched controls mostly LACK —
a bounded hypothesis for why the winner was more legible. Each is scored by the spec's
priority formula:

    priority = explanatory_strength × controllability × similarity × expected_value
               ÷ activation_cost

with a hard rule: **star count never appears in any numerator**. Explanatory strength is
computed from the winner-vs-control contrast and then *discounted* by the cohort's
confounders (existing audience, corporate brand, launch event, suspected star
manipulation), so a repo that "won" on inherited advantage yields low-priority mechanisms
by construction. ``controllability`` and ``activation_cost`` are the only human-curated
inputs (``institutio/observatory/mechanisms.yaml``); everything else is computed.

``run(apply=...)`` is the executive **analyze** stage: it reads the evidence collect wrote,
scores mechanisms, compares them against our hero repo's surface to find the activation
gap, and writes the ranked claims + gap. Fail-open throughout.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import cohort, config, estate, gh, ledger, surface

# candidate mechanisms = the binary surface features + a couple of count features.
_MECHANISMS = (*surface.BINARY_FEATURES, "use_cases")

# expected-value weight by our hero's current product stage.
_STAGE_EV = {"building": 0.6, "deploy-ready": 1.0, "live": 0.9, "monetized": 0.8}

_COST_FLOOR = 0.05


def _seeds_path() -> Path:
    return config.repo_root() / "institutio" / "observatory" / "mechanisms.yaml"


def load_seeds() -> dict:
    """The curated controllability/activation_cost knobs. Fail-open to {} (a mechanism with no
    seed simply can't be scored and is skipped — never guessed)."""
    try:
        data = yaml.safe_load(_seeds_path().read_text(encoding="utf-8")) or {}
        seeds = data.get("mechanisms", {})
        return seeds if isinstance(seeds, dict) else {}
    except Exception:
        return {}


def _has(features: dict, mech: str) -> bool:
    return estate.has_feature(features, mech)


def observe_mechanisms(winner_features: dict, control_features: list[dict]) -> list[dict]:
    """Features the winner has that its controls mostly lack (controls_have_frac < 0.5)."""
    n = len(control_features)
    out = []
    for mech in _MECHANISMS:
        if not _has(winner_features, mech):
            continue
        have = sum(1 for cf in control_features if _has(cf, mech))
        frac = round(have / n, 4) if n else 0.0
        if frac < 0.5:  # a real contrast, not a universal feature
            out.append({"mechanism": mech, "winner_has": True, "controls_have_frac": frac})
    return out


def score(obs: dict, *, seed: dict, confounder_discount: float, hero_outcome: dict) -> dict:
    """Attach the full priority score to one observation. Pure given its inputs."""
    strength = round((1.0 - obs["controls_have_frac"]) * confounder_discount, 4)
    controllability = float(seed.get("controllability", 0.0))
    activation_cost = max(_COST_FLOOR, float(seed.get("activation_cost", _COST_FLOOR)))
    target = seed.get("target_component", "activation")
    primary = (hero_outcome or {}).get("primary_component", "activation")
    similarity = 1.0 if target == primary else 0.6
    expected_value = _STAGE_EV.get((hero_outcome or {}).get("stage") or "", 0.6)

    priority = round(strength * controllability * similarity * expected_value / activation_cost, 4)
    return {
        "mechanism": obs["mechanism"],
        "controls_have_frac": obs["controls_have_frac"],
        "target_component": target,
        "scores": {
            "explanatory_strength": strength,
            "controllability": controllability,
            "similarity": similarity,
            "expected_value": expected_value,
            "activation_cost": activation_cost,
            "priority": priority,
        },
        "priority": priority,
    }


def rank(claims: list[dict]) -> list[dict]:
    """Deterministic priority order (ties broken by mechanism name)."""
    return sorted(claims, key=lambda c: (-c["priority"], c["mechanism"]))


def _features_by_repo(snapshots: list[dict]) -> dict[str, dict]:
    out = {}
    for s in snapshots:
        name = s.get("owner_repo")
        feats = s.get("surface")
        if name and isinstance(feats, dict):
            out[name] = feats
    return out


def claims_from_evidence(cohorts: list[dict], features: dict[str, dict], hero_outcome: dict) -> list[dict]:
    """Reconstruct scored mechanism claims from stored cohorts + surfaces (pure)."""
    seeds = load_seeds()
    claims: list[dict] = []
    for coh in cohorts:
        winner = coh.get("winner")
        if not isinstance(winner, str):
            continue
        wfeat = features.get(winner)
        if not wfeat:
            continue
        cfeats = [features[c["owner_repo"]] for c in (coh.get("controls") or []) if c.get("owner_repo") in features]
        discount = cohort.confounder_discount(coh.get("confounders") or [])
        for obs in observe_mechanisms(wfeat, cfeats):
            seed = seeds.get(obs["mechanism"])
            if not seed:  # no curated knob → cannot score honestly; skip
                continue
            claim = score(obs, seed=seed, confounder_discount=discount, hero_outcome=hero_outcome)
            claim["winner"] = winner
            claims.append(claim)
    return rank(claims)


def run(*, apply: bool = False) -> dict:
    """The executive analyze stage: evidence → ranked claims + the hero's activation gap."""
    cohorts = ledger.read_jsonl("cohorts.jsonl")
    snapshots = ledger.read_jsonl("snapshots.jsonl")
    features = _features_by_repo(snapshots)

    _repos = estate.our_repos()
    hero_candidate = _repos[0] if _repos else None
    hero_outcome = estate.outcome_class(hero_candidate) if hero_candidate else {}

    claims = claims_from_evidence(cohorts, features, hero_outcome)
    for claim in claims:
        ledger.append_jsonl("mechanisms.jsonl", claim)

    # the activation gap against our hero's own surface (needs one live read; fail-open)
    gaps: list[dict] = []
    hero = None
    if hero_candidate:
        tok = gh.token()
        hero_features = estate.our_surface(hero_candidate, tok) if gh.online(tok) else None
        if hero_features is not None:
            for claim in claims:
                gap = estate.activation_gap(claim, hero_features)
                if gap:
                    gaps.append(gap)
            hero = hero_candidate if gaps else None

    gap_doc = {
        "schema": "limen.observatory.gap.v1",
        "hero": hero,
        "hero_outcome_class": hero_outcome,
        "gaps": gaps,
        "claim_count": len(claims),
    }
    ledger.write_latest("gap-latest.json", gap_doc)
    ledger.snapshot_line("gap.jsonl", gap_doc)

    return {"claims": len(claims), "gaps": len(gaps), "hero": hero}
