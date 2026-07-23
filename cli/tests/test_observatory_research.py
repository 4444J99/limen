"""Tests for the OBSERVATORY external-legibility research loop (build #3).

Hermetic: the ``gh`` boundary and the repo root are redirected to a temp tree; the
curated mechanism seeds are written into that tree so scoring is exercised by logic.
"""

from __future__ import annotations

import pytest
from limen.observatory import cohort, collect, config, estate, mechanism, surface

WINNER_README = """# OfficeCLI

The first Office suite built for AI agents. For developers who automate Word and Excel,
so you can generate a report in one command.

![demo](demo.gif)

```bash
npm install -g officecli
officecli build report.docx
```

## Use cases
- Agents editing spreadsheets
## Examples
- A one-line PowerPoint

Unlike LibreOffice, no install required.
"""

CONTROL_README = """# some-lib

A library.

## Installation
Clone the repo and read the source.
"""


@pytest.fixture
def obs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    # seed the curated mechanism knobs into the temp root
    seeds_dir = tmp_path / "institutio" / "observatory"
    seeds_dir.mkdir(parents=True)
    (seeds_dir / "mechanisms.yaml").write_text(
        "version: 1\n"
        "mechanisms:\n"
        "  names_user: {controllability: 0.95, activation_cost: 0.1, target_component: activation}\n"
        "  names_outcome: {controllability: 0.9, activation_cost: 0.12, target_component: activation}\n"
        "  demo_above_fold: {controllability: 0.8, activation_cost: 0.25, target_component: activation}\n"
        "  copy_paste_command: {controllability: 0.9, activation_cost: 0.1, target_component: activation}\n"
        "  comparison: {controllability: 0.7, activation_cost: 0.35, target_component: trust}\n"
        "  use_cases: {controllability: 0.75, activation_cost: 0.3, target_component: reach}\n"
    )
    return tmp_path


# ---------------------------------------------------------------- surface (pure + deterministic)
def test_surface_extract_is_deterministic():
    a = surface.extract(WINNER_README, {"license": {"spdx_id": "MIT"}})
    b = surface.extract(WINNER_README, {"license": {"spdx_id": "MIT"}})
    assert a == b  # same input → identical dict


def test_surface_detects_legibility_features():
    f = surface.extract(WINNER_README, {"license": {"spdx_id": "MIT"}})
    assert f["names_user"] and f["names_outcome"]
    assert f["demo_above_fold"] and f["gifs"] >= 1
    assert f["copy_paste_command"] and f["comparison"]
    assert f["use_cases"] >= 1
    assert f["license"] == "MIT"
    assert f["first_sentence"].startswith("The first Office suite")


def test_surface_control_is_sparse():
    f = surface.extract(CONTROL_README, {})
    assert not f["demo_above_fold"] and not f["names_outcome"]
    assert f["gifs"] == 0


# ---------------------------------------------------------------- cohort (pure)
def _snap(name, **kw):
    base = {
        "owner_repo": name,
        "age_days": 200,
        "language": "TypeScript",
        "category": "dev-tool",
        "owner_archetype": "solo",
        "release_maturity": "v1plus",
        "topics": ["cli"],
        "signals": {"stars": 1200, "forks": 20, "watchers": 30},
    }
    base.update(kw)
    return base


def test_match_key_and_distance():
    w = _snap("o/winner")
    identical = _snap("o/c1")
    different = _snap("o/c2", language="Python", category="ml", owner_archetype="corporate")
    assert cohort.match_distance(cohort.match_key(w), cohort.match_key(identical)) == 0.0
    assert cohort.match_distance(cohort.match_key(w), cohort.match_key(different)) > 0.5


def test_control_query_uses_star_band_below_winner():
    q = cohort.control_query(_snap("o/winner", signals={"stars": 1000}))
    assert "stars:10..500" in q and "language:TypeScript" in q


def test_rank_controls_picks_nearest_k_and_excludes_winner():
    w = _snap("o/winner")
    cands = [
        _snap("o/near1"),
        _snap("o/far", language="Rust", category="ml"),
        _snap("o/near2"),
        _snap("o/winner"),  # must be excluded
    ]
    picks = cohort.rank_controls(w, cands, 2)
    names = [p["owner_repo"] for p in picks]
    assert "o/winner" not in names and len(names) == 2
    assert names == ["o/near1", "o/near2"]  # nearest, deterministic tie-break by name


def test_confounders_flag_audience_and_manipulation():
    w = _snap(
        "o/winner",
        owner_followers=20000,
        owner_archetype="corporate",
        signals={"stars": 5000, "forks": 2, "watchers": 1},
    )
    confs = {c["kind"] for c in cohort.confounders(w, [])}
    assert "existing_audience" in confs and "corporate_brand" in confs
    assert "star_manipulation_suspected" in confs
    assert cohort.confounder_discount(cohort.confounders(w, [])) < 0.2  # heavily discounted


# ---------------------------------------------------------------- estate
def test_outcome_class_derives_from_registries(obs_root):
    (obs_root / "value-repos.json").write_text('{"repos": ["organvm/hero", "organvm/second"]}')
    (obs_root / "revenue-ladder.json").write_text(
        '{"products": [{"repo": "organvm/hero", "stage": "deploy-ready", "whose_hand": "yours"}]}'
    )
    oc = estate.outcome_class("organvm/hero")
    assert oc["value_rank"] == 1 and oc["stage"] == "deploy-ready"
    assert oc["primary_component"] == "activation"


def test_activation_gap_only_when_we_lack_it():
    claim = {"mechanism": "demo_above_fold", "priority": 9.9, "target_component": "activation"}
    assert estate.activation_gap(claim, {"demo_above_fold": False}) is not None
    assert estate.activation_gap(claim, {"demo_above_fold": True}) is None


def test_select_hero_is_highest_ranked_with_gap(obs_root):
    (obs_root / "value-repos.json").write_text('{"repos": ["o/a", "o/b", "o/c"]}')
    hero = estate.select_hero({"o/b": [{"mechanism": "x"}], "o/c": [{"mechanism": "y"}]})
    assert hero == "o/b"  # o/a has no gap, o/b is next highest with one


# ---------------------------------------------------------------- mechanism (scoring)
def test_observe_mechanisms_needs_winner_advantage():
    wf = surface.extract(WINNER_README, {})
    cf = [surface.extract(CONTROL_README, {})]
    mechs = {m["mechanism"] for m in mechanism.observe_mechanisms(wf, cf)}
    assert "demo_above_fold" in mechs and "names_outcome" in mechs
    # a feature both share would not be a mechanism (none here since control is sparse)


def test_score_excludes_stars_and_discounts_confounders(obs_root):
    seed = {"controllability": 0.8, "activation_cost": 0.25, "target_component": "activation"}
    obs = {"mechanism": "demo_above_fold", "winner_has": True, "controls_have_frac": 0.0}
    clean = mechanism.score(
        obs,
        seed=seed,
        confounder_discount=1.0,
        hero_outcome={"stage": "deploy-ready", "primary_component": "activation"},
    )
    discounted = mechanism.score(
        obs,
        seed=seed,
        confounder_discount=0.2,
        hero_outcome={"stage": "deploy-ready", "primary_component": "activation"},
    )
    assert clean["priority"] > discounted["priority"]  # confounders lower priority
    assert "stars" not in clean["scores"]  # star count never in the score


def test_claims_from_evidence_and_rank(obs_root):
    features = {
        "o/winner": surface.extract(WINNER_README, {}),
        "o/control": surface.extract(CONTROL_README, {}),
    }
    cohorts = [{"winner": "o/winner", "controls": [{"owner_repo": "o/control"}], "confounders": []}]
    claims = mechanism.claims_from_evidence(
        cohorts, features, {"stage": "deploy-ready", "primary_component": "activation"}
    )
    assert claims and claims == mechanism.rank(claims)  # already ranked
    assert all(c["priority"] >= 0 for c in claims)


# ---------------------------------------------------------------- collect (IO, offline fail-open)
def test_collect_run_offline_is_honest_empty(obs_root, monkeypatch):
    monkeypatch.setenv("LIMEN_OFFLINE", "1")
    report = collect.run()
    assert report == {"online": False, "winners": 0, "controls": 0, "cohorts": 0}


def test_snapshot_classifies_from_metadata(obs_root, monkeypatch):
    from limen.observatory import gh as ghmod

    meta = {
        "full_name": "alibaba/page-agent",
        "created_at": "2025-01-01T00:00:00Z",
        "language": "TypeScript",
        "topics": ["cli", "devtools"],
        "owner": {"login": "alibaba", "type": "Organization"},
        "stargazers_count": 900,
        "forks_count": 40,
        "license": {"spdx_id": "Apache-2.0"},
    }
    monkeypatch.setattr(ghmod, "repo", lambda name, tok: meta)
    monkeypatch.setattr(ghmod, "releases", lambda name, tok: [{"tag_name": "v2.1.0"}])
    monkeypatch.setattr(ghmod, "readme_markdown", lambda name, tok: WINNER_README)
    snap = collect.snapshot("alibaba/page-agent", None, role="winner")
    assert snap["category"] == "dev-tool"
    assert snap["owner_archetype"] == "corporate"  # 'alibaba' hint
    assert snap["release_maturity"] == "v1plus"
    assert snap["signals"]["star_signal_only"] is True
    assert snap["surface"]["names_user"] is True
