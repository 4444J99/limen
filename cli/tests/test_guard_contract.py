"""Tests for limen.guard_contract — the invariant "a guard that cannot see must WARN, not pass".

A checker that only ever passes proves nothing. The load-bearing cases here are the ones that
prove it CATCHES: a reader that returns trusted on a degenerate input, one that returns a shape
the contract cannot read, and one that raises. All three were live failure modes in the stack this
module generalizes (F7 of the 2026-08-07 cadence-guard arc).
"""

from __future__ import annotations

import os

import limen.model_selection as M
from limen import guard_contract as G


def test_trusted_is_derived_and_cannot_be_forced():
    """The structural half. There is no argument by which a caller can mark an unresolvable state
    trusted — which is why a new guard gets the invariant by construction, not by remembering."""
    assert G.verdict("ok")["trusted"] is True
    assert G.verdict("absent")["trusted"] is False
    # Passing `trusted` must not be possible at all. The first cut spread **extra LAST, so this
    # call silently overwrote the derived value and the guarantee was decorative — this assertion
    # is what found it.
    import pytest

    with pytest.raises(TypeError, match="derives `trusted`"):
        G.verdict("absent", trusted=True)
    # Payload still rides along, it just cannot reach the trust decision.
    assert G.verdict("absent", balance={"x": 1})["balance"] == {"x": 1}
    # A guard may declare its own ok-set, but the derivation still governs.
    assert G.verdict("fresh", ok_states=("fresh",))["trusted"] is True


def test_normalize_refuses_to_guess():
    """Guessing here would reproduce, inside the enforcement mechanism, the exact substitution the
    enforcement exists to forbid."""
    assert G.normalize(None) is None
    assert G.normalize(True) is None
    assert G.normalize({"trusted": True}) is None  # no `state` → not a verdict
    assert G.normalize("ok") is None
    v = G.normalize({"state": "absent", "trusted": False, "detail": "x"})
    assert v == {"state": "absent", "trusted": False, "detail": "x"}
    # A verdict missing `trusted` derives it rather than assuming fine.
    assert G.normalize({"state": "absent"})["trusted"] is False


def test_check_degrades_catches_a_reader_that_passes_on_a_degenerate_input():
    """THE CASE THE WHOLE ARC EXISTS FOR."""

    def permissive(*_args):
        return {"state": "absent", "trusted": True}  # the defect, in one line

    findings = G.check_degrades(permissive, [{"name": "absent input"}])
    assert len(findings) == 1
    assert "TRUSTED" in findings[0]["why"]


def test_check_degrades_catches_wrong_shape_and_crashes():
    """A guard that crashes is NOT failing safe: a SessionStart hook's command ends `|| true`, so
    at the surface that matters a crash and a silence are the same event."""

    def wrong_shape(*_args):
        return None

    def crasher(*_args):
        raise RuntimeError("boom")

    assert "not a verdict" in G.check_degrades(wrong_shape, [{"name": "c"}])[0]["why"]
    assert "raised RuntimeError" in G.check_degrades(crasher, [{"name": "c"}])[0]["why"]


def test_check_degrades_is_silent_when_the_invariant_holds():
    def honest(*_args):
        return G.verdict("absent", detail="nothing to read")

    assert G.check_degrades(honest, [{"name": "absent input"}]) == []


def test_env_overrides_are_restored_exactly(monkeypatch):
    """A leaked degenerate env would make the NEXT case's result meaningless.

    The fixture is set through monkeypatch (per check-test-hygiene) so this test cannot leak even if
    it fails mid-body; the direct os.environ mutation under test happens inside ``_env`` itself.
    """
    monkeypatch.setenv("GUARD_CONTRACT_TEST_PRESENT", "original")
    monkeypatch.delenv("GUARD_CONTRACT_TEST_ABSENT", raising=False)

    with G._env({"GUARD_CONTRACT_TEST_PRESENT": "changed", "GUARD_CONTRACT_TEST_ABSENT": "added"}):
        assert os.environ["GUARD_CONTRACT_TEST_PRESENT"] == "changed"
        assert os.environ["GUARD_CONTRACT_TEST_ABSENT"] == "added"
    assert os.environ["GUARD_CONTRACT_TEST_PRESENT"] == "original"
    assert "GUARD_CONTRACT_TEST_ABSENT" not in os.environ


def test_the_real_readers_speak_the_contract():
    """Both shipped readers must normalize — if one drifts out of shape the ratchet reports it as
    a finding rather than silently passing, which is the invariant applied to its own enforcement."""
    assert G.normalize(M.balance_verdict()) is not None
    assert G.normalize(M.opening_verdict("claude-opus-5")) is not None
    assert G.normalize(M.opening_verdict("some-other-vendor-model-9")) is not None


def test_opening_verdict_degrades_on_every_degenerate_pin():
    for pin in ("", "some-other-vendor-model-9", "claude-fable-5"):
        assert M.opening_verdict(pin)["trusted"] is False, pin
    assert M.opening_verdict("claude-sonnet-5")["trusted"] is True


def test_opening_verdict_degrades_on_a_degenerate_CEILING_too(monkeypatch):
    """The invariant belongs to the READER, not to one of its arguments. `opening_verdict` takes two
    declarations and the declared degenerate population covered only the pin — so the ratchet proved
    everything it was told about while the ceiling axis stayed invisible. The cheapest pin is the
    one that mattered: it was the only one that came back TRUSTED against a ceiling nobody declared."""
    monkeypatch.delenv("LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER", raising=False)
    for ceiling in ("banana", "claude-opus-5", "gpt-5.6"):
        assert M.opening_verdict("claude-haiku-4-5", ceiling)["trusted"] is False, ceiling

    # An EMPTY declaration is absent, not garbage — it falls through to the default, as before.
    assert M.opening_verdict("claude-haiku-4-5", "")["trusted"] is True

    monkeypatch.setenv("LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER", "banana")
    assert M.opening_verdict("claude-haiku-4-5")["trusted"] is False

    # A ceiling that IS declared (any case) still resolves — the fix is a verdict, not a refusal.
    monkeypatch.setenv("LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER", "Opus")
    assert M.opening_verdict("claude-haiku-4-5")["trusted"] is True
