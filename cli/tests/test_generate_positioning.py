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
            {
                "level": 1,
                "name": "Feed me leads",
                "kind": "DaaS",
                "what_they_get": "Recurring exclusive feed.",
                "internal_anchor": "$3k–$15k / mo",
                "cadence": "Recurring",
            },
            {
                "level": 4,
                "name": "Build my whole data org",
                "kind": "Retainer",
                "what_they_get": "We become your data engine.",
                "internal_anchor": "$10k–$25k / mo retainer",
                "cadence": "Ongoing",
            },
        ],
        "cta_client": "Deploy this for your shop",
        "cta_recruiter": "Work with the team that built this",
        "recruiter_bridge_level": 4,
        "public_face": "the full system — source and the test suite. Read every line.",
        "private_operation": "the live instance, fed and tuned — the running engine you put to work.",
    }
    if extra_price_in_public:
        # Smuggle a price into a PUBLIC-rendered field — the guard must catch it.
        seed["expensive_problem"] = "This costs $50k if you ignore it."
    return seed


def _env(tmp_path: Path, seed: dict) -> dict:
    (tmp_path / "value-repos.json").write_text(json.dumps({"repos": [REPO]}))
    (tmp_path / "seeds.json").write_text(json.dumps({"repos": {REPO: seed}}))
    env = dict(os.environ)
    env.update(
        {
            "LIMEN_ROOT": str(tmp_path),
            "LIMEN_VALUE_REPOS": str(tmp_path / "value-repos.json"),
            "LIMEN_POSITIONING_SEEDS": str(tmp_path / "seeds.json"),
            "LIMEN_POSITIONING_DIR": str(tmp_path / "out"),
        }
    )
    return env


def _run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
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


def test_public_page_shows_form_operation_split(tmp_path: Path):
    # The doctrine made concrete: what's OPEN vs the ENGINE you rent must be on the page.
    env = _env(tmp_path, _seed())
    _run(env, "--repo", REPO, "--apply")
    pub = (tmp_path / "out" / f"{SLUG}.md").read_text()
    assert "What's open" in pub
    assert "What you're buying" in pub
    assert "the full system — source and the test suite" in pub
    assert "the running engine you put to work" in pub
    # The split section carries no prices either (guarded), so the page stays clean.
    assert "$" not in pub


def test_cta_is_plain_text_without_contact(tmp_path: Path):
    # No contact configured → CTA is plain text, no address published, no mailto.
    env = _env(tmp_path, _seed())
    _run(env, "--repo", REPO, "--apply")
    pub = (tmp_path / "out" / f"{SLUG}.md").read_text()
    assert "mailto:" not in pub
    assert "Deploy this for your shop →" in pub


def test_cta_is_tagged_mailto_when_contact_set(tmp_path: Path):
    # Capture funnel: a configured contact turns each CTA into a mailto pre-tagged with the
    # repo + door, so a click lands already-classified in the inbox. Nothing is ever sent.
    fd = _frontdoor()
    fd["contact"] = "leads@example.com"
    env = _env_fd(tmp_path, _seed(), fd)
    r = _run(env, "--repo", REPO, "--apply")
    assert r.returncode == 0, r.stderr
    pub = (tmp_path / "out" / f"{SLUG}.md").read_text()
    assert "mailto:leads@example.com?subject=" in pub
    # Subject is tagged with the door; unreserved chars (slug, 'deploy'/'hire') stay literal.
    assert "deploy" in pub and "hire" in pub
    assert "inbound" in pub


def test_frontdoor_doors_are_mailto_when_contact_set(tmp_path: Path):
    fd = _frontdoor()
    fd["contact"] = "leads@example.com"
    env = _env_fd(tmp_path, _seed(), fd)
    r = _run(env, "--frontdoor", "--apply")
    assert r.returncode == 0, r.stderr
    out = (tmp_path / "out" / "_frontdoor.md").read_text()
    assert "mailto:leads@example.com?subject=" in out
    assert "front" in out  # door tag "[front door · ...]" lands literally in the subject


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
    (tmp_path / "seeds.json").write_text(json.dumps({"frontdoor": frontdoor, "repos": {REPO: seed}}))
    env = dict(os.environ)
    env.update(
        {
            "LIMEN_ROOT": str(tmp_path),
            "LIMEN_VALUE_REPOS": str(tmp_path / "value-repos.json"),
            "LIMEN_POSITIONING_SEEDS": str(tmp_path / "seeds.json"),
            "LIMEN_POSITIONING_DIR": str(tmp_path / "out"),
        }
    )
    return env


def test_frontdoor_renders_both_doors_and_systems(tmp_path: Path):
    env = _env_fd(tmp_path, _seed(), _frontdoor())
    r = _run(env, "--frontdoor", "--apply")
    assert r.returncode == 0, r.stderr
    fd = (tmp_path / "out" / "_frontdoor.md").read_text()
    assert "Deploy it for your shop" in fd  # client door
    assert "Work with the builder" in fd  # recruiter door
    assert "Test Platform" in fd  # the system card
    assert f"github.com/{REPO}" in fd  # links to the repo


def test_frontdoor_has_no_prices(tmp_path: Path):
    env = _env_fd(tmp_path, _seed(), _frontdoor())
    _run(env, "--frontdoor", "--apply")
    fd = (tmp_path / "out" / "_frontdoor.md").read_text()
    assert "$" not in fd and "/mo" not in fd


def test_census_is_counts_only(tmp_path: Path):
    fd = _frontdoor()
    fd["contact"] = "secret-leads@example.com"
    seed = _seed()
    seed["search_topics"] = ["good-topic", "BadTopic"]
    seed["seo_description"] = "Private buyer-search phrase."
    env = _env_fd(tmp_path, seed, fd)

    r = _run(env, "--census")
    assert r.returncode == 0, r.stderr
    census = json.loads(r.stdout)
    encoded = json.dumps(census, sort_keys=True)

    assert census["value_repo_count"] == 1
    assert census["seed_repo_count"] == 1
    assert census["publishable_seed_count"] == 1
    assert census["contact_configured"] is True
    assert census["repo_topic_seed_count"] == 1
    assert census["valid_topic_count"] == 1
    assert census["invalid_topic_count"] == 1
    assert census["seo_description_count"] == 1
    assert census["ladder_step_count"] == 2
    assert census["internal_anchor_count"] == 2
    assert REPO not in encoded
    assert SLUG not in encoded
    assert "Test Platform" not in encoded
    assert "secret-leads@example.com" not in encoded
    assert "Private buyer-search phrase" not in encoded
    assert "good-topic" not in encoded
    assert "BadTopic" not in encoded
    assert "$3k" not in encoded


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


PRIVATE_REPO = "organvm/not-public-yet"
PRIVATE_SLUG = "not-public-yet"


def _two_repo_env(tmp_path: Path) -> dict:
    """One public-and-seeded repo + one seeded-but-awaiting_publish repo, both in value-repos."""
    (tmp_path / "value-repos.json").write_text(json.dumps({"repos": [REPO, PRIVATE_REPO]}))
    held = _seed()
    held["awaiting_publish"] = True
    held["display_name"] = "Held Private Platform"
    (tmp_path / "seeds.json").write_text(
        json.dumps(
            {
                "frontdoor": _frontdoor(),
                "repos": {REPO: _seed(), PRIVATE_REPO: held},
            }
        )
    )
    env = dict(os.environ)
    env.update(
        {
            "LIMEN_ROOT": str(tmp_path),
            "LIMEN_VALUE_REPOS": str(tmp_path / "value-repos.json"),
            "LIMEN_POSITIONING_SEEDS": str(tmp_path / "seeds.json"),
            "LIMEN_POSITIONING_DIR": str(tmp_path / "out"),
        }
    )
    return env


def test_awaiting_publish_held_from_default_render(tmp_path: Path):
    # A private repo isn't a lure — its page (in the public limen repo) would link to a 404.
    # The seed is banked but must not render until the repo is public.
    env = _two_repo_env(tmp_path)
    r = _run(env, "--apply")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out" / f"{SLUG}.md").exists()
    assert not (tmp_path / "out" / f"{PRIVATE_SLUG}.md").exists()
    # The hold is surfaced, never silent.
    assert "AWAITING PUBLISH" in r.stderr
    assert PRIVATE_REPO in r.stderr


def test_awaiting_publish_skipped_even_when_named_explicitly(tmp_path: Path):
    # Even --repo on a private seed must not write a public page that links to a 404.
    env = _two_repo_env(tmp_path)
    r = _run(env, "--repo", PRIVATE_REPO, "--apply")
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "out" / f"{PRIVATE_SLUG}.md").exists()


def test_awaiting_publish_excluded_from_frontdoor(tmp_path: Path):
    env = _two_repo_env(tmp_path)
    r = _run(env, "--frontdoor", "--apply")
    assert r.returncode == 0, r.stderr
    fd = (tmp_path / "out" / "_frontdoor.md").read_text()
    assert "Test Platform" in fd  # the public system is shown
    assert "Held Private Platform" not in fd  # the private one is not
    assert f"github.com/{PRIVATE_REPO}" not in fd  # and its 404 link never ships


def test_awaiting_publish_excluded_from_discoverability(tmp_path: Path):
    env = _two_repo_env(tmp_path)
    r = _run(env, "--discoverability", "--apply")
    assert r.returncode == 0, r.stderr
    disc = (tmp_path / "out" / "_discoverability.md").read_text()
    assert f"`{REPO}`" in disc
    assert PRIVATE_REPO not in disc


def test_default_target_is_seeded_value_repos_only(tmp_path: Path):
    # value-repos lists two repos; only one is seeded → only that one renders.
    (tmp_path / "value-repos.json").write_text(json.dumps({"repos": [REPO, "organvm/unseeded-repo"]}))
    (tmp_path / "seeds.json").write_text(json.dumps({"repos": {REPO: _seed()}}))
    env = dict(os.environ)
    env.update(
        {
            "LIMEN_ROOT": str(tmp_path),
            "LIMEN_VALUE_REPOS": str(tmp_path / "value-repos.json"),
            "LIMEN_POSITIONING_SEEDS": str(tmp_path / "seeds.json"),
            "LIMEN_POSITIONING_DIR": str(tmp_path / "out"),
        }
    )
    r = _run(env, "--apply")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out" / f"{SLUG}.md").exists()
    assert not (tmp_path / "out" / "unseeded-repo.md").exists()
