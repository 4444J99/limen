# Resumed closeout attempt

Owner: [#3173](https://github.com/4444J99/limen/issues/3173). This dated update preserves
the original 25-session census and its complete acceptance scope. The overall task
and session release remain unfinished. `resumption-20261023.json` binds live readbacks;
the earlier observations remain the historical record of the first attempt.

## Verified change in state

| Scope | Source landing | Adoption or observation |
| --- | --- | --- |
| Reaper correction and census, #3174 | Merged as `fad6c4f428beb6719f94c225bc869dd46a50dc93` | Included in live checkout and installed CLI |
| Broker persistence, #3117 | Merged as `0d72ed17cccdff2d7717a7599b88e16bdc8d20a7` | Included in source; remote Worker deployment and observed recovery remain unverified |
| Workstream interpreter repair, #3130 | Merged as `7999ae9bc070acf3006c65c4be90790e1846a46e` | Included in live checkout and installed CLI; broader #2848 custody/restoration stays open |

All three merge commits pass ancestry checks against fetched `origin/main` and the
live checkout. The canonical sync rail reports a coherent live `main`, zero ahead,
behind or dirty paths. Domus installed the merged `7999ae9b` runtime at 13:29:40 UTC;
verified protocol discovery succeeds and the runtime-lag predicate exits 0 at zero lag.
Native `limen workstream --help` uses that installed runtime. These observations do
not certify every native feature or remote Worker behavior.

## Verification reused and completed

The completed [#3174 PR Gate](https://github.com/4444J99/limen/actions/runs/39958154767/job/120429086400)
passes 9,394 CLI cases, 75 skips and 52 API cases. Its later documentation-only delta
passes seven local gates; implementation bytes are unchanged.

The exact #3117 head passes its local complete scoped batch: seven cheap gates and
413 Worker tests, zero failures. This successful resumed run supersedes the earlier
admission hold without changing that historical failure into a pass. Restoring the
locked dependencies created no tracked source change.

The completed [#3130 PR Gate](https://github.com/4444J99/limen/actions/runs/39281253169/job/118156174607)
passes 18 cheap gates, 9,386 CLI cases, 75 skips and 52 API cases. Its witness-contract
authentication failure remains separately owned by #3003. Each merge followed a
`CLEARED` merge predicate and exact-head merge; no synchronous CI wait was started.

Advisory audit debt remains visible under #3145 (Python) and newly filed #3175
(three Next advisories). Broker review findings remain under #3118. No audit or
intended capability was disabled to obtain a pass.

## Release audit and preservation

The coordinator's authenticated retained-state audit observes its registration and
native anchor, complete non-truncated retained coverage, zero retained runs and zero
active leases. Request history and rejected/uncommitted requests remain unmeasured.
The registration is human-protected and accepts no new work. Earlier helper requests
were rejected; no child run or new checkout was created.

The existing AV bootstrap was inspected and attempted once in dry-run mode at
13:36:37 UTC. It exits 75 with `approved_attempt_deadline_exhausted`. Its original
deadline and identity were preserved; no policy, secret or executor role was changed.
Production admission and acceptance stay with audiovisual-composition-system #12.

The receipt producer in #2988 is not ready: its failed gate and current unresolved
findings prevent using it to manufacture release evidence. Independent custody and
restoration remain unproven for private payloads and missing historical roots. No
verified custody flag, dummy retired root or two-green release result is invented.

The original four native archives and six reaped branches remain the measured cleanup.
No additional task was archived or atom closed, and no checkout or private payload was
deleted. The phase-skill payload stays retained under Domus #535; canonical source
application remains unfinished. The active sibling retains its own writer and native
session; its independent results are not attributed to this coordinator.

This attempt runs from 13:16:12 to a fixed 13:46:12 UTC deadline. Its published
checkpoint retains the owning checkout and existing owners without renewing any
exhausted task budget. Further implementation and acceptance remain under the full
original objective. This observation is not a canonical session-release receipt.
