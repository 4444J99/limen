# Preserve bounded merge failure diagnostics

Owner: Limen merge-drain control plane. Laurea PR #10 exposed a generic FAILED
receipt that could not distinguish the adjacent policy recheck from GitHub's
mutation call. Preserve stage, exit code and allowlisted policy verdict without
printing provider output. Treat effect timeouts as unconfirmed, never retry them.
Do not change merge eligibility, method, exact-head matching, or enforcement.

Acceptance: regression tests cover HOLD/BLOCKED redaction and timeout/no-retry
semantics; run the implicated scoped verification before the PR rail.
