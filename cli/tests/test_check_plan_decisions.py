"""Tests for scripts/check-plan-decisions.py — a decision recorded only in prose binds nothing.

The predicate's whole value is that it cannot be satisfied by writing more prose. Two properties:

1. Every accepted home is a thing a machine can later CHECK — a registry, a predicate, a lever, a
   precedent — or an explicit `owed:` admission. Confident prose is not a home.
2. The baseline may only SHRINK. A baseline that silently absorbs new rows, or keeps rows that
   have since been homed, becomes the hiding place the predicate exists to close.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_plan_decisions", ROOT / "scripts" / "check-plan-decisions.py")
cpd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpd)


# --- what counts as a home ---------------------------------------------------
@pytest.mark.parametrize(
    "body,kind",
    [
        ("declared in `institutio/governance/gates.yaml` as one row", "registry"),
        ("enforced by scripts/check-audience.py on every PR", "predicate"),
        ("the court is `verify-hot-cache.sh`, beat-wired", "predicate"),
        ("gated behind L-PARTNER-GRANTS (invites are outbound)", "lever"),
        ("case law: PREC-2026-07-08-ask-already-decided", "precedent"),
        ("owed: nobody has built this yet", "owed"),
        ("OWED: still unhomed", "owed"),
    ],
)
def test_recognised_homes(body, kind):
    assert cpd.home_of(body) == kind


@pytest.mark.parametrize(
    "body",
    [
        "We will absolutely do this, it is decided and important.",
        "Everyone agrees this is the right architecture going forward.",
        "This supersedes the previous approach entirely.",
    ],
)
def test_confident_prose_is_not_a_home(body):
    """The failure mode is a decision that SOUNDS binding. Emphasis is not enforcement."""
    assert cpd.home_of(body) is None


# --- the parser --------------------------------------------------------------
def test_only_reads_decision_blocks(tmp_path, monkeypatch):
    (tmp_path / "p.md").write_text(
        "# Plan\n\n"
        "## Background\n\n1. Some numbered background note with no home\n\n"
        "## Decisions made for the operator\n\n"
        "1. **A thing** — enforced by scripts/x.py\n"
        "2. **Another** — no home at all\n\n"
        "## Notes\n\n3. Another numbered note outside the block\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cpd, "PLANS", tmp_path)
    rows = cpd.scan()
    assert [r["n"] for r in rows] == ["1", "2"], "numbered items outside a Decision block are not decisions"
    assert rows[0]["home"] == "predicate"
    assert rows[1]["home"] is None


def test_continuation_lines_belong_to_their_decision(tmp_path, monkeypatch):
    """These are written as prose paragraphs; a home named on line 3 still counts."""
    (tmp_path / "p.md").write_text(
        "## Decisions\n\n"
        "1. **A thing** — a long preamble that wraps\n"
        "   across several lines before it finally\n"
        "   names `institutio/governance/sensors.yaml`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cpd, "PLANS", tmp_path)
    assert cpd.scan()[0]["home"] == "registry"


def test_a_heading_ends_the_block(tmp_path, monkeypatch):
    (tmp_path / "p.md").write_text(
        "## Decisions\n\n1. **A** — owed: yes\n\n### Sub\n\n2. **B** — no home\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cpd, "PLANS", tmp_path)
    assert [r["n"] for r in cpd.scan()] == ["1"]


# --- the baseline may only shrink -------------------------------------------
def test_baseline_entries_are_well_formed():
    for key in cpd.BASELINE:
        assert "#" in key, f"baseline key {key!r} must be '<file>#<number>'"
        name, num = key.rsplit("#", 1)
        assert name.endswith(".md") and num.isdigit()


def test_every_baseline_row_still_exists():
    """A baseline naming a decision that no longer exists is rot; the predicate fails on it."""
    keys = {r["key"] for r in cpd.scan()}
    assert cpd.BASELINE <= keys, f"baseline names decisions that are gone: {sorted(cpd.BASELINE - keys)}"


def test_no_baselined_row_is_already_homed():
    """Once a decision is homed, its baseline row must be dropped — otherwise the baseline becomes
    a place decisions hide after they stop needing to."""
    stale = [r["key"] for r in cpd.scan() if r["home"] and r["baselined"]]
    assert stale == [], f"homed decisions still in BASELINE: {stale}"


# --- the live tree -----------------------------------------------------------
def test_live_plans_have_no_unhomed_new_decision():
    unhomed = [r["key"] for r in cpd.scan() if not r["home"] and not r["baselined"]]
    assert unhomed == [], f"decisions with no binding home: {unhomed}"


def test_the_two_restated_decisions_are_now_homed():
    """The whole reason this predicate exists: decisions 4 and 5 of the PORTVS/ASTRA plan were
    already committed to main, in his words, and he still had to say them again."""
    rows = {r["key"]: r for r in cpd.scan()}
    for n in ("4", "5"):
        key = f"2026-07-30-portvs-astra-consolidation.md#{n}"
        assert key in rows, f"{key} not parsed"
        assert rows[key]["home"], f"{key} still has no binding home"
