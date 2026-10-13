# Final correction inputs and acceptance

Continues the native-heartbeat-execution-boundary plan. Review identified output
and engine-import deadline gaps. Keep flushed output inside the timer; move the
existing standard-library contract, state and receipt helpers to heartbeat_state
so an interrupted engine import cannot require reimporting that engine to record
failure. Include the new module in the reviewed runtime digest. Preserve helper
compatibility exports and the existing state schema, lock and kill-switch policy.

The completed old-tree CLI suite reported 8,561 passes, 18 failures and 58 skips.
Sixteen failures originate from two historical settlement commits absent from
current remote ancestry. Live merged PR receipts preserve their original
identities; byte-identical successor patches are reachable from origin/main.
Record both identities and exact diff hashes, replace only the two current
settled_by pointers, and retain the ancestry guard and historical objects.

The remaining two failures are obsolete storage-pressure fixtures using the
retired reserve helper. Migrate them to the shared RuntimePool observation and
assert outstanding reservations are consumed exactly once. Never probe the real
host from those fixtures. Retest every failed node and the affected engine/state,
notification and native subprocess paths; run the final scoped batch with the
registry's actual 1,500-second CLI allowance instead of the earlier 300-second
command cap. Earlier failures remain evidence, not passing verification.

After passing verification, merge the exact head, install and activate its
reviewed immutable runtime, then verify a real natural maintenance fire and a
fresh below-70 capacity census. Preserve divergent primaries, active caches and
the existing read-only watch. Neither source review nor elapsed watch time
substitutes for these live predicates.
