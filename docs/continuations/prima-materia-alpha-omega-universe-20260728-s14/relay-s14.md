# Prima Materia α→Ω universe relay — S14

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s14`.
- Admitted capsule commit: `3f9059cd1bd445e2ced6e46b50cb1e348768a6f1`.
- Funnel-record adapter packet commit: `b0bdc8275c53d8771b3d41449729fac9aecf715c`.
- Capsule receipt SHA-256:
  `aa03d36cd04fc47615839b70f575978f3c7cdd29f3e5c8c77866f9d5251251aa`.

## Completed predicate

The S14 packet replaces the funnel-record placeholder with a read-only executable adapter over a
tracked source-instance manifest.

The packet:

- creates a source-owned denominator for the generated funnel summary, PII-clean opportunity
  aggregate, and repository traffic observations without treating their executable readers or
  writers as data rows;
- retains each declared runtime record as a source instance when its file is absent, producing one
  opaque unclassified availability debt row rather than silently reporting zero records;
- adds optional input files to the enumerator contract so absence, appearance, disappearance, and
  byte changes all invalidate the cache;
- re-hashes required and optional inputs after execution or cache validation and fails closed on
  source drift;
- validates exact parity between the tracked funnel manifest and all three registered optional-input
  sets;
- bounds each source by bytes and rows, rejects symlinks and path escapes, and converts malformed,
  oversize, empty, or semantically unclassified records into privacy-safe opaque debt;
- classifies only an explicit JSON `_doc` string and JSONL blank formatting as non-project data;
  repositories, referrers, funnel metrics, inbound classifications, and identities never become
  projects or collaborators by inference; and
- proves source add, remove, and reorder changes coverage without changing retained source-instance
  identities.

All three runtime record files are absent in this disposable checkout. Current funnel truth is
therefore three census-bound, incomplete observations, each with zero projects, zero collaborators,
and one unclassified availability row.

The tracked end-to-end runner now reports 12 executed enumerators, 21 missing enumerators,
7 placeholder source instances, 6 observations, and zero adapter failures. Its overall exit remains
nonzero because whole-universe enumeration is incomplete.

Evidence on the packet state:

- focused funnel, adapter-runner, freezer, and contract tests — `37 passed`;
- exact runner assertions after the final parity addition — `12 passed`;
- tracked executable runner — 12 executed, 21 missing, 7 placeholders, 6 observations, 0 failed;
- `scripts/verify-scoped.sh` — passed:
  - Python: `4300 passed, 2 skipped`;
  - API: `45 passed`;
  - generated surface and contract-schema validation: passed;
  - Next.js production build, TypeScript, static export, and exported-page validation: passed.

The scoped heavy shard was initially denied twice before execution by the live disk-throughput
admission predicate while a protected peer snapshot was active. No peer was signaled or retuned.
After the snapshot write ended and admission passed, the unchanged exact state completed the single
heavy run above. The exact-state receipt must not be rerun unchanged.

## Local lifecycle

- S2 through S13 are clean, inactive, exact-HEAD remote-preserved, and removed locally.
- S13's ignored Node, build, and test caches were physically removed with its worktree.
- S14's ignored dependencies, generated surfaces, and build output are disposable and must be
  removed with the worktree after a successor has a remote capsule receipt.

## Live owner gates

- PR `organvm/limen#1606` remains owner-gated for merge-queue admission; do not rewrite its exact
  green head or wait on non-required checks.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  S14 performed no GitHub mutation and did not refresh credentials.
- Sealed private enumeration remains custody-gated and did not run.
- The career lane and the separate laptop-wide recovery S18 lineage remain human-protected and must
  not be signaled, retuned, reclaimed, or retired by this workstream.

## Next admissible packet

Implement the read-only executable adapter family for `github_estate`. Treat
`institutio/github/estate.yaml` as desired-state ownership and live paginated GitHub reads as the
remote observation source; neither the current local checkout nor three known grants may cap the
denominator. Reuse the privacy-safe snapshot and reconciliation models in
`cli/src/limen/github_universe.py` where their contracts fit, but do not mistake the existing
file-driven reconciler for a live census.

The census must preserve every remotely discovered repository, outside collaborator grant, pending
invitation, and marker-bound user Project item or emit exact unavailable-surface debt. Hash logins
before they cross the adapter boundary. Repository observations must remain distinct from canonical
projects until source lineage binds them; live access proves access, not relationship role or
authority. Project membership must not imply repository access. Missing Projects scope is one
credential-wall atom and must not stop repository/collaborator enumeration.

Do not perform GitHub writes, create a Project, invite or remove anyone, refresh credentials, merge,
install a runtime, mutate custody, spend, or touch either protected lineage.
