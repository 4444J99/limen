# Prima Materia α→Ω universe relay — S10

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s10`.
- Admitted capsule commit: `1784975a6966ff04d32e5b8e73c8e353dd93fbc7`.
- Universe source-adapter runner packet commit: `eed0ebab1a68667e587a0abe4e1b544a687a981d`.
- Capsule receipt SHA-256:
  `1873f74aed724f0d7ec50c0eca1cb2a5a6f35b953b81f5cd95f7b199f53fca41`.

## Completed predicate

The S10 packet implements a dynamic, bounded, resumable execution boundary between the tracked
universe source registry and the S8 manifest freezer.

The runner:

- discovers census, project, and collaborator enumerator references from every live source adapter
  at runtime;
- validates exact, shell-free argv digests and never executes through a shell;
- supplies only a bounded privacy-safe context on standard input;
- drains stdout and stderr incrementally, kills the process group at the declared timeout or
  combined-output ceiling, and emits no raw stderr;
- validates source kind, frozen boundary, strict fragment schemas, and privacy-safe fields;
- requires a custody receipt before any enumerator marked as sealed may run;
- independently derives source instances from census fragments and merges project/collaborator
  fragments only for exact census-bound instances;
- turns missing, failed, wrong-kind, over-limit, timed-out, or privacy-invalid adapters into
  explicit missing/failed references and deterministic placeholder source debt;
- caches only successful exact-input receipts and reuses them without rerunning commands; and
- emits a source census, per-instance observations, and a compact run receipt consumable by S8.

The source contract now carries an independent `census_enumerator_ref` for all 11 tracked source
kinds. The tracked executable registry is intentionally empty, so current live truth is explicit:
33 missing enumerators, 11 placeholder source instances, zero observations, and no false
completeness.

Evidence on the packet state:

- focused adapter, freezer, audit, and manifest tests — `32 passed`;
- focused `ruff format`, `ruff check`, JSON parse, schema generation, executable wrapper mode, and
  diff hygiene — passed;
- `bash scripts/verify-scoped.sh` — passed:
  - Python: `4280 passed, 2 skipped`;
  - API: `45 passed`;
  - generated surface and contract-schema validation: passed;
  - Next.js production build, TypeScript, static export, and exported-page validation: passed.

The exact-state scoped receipt must not be rerun unchanged.

## Local lifecycle

- S2 through S9 are clean, inactive, exact-HEAD remote-preserved, and removed locally.
- S9's ignored Node, build, and test caches were physically removed with its worktree.
- S10's ignored dependencies and build output are disposable and must be removed with the worktree
  after a successor has a remote capsule receipt.

## Live owner gates

- PR `organvm/limen#1606` remains owner-gated for merge-queue admission; do not rewrite its exact
  green head or wait on non-required checks.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  S10 performed no GitHub mutation and did not refresh credentials.
- Sealed private enumeration remains custody-gated and did not run.
- The career lane remains human-protected and must not be signaled, retuned, reclaimed, or
  retired by this workstream.

## Next admissible packet

Implement the first real, read-only executable adapter family for the curated ORGANVM registry:
its independent census, project, and collaborator enumerators plus exact command registrations.
It must derive identities and lineages from tracked source bytes, classify non-project rows
explicitly, emit no raw personal identities, preserve zero/multi-repository project shapes, and
leave every unsupported or ambiguous row as incomplete source debt. Run the S10 runner to prove
only these exact three references move from missing to successful while the other 30 remain visible.
Do not implement private-overlay enumeration, perform GitHub writes, refresh credentials, merge,
install a runtime, mutate custody, spend, or touch the career lane.
