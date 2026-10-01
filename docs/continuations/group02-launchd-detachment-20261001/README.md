# Group 02 LaunchAgent source detachment

Owner: Domus #397 under Limen #2739. Shared dependency edits were explicitly
authorized by the user on 2026-10-01. This continues the merged Group 02 custody
and merge-policy work in Limen PR #2798 (`c92bcf3318749bd6312252ccaa51a9a2d14d0cc1`).

Three installed and loaded LaunchAgents still consume editable Limen paths:
`com.limen.creds-hydrate`, `com.limen.claude-stub-heal`, and `com.ianva.gateway`.
Their owning source plists now select the receipt-bound Domus runtime and put
logs under the host state root. The credential job uses the installed venv
without a fallback to an unrelated interpreter; the gateway PATH selects that
same venv. The native responsibility host remains unchanged for both control
jobs. Configured vendor capabilities and triggers remain declared.

Six focused tests pass, including a recursive check across argv, environment
and log paths for editable-source dependencies. All three plists parse. The
current installed runtime contains all three entrypoints, its interpreter
exists, and the gateway config imports successfully with its installed source.
These checks establish source preparation, not native cutover or natural fires.

The scoped resolver passed seven cheap gates but its whole-estate Ruff lint
failed on existing neighboring findings (output exceeded its 1 MiB limit).
The touched test's pre-existing import-order finding and the newly extended
assertion's formatting were corrected; focused Ruff lint/format and all six
tests then passed. The full estate lint is not represented as green. Unchanged
neighboring findings were not bulk-rewritten as part of host cutover.

## Current application gates

The exact merged PR #2798 runtime installation was attempted once through
Domus after acquiring machine-wide host admission. Admission refused the heavy
lease for `swap-fraction` and `disk-throughput`: swap 6,450,839,552 bytes of
17,179,869,184 physical bytes; disk samples 141.13 and 114.72 MiB/s. No installer
started and no runtime binding changed. Resume the same exact merged revision
through normal admission when pressure changes; do not bypass it.

Launchd observations: gateway running, one run, no prior exit; stub healer idle,
six runs, last exit 0; credential job idle, 316 runs, last exit 134. Its failure
is retained as failure evidence. Source changes do not establish its repair.
The gateway is an active shared service, so it was not signaled or restarted.

Rule #55a application requires process-specific IRF registration, hard wall and
resource limits, low priority, failure-streak disablement, bounded audit custody,
and exact merged runtime/plist identities. The legacy control plists do not yet
provide that complete activation boundary, and the generic Domus wrapper
correctly refuses ad-hoc live plist generation. No new launchd activation,
bootstrap, bootout or scheduled process was performed by this implementation.
The existing heartbeat's IRF-SYS-257 is process-specific and is not authority
for these other labels. Implement/admit their own contracts through #397 before
applying the prepared plists; protect active clients and prove rollback.

The main dirty Domus source, legacy native state, compatibility consumers and
remaining ten original Group 02 roots stay retained. Native state capture,
independent-key/replica recovery, drain/canary and full E3 acceptance remain
required. Source preparation is not completion of those predicates.
