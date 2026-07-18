#!/usr/bin/env python3
"""Hermetic regression for correspondence-walk.py's stale-awaiting-them nudge (Tier 3.1).

Two pure units, no live IMAP, no Gmail:
  1. _parse_internaldate — an IMAP FETCH (INTERNALDATE) response → an aware UTC datetime (and None,
     fail-open, on garbage).
  2. _disposition branch 1b — an out-of-band-answered thread whose Sent reply is older than
     stale_days flips awaiting-them → a needs-human nudge; a fresh reply stays awaiting-them;
     stale_days=0 disables the nudge entirely (exact prior behavior).
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def _load_walk():
    spec = importlib.util.spec_from_file_location("correspondence_walk", SCRIPTS / "correspondence-walk.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeSD:
    """Minimal stand-in for the UMA module: _disposition needs _ob_key + tier_of only."""
    def _ob_key(self, ob):
        return "cls|domain|subject"

    def tier_of(self, ob, tiers):
        return "hold"


def main() -> int:
    mod = _load_walk()

    # 1. _parse_internaldate on a real FETCH response line → aware UTC datetime.
    resp = [b'1 (INTERNALDATE "19-Jul-2026 14:23:45 +0000")']
    got = mod._parse_internaldate(resp)
    want = datetime(2026, 7, 19, 14, 23, 45, tzinfo=timezone.utc)
    assert got == want, f"internaldate parse: got {got!r}, want {want!r}"

    # 1b. A non-UTC offset must be normalized to the same absolute instant.
    resp_offset = [b'7 (INTERNALDATE "19-Jul-2026 10:23:45 -0400")']
    assert mod._parse_internaldate(resp_offset) == want, "offset not normalized to UTC"

    # 1c. A fetch TUPLE element (INTERNALDATE alongside a body literal) is handled.
    resp_tuple = [(b'9 (INTERNALDATE "19-Jul-2026 14:23:45 +0000" BODY[] {3}', b'hi'), b')']
    assert mod._parse_internaldate(resp_tuple) == want, "tuple fetch element not parsed"

    # 1d. Garbage / empty ⇒ None (fail-open, never raises).
    assert mod._parse_internaldate([b'nonsense']) is None, "garbage should parse to None"
    assert mod._parse_internaldate(None) is None, "None input should be None"
    assert mod._parse_internaldate([]) is None, "empty list should be None"

    ob = {"cls": "personal", "sample_subjects": ["Re: quick question"], "reply_to": "x@y.com"}
    sd = _FakeSD()
    now = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)

    # 2. Stale: a reply sent 32 days ago, stale_days=14 → needs-human nudge (STALE_NUDGE_PREFIX reason).
    stale_at = datetime(2026, 7, 19, 0, 0, 0, tzinfo=timezone.utc)
    disp, reason, missing = mod._disposition(
        ob, None, set(), sd, answered_fn=lambda o: stale_at, now=now, stale_days=14)
    assert disp == "needs-human", f"stale reply should nudge, got {disp} ({reason})"
    assert reason.startswith(mod.STALE_NUDGE_PREFIX), f"reason should carry the nudge marker: {reason}"
    assert missing is False

    # 3. Fresh: a reply sent 2 days ago, stale_days=14 → awaiting-them (unchanged; drains upstream).
    fresh_at = datetime(2026, 8, 18, 0, 0, 0, tzinfo=timezone.utc)
    disp, reason, _ = mod._disposition(
        ob, None, set(), sd, answered_fn=lambda o: fresh_at, now=now, stale_days=14)
    assert disp == "awaiting-them", f"fresh reply should stay awaiting-them, got {disp} ({reason})"

    # 4. Disabled: stale_days=0 means an old reply still reads awaiting-them (exact prior behavior).
    disp, _, _ = mod._disposition(
        ob, None, set(), sd, answered_fn=lambda o: stale_at, now=now, stale_days=0)
    assert disp == "awaiting-them", f"stale_days=0 must disable the nudge, got {disp}"

    # 5. No Sent reply (answered_fn → None): branch 1b falls through (not awaiting-them here).
    disp, _, _ = mod._disposition(
        ob, None, set(), sd, answered_fn=lambda o: None, now=now, stale_days=14)
    assert disp != "awaiting-them", f"a None answered_fn must not stamp awaiting-them via 1b, got {disp}"

    print("correspondence-await-stale.test: all cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
