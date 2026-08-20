# Prima Materia α→Ω universe relay — S6

## Goal and runway

- Goal: bring the complete Prima Materia and ORGANVM universe from α through Ω, with every
  discovered leaf closed by its source-owned predicate and durable receipt.
- Campaign identity: `prima-materia-alpha-omega-universe-v3`.
- Original epoch: `2026-07-28T20:43:09Z` through `2026-07-29T04:43:09Z`.
- This relay does not reset or extend that deadline.

## Exact custody

- Branch: `work/prima-materia-alpha-omega-universe-20260728-s6`.
- Admitted capsule commit: `660ba838afc7fe7edad23398bd35555adb326745`.
- Universe fixed-point packet commit: `edaf9ebb879c3959256d1e2189839662e1c6e790`.
- Capsule receipt SHA-256:
  `8a5aeb2cfd167b8c8570ebe9e539123bdbc48d6b4c70453b517585a05f1f26b0`.

## Completed predicate

The S6 packet adds the separate universe fixed-point rung registry without changing or replacing
the original 13 λ predicates. Its six rungs cover:

- source coverage;
- canonical project coverage;
- all canonical project builds;
- collaborator reconciliation;
- privacy-safe projection;
- idempotent GitHub projection.

Each rung binds one frozen-wave digest and one installed-runtime SHA, plus explicit dependencies,
freshness, timeout, and a source-owned receipt path. The evaluator rejects missing, stale,
wrong-predicate, wrong-runtime, and non-PASS receipts and propagates failed dependencies through
the graph.

Evidence on the packet state:

- `PYTHONPATH=cli/src pytest -q cli/tests/test_alpha_omega.py` — `14 passed`;
- focused `ruff format` and `ruff check` — passed;
- JSON parse and `git diff --check` — passed.

The one sanctioned `bash scripts/verify-scoped.sh` run reached `4257 passed, 2 skipped` and
failed only at
`cli/tests/test_workstream_command.py::test_autonomous_jules_workstream_uses_remote_cloud_transport`:
under the loaded xdist run, a deliberately one-second provider timeout returned in 4.38 seconds
against a four-second timing ceiling. The three packet-owned files were not implicated, and the
unchanged broad shard must not be rerun merely for reassurance.

## Local lifecycle

- S4 and S5 were clean, inactive, exact-HEAD remote-preserved, and removed locally.
- Their local branches were deleted; their remote branches remain durable.
- S6 is the only local hot-cache worktree in this campaign lineage.

## Live owner gates

- PR `organvm/limen#1606` remains exact-head green and mergeable but requires its human owner
  to admit the immutable head through the merge queue.
- Runtime installation and installed-SHA attestation remain owner-gated after merge.
- GitHub Projects mutation remains behind the credential scope atom `gh auth refresh -s project`;
  enumeration and local reconciler work remain independently admissible.
- The career lane remains human-protected and must not be signaled, retuned, reclaimed, or
  retired by this workstream.

## Next admissible packet

Implement `scripts/prima-materia-universe-audit.py` as the bounded, read-only producer for these
six predicates. It must load the tracked universe-source registry plus frozen project and
collaborator manifests, bind their canonical digests to the frozen wave and installed runtime,
and fail closed for missing source instances, missing canonical projects, absent build artifacts
or receipts, unresolved collaborator dispositions, private-data projection, and non-idempotent
GitHub plans. Do not perform GitHub writes, merge, install a runtime, mutate custody, spend, send,
or touch the career lane.
