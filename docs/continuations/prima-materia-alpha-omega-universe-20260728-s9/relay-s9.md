# Prima Materia α→Ω universe relay — S9

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s9`.
- Admitted capsule commit: `81c995620d6e983bc7167bc2b15d989491ca3c06`.
- GitHub universe reconciliation packet commit: `2c270796dfb88c918d9eca240932f4468c2cc42d`.
- Capsule receipt SHA-256:
  `827e38aa1c9b66aece7b827cc96050d5b79077874ee9e28fc3a2ef8d7d0144a6`.

## Completed predicate

The S9 packet implements privacy-safe, snapshot-driven `check` and `plan` modes for the GitHub
universe projection. It contains no GitHub mutation client and no credential-refresh path.

The reconciler:

- adopts exactly one `4444J99` user Project carrying `organvm-universe:v1`;
- proposes `ORGANVM Universe` creation only when no marker-bound Project exists;
- fails closed on duplicate marker-bound Projects, duplicate canonical cards, or unbound cards;
- derives card phase, build, artifact, receipt, and privacy-safe collaborator fields from the
  frozen project manifest;
- derives Admin, Write, and Read Project access only from explicit source-authorized collaborator
  relationships with proven hashed GitHub identities;
- derives repository access independently, so Project membership never grants repository access;
- plans only missing access or upward changes;
- preserves stronger or unclassified live Project/repository grants as non-mutating, visible
  source-owner drift;
- emits the exact `GitHubProjectionPlanV1` consumed by the S7 fixed-point audit; and
- atomically replaces stale plan output with a failure sentinel if input validation fails.

Evidence on the packet state:

- focused GitHub reconciler and universe audit tests — `10 passed`;
- focused `ruff format`, `ruff check`, executable wrapper mode, and diff hygiene — passed;
- `bash scripts/verify-scoped.sh` — passed:
  - Python: `4274 passed, 2 skipped`;
  - API: `45 passed`;
  - generated surface and contract-schema validation: passed;
  - Next.js production build, TypeScript, static export, and exported-page validation: passed.

The exact-state scoped receipt must not be rerun unchanged.

## Local lifecycle

- S2 through S8 are clean, inactive, exact-HEAD remote-preserved, and removed locally.
- S8's ignored Node, build, and test caches were physically removed with its worktree.
- S9's ignored dependencies and build output are disposable and must be removed with the worktree
  after a successor has a remote capsule receipt.

## Live owner gates

- PR `organvm/limen#1606` remains owner-gated for merge-queue admission; do not rewrite its exact
  green head or wait on non-required checks.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  S9 performed no GitHub mutation and did not refresh credentials.
- The career lane remains human-protected and must not be signaled, retuned, reclaimed, or
  retired by this workstream.

## Next admissible packet

Implement the bounded universe source-adapter runner that turns the tracked dynamic registry's
enumerator references into one independently receipted source census plus privacy-safe
`UniverseSourceObservationV1` packets consumable by S8. It must discover adapters from the registry
at runtime, bind every subprocess input/output to the frozen wave and registry digest, enforce
per-adapter timeout and output limits, retain missing/unknown adapters as coverage debt, reject
self-enumerated completeness and raw private identity fields, and resume without rerunning
unchanged successful adapter receipts. Start with fixture adapters and the tracked registry
contract; do not invent source counts, read sealed private payloads before custody restoration,
perform GitHub writes, refresh credentials, merge, install a runtime, mutate custody, spend, or
touch the career lane.
