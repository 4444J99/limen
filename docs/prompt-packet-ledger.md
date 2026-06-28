# Prompt Packet Ledger

Generated: `2026-06-28T03:03:57+00:00`

## Canonical Decision

- Packets are bounded owner/task units derived from redacted batch/session hashes.
- Packetization is not dispatch by itself; a packet needs an owner repo or owner ledger, a narrow predicate, no secret dependency, and an expected receipt before external delegation.
- Stalled-review packets default to Codex because they require lifecycle judgment before cheaper lanes can safely execute.
- This ledger contains no raw prompt or session text.

## Coverage

- Source review batches: `153`.
- Batches needing packetization: `3`.
- Packets emitted: `8`.
- Recorded packets: `1`.
- Open packets: `7`.
- Session receipts packetized: `58`.
- Prompt events packetized: `252`.
- Unique prompt hash refs in packets: `158`.
- Packet resolution receipts: `1`.
- Packet status mix: `packetized` 7, `owner-recorded` 1.
- Dispatchability mix: `codex-owner-packet` 4, `needs-owner-repo` 3, `recorded-owner-receipt` 1.
- Family mix: `session_lifecycle` 3, `worktree_lifecycle` 1, `github_review` 1, `agent_coordination` 1, `technical_debt_ci` 1, `uncategorized` 1.

## Recorded Packets

| Rank | Packet | Status | Family | Sessions | Events | Root Evidence | Gate |
|---:|---|---|---|---:|---:|---|---|
| 1 | `packet-prompt-batch-critical-stalled-review-001-worktree_lifecycle` | `owner-recorded` | `worktree_lifecycle` | 14 | 60 | `historical_absent_reference` 13, `remote_pr_preserved` 1 | No broad worktree cleanup or delegation remains for this packet. Rehydrate a root only if a later owner-repo review explicitly names the repo, branch, predicate, and expected receipt. |

## Packet Queue

| Rank | Packet | Source Batch | Family | Dispatch Gate | Sessions | Events | Worktrees | Agent Fit | Predicate |
|---:|---|---|---|---|---:|---:|---|---|---|
| 1 | `packet-prompt-batch-critical-stalled-review-001-session_lifecycle` | `prompt-batch-critical-stalled-review-001` | `session_lifecycle` | `codex-owner-packet` | 11 | 48 | `bld2-peer-audited--behavioral-blockchain-integration-tests-c82f`, `cifix-organvm-i-theoria-conversation-corpus-engine-2e73`, `rev-styx-stripe-subscription-719b`, `bld-peer-audited--behavioral-blockchain-ci-706e`, `resolve-a-organvm-peer-audited--behavioral-blockchain-714-6648` | codex | `python3 scripts/prompt-priority-map.py --write && python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write` |
| 2 | `packet-prompt-batch-critical-stalled-review-002-session_lifecycle` | `prompt-batch-critical-stalled-review-002` | `session_lifecycle` | `codex-owner-packet` | 5 | 19 | `limen-084-8712`, `limen-054`, `gh-a-organvm-organvm-corpvs-testamentvm-494-0388`, `gh-4444j99-domus-genoma-86-8188`, `cifix-a-organvm-peer-audited--behavioral-blockchain-6f84` | codex | `python3 scripts/prompt-priority-map.py --write && python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write` |
| 3 | `packet-prompt-batch-critical-stalled-review-002-github_review` | `prompt-batch-critical-stalled-review-002` | `github_review` | `needs-owner-repo` | 12 | 58 | `bld-card-trade-social-harden-b07b`, `bld2-mirror-mirror-dashboard-0ba3`, `bld-public-record-data-scrapper-readme-345a`, `bld2-the-invisible-ledger-integration-tests-015e`, `bld2-public-record-data-scrapper-dashboard-90d1` | codex packetization, then opencode/jules only after repo and PR are explicit | `python3 scripts/session-attack-paths.py --write && python3 scripts/prompt-packet-ledger.py --write` |
| 4 | `packet-prompt-batch-high-stalled-review-001-agent_coordination` | `prompt-batch-high-stalled-review-001` | `agent_coordination` | `codex-owner-packet` | 9 | 35 | `bld2-my--father-mother-billing-1c41`, `rev-avditor-premium-tier-0af4`, `bld-edgarflash-harden-c3c1`, `rev-mediaark-readme-pro-a6c1`, `limen-004` | codex | `python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write` |
| 5 | `packet-prompt-batch-high-stalled-review-001-session_lifecycle` | `prompt-batch-high-stalled-review-001` | `session_lifecycle` | `codex-owner-packet` | 2 | 9 | none | codex | `python3 scripts/prompt-priority-map.py --write && python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write` |
| 6 | `packet-prompt-batch-high-stalled-review-001-technical_debt_ci` | `prompt-batch-high-stalled-review-001` | `technical_debt_ci` | `needs-owner-repo` | 3 | 13 | `bld-essay-pipeline-readme-94ce`, `bld-media-ark-tests-2698`, `bld-media-ark-tests-795d` | codex packetization, then opencode/jules after repo and predicate are explicit | `python3 scripts/prompt-packet-ledger.py --write` |
| 7 | `packet-prompt-batch-high-stalled-review-001-uncategorized` | `prompt-batch-high-stalled-review-001` | `uncategorized` | `needs-owner-repo` | 2 | 10 | none | codex | `python3 scripts/prompt-priority-map.py --write && python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-packet-ledger.py --write` |

## Packet Routes

| Packet | Owner | Route |
|---|---|---|
| `packet-prompt-batch-critical-stalled-review-001-session_lifecycle` | session lifecycle | Collapse stalled session receipts into owner records, supersession notes, or blocker receipts before delegation. |
| `packet-prompt-batch-critical-stalled-review-002-session_lifecycle` | session lifecycle | Collapse stalled session receipts into owner records, supersession notes, or blocker receipts before delegation. |
| `packet-prompt-batch-critical-stalled-review-002-github_review` | github review | Map each stalled GitHub-review receipt to an owner repo, PR/issue receipt, predicate, and merge/supersession gate. |
| `packet-prompt-batch-high-stalled-review-001-agent_coordination` | agent coordination | Convert broad coordination residue into bounded packets; do not dispatch broad sprawl prompts. |
| `packet-prompt-batch-high-stalled-review-001-session_lifecycle` | session lifecycle | Collapse stalled session receipts into owner records, supersession notes, or blocker receipts before delegation. |
| `packet-prompt-batch-high-stalled-review-001-technical_debt_ci` | technical debt / CI | Route CI/debt receipts to an owner repo and narrow predicate before any dispatch. |
| `packet-prompt-batch-high-stalled-review-001-uncategorized` | unassigned corpus review | Privately classify the receipt, then re-run priority and batch ledgers with an owner route. |

## Private Output

- Prompt packet private index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-packet-ledger.json`.
- The private index keeps packet membership, prompt hashes, session keys, worktree slugs, and attack-path evidence; it contains no prompt text.
- Public packet resolution receipts: `docs/prompt-packet-resolution-receipts.json`.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-priority-map.py --write`
- Refresh this packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-packet-ledger.py --write --limit 60`
