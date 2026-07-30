# OpenCode Session Review

Generated: `2026-07-04T02:41:00Z`

## Scope

- Input: private full-stack session review plus the local OpenCode SQLite database.
- Prompt bodies remain private under `.limen-private/session-corpus/full-stack-review/`.
- This report records metadata, token/diff surfaces, and prompt-vs-done failure modes only.

## Coverage

- OpenCode sessions reviewed: `1268`.
- Prompt events: `1275`.
- Native SQLite DB size: `5497249792` bytes.
- Structured-change sessions: `405`.
- Sessions with no structured changed-file refs: `863`.
- Unique changed-file targets: `744`.
- Immediate changed-file review candidates in the queue: `226`.
- Board/log-only sessions in the queue: `179`.
- Reconstruction/no-change sessions in the queue: `861`.

## Native DB Surface

| Table | Rows |
|---|---:|
| `session` | 1273 |
| `message` | 13277 |
| `part` | 59727 |
| `event` | 69957 |
| `todo` | 2721 |
| `project` | 155 |
| `project_directory` | 713 |
| `session_message` | 786 |
| `account` | 0 |
| `credential` | 0 |
| `permission` | 0 |

OpenCode is the strongest native surface for tokens and summary diffs in this corpus, but the DB still has to be interpreted through receipts. A session row with prompt text and token spend is not the same thing as verified task completion.

## Token Surface

| Metric | Tokens |
|---|---:|
| Input | 145344500 |
| Output | 2839094 |
| Reasoning | 1777101 |

The token clock is useful for spend and throttling. It does not prove acceptance unless the session also records verification and a durable receipt.

## Changed-File Distribution

| Changed refs per session | Sessions |
|---:|---:|
| 0 | 863 |
| 1 | 205 |
| 2 | 62 |
| 3 | 20 |
| 4 | 18 |
| 5 | 18 |
| 7 | 11 |
| 6 | 8 |
| 9 | 6 |

## Top Changed Targets

| Count | Target |
|---:|---|
| 327 | `/Users/4jp/Workspace/limen/tasks.yaml` |
| 56 | `/Users/4jp/Workspace/limen/cli/src/limen/dispatch.py` |
| 35 | `/Users/4jp/Workspace/limen/docs/capacity-fill.md` |
| 26 | `/Users/4jp/Workspace/limen/cli/src/limen/capacity.py` |
| 24 | `/Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh` |
| 24 | `/Users/4jp/Workspace/limen/docs/dispatch-health.md` |
| 18 | `/Users/4jp/Workspace/limen/scripts/route.py` |
| 18 | `/Users/4jp/Workspace/limen/cli/tests/test_dispatch.py` |
| 17 | `/Users/4jp/Workspace/limen/cli/tests/test_async_dispatch.py` |
| 17 | `/Users/4jp/Workspace/limen/scripts/dispatch-async.py` |
| 17 | `/Users/4jp/Workspace/limen/docs/live-root-gate.md` |
| 16 | `/Users/4jp/Workspace/limen/.github/workflows/ci.yml` |

## Ideal-Form Gaps

| Gap | Sessions |
|---|---:|
| prompt missing expected receipt/artifact | 549 |
| session outcome lacks verification signal | 401 |
| prompt missing executable predicate | 396 |
| session outcome lacks durable receipt signal | 228 |
| likely no-op or unrecorded work | 228 |
| failure/blocker language outweighs done language | 179 |

## What Went Wrong

1. OpenCode was overused for board/control-plane churn. `tasks.yaml` is the top changed target by a large margin, so many sessions closed accounting loops rather than proving product/code outcomes.
2. `863/1268` sessions have no structured changed-file refs. Some are legitimate read-only or planning sessions, but they cannot be credited as implementation without a separate receipt.
3. Prompt packets often omitted explicit predicates and expected receipts. That makes the ideal diff weak even when OpenCode generated useful work.
4. Board-only OpenCode sessions need stricter handling. The board/log review found historical commits where one named completion bundled broad queue rewrites, budget counter shifts, noncanonical `cancelled` statuses, and missing verification phrases.
5. Native token accounting is strong, but outcome accounting is not. Token spend proves model work happened; it does not prove the right artifact landed.

## Improvements

1. Require OpenCode prompts to include `owner_scope`, `predicate`, `expected_receipt`, and `allowed_paths` before mutation.
2. Treat `tasks.yaml`-only OpenCode sessions as governance/accounting reviews unless they point to a PR, commit, verification command, or explicit blocker.
3. Keep using OpenCode SQLite `summary_diffs` as the first changed-file surface, but cross-check high-risk rows against git history before accepting done claims.
4. Add a receipt handshake for no-change sessions: read-only review, no-op, interrupted, failed, or externally blocked must be recorded explicitly.
5. Keep token-clock data separate from acceptance data. Spend controls should not double as done-state proof.

## Commands

- Refresh full-stack source: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`
- Refresh code-review queue: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write`
- Refresh board/log review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-board-log-review.py --write`
- Refresh reconstruction review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-reconstruction-review.py --write`
