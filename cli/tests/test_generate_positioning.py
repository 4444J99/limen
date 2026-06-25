"""Tests for scripts/generate-positioning.py — the inbound positioning generator.

Hermetic: no network, no gh. Seeds and value-repos are written into tmp_path and pointed at
via env vars; the script is run as a subprocess (matching test_generate_backlog.py's style).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-positioning.py"

REPO = "organvm/public-record-data-scrapper"
SLUG = "public-record-data-scrapper"


def _seed(extra_price_in_public: bool = False) -> dict:
    seed = {
        "display_name": "Test Platform",
        "what_it_is": "A production platform that does a serious thing.",
        "proof_signals": ["3,399 passing tests", "Terraform AWS", "50 states"],
        "buyer": "People with an expensive problem.",
        "expensive_problem": "Commodity data is worthless; exclusive scored data wins deals.",
        "cost_of_not_having_it": "Real money per conversion.",
        "ladder": [
            {"level": 1, "name": "Feed me leads", "kind": "DaaS",
             "what_they_get": "Recurring exclusive feed.",
             "internal_anchor": "$3k–$15k / mo", "cadence": "Recurring"},
            {"level": 4, "name": "Build my whole data org", "kind": "Retainer",
             "what_they_get": "We become your data engine.",
             "internal_anchor": "$10k–$25k / mo retainer", "cadence": "Ongoing"},
        ],
        "cta_client": "Deploy this for your shop",
        "cta_recruiter": "Work with the team that built this",
        "recruiter_bridge_level": 4,
    }
    if extra_price_in_public:
        # Smuggle a price into a PUBLIC-rendered field — the guard must catch it.
        seed["expensive_problem"] = "This costs $50k if you ignore it."
    return seed


def _env(tmp_path: Path, seed: dict) -> dict:
    (tmp_path / "value-repos.json").write_text(json.dumps({"repos": [REPO]}))
    (tmp_path / "seeds.json").write_text(json.dumps({"repos": {REPO: seed}}))
    env = dict(os.environ)
    env.update({
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_VALUE_REPOS": str(tmp_path / "value-repos.json"),
        "LIMEN_POSITIONING_SEEDS": str(tmp_path / "seeds.json"),
        "LIMEN_POSITIONING_DIR": str(tmp_path / "out"),
    })
    return env


def _run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


def test_dry_run_renders_but_writes_nothing(tmp_path: Path):
    env = _env(tmp_path, _seed())
    r = _run(env, "--repo", REPO)
    assert r.returncode == 0, r.stderr
    assert "Ways to work together" in r.stdout
    assert "Feed me leads" in r.stdout
    assert not (tmp_path / "out").exists(), "dry-run must not write any file"


def test_apply_writes_public_and_internal(tmp_path: Path):
    env = _env(tmp_path, _seed())
    r = _run(env, "--repo", REPO, "--apply")
    assert r.returncode == 0, r.stderr
    public = tmp_path / "out" / f"{SLUG}.md"
    internal = tmp_path / "out" / f"{SLUG}.internal.md"
    assert public.exists() and internal.exists()
    # The two-door CTA is on the public page.
    pub = public.read_text()
    assert "Deploy this for your shop" in pub
    assert "Work with the team that built this" in pub


def test_public_page_has_no_prices(tmp_path: Path):
    env = _env(tmp_path, _seed())
    _run(env, "--repo", REPO, "--apply")
    pub = (tmp_path / "out" / f"{SLUG}.md").read_text()
    # The whole thesis: zero currency/price tokens on the page.
    assert "$" not in pub
    assert "/mo" not in pub and "/ mo" not in pub
    assert "k / mo" not in pub
    assert "internal anchor" not in pub.lower()


def test_internal_page_carries_the_anchors(tmp_path: Path):
    env = _env(tmp_path, _seed())
    _run(env, "--repo", REPO, "--apply")
    internal = (tmp_path / "out" / f"{SLUG}.internal.md").read_text()
    assert "$3k–$15k / mo" in internal
    assert "NOT FOR PUBLICATION" in internal


def test_guard_refuses_when_a_price_leaks_into_public(tmp_path: Path):
    env = _env(tmp_path, _seed(extra_price_in_public=True))
    r = _run(env, "--repo", REPO, "--apply")
    assert r.returncode != 0, "must fail when a price token reaches the public page"
    assert not (tmp_path / "out" / f"{SLUG}.md").exists(), "no public file on a guard failure"


def _frontdoor() -> dict:
    return {
        "headline": "I build production systems that solve expensive problems.",
        "subhead": "Live platforms. Two doors:",
        "door_client": {"label": "Deploy it for your shop", "blurb": "Pick the depth that fits."},
        "door_recruiter": {"label": "Work with the builder", "blurb": "This is the evidence."},
        "closing": "Reach out. This conversation starts at serious.",
    }


def _env_fd(tmp_path: Path, seed: dict, frontdoor: dict) -> dict:
    (tmp_path / "value-repos.json").write_text(json.dumps({"repos": [REPO]}))
    (tmp_path / "seeds.json").write_text(
        json.dumps({"frontdoor": frontdoor, "repos": {REPO: seed}}))
    env = dict(os.environ)
    env.update({
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_VALUE_REPOS": str(tmp_path / "value-repos.json"),
        "LIMEN_POSITIONING_SEEDS": str(tmp_path / "seeds.json"),
        "LIMEN_POSITIONING_DIR": str(tmp_path / "out"),
    })
    return env


def test_frontdoor_renders_both_doors_and_systems(tmp_path: Path):
    env = _env_fd(tmp_path, _seed(), _frontdoor())
    r = _run(env, "--frontdoor", "--apply")
    assert r.returncode == 0, r.stderr
    fd = (tmp_path / "out" / "_frontdoor.md").read_text()
    assert "Deploy it for your shop" in fd        # client door
    assert "Work with the builder" in fd          # recruiter door
    assert "Test Platform" in fd                  # the system card
    assert f"github.com/{REPO}" in fd             # links to the repo


def test_frontdoor_has_no_prices(tmp_path: Path):
    env = _env_fd(tmp_path, _seed(), _frontdoor())
    _run(env, "--frontdoor", "--apply")
    fd = (tmp_path / "out" / "_frontdoor.md").read_text()
    assert "$" not in fd and "/mo" not in fd


def test_frontdoor_guard_refuses_price_leak(tmp_path: Path):
    env = _env_fd(tmp_path, _seed(extra_price_in_public=True), _frontdoor())
    r = _run(env, "--frontdoor", "--apply")
    assert r.returncode != 0, "front door must refuse to write when a price leaks"
    assert not (tmp_path / "out" / "_frontdoor.md").exists()


def test_discoverability_recommends_topics_and_apply_command(tmp_path: Path):
    seed = _seed()
    seed["search_topics"] = ["merchant-cash-advance", "ucc-leads", "lead-scoring"]
    seed["seo_description"] = "Fresh, scored MCA leads via API."
    env = _env(tmp_path, seed)
    r = _run(env, "--discoverability", "--apply")
    assert r.returncode == 0, r.stderr
    disc = (tmp_path / "out" / "_discoverability.md").read_text()
    assert "merchant-cash-advance" in disc
    assert "Recommended description" in disc
    # Hands over an explicit apply command — never auto-mutates the public repo.
    assert f"repos/{REPO}/topics" in disc
    assert "names[]=ucc-leads" in disc


def test_discoverability_flags_invalid_topics(tmp_path: Path):
    seed = _seed()
    # Uppercase + a space are illegal GitHub topics — must be surfaced, not silently mangled.
    seed["search_topics"] = ["good-topic", "BadTopic", "has space"]
    env = _env(tmp_path, seed)
    r = _run(env, "--discoverability", "--apply")
    assert r.returncode == 0, r.stderr
    disc = (tmp_path / "out" / "_discoverability.md").read_text()
    assert "Invalid topics" in disc
    assert "BadTopic" in disc
    assert "good-topic" in disc


def test_default_target_is_seeded_value_repos_only(tmp_path: Path):
    # value-repos lists two repos; only one is seeded → only that one renders.
    (tmp_path / "value-repos.json").write_text(
        json.dumps({"repos": [REPO, "organvm/unseeded-repo"]}))
    (tmp_path / "seeds.json").write_text(json.dumps({"repos": {REPO: _seed()}}))
    env = dict(os.environ)
    env.update({
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_VALUE_REPOS": str(tmp_path / "value-repos.json"),
        "LIMEN_POSITIONING_SEEDS": str(tmp_path / "seeds.json"),
        "LIMEN_POSITIONING_DIR": str(tmp_path / "out"),
    })
    r = _run(env, "--apply")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out" / f"{SLUG}.md").exists()
    assert not (tmp_path / "out" / "unseeded-repo.md").exists()
