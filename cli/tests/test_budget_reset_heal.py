"""Heal: a stale per-agent budget counter must never deadlock a lane forever.

Regression for the jules zero-dispatch incident (2026-07-03). jules sat at 100/100 with a reset
stamp frozen ~4 days stale, so BOTH gates excluded it: the capacity gate (remaining = cap-spent = 0
-> reachable False) and the usage-dead gate (usage.json health "exhausted"). The daily reset
computed correctly in memory but was DISCARDED on every no-candidate / gated early-return, so the
counter could never self-clear -- and because every lane's reset stamp was frozen at 2026-06-29, it
was a fleet-wide time bomb (codex was already at 81/100).

The fix: `_reset_budget_if_needed` REPORTS when it cleared a non-zero counter, so both dispatch
paths persist the reset even on a beat that dispatches nothing. Any healthy lane's beat then clears
every stale lane as a side effect (the reset loops all per_agent), so the deadlock cannot recur.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen import dispatch as D
from limen.models import Budget, BudgetTrack, LimenFile, Portal


def _lf(caps: dict, spent: dict, resets: dict) -> LimenFile:
    track = BudgetTrack(
        date="2026-07-03", spent=sum(spent.values()), per_agent=dict(spent), per_agent_reset=dict(resets)
    )
    return LimenFile(portal=Portal(budget=Budget(daily=600, per_agent=caps, track=track)))


def test_stale_capped_lane_is_cleared_and_reset_is_reported():
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    stale = (now - timedelta(days=4)).isoformat()  # >> any vendor window (5h / 24h)
    lf = _lf(
        caps={"jules": 100, "codex": 100},
        spent={"jules": 100, "codex": 81},
        resets={"jules": stale, "codex": stale},
    )
    changed = D._reset_budget_if_needed(lf, now)
    assert changed is True  # a non-zero counter was cleared -> callers MUST persist the reset
    assert lf.portal.budget.track.per_agent["jules"] == 0
    assert lf.portal.budget.track.per_agent["codex"] == 0
    # the capacity gate re-opens for the deadlocked lane: remaining = cap(100) - spent(0)
    assert D._remaining_budget(lf, "jules", 600) == 100


def test_fresh_counter_within_window_is_untouched_and_not_reported():
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    fresh = (now - timedelta(minutes=5)).isoformat()  # << every window
    lf = _lf(caps={"jules": 100}, spent={"jules": 40}, resets={"jules": fresh})
    changed = D._reset_budget_if_needed(lf, now)
    assert changed is False  # nothing cleared -> no forced write this beat
    assert lf.portal.budget.track.per_agent["jules"] == 40


def test_already_zero_stale_lane_advances_stamp_without_forcing_save():
    # A stale lane already at 0 advances its stamp but reports no change: there is no deadlock to
    # break, so no reason to force an extra tasks.yaml write every beat.
    now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    stale = (now - timedelta(days=4)).isoformat()
    lf = _lf(caps={"opencode": 100}, spent={"opencode": 0}, resets={"opencode": stale})
    changed = D._reset_budget_if_needed(lf, now)
    assert changed is False
    assert lf.portal.budget.track.per_agent["opencode"] == 0
    assert lf.portal.budget.track.per_agent_reset["opencode"] == now.isoformat()
