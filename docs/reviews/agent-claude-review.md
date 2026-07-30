# Claude Session Review

Generated: `2026-07-04T02:43:00Z`

## Scope

- Input: private full-stack session review for Claude project/task JSONL.
- Prompt bodies remain private under `.limen-private/session-corpus/full-stack-review/`.
- Structured changed-file refs are conservative tool/write/edit paths, often from subagent fanout.

## Coverage

- Claude sessions reviewed: `1276`.
- Prompt events: `115958`.
- Prompt bytes: `247732459`.
- Normalized task-body bytes: `243719645`.
- Structured-change sessions: `448`.
- Structured changed-file refs: `2795`.
- Sessions with no structured changed-file refs: `828`.
- Immediate changed-file review candidates in the queue: `448`.
- Board/log-only sessions in the queue: `0`.
- Reconstruction/no-change sessions in the queue: `826`.

## Changed-File Distribution

| Changed refs per session | Sessions |
|---:|---:|
| 0 | 828 |
| 1 | 133 |
| 2 | 114 |
| 4 | 39 |
| 3 | 38 |
| 6 | 21 |
| 5 | 16 |
| 8 | 14 |
| 10 | 9 |
| 9 | 8 |
| 12 | 6 |

## Top Changed Targets

| Count | Target |
|---:|---|
| 19 | `/Users/4jp/.claude/projects/-Users-4jp-Workspace-limen/memory/MEMORY.md` |
| 3 | `/Users/4jp/.claude/hooks/allow-trusted-cd-git.sh` |
| 2 | `/Users/4jp/.claude/plans/rippling-launching-trinket.md` |
| 2 | `/Users/4jp/Workspace/limen/.claude/worktrees/rippling-launching-trinket/scripts/ingest-backlog.py` |
| 2 | `/Users/4jp/Workspace/limen/docs/PLAN-LONG-AND-WIDE.md` |
| 2 | `/tmp/vh-commit-msg2.txt` |
| 2 | `/Users/4jp/Workspace/limen/scripts/verify-budget-gauge.py` |
| 2 | `/Users/4jp/Workspace/LEMONSQUEEZY-HANDOFF.md` |

## Ideal-Form Gaps

| Gap | Sessions |
|---|---:|
| session outcome lacks verification signal | 511 |
| session outcome lacks durable receipt signal | 400 |
| repeated broad/invariant prompt pressure | 367 |
| failure/blocker language outweighs done language | 362 |
| likely no-op or unrecorded work | 345 |
| prompt missing executable predicate | 149 |
| prompt missing expected receipt/artifact | 126 |

## What Went Wrong

1. Claude carries the largest prompt mass by far. Subagent fanout and invariant scaffolds produced `115958` prompt events and `243719645` normalized task-body bytes, which makes prompt-vs-done review expensive unless packets are sharply scoped.
2. `828/1276` Claude sessions have no structured changed-file refs. Many were planning, broad audit, off-host, or artifact-loss sessions, so closure depends on external receipts.
3. Several high-risk Claude worktrees and temp files were gone during code-diff review. The surviving evidence was often transcript/memory/plan state rather than live code.
4. Claude frequently touched home-state memory, hooks, plans, and `/tmp` artifacts. Those are useful evidence, but they are not substitute implementation receipts.
5. Broad/invariant prompts created false pressure: the model was often asked to preserve or review the whole organism while the actual accept condition was narrow.

## Improvements

1. Keep Claude subagent packets small and require `owner_scope`, `predicate`, `expected_receipt`, and `artifact_preservation` fields.
2. Treat home memory, plan files, and temp files as evidence leads until a repo commit/PR/verification receipt confirms absorption.
3. Preserve per-run worktree deltas or record a named artifact-loss blocker before cleanup.
4. For broad Claude runs, require a manifest of child agents, changed roots, and verification commands before claiming done.
5. Continue using `docs/agent-code-diff-review.md` for line-level Claude review; ranks `1-30` have already produced concrete fixes, rejections, or artifact-loss records.

## Commands

- Refresh full-stack source: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`
- Refresh code-review queue: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write`
- Refresh reconstruction review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-reconstruction-review.py --write`
