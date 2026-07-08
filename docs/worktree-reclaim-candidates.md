# Worktree Reclaim Candidates

Generated: `2026-07-08T05:47:05Z`

This is a candidate packet, not acceptance. It does not write
`docs/worktree-reclaim-acceptance.jsonl` and it does not delete roots.

## Summary

- Scanned roots: `962`
- Debt roots: `292`
- Clean merged idle roots available: `542`
- Candidate roots in this packet: `50`
- Measured candidate size: `8.1 GiB`

## Authority Gate

- Decision: `allowed-candidate-packet-only`
- Repo in value tier: `true`
- Prompt family: `worktree_lifecycle` score `32`
- Candidate lane: `codex-conductor`
- Delete gate: `human-acceptance-then-reclaim-worktrees`

Authority sources: `value-repos.json`, `cli/src/limen/census.py`, `cli/src/limen/capacity.py`, `cli/src/limen/model_selection.py`, `scripts/score-dispatch.py`, `scripts/session-attack-paths.py`, `scripts/reclaim-worktrees.py`, `docs/worktree-reclaim-acceptance.md`

## Acceptance Flow

1. Review the roots below.
2. Copy only the explicitly accepted JSON objects into `docs/worktree-reclaim-acceptance.jsonl`.
3. Replace `<ISO-8601-UTC>` with the current UTC timestamp.
4. Run `python3 scripts/reclaim-worktrees.py --apply --force`.

## Candidates

### 1. `heal-cifix-organvm-universal-mail--automation-118-9f686157`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-universal-mail--automation-118-9f686157`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `529.3 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-universal-mail--automation-118-9f686157", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-universal-mail--automation-118-9f686157"}
```

### 2. `heal-cifix-organvm-the-invisible-ledger-39-50be9f89`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-the-invisible-ledger-39-50be9f89`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `465.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-the-invisible-ledger-39-50be9f89", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-the-invisible-ledger-39-50be9f89"}
```

### 3. `heal-cifix-organvm-a-i-council--coliseum-177-f2be6be4`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-a-i-council--coliseum-177-f2be6be4`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `331.5 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-a-i-council--coliseum-177-f2be6be4", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-a-i-council--coliseum-177-f2be6be4"}
```

### 4. `heal-rebase-organvm-organvm-corpvs-testamentvm-505-390d3afa`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-505-390d3afa`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-505-390d3afa", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-505-390d3afa"}
```

### 5. `heal-rebase-organvm-organvm-corpvs-testamentvm-498-b4cabe27`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-b4cabe27`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-b4cabe27", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-498-b4cabe27"}
```

### 6. `heal-rebase-organvm-organvm-corpvs-testamentvm-498-1faa3da6`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-1faa3da6`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-1faa3da6", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-498-1faa3da6"}
```

### 7. `heal-rebase-organvm-organvm-corpvs-testamentvm-496-e5e1e40a`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-496-e5e1e40a`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-496-e5e1e40a", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-496-e5e1e40a"}
```

### 8. `heal-rebase-organvm-organvm-corpvs-testamentvm-495-4bffd30d`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-495-4bffd30d`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-495-4bffd30d", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-495-4bffd30d"}
```

### 9. `heal-rebase-organvm-organvm-corpvs-testamentvm-491-26e2f5c1`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-491-26e2f5c1`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-491-26e2f5c1", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-491-26e2f5c1"}
```

### 10. `heal-rebase-organvm-organvm-corpvs-testamentvm-505-6d713222`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-505-6d713222`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-505-6d713222", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-505-6d713222"}
```

### 11. `heal-rebase-organvm-organvm-corpvs-testamentvm-505-26644982`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-505-26644982`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-505-26644982", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-505-26644982"}
```

### 12. `heal-rebase-organvm-organvm-corpvs-testamentvm-498-7bc25e20`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-7bc25e20`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-7bc25e20", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-498-7bc25e20"}
```

### 13. `heal-rebase-organvm-organvm-corpvs-testamentvm-498-1b9a3103`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-1b9a3103`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-498-1b9a3103", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-498-1b9a3103"}
```

### 14. `heal-rebase-organvm-organvm-corpvs-testamentvm-496-621fc169`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-496-621fc169`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-496-621fc169", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-496-621fc169"}
```

### 15. `heal-rebase-organvm-organvm-corpvs-testamentvm-495-e5ab1421`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-495-e5ab1421`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-495-e5ab1421", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-495-e5ab1421"}
```

### 16. `heal-rebase-organvm-organvm-corpvs-testamentvm-495-51e4073a`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-495-51e4073a`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-495-51e4073a", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-495-51e4073a"}
```

### 17. `heal-rebase-organvm-organvm-corpvs-testamentvm-491-c89c6254`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-491-c89c6254`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-491-c89c6254", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-491-c89c6254"}
```

### 18. `heal-rebase-organvm-organvm-corpvs-testamentvm-491-80282be3`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-491-80282be3`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `174.8 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-organvm-corpvs-testamentvm-491-80282be3", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-organvm-corpvs-testamentvm-491-80282be3"}
```

### 19. `heal-rebase-organvm-peer-audited--behavioral-blockchain-757-62982f1d`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-757-62982f1d`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-757-62982f1d", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-757-62982f1d"}
```

### 20. `heal-rebase-organvm-peer-audited--behavioral-blockchain-728-6a6303e6`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-728-6a6303e6`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-728-6a6303e6", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-728-6a6303e6"}
```

### 21. `heal-rebase-organvm-peer-audited--behavioral-blockchain-728-5dc1e570`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-728-5dc1e570`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-728-5dc1e570", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-728-5dc1e570"}
```

### 22. `heal-rebase-organvm-peer-audited--behavioral-blockchain-728-43bb34fa`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-728-43bb34fa`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-728-43bb34fa", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-728-43bb34fa"}
```

### 23. `heal-rebase-organvm-peer-audited--behavioral-blockchain-726-b65d6cfc`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-726-b65d6cfc`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-726-b65d6cfc", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-726-b65d6cfc"}
```

### 24. `heal-rebase-organvm-peer-audited--behavioral-blockchain-713-a265ed3f`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-a265ed3f`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-a265ed3f", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-713-a265ed3f"}
```

### 25. `heal-rebase-organvm-peer-audited--behavioral-blockchain-713-9797c829`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-9797c829`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-9797c829", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-713-9797c829"}
```

### 26. `heal-rebase-organvm-peer-audited--behavioral-blockchain-713-740e0af7`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-740e0af7`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-740e0af7", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-713-740e0af7"}
```

### 27. `heal-rebase-organvm-peer-audited--behavioral-blockchain-713-19a68f18`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-19a68f18`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-19a68f18", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-713-19a68f18"}
```

### 28. `heal-rebase-organvm-peer-audited--behavioral-blockchain-713-08cbe1c8`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-08cbe1c8`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-rebase-organvm-peer-audited--behavioral-blockchain-713-08cbe1c8", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-rebase-organvm-peer-audited--behavioral-blockchain-713-08cbe1c8"}
```

### 29. `heal-cifix-organvm-peer-audited--behavioral-blockchain-771-0433512f`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-peer-audited--behavioral-blockchain-771-0433512f`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `148.9 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-peer-audited--behavioral-blockchain-771-0433512f", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-peer-audited--behavioral-blockchain-771-0433512f"}
```

### 30. `heal-cifix-organvm-domus-genoma-132-9e2ce2a0`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-132-9e2ce2a0`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `128.0 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-132-9e2ce2a0", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-132-9e2ce2a0"}
```

### 31. `heal-cifix-organvm-domus-genoma-120-f5bb6297`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-120-f5bb6297`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-120-f5bb6297", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-120-f5bb6297"}
```

### 32. `heal-cifix-organvm-domus-genoma-109-83be4de7`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-109-83be4de7`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-109-83be4de7", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-109-83be4de7"}
```

### 33. `heal-cifix-organvm-domus-genoma-136-e500adaf`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-136-e500adaf`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-136-e500adaf", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-136-e500adaf"}
```

### 34. `heal-cifix-organvm-domus-genoma-118-46a5ada9`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-118-46a5ada9`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-118-46a5ada9", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-118-46a5ada9"}
```

### 35. `heal-cifix-organvm-domus-genoma-159-97fee589`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-159-97fee589`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-159-97fee589", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-159-97fee589"}
```

### 36. `heal-cifix-organvm-domus-genoma-159-2cfdfff6`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-159-2cfdfff6`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-159-2cfdfff6", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-159-2cfdfff6"}
```

### 37. `heal-cifix-organvm-domus-genoma-157-2ae8f227`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-157-2ae8f227`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-157-2ae8f227", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-157-2ae8f227"}
```

### 38. `heal-cifix-organvm-domus-genoma-157-088ea9fb`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-157-088ea9fb`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-157-088ea9fb", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-157-088ea9fb"}
```

### 39. `heal-cifix-organvm-domus-genoma-155-83292900`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-155-83292900`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-155-83292900", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-155-83292900"}
```

### 40. `heal-cifix-organvm-domus-genoma-154-0d80d55c`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-154-0d80d55c`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-154-0d80d55c", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-154-0d80d55c"}
```

### 41. `heal-cifix-organvm-domus-genoma-154-0d7fe61f`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-154-0d7fe61f`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-154-0d7fe61f", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-154-0d7fe61f"}
```

### 42. `heal-cifix-organvm-domus-genoma-153-eb2b9ba6`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-153-eb2b9ba6`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-153-eb2b9ba6", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-153-eb2b9ba6"}
```

### 43. `heal-cifix-organvm-domus-genoma-153-451788bb`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-153-451788bb`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-153-451788bb", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-153-451788bb"}
```

### 44. `heal-cifix-organvm-domus-genoma-152-d3af5bd7`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-152-d3af5bd7`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-152-d3af5bd7", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-152-d3af5bd7"}
```

### 45. `heal-cifix-organvm-domus-genoma-150-7af8143e`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-150-7af8143e`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-150-7af8143e", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-150-7af8143e"}
```

### 46. `heal-cifix-organvm-domus-genoma-149-da30531a`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-da30531a`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-da30531a", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-149-da30531a"}
```

### 47. `heal-cifix-organvm-domus-genoma-149-d5e7f4d5`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-d5e7f4d5`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-d5e7f4d5", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-149-d5e7f4d5"}
```

### 48. `heal-cifix-organvm-domus-genoma-149-b73c4ce9`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-b73c4ce9`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-b73c4ce9", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-149-b73c4ce9"}
```

### 49. `heal-cifix-organvm-domus-genoma-149-9f9060b8`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-9f9060b8`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-9f9060b8", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-149-9f9060b8"}
```

### 50. `heal-cifix-organvm-domus-genoma-149-762c5b71`

- Path: `/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-762c5b71`
- Action: `remove-worktree`
- Reason: `clean+merged+idle`
- Size: `127.4 MiB`

Acceptance event template:

```json
{"accepted": true, "accepted_at": "<ISO-8601-UTC>", "action": "remove-worktree", "archive_proof": "worktree debt classified this root clean+merged+idle; HEAD/content is already merged into the remote/default lifecycle", "archive_status": "not_required_clean_merged_remote", "path": "/Users/4jp/Workspace/.limen-worktrees/heal-cifix-organvm-domus-genoma-149-762c5b71", "reason": "clean+merged+idle", "redaction_proof": "local removal deletes only a clean merged root; no dirty, untracked, private-only, or generated payload remains outside the documented remote/default lifecycle", "redaction_review": "not_required_remote_only", "root": "heal-cifix-organvm-domus-genoma-149-762c5b71"}
```
