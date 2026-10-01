# Multi-scope session release

Owner: https://github.com/4444J99/limen/issues/2763

Implement backward-compatible v2 receipts for exact native non-Git anchors and explicit
Git/retained subjects. Each subject must prove publication, path attribution, scoped
verification and custody; one process census covers exact anchor, declared descendants
and native lineage. Preserve v1 and never signal peers or delete evidence to pass.

Reconcile historical sessions `01a0f92b-a511-7871-89fe-d86f687b8bc3` and
`01a0f4d8-3220-7b92-b78e-5f0a58e24313` as handoffs under their existing owners.
The current session is `01a0f974-79b7-7f90-a787-5ef3f5359948`. Private evidence and
new receipts belong to the existing private owner PR. Preserve prior invalid attempts.

Release requires merged source, verified installed protocol, exact native transcript
binding, complete scope, independent restored journal custody, and two unchanged
exit-zero predicate runs. Completion/retirement/reaping remains separately owned.

Implementation adds repeatable `--scope-root ID=PATH`, stable GitHub repository IDs,
central cross-repository receipts, typed external-effect evidence, and one bounded
multi-root process snapshot. The custody serial parser preserves unrelated ioreg bytes
while rejecting invalid bytes in the selected hardware identity.

Acceptance: focused closeout/process/custody tests, required scoped gate batch, Python
type checking, changed-file lint/format, credential wall, instruction drift, publication,
installation SHA/digest, and all three exact-session predicates. The global finite
attempt remains 30 minutes; a failed gate must be recorded and checkpointed, never
treated as merged or installed acceptance.
