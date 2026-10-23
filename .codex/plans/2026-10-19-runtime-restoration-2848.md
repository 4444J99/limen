# Runtime restoration continuation

Owner: 4444J99/limen#2848
Native session: 01a154c1-f69f-7013-979c-69516316a258
Attempt deadline: 2026-10-19T15:52:52Z; verification <=600 seconds.

Continue the requested runtime repairs, native restoration and cleanup.
Preserve the failed original watch and all native state/custody/dirty work.

1. Reconcile current clock, broker census and reader identities.
2. Run the existing five-reader ten-turn fixture under normal heavy admission
   with a 540-second deadline. Preserve failures and old evidence.
3. Publish only valid evidence for exact current binaries. Record the
   maintenance controller twice if admitted.
4. Classify cleanup by inactivity, reconstruction, native acceptance and
   independent custody before any retirement.
5. Publish the redacted receipt and implicated verification through the PR rail.

Broker read admission returned 409; no run, child or reservation was accepted.
The released audit checkout still has a foreign local lease, so this inactive
related checkout is reused. No new checkout or branch was created.
No live history compression or native history deletion is authorized here.

Observed source defect: CLI worktree inventory reservation falls back to PATH
Python and loses the running CLI toolchain. Add a regression for new/existing
branches and bind only inventory reservation calls to the CLI interpreter.
