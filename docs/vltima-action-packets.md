# VLTIMA Action Packets

Generated: `2026-07-06T16:54:15+00:00`

## Canonical Decision

- Result doctrine does not dispatch directly.
- A packet is only a bounded candidate with owner, scope, verification, and receipt target.
- v1 never mutates `tasks.yaml`; enqueue remains a future explicit gate.

## Coverage

- Source claims: `434`.
- Candidate claims: `421`.
- Packets emitted: `40`.
- Mutation levels: `review_only` 40.
- Truncated: `True`.

## Packets

| Packet | Owner | Mutation | Subject | Next | Verify |
|---|---|---|---|---|---|
| `VLTIMA-PACKET-001-local-pressure-bytes` | `limen:priority-routing` | `review_only` | `local_pressure_bytes` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-002-object-bytes` | `limen:session-corpus` | `review_only` | `object_bytes` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-003-bytes` | `limen:capability-substrate` | `review_only` | `bytes` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-004-units` | `limen:session-corpus` | `review_only` | `units` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-005-units` | `limen:session-corpus` | `review_only` | `units` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-006-private-object-count` | `limen:session-corpus` | `review_only` | `private_object_count` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-007-unique-hashes` | `limen:session-corpus` | `review_only` | `unique_hashes` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-008-clusters` | `limen:session-corpus` | `review_only` | `clusters` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-009-clusters` | `limen:session-corpus` | `review_only` | `clusters` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-010-prompt-events` | `limen:priority-routing` | `review_only` | `prompt_events` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-011-direct` | `limen:prompt-lifecycle` | `review_only` | `direct` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-012-claude-projects` | `limen:prompt-lifecycle` | `review_only` | `claude-projects` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-013-prompt-units` | `limen:priority-routing` | `review_only` | `prompt_units` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-014-scanned-files` | `limen:capability-substrate` | `review_only` | `scanned_files` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-015-insertions` | `limen:priority-routing` | `review_only` | `insertions` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-016-prompt-events-recorded` | `limen:priority-routing` | `review_only` | `prompt_events_recorded` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-017-unique-prompt-hash-refs-recorded` | `limen:priority-routing` | `review_only` | `unique_prompt_hash_refs_recorded` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-018-claim` | `limen:session-corpus` | `review_only` | `.` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-019-sessions` | `limen:prompt-lifecycle` | `review_only` | `sessions` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-020-prompt-files` | `limen:priority-routing` | `review_only` | `prompt_files` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-021-local-files` | `limen:session-corpus` | `review_only` | `local_files` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-022-object-count` | `limen:session-corpus` | `review_only` | `object_count` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-023-products` | `limen:product-surface` | `review_only` | `products` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-024-codex-sessions` | `limen:prompt-lifecycle` | `review_only` | `codex-sessions` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-025-session-items` | `limen:priority-routing` | `review_only` | `session_items` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-026-claude-projects` | `limen:session-corpus` | `review_only` | `claude-projects` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-027-claude-file-history` | `limen:session-corpus` | `review_only` | `claude-file-history` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-028-sessions-indexed` | `limen:session-corpus` | `review_only` | `sessions_indexed` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-029-deletions` | `limen:priority-routing` | `review_only` | `deletions` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-030-sessions` | `limen:session-corpus` | `review_only` | `sessions` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-031-volumes-archive4t` | `limen:session-corpus` | `review_only` | `/Volumes/Archive4T` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-032-unknown` | `limen:session-corpus` | `review_only` | `unknown` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-033-workspace-limen--claude-worktrees-rippling-launc` | `limen:session-corpus` | `review_only` | `~/Workspace/limen/.claude/worktrees/rippling-launching-trinket` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-034-code` | `limen:session-corpus` | `review_only` | `code` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-035-docs` | `limen:session-corpus` | `review_only` | `docs` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-036-flame-scaffold` | `limen:prompt-lifecycle` | `review_only` | `flame_scaffold` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-037-sessions-without-changed-refs` | `limen:session-corpus` | `review_only` | `sessions_without_changed_refs` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-038-flame-with-task-body` | `limen:prompt-lifecycle` | `review_only` | `flame_with_task_body` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-039-volumes-archive4t` | `limen:session-corpus` | `review_only` | `/Volumes/Archive4T` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |
| `VLTIMA-PACKET-040-workspace-limen--claude-worktrees-fluttering-wan` | `limen:session-corpus` | `review_only` | `~/Workspace/limen/.claude/worktrees/fluttering-wandering-wilkes` | review current doctrine and choose the smallest bounded next action | `python3 scripts/vltima-organ.py --check` |

## Contract

- `candidate` is not `queued`.
- `human_gated` packets require a separate explicit approval path before mutation.
- Every packet must preserve its receipt target and verification command if later converted into a task.
