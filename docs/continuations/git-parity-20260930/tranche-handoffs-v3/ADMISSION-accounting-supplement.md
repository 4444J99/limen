# Native-time reconciliation and keeper admission request

Prepared 2026-09-30T21:47:06Z. Original outcome: Workspace Git parity followed by custody-qualified retirement. Program owner: 4444J99/limen#2739; residency: 4444J99/portvs#14; consumers: 4444J99/domus-genoma#397.

## Reconciled accounting

| Native evidence class | Seconds | Agent-minutes | Interpretation |
|---|---:|---:|---|
| Four matching Codex physical execution records, completed turns | 4213.114 | 70.2186 | Exact task-start/task-complete event pairs, deduplicated by turn identity; active turn excluded |
| Two managed OpenCode S2 sessions | 1137.450 | 18.9575 | Assistant message execution intervals; human idle excluded |
| Five earlier Agy sessions | 623.000 | 10.3833 | Conservative invocation bounds through the last terminal response before each later human input |
| Newly launched Agy handoff session | 240.000 | 4.0000 | Two invocation bounds: 233 seconds and 7 seconds |
| Brief Agy child | 9.000 | 0.1500 | Conservative parent launch-to-stop bound; child completion record unavailable |
| Current Codex turn through this snapshot | 320.176 | 5.3363 | Open execution interval; continues increasing until completion |
| **Accounted total through snapshot** | **6542.740** | **109.0457** | Mixed completed measurements and conservative bounds; incomplete outcome denominator |

The five earlier Agy sessions previously contributed a 1419-second whole-session bound. Removing 796 seconds between final responses and later human inputs lowers that contribution by 13.2667 minutes. This does not remove internal autonomous continuation work. The managed OpenCode database, rather than the stale unmanaged database, supplied the S2 records.

**120 minus this accounted total is 10.9543 minutes before unmatched execution. This is not a spendable allowance.** Earlier stopped inspector streams still lack a complete native-record match. Records copied into forked Codex sessions are not independently charged again merely because they occur in another file; separate branch execution remains charged. Neither daily provider-run counters nor zero keeper leases measure this outcome's cumulative elapsed time.

The original 20:25:33Z cutoff remains an inferred timestamp, not a demonstrated keeper-issued deadline. Exhaustion is not established solely by that cutoff. Admission nevertheless remains absent. The latest authenticated capabilities snapshot at 21:43:21.255Z showed zero active leases and no registered Agy executor. The current protected Codex session is not a recovery lease and must not be adopted.

## Exact request to the authenticated keeper

This is an **unsubmitted admission request specification**, not a WorkPacketV1, lease or new attempt allowance. A schema-valid executable packet cannot be honestly finalized while required lineage, remaining spend and deadline bindings are unresolved.

Request:
1. Resolve the original outcome's canonical work_key, root run, stopped attempt and keeper-issued deadline from retained authenticated records under #2739. Return record identifiers and authoritative timestamps; do not create a replacement outcome to replenish its envelope.
2. Match the remaining stopped inspector executions to native records, including original inspection, consolidation and corrective work. Incorporate the completed current Codex turn and all Agy/OpenCode activity after this snapshot. Return the cumulative total and its uncertainty; unresolved spend is retaining.
3. Determine whether the one changed-input corrective retry remains available. Changed inputs are the five handoffs, rejected S2 classifications and operations, collector defects, and provider-ref boundary defect. Return the keeper decision and original lineage; do not treat prompt publication or a human launch as admission.
4. If eligible, have Agy register its own actual protected native identity using its documented credential bootstrap. Bind that executor to the original outcome. Codex must not register or impersonate Agy, transfer a protected session, or fabricate a historical root run.
5. Issue a WorkPacketV1 with the authenticated original work_key/root_run_id, actual Agy initiator/conductor identity, exact authorized repository/common-directory assignment in its private evidence destination, hard deadline, and remaining cumulative spend. Bound the attempt to the lesser of the actual remaining envelope and 30 minutes. Verification is within that same attempt and at most 10 minutes.
6. Reserve OpenCode's read-only review capacity and independent S5 verification within that envelope before their execution. All participants inherit the same deadline. No reservation is free. If enough capacity cannot be established for removal and verification, narrow the packet to a concrete preservation gap or checkpoint.
7. Validate the packet and return the admission/run/lease identifiers and receipt destination. Only then may Agy execute its writer handoff and supply OpenCode's admitted scoped review packet.

If any binding remains unknown, return the specific missing record and owning action under #2739. Do not silently replace unknowns with zero, a new root, a proposed deadline or an assumed allowance. Do not restart a whole-estate census to resolve accounting.

## Delivery and ownership

Agy's handoff session explicitly paused after the human said it was waiting for a handoff; its brief child was reported stopped. This document completes the requested accounting supplement. The existing AGY-recovery-writer.md and OPENCODE-corrections-review.md remain the substantive tranche instructions. Agy is the sole recovery writer after admission; OpenCode is an admitted read-only reviewer. Codex prepared this supplement without fetching, staging, committing, switching or removing Git state.

No source collector patch, candidate qualification, preservation publication, removal or estate completion is claimed. Raw native transcripts and private repository identities remain local/private; this artifact contains redacted aggregate accounting only.
