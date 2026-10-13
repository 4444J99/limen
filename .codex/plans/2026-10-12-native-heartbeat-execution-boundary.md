# Repair native heartbeat execution and witness checkout

Owner: Limen. Continues the authorized shared operating-system repair and the
witness-source-access plan without rewriting earlier plans or shared checkouts.

## Evidence

Accepted revision 482e97d201247200ce1ab8b7383de2d3a03eae20 passed controlled
activation but failed its first natural maintenance observation with
`unavailable:rss_census`. Three consecutive failures legitimately disabled the
LaunchAgent. Preserve those receipts; controlled activation is not natural-run
acceptance. Host-wide `ps` remains unreliable under current pressure. The old
probe-only duration omitted CLI startup and notification delivery.

The immutable Jules witness checkout also failed with HTTP 404: its private
repository moved to 4444J99/ops-witness and the default repository token cannot
read that source. Use the existing source-read credential, only for the pinned
checkout, with credential persistence disabled. Preserve the pinned commit and
content hashes, provider-write restrictions, and all witness assertions.

## Implementation

1. Census the owned Darwin process group through libproc, bounded by the original
   wall allowance; reject truncated membership or unreadable RSS. Keep the
   bounded POSIX fallback elsewhere and all existing cleanup/resource guards.
2. Use an isolated exec bootstrap instead of a Python preexec callback. Establish
   the owned session, close inherited descriptors, preserve cwd/environment and
   native descriptor limits, and apply the existing CPU limit before target exec.
3. Route scheduled heartbeat invocation through a small standard-library entry
   point. Bound imports, probing and delivery together; unwind children and
   leases before persisting one failure and enforcing the existing kill switch.
4. Include entrypoint and package metadata in the accepted runtime digest. Keep
   every scheduled probe, cadence and per-probe resource limit unchanged.

## Verification and delivery

Focused tests cover real bootstrap context/descriptor isolation, child cleanup,
CPU/RSS/output limits, native PID-count semantics and incomplete observations,
whole-tick deadline unwinding, exactly-once failure accounting, and confined
immutable witness-source access. Run the registry-selected scoped verification
batch on the final tree. Diagnose failures without omitting intended checks.

Merge the verified exact head through the registered fast lane, install that
accepted revision, and activate only its reviewed heartbeat plan. Retain package,
runtime, contract, launcher, interpreter and plist identities. Capture controlled
activation and a subsequent natural scheduled maintenance pass with launchd
origin and whole-process timing. Keep the existing read-only 24-hour watch; do
not create a second scheduler or pretend its window has elapsed.

Re-measure shared capacity after deployment. The last independent measurement
was 70.9248 percent, not a passing below-70 result. Bounded npm cache verification
timed out; allocated cache decreased but filesystem free space also decreased,
so it establishes no successful physical recovery. Preserve native history,
active caches, divergent primaries and custody evidence.

External native-app platform denial remains recorded by its existing owner.
Neither local tests nor receipt prose can substitute for required live evidence.
