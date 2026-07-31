"""Tests for scripts/check-audience.py — the custody half of the world|collab|self axis.

Two properties carry the weight:

1. The derivation is PURE and total — every (visibility, granted) pair lands on exactly one
   audience, so no repo can fall through unclassified.
2. The register may only ever SUGGEST. A people-file edit must never be able to change access
   posture, because the machine-runnable direction of a "collab that isn't granted" finding is
   REMOVAL of a partner's access (L-PARTNER-GRANTS). `test_register_never_decides` is the guard.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_audience", ROOT / "scripts" / "check-audience.py")
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)


# --- the derivation ----------------------------------------------------------
@pytest.mark.parametrize(
    "visibility,granted,want",
    [
        ("public", False, "world"),
        ("public", True, "world"),  # public wins; the guest is reported separately, not folded in
        ("private", True, "collab"),
        ("private", False, "self"),
        ("any", False, "self"),  # fork mirrors / archives read conservatively
        ("any", True, "collab"),
    ],
)
def test_observed_audience_is_total(visibility, granted, want):
    assert ca.observed_audience(visibility, granted) == want


def _estate(**overrides):
    return {
        "classes": {
            "operation_private": {"visibility": "private"},
            "portal_public": {"visibility": "public"},
            "vault_private": {"visibility": "private"},
        },
        "repo_overrides": overrides,
    }


def _access(grants=None, never=("vault_private",)):
    return {"grants": grants or {}, "policy": {"never_grant_classes": list(never)}}


def _register(**lanes):
    return {"people": [{"slug": slug, "projects": [{"repo": repo}]} for slug, repo in lanes.items()]}


# --- structural BREAKs (exit 1: no human decision can legitimize these) -------
def test_unknown_audience_value_is_a_break():
    d = ca.derive(_estate(**{"o/x": {"class": "operation_private", "audience": "wrold"}}), _access(), {})
    breaks, _ = ca.assess(d)
    assert any("not one of" in b for b in breaks)


def test_collab_on_a_never_grantable_class_is_a_break():
    """A shared audience the repo can never actually be granted is a contradiction, not a wish."""
    d = ca.derive(_estate(**{"o/vault": {"class": "vault_private", "audience": "collab"}}), _access(), {})
    breaks, _ = ca.assess(d)
    assert any("never_grant_classes" in b for b in breaks)


# --- OWED judgments (reported; they do not halt the estate) ------------------
def test_declared_collab_without_a_grant_is_the_partner_cannot_see_it_finding():
    d = ca.derive(_estate(**{"o/lane": {"class": "operation_private", "audience": "collab"}}), _access(), {})
    breaks, owed = ca.assess(d)
    assert breaks == []
    assert any("cannot see their own lane" in o and "L-PARTNER-GRANTS" in o for o in owed)


def test_partner_lane_carrying_publish_candidate_is_a_judgment_collision():
    d = ca.derive(
        _estate(**{"o/tato": {"class": "operation_private", "publish_candidate": True}}),
        _access(),
        _register(rob="o/tato"),
    )
    breaks, owed = ca.assess(d)
    assert breaks == []
    assert any("shared operation or solo publication" in o for o in owed)


def test_public_plus_grant_is_named_not_treated_as_drift():
    """`world` is "public, SOLO", so public+granted is a fourth state. It must be NAMED and owed —
    never a demand to flip a traction repo private, which would put this at war with class G."""
    d = ca.derive(
        _estate(**{"o/pub": {"class": "portal_public"}}),
        _access(grants={"o/pub": [{"login": "someone", "role": "push"}]}),
        {},
    )
    breaks, owed = ca.assess(d)
    assert breaks == []
    assert any("world+guest" in o for o in owed)
    assert not any("private" in o.lower() and "flip" in o.lower() for o in owed)


# --- the register may suggest, never decide ----------------------------------
def test_register_never_decides():
    """A repo the register names, with no declared audience and no grant, still derives `self`.

    If the register could DECIDE, this row would read `collab`, and removing the project from the
    register would then turn a live human-decided grant into an "undeclared exposure" finding whose
    armable direction is revoking a partner's access. It suggests; it does not decide.
    """
    d = ca.derive(
        _estate(**{"o/lane": {"class": "operation_private"}}),
        _access(),
        _register(rob="o/lane"),
    )
    row = d["rows"][0]
    assert row["observed"] == "self"
    assert row["declared"] is None
    assert row["suggested_by"] == "rob"


def test_declared_intent_outranks_the_register_hint():
    d = ca.derive(
        _estate(**{"o/lane": {"class": "operation_private", "audience": "world"}}),
        _access(),
        _register(rob="o/lane"),
    )
    breaks, owed = ca.assess(d)
    assert breaks == []
    assert any("declared 'world' but observed 'self'" in o for o in owed)


def test_register_lanes_skips_null_repos():
    """Most register projects carry `repo: null` (protocol-stage people). They are not lanes."""
    lanes = ca.register_lanes({"people": [{"slug": "x", "projects": [{"repo": None}, {"repo": "o/r"}]}]})
    assert lanes == {"o/r": "x"}


# --- the live estate ---------------------------------------------------------
def test_live_estate_has_no_structural_break():
    """The registry may carry open judgments; it may never contradict itself."""
    d = ca.derive(ca._yaml(ca.ESTATE), ca._yaml(ca.ACCESS), ca._yaml(ca.REGISTER))
    breaks, _ = ca.assess(d)
    assert breaks == [], f"estate contradicts itself: {breaks}"


def test_live_estate_classifies_every_override_row():
    d = ca.derive(ca._yaml(ca.ESTATE), ca._yaml(ca.ACCESS), ca._yaml(ca.REGISTER))
    assert d["rows"], "no repo_overrides parsed — the registry path is probably wrong"
    assert all(r["observed"] in ca.AUDIENCES for r in d["rows"])
