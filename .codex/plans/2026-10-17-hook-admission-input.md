# Limen hook admission input repair

Authority: hook estate survey and evolution attachment, 2026-10-17.
Owner: Limen admission; native session 01a14ab2-92e3-7303-9d6f-aba7c66863ed.
Checkout: /Volumes/Archive4T/limen-hook-admission-input-20261017.
Branch: fix/hook-admission-input-20261017, base ae8319226.
Attempt: 16:30-17:00 UTC; verification bounded to ten minutes.

The concurrent Domus implementation owns shared inventory, dispatcher, templates,
and native adapters in its own checkout. This lane changes only the Limen
admission reader/delegate boundary and its tests. Preserve primary checkouts,
trust stores, all capabilities, existing session-start behavior, and Stop release.

- [ ] Reproduce malformed/stalled/oversized stdin and invalid delegate verdicts
  using isolated harmless subprocesses; assert exact JSON and exit status.
- [ ] Add a bounded reader with an end-to-end deadline, byte limit, and a native
  PreToolUse denial when a covered event cannot be classified. Known lifecycle
  events stay advisory; a registered event argument supplies classification
  independent of malformed JSON.
- [ ] Bound immutable capability/delegate work by the same remaining deadline;
  reject invalid or ambiguous verdicts instead of treating them as permission.
- [ ] Verify focused admission regressions and implicated scoped gates, then
  commit/push source, tests, and sanitized evidence to a topic PR.

No hook activation, fabricated trust hashes, new schedules, provider launches,
or live enforcement claim. Full estate acceptance still requires independent
interception/enforcement, two fresh sessions per surface, and 24 hours/20 events.
Retain this checkout until published and the owning lifecycle permits retirement.
