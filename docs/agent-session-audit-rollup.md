# Agent Session Audit Roll-Up

Generated: `2026-07-04T02:46:00Z`

## Scope

This is the public redacted entry point for the Codex / Claude / Agy / OpenCode prompt-and-session review.

- Prompt layer: verbatim prompt events are stored privately under `.limen-private/session-corpus/full-stack-review/verbatim-prompts.jsonl`.
- Session layer: redacted session metadata and ideal-form diffs are stored privately under `.limen-private/session-corpus/full-stack-review/agent-session-review.json`.
- Public layer: tracked docs contain counts, hashes/IDs, paths, commits, and findings only.

## Public Artifacts

| Artifact | Purpose |
|---|---|
| `docs/agent-session-full-stack-review.md` | Corpus-wide prompt/session coverage and ideal-form diff rules |
| `docs/agent-code-review-queue.md` | Ranked queue for changed-file, board/log, and reconstruction review |
| `docs/agent-code-diff-review.md` | Line-level code-diff findings, fixes, rejected branches, and artifact-loss records |
| `docs/agent-board-log-review.md` | Task-board-only session review and historical `tasks.yaml` churn findings |
| `docs/agent-reconstruction-review.md` | No-change-ref session reconstruction by root and temporal git windows |
| `docs/agent-agy-antigravity-review.md` | Agy CLI / Antigravity-specific session and provider-surface review |
| `docs/agent-opencode-review.md` | OpenCode SQLite/token/diff surface review |
| `docs/agent-codex-review.md` | Codex session/history review |
| `docs/agent-claude-review.md` | Claude project/subagent fanout review |

## Current Coverage

- Sessions reviewed: `4375`.
- Prompt events extracted: `125919`.
- Unique prompt hashes: `74742`.
- Agents covered: Codex, Claude, Agy/Antigravity CLI, OpenCode.
- Structured changed-file sessions: `1963`.
- Board/log-only sessions: `185`.
- No-change-ref reconstruction sessions: `2398`.
- Code-diff review queue has been worked through changed-file ranks `1-30`, with concrete fixes, rejected stale branches, and report-only artifact-loss records captured in `docs/agent-code-diff-review.md`.

## What Was Fucked Up

1. Prompts often lacked the ideal-form fields: concrete owner scope, executable predicate, expected receipt/artifact, and gate class.
2. Broad/invariant prompt scaffolds inflated work and blurred acceptance. Claude was the worst case by prompt mass; Codex and OpenCode also inherited broad autonomous framing in places.
3. Many sessions had prompt events but no verification signal, no durable receipt, or no changed-file surface. Those cannot be credited as completed implementation without reconstruction.
4. Historical board-only sessions mixed one named completion with broad `tasks.yaml` rewrites, budget-counter shifts, noncanonical `cancelled` statuses, and missing verification phrases.
5. Several high-risk Claude worktrees/temp files were gone by review time. Surviving evidence was transcript/memory/plan state, not always live code.
6. Agy root attribution was weak: most Agy CLI conversation rows had `cwd=None`, and native Antigravity IDE conversation directories were empty on this host.
7. OpenCode has strong SQLite token/diff data, but token spend and summary diffs are not acceptance proof.
8. Codex changed-file refs are conservative tool-path leads. They require git/window verification before they count as landed work.

## Repairs Already Landed From This Audit

- Redaction boundary hardened after raw prompt evidence was exposed in audit metadata.
- Multiple fail-open crash paths fixed in route, dispatch, async dispatch, auto-scale, parallel dispatch, CVSTOS/VVLTVS, social scheduler, IANVA, Moneta, health, workstream, revenue backlog, credential-wall, and related control-plane surfaces.
- Stale/security branches that would delete current control-plane work were explicitly rejected; salvage is limited to reviewed hunks.
- Board/log and reconstruction review generators were added so future audits can refresh without raw prompt publication.
- Agent-specific review docs were added for Agy/Antigravity, OpenCode, Codex, and Claude.

## Operating Improvements

1. Every agent packet should include `owner_scope`, `repo_root`, `allowed_paths`, `predicate`, `expected_receipt`, and `gate_class`.
2. A `done` report should be rejected unless it names a verification command/result plus a durable receipt: commit, PR, artifact, or precise blocker.
3. Board-only work should be treated as governance/accounting unless it links to the implementation receipt being closed.
4. Agy scratch-space work should not count until a bridge receipt ties changed targets into the owner worktree.
5. OpenCode token accounting should remain spend telemetry, separate from acceptance telemetry.
6. Claude subagent fanout needs a child-agent manifest, changed-root manifest, and artifact preservation receipt.
7. Codex changed-file refs should stay as review leads until confirmed against git history or live file state.
8. Missing worktrees and no-change sessions should be recorded as artifact-loss/no-op/blocker lanes instead of silently counted as absorbed work.

## Refresh Commands

```bash
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-board-log-review.py --write
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-reconstruction-review.py --write
```
