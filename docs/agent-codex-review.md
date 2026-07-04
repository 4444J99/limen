# Codex Session Review

Generated: `2026-07-04T02:43:00Z`

## Scope

- Input: private full-stack session review for Codex session/history JSONL.
- Prompt bodies remain private under `.limen-private/session-corpus/full-stack-review/`.
- Structured changed-file refs are conservative tool-payload paths, not a guarantee that the final git diff survived.

## Coverage

- Codex sessions reviewed: `1303`.
- Prompt events: `8132`.
- Prompt bytes: `18846241`.
- Normalized task-body bytes: `13794477`.
- Structured-change sessions: `885`.
- Structured changed-file refs: `4808`.
- Sessions with no structured changed-file refs: `418`.
- Immediate changed-file review candidates in the queue: `884`.
- Board/log-only sessions in the queue: `1`.
- Reconstruction/no-change sessions in the queue: `418`.

## Changed-File Distribution

| Changed refs per session | Sessions |
|---:|---:|
| 0 | 418 |
| 1 | 233 |
| 2 | 168 |
| 3 | 108 |
| 4 | 67 |
| 6 | 48 |
| 5 | 46 |
| 7 | 45 |
| 10 | 27 |
| 9 | 25 |
| 8 | 25 |

## Top Changed Targets

| Count | Target |
|---:|---|
| 119 | `README.md` |
| 45 | `DISCOVERY.md` |
| 39 | `.github/workflows/ci.yml` |
| 34 | `cli/src/limen/dispatch.py` |
| 31 | `value-repos.json` |
| 29 | `package.json` |
| 26 | `.gitignore` |
| 23 | `scripts/verify-whole.sh` |
| 20 | `tsconfig.json` |
| 18 | `institutio/governance/parameters.yaml` |
| 17 | `tasks.yaml` |
| 17 | `cli/tests/test_dispatch.py` |

## Ideal-Form Gaps

| Gap | Sessions |
|---|---:|
| failure/blocker language outweighs done language | 726 |
| session outcome lacks verification signal | 264 |
| prompt missing executable predicate | 252 |
| session outcome lacks durable receipt signal | 236 |
| likely no-op or unrecorded work | 236 |
| prompt missing expected receipt/artifact | 228 |
| repeated broad/invariant prompt pressure | 24 |

## What Went Wrong

1. Codex has many changed-file leads, but they are conservative tool-path refs. Each high-risk row still needs git-window reconstruction or live file inspection before it can be credited as done.
2. Failure/blocker language dominates `726` sessions. That means many Codex runs ended in interruption, auth/quota/tool failure, or partial work even when prompts existed.
3. `418` sessions have no structured changed refs. Those are likely review-only, no-op, failed-before-mutation, or off-window sessions unless a separate receipt exists.
4. The common targets are broad repo surfaces (`README.md`, `DISCOVERY.md`, CI, package metadata, Limen dispatch). This increases the risk of generic churn unless the prompt names the exact owner scope and predicate.
5. Codex history/session JSONL gives good local evidence, but final acceptance still depends on durable receipts: commit, PR, verification command, or blocker.

## Improvements

1. Require Codex prompts to include exact repo/root, allowed paths, predicate, and expected receipt before broad mutation.
2. Treat changed-file refs from tool payloads as review leads until confirmed with `git log`, `git diff`, or live file checks.
3. Mark failure-heavy sessions as failed/unrecorded unless they ended with a concrete blocker receipt.
4. Keep board-only Codex work out of implementation ledgers unless it references the implementation receipt it is closing.
5. Use `docs/agent-code-review-queue.md` and `docs/agent-code-diff-review.md` as the active Codex deep-review queue.

## Commands

- Refresh full-stack source: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`
- Refresh code-review queue: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write`
- Refresh reconstruction review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-reconstruction-review.py --write`
