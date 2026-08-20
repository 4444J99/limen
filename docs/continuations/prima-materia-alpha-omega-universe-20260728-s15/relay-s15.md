# Prima Materia α→Ω universe relay — S15

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s15`.
- Admitted capsule commit: `1bda6ec84718a25c37264364ac036d85915abdfc`.
- GitHub-estate adapter packet commit: `cea5ca46f892b7fd74c14a1c06eb4c9c6da4426e`.
- Capsule receipt SHA-256:
  `db6420f3b6194a3cab19ca7da463950e15d1a384a50a9cdc9c10b23f424c3aae`.

## Completed predicate

The S15 packet replaces the GitHub-estate placeholder with a read-only executable adapter over one
frozen, privacy-safe live snapshot.

The packet:

- enumerates every repository returned by the live `organvm` organization API and scans both
  outside-collaborator and pending-invitation surfaces for every repository;
- bounds pagination output, repository count, worker concurrency, execution time, and persisted
  output;
- hashes repository names and GitHub logins before persistence, and stores no raw repository name,
  account name, or owner handle in the snapshot;
- keeps live access level and pending versus active status without inferring relationship role,
  project membership, access authority, or canonical-project identity;
- treats an empty or unavailable repository census, any repository access read failure, an unknown
  access role, invalid rows, duplicate/conflicting rows, or source drift as explicit opaque debt;
- queries user ProjectsV2 independently, records missing Project scope as one opaque debt atom, and
  retains item/member enumeration as visible implementation debt even when scope is available;
- binds the complete redacted snapshot to a canonical SHA-256 read receipt;
- rejects a snapshot newer than the frozen wave; and
- registers census, project, and collaborator enumerators whose cache keys bind the code, wrapper,
  desired-state owner, and exact snapshot bytes.

Live snapshot truth at `2026-07-29T00:34:00.940275Z`:

- repositories: `308`, repository enumeration complete;
- access rows: `4`, repository-level collaborator enumeration complete;
- Project rows: `0`;
- Project scope available: `false`;
- Project enumeration complete: `false`;
- explicit debt rows: `1`;
- GitHub read receipt SHA-256:
  `3b34c6c4967fb5fe96fcaf281dd7575bc50f8c1bb17b7e13b77e95822cf66fb1`.

The prior observation of three current grants was therefore a lower bound, not the collaborator or
access denominator. S15 performed no GitHub mutation, sent no invitation, removed no access, and
refreshed no credential.

The tracked end-to-end runner now reports 15 executed enumerators, 18 missing enumerators,
6 placeholder source instances, 9 observations, and zero adapter failures. Its three GitHub
observations retain 313 unclassified repository, access, or Project/debt rows. The overall exit
remains nonzero because whole-universe enumeration is incomplete.

Evidence on the packet state:

- focused GitHub-estate and adapter-runner tests — `17 passed`;
- Ruff format and lint — passed;
- tracked snapshot and enumerator-registry model validation — passed;
- tracked executable runner — 15 executed, 18 missing, 6 placeholders, 9 observations, 0 failed;
- `scripts/verify-scoped.sh`:
  - all non-Python implicated gates passed;
  - Python completed with `4304 passed, 2 skipped` and one unrelated timing failure in
    `test_autonomous_jules_workstream_uses_remote_cloud_transport` because a one-second timeout
    returned in 4.07 seconds against a four-second wall bound;
  - that exact failed predicate was rerun alone and passed in 13.96 seconds total;
  - no S15 test failed.

## Local lifecycle

- S2 through S14 are clean, inactive, exact-HEAD remote-preserved, and removed locally.
- Their ignored dependency, build, and test caches were physically removed with their worktrees.
- S15 remains the sole local Prima Materia successor until the next capsule is admitted and
  remote-preserved; then S15 and its disposable caches must be removed.
- The separate laptop-wide recovery S18 lineage and the career lane are untouched.

## Recalibration boundary

The human explicitly asked whether the campaign remains useful or should refresh. Do not discard the
verified S2–S15 lineage or restart from scratch. The next packet is a live root-level recalibration,
not an automatically selected sixteenth adapter:

1. re-read the exact remote and installed state for α, including PR `organvm/limen#1606`, merge
   status, required receipts, installed runtime SHA, and retained owner gates;
2. refresh custody, two-device restore, repository/storage wave, safe-reclaim, and protected-blocker
   predicates without performing destructive work;
3. run the current source-registry, executable-adapter, universe-freezer, λ-rung, and
   universe-fixed-point audits from their durable receipts;
4. measure remaining campaign runway and distinguish genuinely completed predicates from adapter
   throughput; and
5. route the next bounded packet to the highest-leverage live open gate.

The recalibration must produce a durable predicate matrix and an explicit continue, redirect, or
finite-epoch-close decision. Adapter count alone is not progress toward α, custody, reconstruction,
all-project builds, λ, or Ω.

## Retained prohibitions

Do not merge, install a runtime, refresh credentials, mutate GitHub, perform custody/reclaim writes,
spend, send publicly, or touch the career or recovery-S18 lanes without their retained owner gates.
Progress-report email to the authenticated account is explicitly authorized after each remotely
durable work chunk.
