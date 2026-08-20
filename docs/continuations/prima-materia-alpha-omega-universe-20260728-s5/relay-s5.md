# Prima Materia α→Ω universe relay — S5

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s5`.
- Admitted capsule commit: `734ab2208c60b0e432c23f72d359d43735282751`.
- Universe-source packet commit: `ae2c316d7ff6c4eb08498bb8be8abcb70bbcba7b`.
- Capsule receipt SHA-256:
  `4304d4122635c59fda1431083bbbbf4208fb0c88de3114d956646f8eaa67099f`.
- Generated universe-source schema SHA-256:
  `0d550b92d5f4155957fe40ebadb106b0bdf1ac303a4005c7ac4cff7857f70582`.

## Completed predicate

The S5 packet adds an order-independent `UniverseSourceRegistryV1`, a tracked registry for
the source classes named by the program, a portable generated schema, and tests proving:

- source reorder leaves the canonical registry digest unchanged;
- source addition or removal changes the digest without a code change;
- duplicate adapter identities and duplicate source kinds fail closed;
- every tracked source binds project, collaborator, completeness, and privacy projection
  references.

Evidence on the packet state:

- `PYTHONPATH=cli/src pytest -q cli/tests/test_prima_materia.py` — `15 passed`;
- focused `ruff format --check` and `ruff check` — passed;
- repeated schema generation — byte-identical;
- `git diff --check` — passed.

The one sanctioned `bash scripts/verify-scoped.sh` run reached `4253 passed, 2 skipped` and
failed only at
`cli/tests/test_host_admission.py::test_shell_helper_acquires_refreshes_and_releases_exact_lease`:
the fixture received the inherited live `vitals-shed` signal. The five packet-owned files were
not implicated by that assertion, and the unchanged broad shard must not be rerun merely for
reassurance.

## Live owner gates

- PR `organvm/limen#1606` remains exact-head green and mergeable but requires its human owner
  to admit the immutable head through the merge queue.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  enumeration and local reconciler work remain independently admissible.
- The career lane remains human-protected and must not be signaled, retuned, reclaimed, or
  retired by this workstream.

## Next admissible packet

Implement the provider-neutral universe fixed-point rung registry that binds each universe
predicate to dependencies, freshness, timeout, frozen-wave digest, and receipt. Its predicate
must reject arbitrary booleans, stale receipts, incomplete source censuses, and wrong installed
runtime SHAs. Keep GitHub writes, merge, runtime installation, destructive custody actions,
paid spend, and public sends outside the packet.
