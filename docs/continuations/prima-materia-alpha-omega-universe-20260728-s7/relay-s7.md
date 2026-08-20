# Prima Materia α→Ω universe relay — S7

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s7`.
- Admitted capsule commit: `816e75c4f52d5a5e3dcbb408fce640969dc19987`.
- Universe audit packet commit: `8894c007b759dc79df670b2eeaa6ea19b58b6e20`.
- Capsule receipt SHA-256:
  `bd114ec3655faa4e8facc6f4a99b6f170c96b0ea2e1186c56a2b9799e3baa01f`.

## Completed predicate

The S7 packet implements the bounded, read-only producer for all six universe fixed-point
predicates registered by S6. It cryptographically binds:

- the dynamic source registry;
- the frozen project and collaborator manifests;
- the privacy-safe GitHub reconciliation plan;
- the frozen-wave digest; and
- the exact installed runtime SHA.

The evaluator fails closed for missing or mismatched bindings, missing source coverage, incomplete
canonical project coverage, failed project builds, unresolved collaborators, stale GitHub
observations, privacy findings, duplicate Projects, unbound cards, and non-zero reconciliation
changes. It emits one bounded JSON result and performs no GitHub or filesystem writes.

Evidence on the packet state:

- `PYTHONPATH=cli/src pytest -q cli/tests/test_universe_audit.py` — `5 passed`;
- focused `ruff format` and `ruff check` — passed;
- `git diff --check` and executable wrapper mode — passed;
- scoped Python shard — `4263 passed, 2 skipped`;
- scoped API shard — `45 passed`;
- the first scoped web build stopped only because this disposable worktree had no installed
  lockfile dependencies; after one `npm ci`, the failed `npm run build` predicate passed,
  including data generation, surface/schema validation, TypeScript, static export, and exported
  page validation.

The sanctioned scoped run and its targeted environmental bootstrap are the exact-state receipt;
they must not be rerun unchanged.

## Local lifecycle

- S2 through S6 are clean, inactive, exact-HEAD remote-preserved, and removed locally.
- Their local branches are deleted; their remote branches remain durable.
- The S7 dependency/build caches are disposable and must be removed with the worktree after a
  successor has a remote capsule receipt.

## Live owner gates

- PR `organvm/limen#1606` remains owner-gated for merge-queue admission; do not rewrite its exact
  green head or wait on non-required checks.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  read-only enumeration and local planning remain independently admissible.
- The career lane remains human-protected and must not be signaled, retuned, reclaimed, or
  retired by this workstream.

## Next admissible packet

Implement a bounded, privacy-safe universe manifest freezer that consumes dynamically enumerated
source-owned project and collaborator observations and emits canonically ordered
`ProjectUniverseManifestV1` and `CollaboratorUniverseManifestV1` files with one shared frozen-wave
and source-registry binding. It must retain unknown/missing source debt, distinguish task rows from
projects, preserve aliases and multi-repository/zero-repository projects, keep reference-only people
out of the access universe, and refuse to manufacture completeness. Do not perform GitHub writes,
merge, install a runtime, mutate custody, spend, send externally except for the requested self
progress report, or touch the career lane.
