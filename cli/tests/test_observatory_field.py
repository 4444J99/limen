"""Tests for the full-field + estate-wide build: the whole trending field is studied (bounded,
never silently dropped), every value repo is gap-analyzed with its own outcome class, and the
one experiment is selected portfolio-wide.

Hermetic: the ``gh`` boundary and the repo root are redirected; registries and evidence are
seeded into the temp tree.
"""

from __future__ import annotations

import json

import pytest

from limen.observatory import brief, collect, config, estate, gh as ghmod, ledger, mechanism

WINNER_README = """# OfficeCLI

The first Office suite built for AI agents. For developers who automate Word and Excel.

```bash
npm install -g officecli
```
"""

PLAIN_README = """# some-lib

A library. Clone the repo and read the source.
"""


@pytest.fixture
def obs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    seeds_dir = tmp_path / "institutio" / "observatory"
    seeds_dir.mkdir(parents=True)
    (seeds_dir / "mechanisms.yaml").write_text(
        "version: 2\n"
        "mechanisms:\n"
        "  copy_paste_command: {controllability: 0.9, activation_cost: 0.1, target_component: activation}\n"
        "  names_user: {controllability: 0.95, activation_cost: 0.1, target_component: activation}\n"
    )
    return tmp_path


def _meta(name: str, *, language: str = "Python", topics: list | None = None) -> dict:
    return {
        "full_name": name,
        "owner": {"login": name.split("/")[0], "type": "User"},
        "topics": ["cli"] if topics is None else topics,
        "language": language,
        "created_at": "2026-06-20T00:00:00Z",
        "stargazers_count": 400,
        "forks_count": 40,
        "watchers_count": 40,
        "open_issues_count": 3,
    }


def _fake_gh(monkeypatch, *, trending: list[str], headroom: int = 80, releases_calls: dict | None = None):
    """Redirect the whole gh boundary: one trending search, empty control searches."""

    def search_repos(query, tok, *, sort="stars", per_page=10):
        if "created:>=" in query:  # the trending field query
            return [{"full_name": n} for n in trending][:per_page]
        return []  # control-band searches find nothing (controls aren't under test here)

    def releases(name, tok):
        if releases_calls is not None:
            releases_calls[name] = releases_calls.get(name, 0) + 1
        return []

    monkeypatch.setattr(ghmod, "token", lambda: None)
    monkeypatch.setattr(ghmod, "online", lambda tok: True)
    monkeypatch.setattr(ghmod, "rate_headroom_pct", lambda tok: headroom)
    monkeypatch.setattr(ghmod, "search_repos", search_repos)
    monkeypatch.setattr(ghmod, "repo", lambda name, tok: _meta(name))
    monkeypatch.setattr(ghmod, "releases", releases)
    monkeypatch.setattr(ghmod, "readme_markdown", lambda name, tok: WINNER_README)


# ---------------------------------------------------------------- collect: the field
def test_field_is_studied_and_counts_are_honest(obs_root, monkeypatch):
    monkeypatch.setenv("OBSERVATORY_WINNERS_LIMIT", "2")
    monkeypatch.setenv("OBSERVATORY_FIELD_LIMIT", "5")
    rel_calls: dict = {}
    _fake_gh(monkeypatch, trending=[f"org/w{i}" for i in range(8)], releases_calls=rel_calls)

    report = collect.run()
    assert report["winners"] == 2
    assert report["field_total"] == 8
    assert report["field_studied"] == 5
    assert report["field_dropped"] == 3
    assert report["degraded"] is False
    assert report["field_repos"] == ["org/w0", "org/w1", "org/w2", "org/w3", "org/w4"]

    snaps = ledger.read_jsonl("snapshots.jsonl")
    roles = sorted(s["role"] for s in snaps)
    assert roles == ["field", "field", "field", "winner", "winner"]
    # light rows: no releases read, maturity honestly unknown; every field row still has a surface
    field_rows = [s for s in snaps if s["role"] == "field"]
    assert all(s["release_maturity"] is None for s in field_rows)
    assert all(isinstance(s["surface"], dict) for s in field_rows)
    assert set(rel_calls) == {"org/w0", "org/w1"}  # only the deep winners paid the releases call


def test_field_degrades_to_core_on_low_headroom(obs_root, monkeypatch):
    monkeypatch.setenv("OBSERVATORY_WINNERS_LIMIT", "2")
    monkeypatch.setenv("OBSERVATORY_FIELD_LIMIT", "6")
    _fake_gh(monkeypatch, trending=[f"org/w{i}" for i in range(8)], headroom=5)

    report = collect.run()
    assert report["degraded"] is True
    assert report["field_studied"] == report["winners"] == 2  # field collapsed to the deep core


# ---------------------------------------------------------------- mechanism: prevalence + rescore
def test_field_prevalence_is_pure_counting():
    features = {
        "org/a": {"copy_paste_command": True},
        "org/b": {"copy_paste_command": False},
        "org/c": {"copy_paste_command": True, "names_user": True},
    }
    prev = mechanism.field_prevalence(features, ["org/a", "org/b", "org/c", "org/missing"])
    assert prev["copy_paste_command"] == round(2 / 3, 4)
    assert prev["names_user"] == round(1 / 3, 4)
    assert mechanism.field_prevalence(features, []) == {}


def test_rescore_for_varies_with_outcome_class():
    claim = {
        "mechanism": "copy_paste_command",
        "target_component": "activation",
        "priority": 0.0,
        "scores": {"explanatory_strength": 1.0, "controllability": 0.9, "activation_cost": 0.1},
    }
    a = mechanism.rescore_for(claim, {"stage": "deploy-ready", "primary_component": "activation"})
    b = mechanism.rescore_for(claim, {"stage": "monetized", "primary_component": "economic_return"})
    assert a["priority"] == round(1.0 * 0.9 * 1.0 * 1.0 / 0.1, 4)  # matched component, deploy-ready EV
    assert b["priority"] == round(1.0 * 0.9 * 0.6 * 0.8 / 0.1, 4)  # cross-component, monetized EV
    assert claim["priority"] == 0.0  # pure — the input claim is untouched


# ---------------------------------------------------------------- estate: facing edges
def test_facing_repos_matches_category_then_language():
    profiles = {
        "organvm/tool": {"category": "dev-tool", "language": "Python"},
        "organvm/site": {"category": "app", "language": "TypeScript"},
    }
    faced = estate.facing_repos({"category": "dev-tool", "language": "Rust"}, profiles)
    assert faced == ["organvm/tool"]
    faced = estate.facing_repos({"category": "unknown", "language": "TypeScript"}, profiles)
    assert faced == ["organvm/site"]
    assert estate.facing_repos({"category": "unknown", "language": None}, profiles) == []


# ---------------------------------------------------------------- analyze: estate-wide gaps
def _seed_evidence(root):
    """A winner-with-mechanism vs a control-without, plus today's field roster."""
    ledger.append_jsonl(
        "snapshots.jsonl",
        {"owner_repo": "org/w", "role": "winner", "surface": {"copy_paste_command": True}},
    )
    ledger.append_jsonl(
        "snapshots.jsonl",
        {"owner_repo": "org/c", "role": "control", "surface": {"copy_paste_command": False}},
    )
    ledger.append_jsonl(
        "cohorts.jsonl",
        {"winner": "org/w", "controls": [{"owner_repo": "org/c"}], "confounders": []},
    )
    ledger.write_latest(
        "collect-latest.json",
        {"field_total": 2, "field_repos": ["org/w", "org/c"]},
    )
    (root / "value-repos.json").write_text(json.dumps({"repos": ["organvm/hero1", "organvm/hero2"]}))
    (root / "revenue-ladder.json").write_text(
        json.dumps(
            {
                "products": [
                    {"repo": "organvm/hero1", "stage": "deploy-ready", "whose_hand": "mine"},
                    {"repo": "organvm/hero2", "stage": "live", "whose_hand": "mine"},
                ]
            }
        )
    )


def test_gaps_span_the_estate_and_hero_is_first_with_a_gap(obs_root, monkeypatch):
    _seed_evidence(obs_root)
    monkeypatch.setattr(ghmod, "token", lambda: None)
    monkeypatch.setattr(ghmod, "online", lambda tok: True)
    monkeypatch.setattr(ghmod, "repo", lambda name, tok: _meta(name))
    # hero1 already HAS the mechanism (no gap); hero2 lacks it (gap) → the hero is hero2.
    readmes = {"organvm/hero1": WINNER_README, "organvm/hero2": PLAIN_README}
    monkeypatch.setattr(ghmod, "readme_markdown", lambda name, tok: readmes.get(name, PLAIN_README))

    result = mechanism.run()
    assert result["repos_gapped"] == 1
    assert result["hero"] == "organvm/hero2"

    doc = ledger.read_latest("gap-latest.json")
    assert doc["schema"] == "limen.observatory.gap.v2"
    assert list(doc["gaps_by_repo"]) == ["organvm/hero2"]
    assert all(g["repo"] == "organvm/hero2" for g in doc["gaps"])
    assert doc["field"]["studied"] == 2
    # mechanism history rows carry the field prevalence (evidence for synthesis)
    claims = ledger.read_jsonl("mechanisms.jsonl")
    assert claims and claims[0]["field_prevalence"] == 0.5  # 1 of the 2 field repos has it


def test_brief_selects_portfolio_wide_and_task_targets_the_gap_repo(obs_root, monkeypatch):
    _seed_evidence(obs_root)
    monkeypatch.setattr(ghmod, "token", lambda: None)
    monkeypatch.setattr(ghmod, "online", lambda tok: True)
    monkeypatch.setattr(ghmod, "repo", lambda name, tok: _meta(name))
    readmes = {"organvm/hero1": WINNER_README, "organvm/hero2": PLAIN_README}
    monkeypatch.setattr(ghmod, "readme_markdown", lambda name, tok: readmes.get(name, PLAIN_README))
    mechanism.run()

    b = brief.build_brief()
    assert b["hero"] == "organvm/hero2"
    assert b["experiment"]["repo"] == "organvm/hero2"
    assert "organvm/hero2" in b["experiment"]["change"]
    assert b["portfolio"][0]["repo"] == "organvm/hero2"
    assert b["portfolio"][0]["gap_count"] >= 1
    assert b["field"]["studied"] == 2
    md = brief.render_markdown(b)
    assert "Portfolio" in md and "organvm/hero2" in md

    from limen.observatory import lever

    proposal = lever.propose(b, apply=False)
    assert proposal["task"]["repo"] == "organvm/hero2"  # the task targets the gap's own repo


def test_brief_stays_backward_compatible_without_field_keys(obs_root):
    ledger.write_latest("gap-latest.json", {"hero": None, "gaps": []})
    ledger.write_latest("reconcile-latest.json", {"gaps": []})
    b = brief.build_brief()
    assert "portfolio" not in b and "field" not in b  # additive keys absent → old shape exactly
