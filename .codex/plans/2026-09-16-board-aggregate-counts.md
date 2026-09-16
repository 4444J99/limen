# Board aggregate measurement integrity

Owner: Codex; full gap-filling plan board-partition acceptance lane.

PR #2001 is merged at c0768c95416bab20d7d681766732b3ed022efdc7, observed through GitHub. This proves publication landing, not current private custody or resident adoption.

The public-board validator previously accepted any values in the required count fields. Validate exact nonnegative integer counts (excluding booleans), complete status/priority totals, completed and active accounting, and the keeper three-decimal completion rate. Malformed containers fail without traceback or echoing unexpected category names. Unknown remains an explicit allowed bucket. Correct the truncated aggregate fixture to contain its full declared denominator.

The architecture stays private canonical custody with counts-only public projection. No task state or projection is edited. This predicate verifies aggregate integrity only; it cannot satisfy the lever's full live-custody and runtime acceptance condition. Those remain separately unmeasured.

## Verification and current external evidence

Code head 0e8cd919cc9a7905e6028060566859f57ba2bde5: scoped verification passed 11 cheap gates, 7,744 CLI tests (2 skipped) and 52 API tests. Includes malformed containers, negative/string/boolean counts, inconsistent totals, invalid categories, nonfinite and oversized rates, and the empty-board case.

Read-only observations on September 16: default 9d991eba512b196ef70eef56049d15aaa8efb428 tasks blob ab74146dda72ad8fd3efe944ead709e6a72ac680 passes aggregate integrity, reports 3,185 rows, and retains generated_at 2026-08-21T11:45:05.230Z. The documented dispatch environment-cache bootstrap enabled authenticated private-board access: 3,186 rows, keeper SHA 16fd02e1a72d7ee8d5432d637221938aa94e3cf5, deployment 4839ca12-ac13-4b48-a215-57b727117243. Only counts and deployment identity were emitted.

The publication ref tabularius/board-projection returned 404, and its open-PR query returned an empty list. Publication freshness is therefore incomplete; private custody is readable, not absent. No task or ref mutations were performed. Owner: existing keeper publication lane / L-BOARD-PARTITION-DECISION. Next: inspect the keeper publication bootstrap and existing verify-keeper-publication.py receipt before any broker-owned recovery; do not synthesize a manual ref or repeat an already submitted canary.
