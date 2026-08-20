# Prima Materia α→Ω universe relay — S8

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s8`.
- Admitted capsule commit: `85b7362e918c9bb360e3b4212aecf4672f353222`.
- Universe manifest-freezer packet commit: `ed4daaaab1f235e11b163c509da35ea79fd6c0e8`.
- Capsule receipt SHA-256:
  `6755c221ae6d6f8fe685990d8719721fa9112f7c486dbd0fd09fa69c60385990`.

## Completed predicate

The S8 packet implements a deterministic freezer over an independently frozen source census and
privacy-safe, source-owned observation packets. It emits one canonically ordered
`ProjectUniverseManifestV1` and one bound `CollaboratorUniverseManifestV1` without hiding missing
or unexpected leaves.

The freezer:

- binds every census and observation to one source-registry digest and frozen-wave digest;
- derives the source, project, and collaborator denominators independently from the observations
  they judge;
- retains stable alias lineage while rejecting aliases that resolve to multiple canonical
  identities;
- merges multi-source evidence conservatively so incomplete or conflicting evidence cannot become
  green;
- supports zero-repository and multi-repository projects;
- rejects canonical or alias project identities reused as child tasks;
- rejects non-project rows reused as projects, tasks, or collaborators;
- keeps reference-only identities out of collaborator and access projections;
- preserves missing/unexpected source, project, and collaborator debt in the output manifests; and
- exposes a write mode plus an exact, read-only `--check` fixed-point mode.

Evidence on the packet state:

- focused universe freezer, manifest, and audit tests — `26 passed`;
- focused `ruff format` and `ruff check` — passed;
- generated JSON Schemas include stable alias fields and are byte-stable;
- `bash scripts/verify-scoped.sh` — passed:
  - Python: `4269 passed, 2 skipped`;
  - API: `45 passed`;
  - generated surface and contract-schema validation: passed;
  - Next.js production build, TypeScript, static export, and exported-page validation: passed.

The exact-state scoped receipt must not be rerun unchanged.

## Local lifecycle

- S2 through S7 are clean, inactive, exact-HEAD remote-preserved, and removed locally.
- S7's ignored Node, build, and test caches were physically removed with its worktree.
- S8's ignored dependencies and build output are disposable and must be removed with the worktree
  after a successor has a remote capsule receipt.

## Live owner gates

- PR `organvm/limen#1606` remains owner-gated for merge-queue admission; do not rewrite its exact
  green head or wait on non-required checks.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  local and snapshot-driven reconciliation remain independently admissible.
- The career lane remains human-protected and must not be signaled, retuned, reclaimed, or
  retired by this workstream.

## Next admissible packet

Implement the privacy-safe GitHub Project reconciler's `check` and `plan` modes over frozen project
and collaborator manifests plus a bounded remote-read snapshot. It must adopt exactly one existing
`4444J99` user Project carrying `organvm-universe:v1`, propose creation only when none exists, fail
closed on duplicate marker-bound Projects or unbound cards, keep Project access separate from
repository access, never invite reference-only roles, preserve stronger live repository grants,
and emit the exact `GitHubProjectionPlanV1` consumed by the S7 audit. Do not implement or invoke
`apply`, perform GitHub writes, refresh credentials, merge, install a runtime, mutate custody,
spend, or touch the career lane.
