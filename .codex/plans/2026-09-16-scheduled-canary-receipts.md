# Scheduled sensor canary uses current execution receipts

Owner: runtime acceptance issue #2664; Codex direct-session gap-filling work.

The first natural sensor-canary fire on runtime 2739be92a7eca233429df38939e04b4d1ba4bc40
returned a finding. Its command still read retired heartbeat/fast-wave voice stamps from the
immutable source tree. A focused reproduction reported 44 live-lane never-ran findings and
12 registry-only findings. This is incompatible with the current bounded scheduled runtime.

Keep the legacy canary available for explicit legacy diagnostics. Route both current observer
and scheduled-contract sensor-canary commands through check-heartbeat-rollout --scheduled-probes.
Read the installed immutable source receipt for runtime identity, or accept an explicit SHA for
diagnostics. Measure every contract-declared probe against its latest exact-runtime receipt.
Missing, stale, malformed, disabled, deferred, failed, inconsistent and surviving-child evidence
must remain visible and prevent a complete execution-coverage result. The freshness allowance
is each probe cadence plus one full single-probe-per-fire rotation.

A finding is evidence that a probe executed, not that its underlying sensor is healthy. Count
findings separately; otherwise the canary's own initial incomplete result could prevent its
future recovery. External and explicit-maintenance owners remain explicitly unmeasured by this
scheduled-only check. The 44-rung ownership denominator is retained by registry validation.

Acceptance: focused rollout/supervisor tests, scoped resolver, exact-head PR landing and later
installed scheduled execution. Preserve the current installed revision while its remaining
pressure-specific scheduled proof accumulates; source verification alone is not runtime adoption.
