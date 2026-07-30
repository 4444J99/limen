# Campaign successor relay

Institutional campaigns stop admitting work at T−30. That boundary reserves one deterministic,
unadmitted successor identity before returning `wait_relay`; it does not evaluate Omega, create a
worktree, register a session, or launch a provider.

## Reservation contract

The relay identity binds the workstream, committed predecessor receipt Git blob, validated committed
contract digest, predecessor deadline, and exact remote default-branch commit. Its stable successor
slug, branch, and broker session ID derive from that digest.

The reservation lives in the repository's Git common directory, not in a worktree. A mode-`0600`
receipt and lock provide cross-worktree and cross-beat duplicate suppression. Receipt replacement is
atomic and fsyncs both file and directory. Repeated beats return the same byte-stable `reserved`
record with `attempts=0`.

Heartbeat output exposes only the path-free relay ID, state, attempt count, successor session ID,
workstream, and next lifecycle predicate. Private store paths never enter heartbeat JSON.

## Deliberate split

This reservation boundary does not implement launch readiness or topic-branch following. Those
effects remain owned by Institutional Omega issue #1571 and require a separate reviewed change that:

- holds the relay lock through one bounded creation and launch attempt;
- emits readiness only beside the final provider exec, after every fallible preparation step;
- proves the exact protected broker session, remote receipt commit, and provider PID/start
  continuity before marking the successor ready;
- records bounded child output and every partial or failed phase without automatic retry;
- lets main-only campaign wake follow only the immutable ready topic-branch receipt.

No evaluator or trial function runs at T−30, and neither the predecessor receipt nor frozen trial
evidence is modified.
