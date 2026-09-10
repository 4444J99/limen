# Prompt Packet Ledger

Generated: `2026-09-10T23:39:29+00:00`

## Canonical Decision

- Packets are bounded owner/task units derived from redacted batch/session hashes.
- Packetization is not dispatch by itself; a packet needs an owner repo or owner ledger, a narrow predicate, no secret dependency, and an expected receipt before external delegation.
- Stalled-review packets default to a Codex conductor: Codex owns judgment and integration, while broad redacted sweeps should be delegated to cheaper explorer lanes whenever scope is bounded.
- This ledger contains no raw prompt or session text.

## Coverage

- Source review batches: `0`.
- Batches needing packetization: `0`.
- Packets emitted: `0`.
- Recorded packets: `0`.
- Open packets: `0`.
- Session receipts packetized: `0`.
- Prompt events packetized: `0`.
- Unique prompt hash refs in packets: `0`.
- Packet resolution receipts: `9`.
- Packet status mix: none.
- Dispatchability mix: none.
- Family mix: none.

## Recorded Packets

| Rank | Packet | Status | Family | Sessions | Events | Root Evidence | Gate |
|---:|---|---|---|---:|---:|---|---|
| 0 | none | n/a | n/a | 0 | 0 | none | n/a |

## Packet Queue

| Rank | Packet | Source Batch | Family | Dispatch Gate | Sessions | Events | Worktrees | Agent Fit | Predicate |
|---:|---|---|---|---|---:|---:|---|---|---|
| 0 | none | n/a | n/a | n/a | 0 | 0 | none | n/a | n/a |

## Packet Routes

| Packet | Owner | Route |
|---|---|---|
| none | n/a | n/a |

## Private Output

- Prompt packet private index: `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/.limen-private/session-corpus/lifecycle/prompt-packet-ledger.json`.
- The private index keeps packet membership, prompt hashes, session keys, worktree slugs, and attack-path evidence; it contains no prompt text.
- Public packet resolution receipts: `docs/prompt-packet-resolution-receipts.json`.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-priority-map.py --write`
- Refresh this packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-packet-ledger.py --write --limit 60`
