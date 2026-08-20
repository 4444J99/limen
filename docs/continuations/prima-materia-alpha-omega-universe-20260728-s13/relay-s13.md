# Prima Materia α→Ω universe relay — S13

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s13`.
- Admitted capsule commit: `3436562a9215538c69bb6c0f1e386abdca18176d`.
- Engagement-ledger adapter packet commit: `b5d1e334e117a6ce1bd5bc0bc7c4d846fceb0a31`.
- Capsule receipt SHA-256:
  `08edae52a0218d5d1ba7067211a59c936bd2a8cf798073eb17b06da54dad2869`.

## Completed predicate

The S13 packet implements the read-only executable universe adapter family for the tracked AUG1
engagement ledger.

The adapter family:

- independently registers exact census, project, and collaborator commands whose cache inputs bind
  the tracked implementation, wrapper, and source bytes;
- classifies the current empty engagement list as zero project rows and zero collaborator rows
  rather than confusing the ledger's documentation field with either universe;
- retains the documentation field as one explicit non-project row;
- treats every future engagement row as opaque unclassified debt until a source-owned row schema is
  registered, instead of inventing project, person, access, or lifecycle semantics;
- makes duplicate-row classification order-independent while retaining the duplicate count in the
  opaque identity;
- forbids a source observation from claiming completeness while any unclassified row remains; and
- propagates sorted, unique unclassified row identities through project and collaborator fragments,
  the end-to-end runner, and the universe freezer.

The tracked end-to-end runner now executes all nine curated-registry, constellation, and engagement
references. Current whole-registry truth is 24 missing enumerators, 8 placeholder source instances,
3 complete source observations, and zero adapter failures. The engagement observation contains
0 projects, 0 collaborators, 1 non-project row, and 0 unclassified rows. The overall runner still
exits nonzero because whole-universe enumeration is incomplete.

Evidence on the packet state:

- focused engagement, adapter-runner, freezer, constellation, and curated-registry tests —
  `25 passed`;
- tracked executable runner — 9 executed, 24 missing, 8 placeholders, 3 observations, 0 failed;
- `scripts/verify-scoped.sh` — passed:
  - Python: `4293 passed, 2 skipped`;
  - API: `45 passed`;
  - generated surface and contract-schema validation: passed;
  - Next.js production build, TypeScript, static export, and exported-page validation: passed.

The exact-state scoped receipt must not be rerun unchanged.

## Host admission correction

At the S12→S13 boundary, the public host-admission release command returned an allowed response
while retaining the S12 lease, briefly leaving S12 and S13 workspace leases owned by the same
protected PID and process identity. The stale S12 lease was released through the controller's exact
kind, owner, and PID interface; live status then contained only the S13 lease. Future rotations must
resolve the live lease ID/kind and use the exact lower-level release interface, then prove the
outgoing kind is absent before acquiring the successor. Never delete the lease store.

## Local lifecycle

- S2 through S12 are clean, inactive, exact-HEAD remote-preserved, and removed locally.
- S12's ignored Node, build, and test caches were physically removed with its worktree.
- S13's ignored dependencies, generated surfaces, and build output are disposable and must be
  removed with the worktree after a successor has a remote capsule receipt.

## Live owner gates

- PR `organvm/limen#1606` remains owner-gated for merge-queue admission; do not rewrite its exact
  green head or wait on non-required checks.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  S13 performed no GitHub mutation and did not refresh credentials.
- Sealed private enumeration remains custody-gated and did not run.
- The career lane and the separate laptop-wide recovery S18 lineage remain human-protected and must
  not be signaled, retuned, reclaimed, or retired by this workstream.

## Next admissible packet

Implement the read-only executable adapter family for `funnel_records`, but first resolve its real
source-owned instances instead of treating `scripts/conversion-funnel.py` as the record denominator.
The script declares `logs/observatory/traffic.jsonl`, `logs/opportunity-status.json`, and
`logs/profile-conversion-funnel-latest.json`; none is present in this disposable checkout. Derive
whether the canonical record inputs are tracked, remotely queryable, custody-bound, or genuinely
missing, and preserve every missing/unavailable input as visible source debt.

Register independent census, project, and collaborator commands only after their actual inputs and
privacy boundaries are explicit. Funnel metrics, repositories, referrers, inbound classifications,
and documentation must not silently become projects or collaborators. Any record that lacks a
source-owned semantic disposition remains opaque unclassified debt and forces incompleteness.

Do not generate or mutate funnel logs, enumerate the sealed private overlay, perform GitHub writes,
refresh credentials, merge, install a runtime, mutate custody, spend, or touch either protected
lineage.
