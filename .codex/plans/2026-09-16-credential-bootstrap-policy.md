# Credential bootstrap policy and recoverable diagnostics

Owner: Codex; collector activation #269/#1995 and credential Wall #320.

The live owner vault read timed out before any service-account creation intent or
pending credential existed. The installed credential was preserved. Chrome page
access works; native app observation and discovery separately timed out. No account
lock, billing cause, or manual authentication requirement is inferred from those
timeouts. Native process discovery confirms the app and Computer Use service exist.

Code inspection found that an empty policy silently acquired default account and
installation settings even with `--apply`. Mutation now requires explicit account,
vault, exact grant scope, absolute installation path and typed classification policy.
Read-only defaults retain their existing compatibility behavior. Provider failures
report only a closed stage/reason vocabulary, never provider output, arguments or
credentials. Creation-intent and custody recovery remain unchanged. The policy's
stale automatic-revocation claim is corrected: old credential retirement is separate.

Acceptance: malformed/missing policy reaches no provider; wrong grants or target
scope fail; timeout, unavailable executable and rejection are distinguishable without
secret output; existing restart/custody tests remain green. Run the scoped predicate
against efc7feec04facb5f9bb5be7db1b59ab1a8f5a75e before landing.

Collector activation still requires canonical credential custody, additive principal
deployment, frozen inventory authority and fresh ingestion/admission evidence. This
repair does not satisfy those deployment predicates or the full estate plan.

## Verification receipt

All 25 focused credential tests passed. The scoped batch passed its ten cheap gates
(including full Python lint/format); heavy CLI/API execution was refused by live host
admission with `swap-fraction`, exit 75. This is incomplete verification, not a pass.
The published draft owns the unexecuted heavy predicates; no merge is authorized by
this local receipt. No provider mutation was attempted during this repair.

An independent relay administration read found repository ID 1350979676 with current
`admin: true`, rulesets `[]`, and branch-protection readback `Branch not protected`.
The earlier managed-integration restriction does not describe this credential. App
registration, isolated deployment and protected canaries remain required; possession
of administrator access is not activation evidence.

## Additive keeper deployment prerequisite

Cloudflare's current settings read exposes only names/types for secret bindings;
it cannot prove that a local principal registry preserves every deployed binding.
Add a conductor-only, non-cacheable principal-registry readback: redacted identities
plus a stable SHA-256 fingerprint covering all validated credential/role bindings.
The readback performs no keeper-state operation. It does not grant a write lease or
make an eventual Cloudflare update atomic. Reconcile custody on mismatch, then use
the owning deployment lane and verify all retained principals after installation.

Three Worker security tests pass: exact role exclusion and no secret disclosure,
fingerprint sensitivity/order stability, and malformed-registry refusal. The combined
source passes all sixteen scoped cheap gates, including the two cross-language
dependency integration tests. Host admission again refuses the unexecuted heavy
CLI/API/Worker wave for swap-fraction. The endpoint is not deployed by this receipt.
