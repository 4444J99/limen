"""The cut must be able to reach every section the registry declares cuttable.

One file per concern, per the sibling-branch reasoning in test_diurnal_ledger.py.

What is under test: `cuttable: true` is a declaration, and a declaration is worth exactly what its
consumer does with it. Measured on the live root 2026-08-02, `diurnal.yaml` declared 11 cuttable
sections and `section-scores.json` held 3. Three independent leaks in build_claims() produced that
single symptom, and each gets a case here:

  1. a display cap (`break` at the old CLAIM_MAX) also capped the SCORE surface, because the claim
     list and the score list are the same list;
  2. stale sections were skipped, so a section reading a dead source could never accrue a streak —
     staleness was a shield, and it shielded exactly the sections most worth examining;
  3. only `metric_decreased` was implemented, so the two `metric_changed` sections that
     check-diurnal.py's load-bearing rule explicitly admits were structurally unclaimable.

A subset looks exactly like a full set from the outside, which is why none of this was visible.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diurnal.py"


@pytest.fixture()
def mod():
    spec = importlib.util.spec_from_file_location("diurnal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["diurnal"] = module
    spec.loader.exec_module(module)
    return module


def _sections(**overrides) -> dict:
    """Twelve claimable sections — deliberately more than any plausible render cap."""
    base = {
        f"s{i}": {
            "_key": f"s{i}",
            "title": f"section {i}",
            "metric": "count",
            "acted_when": "metric_decreased",
            "cuttable": True,
        }
        for i in range(12)
    }
    base.update(overrides)
    return base


def _rendered(mod, sections: dict, *, metric: int = 7, stale: bool = False) -> list:
    out = []
    for key in sections:
        r = mod.Rendered(key, sections[key]["title"], [])
        r.metric, r.stale = metric, stale
        out.append(r)
    return out


# ── 1 · the score surface is not the render surface ────────────────────────────────


def test_every_eligible_section_is_claimed_not_just_the_first_few(mod, tmp_path):
    sections = _sections()
    claims = mod.build_claims(tmp_path, sections, _rendered(mod, sections))
    assert len(claims) == 12, "a display cap must never bound what the organ scores"
    assert {c["section"] for c in claims} == set(sections)


def test_the_page_is_capped_and_says_how_much_it_hid(mod, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_DIURNAL_CLAIM_RENDER_MAX", "5")
    sections = _sections()
    claims = mod.build_claims(tmp_path, sections, _rendered(mod, sections))
    lines = mod.r_claims(tmp_path, {"title": "claims"}, {"claims": claims}).lines
    assert len(lines) == 6, "five claims plus one elision line"
    assert "7 more scored" in lines[-1], "a silent elision is how a render cap passed for a score cap"


def test_the_score_tally_counts_every_section_not_just_the_visible_ones(mod, tmp_path, monkeypatch):
    """A summary derived from the visible rows would understate the day and mis-denominate streaks."""
    monkeypatch.setenv("LIMEN_DIURNAL_CLAIM_RENDER_MAX", "2")
    sections = _sections()
    claims = mod.build_claims(tmp_path, sections, _rendered(mod, sections))
    scored = mod.score_claims(claims, _rendered(mod, sections, metric=1))  # all decreased → held
    lines = mod.r_claim_scores(tmp_path, {"title": "score"}, {"scored": scored}).lines
    assert lines[-1] == "— held 12 · missed 0 · noop 0"


def test_what_moved_survives_the_elision(mod, tmp_path, monkeypatch):
    """Eliding the day's only news to make room for sections that did nothing inverts the briefing."""
    monkeypatch.setenv("LIMEN_DIURNAL_CLAIM_RENDER_MAX", "1")
    sections = _sections()
    claims = mod.build_claims(tmp_path, sections, _rendered(mod, sections))
    probe = _rendered(mod, sections, metric=7)  # unchanged → noop …
    probe[-1].metric = 99  # … except the LAST one, which worsened
    lines = mod.r_claim_scores(tmp_path, {"title": "score"}, {"scored": mod.score_claims(claims, probe)}).lines
    assert "[missed]" in lines[0], "the one section that moved must not be the one elided"


# ── 2 · staleness is not a shield ──────────────────────────────────────────────────


def test_a_stale_section_is_still_not_claimed(mod, tmp_path):
    """Unchanged and correct: a claim about a value you cannot read is not falsifiable."""
    sections = _sections()
    assert mod.build_claims(tmp_path, sections, _rendered(mod, sections, stale=True)) == []


def test_a_blind_cuttable_section_accrues_a_streak_and_is_proposed(mod, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_DIURNAL_BLIND_THRESHOLD", "3")
    sections = _sections()
    scores: dict = {}
    for _ in range(2):
        applied, proposed = mod.apply_cuts(
            tmp_path, sections, [], scores, 5, 1, True, _rendered(mod, sections, stale=True)
        )
        assert not proposed, "below threshold, blindness is observed and not yet actionable"
    applied, proposed = mod.apply_cuts(tmp_path, sections, [], scores, 5, 1, True, _rendered(mod, sections, stale=True))

    assert scores["s0"]["blind_streak"] == 3
    assert not applied, "a blind section is PROPOSED, never cut — cutting silences the evidence"
    assert {p["what"] for p in proposed} == {f"section:s{i}" for i in range(12)}


def test_a_source_that_goes_fresh_resets_the_blind_streak(mod, tmp_path):
    sections = _sections()
    scores: dict = {}
    mod.apply_cuts(tmp_path, sections, [], scores, 5, 1, True, _rendered(mod, sections, stale=True))
    assert scores["s0"]["blind_streak"] == 1
    mod.apply_cuts(tmp_path, sections, [], scores, 5, 1, True, _rendered(mod, sections, stale=False))
    assert scores["s0"]["blind_streak"] == 0


def test_an_unengaged_day_moves_no_blind_streak_either(mod, tmp_path):
    """The runway is denominated in engaged days; an away-week must not manufacture a proposal."""
    sections = _sections()
    scores: dict = {}
    mod.apply_cuts(tmp_path, sections, [], scores, 5, 1, False, _rendered(mod, sections, stale=True))
    assert scores == {}


def test_a_fresh_section_pinned_at_its_floor_accrues_a_dormant_streak(mod, tmp_path, monkeypatch):
    """The third escape route, found by driving the fix rather than reading it.

    metric 0 under `metric_decreased` emits no claim ("falls below 0" is not falsifiable) and is
    not stale — so before this counter existed such a section carried a record with two zero
    counters and read as reachable while remaining uncuttable forever.
    """
    monkeypatch.setenv("LIMEN_DIURNAL_DORMANT_THRESHOLD", "2")
    sections = _sections()
    scores: dict = {}
    for _ in range(2):
        applied, proposed = mod.apply_cuts(
            tmp_path, sections, [], scores, 5, 1, True, _rendered(mod, sections, metric=0)
        )
    assert scores["s0"]["dormant_streak"] == 2
    assert not applied, "a healthy zero must not be cut — mail.owed == 0 is good news"
    assert "sat at its floor" in next(p["reason"] for p in proposed if p["what"] == "section:s0")


def test_a_scored_section_is_neither_blind_nor_dormant(mod, tmp_path):
    """Exactly one counter advances per engaged evening; a working section advances none of them."""
    sections = _sections()
    scores: dict = {}
    claims = mod.build_claims(tmp_path, sections, _rendered(mod, sections))
    scored = mod.score_claims(claims, _rendered(mod, sections, metric=1))
    mod.apply_cuts(tmp_path, sections, scored, scores, 5, 1, True, _rendered(mod, sections))
    assert scores["s0"]["blind_streak"] == 0
    assert scores["s0"]["dormant_streak"] == 0
    assert scores["s0"]["noop_streak"] == 0, "it held — the streak resets"


def test_a_non_cuttable_section_accrues_no_blind_streak(mod, tmp_path):
    sections = _sections(s0={**_sections()["s0"], "cuttable": False})
    scores: dict = {}
    mod.apply_cuts(tmp_path, sections, [], scores, 5, 1, True, _rendered(mod, sections, stale=True))
    assert "s0" not in scores


# ── 3 · both declared acted_when rules have a consumer ─────────────────────────────


def test_metric_changed_sections_are_claimable(mod, tmp_path):
    """check-diurnal.py admits `metric_changed`; two live sections use it; nothing implemented it."""
    sections = _sections(s0={**_sections()["s0"], "acted_when": "metric_changed"})
    claims = mod.build_claims(tmp_path, sections, _rendered(mod, sections))
    c0 = next(c for c in claims if c["section"] == "s0")
    assert c0["acted_when"] == "metric_changed"
    assert "changes from 7" in c0["text"]


def test_metric_changed_scores_any_movement_as_held_and_never_missed(mod, tmp_path):
    """No direction is declared, so the only failure the rule can express is not moving at all."""
    sections = _sections(s0={**_sections()["s0"], "acted_when": "metric_changed"})
    claims = [c for c in mod.build_claims(tmp_path, sections, _rendered(mod, sections)) if c["section"] == "s0"]
    worse = mod.score_claims(claims, _rendered(mod, sections, metric=99))
    same = mod.score_claims(claims, _rendered(mod, sections, metric=7))
    assert worse[0]["verdict"] == "held"
    assert same[0]["verdict"] == "noop"


def test_metric_changed_can_claim_from_zero(mod, tmp_path):
    """`received_count changes from 0` is IF-FIRST-DOLLAR — the most consequential claim there is.

    A `metric_decreased` claim from 0 stays excluded: you cannot fall below zero.
    """
    sections = _sections(
        s0={**_sections()["s0"], "acted_when": "metric_changed"},
        s1={**_sections()["s1"], "acted_when": "metric_decreased"},
    )
    claimed = {c["section"] for c in mod.build_claims(tmp_path, sections, _rendered(mod, sections, metric=0))}
    assert "s0" in claimed
    assert "s1" not in claimed


def test_a_claim_predating_the_acted_when_field_still_scores(mod, tmp_path):
    """Tonight's evening scores a morning emitted by yesterday's code. It must not crash or drift."""
    sections = _sections()
    legacy = [{"id": 1, "section": "s0", "metric": "count", "was": 7, "text": "old-shape claim"}]
    assert mod.score_claims(legacy, _rendered(mod, sections, metric=1))[0]["verdict"] == "held"
    assert mod.score_claims(legacy, _rendered(mod, sections, metric=99))[0]["verdict"] == "missed"


# ── the whole point, against the real registry ─────────────────────────────────────


def test_every_cuttable_section_in_the_live_registry_is_claimable_or_blind_countable(mod):
    """The predicate check 7b enforces at runtime; this pins it at the unit level.

    Every `cuttable: true` row must be reachable by ONE of the two counters — claimed when its
    source is fresh, counted blind when it is not. A row reachable by neither is declared cuttable
    and cannot be cut, which is the defect this file exists for.
    """
    import yaml

    sections = yaml.safe_load((ROOT / "institutio/governance/diurnal.yaml").read_text())["sections"]
    cuttable = {k for k, v in sections.items() if v.get("cuttable")}
    assert cuttable, "registry declares no cuttable section — the cut loop would be inert"

    claimable = {k for k in cuttable if sections[k].get("acted_when") in ("metric_decreased", "metric_changed")}
    assert claimable == cuttable, f"declared cuttable but no acted_when rule reaches them: {cuttable - claimable}"

    # And blind-counting needs the section to be re-probed at evening, which re-renders morning.
    morning = {k for k in cuttable if "morning" in (sections[k].get("phases") or [])}
    assert morning == cuttable, f"cuttable but never re-probed, so never counted blind: {cuttable - morning}"
