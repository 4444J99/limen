# CI bounded-shard owner plan

Owner: Limen gate registry and CI workflow.

## Observed defect

Exact-head run `29340908636` began at `14:27:18Z` and finished its final verify job at
`14:57:36Z`. The critical path was about 30 minutes because `python` first ran the API/CLI suite,
then `verify-whole.sh` serially repeated that suite, runtime probes, and the web build after their
dedicated jobs had already passed. This is duplicate execution, not a justified integration seam.

## Target form

- Derive named shards from the gate registry and each gate's execution profile.
- Give every shard one owner, predicate, input hash, timeout, finite transient-retry policy, output
  cap, and content-addressed receipt.
- Run independent shards in parallel remotely; let the local orchestrator derive safe concurrency
  from host pressure.
- Make the final job validate shard coverage, hashes, and genuine cross-module seams only. It must
  not rerun a successful child.
- Keep `verify-whole.sh` as a thin compatibility entrypoint over the same shard registry.

## Predicate

1. Every registered gate resolves to exactly one shard and execution profile.
2. A fixture failure identifies one shard without erasing successful shard receipts.
3. Static validation rejects duplicated child commands in the aggregate job.
4. Timeouts, retries, and output bounds come from declared parameters, not workflow literals.
5. Online and offline aggregate passes preserve current coverage and produce byte-identical receipts
   on an unchanged second pass.
6. The receipt reports measured critical-path change; no arbitrary duration target manufactures green.

Receipt target: a focused Limen PR that supersedes this plan and links exact-head CI evidence.
