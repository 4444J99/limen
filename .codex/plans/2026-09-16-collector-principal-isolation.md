# Collector principal isolation

Owner: Codex. Continuation of the full gap-filling plan, including #269/#1995,
L-CONDUCT-REGISTRY-DEPLOY, and the remaining estate decisions.

The legacy principal merge helper could append compatibility to a dedicated
inventory collector. Worker authentication rejects that mixed role, so the
helper could generate an unusable production registry. It now refuses that
combination and already-mixed collector roles, rejects malformed entries, and
works on a copy so a refused merge cannot mutate caller state. A separate
collector remains unchanged while a distinct legacy principal is added.

Verification: 11 focused tests and seven scoped gates passed. No production
secret, principal assignment, fleet dispatch or relay job was changed. Dedicated
collector provisioning and admission evidence remain owned by #269/#320; relay
execution is still subject to that authority. Future helper and deployment-script
changes select the dedicated registry-merge test gate.

The full plan remains active. Continue per-component acceptance and estate work
from the merged progress receipt and estate decision plan; this fix does not
establish inventory activation, relay protection, or completed external outcomes.
