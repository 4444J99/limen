# Shared agent OS implementation attempt — 2026-10-12

Requested window: April 12 through October 12, 2026 (local America/New_York dates).
Owners: Limen resource envelopes, host admission, corpus and healing; Domus Genoma managed configuration and launchers. Billing quotas stay provider-specific.

## Changes

1. Limen provides `limen.runtime_pool.v1` using the existing host lock, live resource-envelope reserve, filesystem free bytes and atomic owner/process-bound growth leases. Claims already included in the reserve are subtracted from growth leases before accounting. No fixed vendor allocations. Expired live owners retain capacity; expiry plus verified process death releases it. Release is idempotent. Native unmanaged writes are observational.
2. Domus `domus.agent_runtime.v2` retains complete census and containment; consumption is per-agent, all capacity is shared. Retired environment settings emit migration diagnostics. Launch reserves a 64 MiB managed startup allowance and releases it in `finally`; this does not enforce vendor application writes. A launch lease expires after 30 minutes but remains charged while the launcher lives. Consumers in maintenance and SQLite reclamation accept v2; prior v1 observations remain supported. Limen maintenance intake is aggregate-only for v2, preserving deduplication and custody gates.
3. Claude instructions and PostToolUse import hook are corrected at source. Existing managed templates cannot be overwritten by automatic import of rendered output. New authored plan/memory Markdown remains importable. Application settings, sessions, databases and plugin state are excluded.
4. Existing corpus ledger gains a bounded redacted OS review. Coverage gaps, exact line hashes in the private locator index, chronological corrections and repository-qualified receipt candidates remain distinct from acceptance. Existing substrate pressure monitoring exposes the pool decision and subtracts reservations once.

## Regression and acceptance matrix

| Defect / priority | Owner | Regression | Acceptance |
|---|---|---|---|
| Preservation / highest | Domus | test_domus_codex_reclaim.py and accounting incomplete-census cases | No worker without complete containment/census; verified preserved contents before reclamation |
| Vendor slicing / blocked capability | Limen + Domus | test_runtime_pool.py; test_domus_runtime_accounting.py | One agent above 12 GiB admitted with shared capacity; competing grants cannot oversubscribe |
| Stale or missing resource claims / rollout dependency | Limen | missing-selected-graph and stale-telemetry cases | Fresh machine workload census from owning authority; no invented empty graph |
| Render/source recursion / recurring | Domus | test_claude_source_ownership.py | Reviewed source parity, preserved runtime alias, second apply changes nothing |
| Native visual / blocked capability | Domus + external platform | test_operating_system_evidence.py visual classification | Real permitted native capture plus explicit resolution of target-specific external gates |
| Repeated failures / recurring | Limen | test_operating_system_evidence.py | Inclusive/exclusive boundaries, redaction, deduplication, correction chronology, visible gaps and exact receipt validation |

## Current evidence and limitations

Both dirty/divergent primary histories were preserved. Clean idle worktrees were reused because low-disk policy disallows new worktrees. Limen branch is based on origin/main 8cbed84fb40da5995c61fb01f49e09a9b177acf6. Domus branch is stacked on PR #418, head 4abf6c138b37517a71aedaa3aba67ef629d47547; it must not deploy before the resource owner.

Claude candidate source apply succeeded for exactly CLAUDE.md and hooks/chezmoi-add-after-edit.sh with files-only selection. Its runtime directory symlink remained `Workspace/limen/.agent-runtime/claude/legacy-home`. The candidate-source diff was empty and a second files-only apply succeeded. The default dirty canonical checkout has not been reset or overwritten; accepted-source deployment parity is still a rollout gate.

Native evidence is retained in Codex task 01a13168-8c50-7fb2-a163-8b7fcc79b598. CUA inventory succeeded; Finder returned cgWindowNotFound; TextEdit returned an actual screenshot of its Open panel. Codex returned: Computer Use is not allowed to use the app 'com.openai.codex' for safety reasons. This is a platform safeguard, not a local TCC defect; no bypass is authorized or implemented. Supported DomusAgentHost routing remains intact.

Cached-credential bootstrap succeeded for authenticated conductor capabilities at 2026-10-12T19:06:38Z; deployed keeper git SHA b6231a736d7bd4594eb7b7264f42f4560271d47a, deployment 6e792d6a-f7cf-426a-9a92-09b5ed2a2525. Session metadata is not a complete active storage-claim census. No current `LIMEN_RESOURCE_TASK_GRAPH` was selected for this direct session. The pool correctly denies new growth with ResourceGraphMissing. This prevents safe whole-launcher cutover; do not substitute an empty claim graph.

At 19:13 UTC filesystem free was 31,784,165,376 bytes (29.60 GiB), higher than the supplied 14.37 GiB baseline. This session performed no cache deletion or history retirement; that increase is not attributed to this repair. Managed shared available growth remains unknown until reserve/claim observation passes. Quota arithmetic changes are not physical storage recovery.

The corpus report is bounded and partial. Native Gemini JSON and OpenCode SQLite coverage require existing native adapters; zero observed records is not proof of no failures. Receipt URLs are candidates until exact remote linkage is verified. Complete six-month review, full correction supersession, all-provider coverage, machine census integration, accepted-revision deployment and target-specific visual acceptance remain incomplete. This is a reviewable implementation checkpoint, not full healing.

## Rollout

Land the tested Limen contract first. Supply fresh complete workload claims through the existing admission authority; run live observe/reserve/release and retain measured headroom. Reconcile/land Domus #418 and the stacked consumer branch, then use the exact accepted Limen runtime installer and files-only reviewed Domus targets. Verify immutable revision, all consumers, Claude canonical-source parity and no-change second apply. Complete the corpus/native adapter and exact receipt gaps before claiming six-month acceptance. Preserve all external visual gates explicitly.

## Verification receipt

- Domus: 162 passed across agent runtime, complete accounting, maintenance lifecycle, diagnostic/native subprocess fixtures, SQLite reclamation, substrate check and Claude source ownership.
- Limen: 13 passed across shared reservations, evidence boundaries/redaction/classification, and deduplicated maintenance intake.
- Candidate Claude source parity: empty files-only diff and two successful scoped applies, retaining the parent runtime symlink.
- Limen registry-driven scoped verification: NOT PASSED. Syntax, diff hygiene, test hygiene and docs exports passed. Other selected checks reported missing mypy/pytest/pinned Ruff, parameter-panel YAML parsing, and estate ratchets. Complete diagnostic output is in this task's tool receipt. Those checks were not silently bypassed or represented as baseline passes.
- No aggregate launcher deployment or source merge is certified; branches remain review checkpoints until full rollout predicates pass.
