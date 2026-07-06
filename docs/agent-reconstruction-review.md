# Agent Reconstruction Review

Generated: `2026-07-06T15:36:21Z`

## Scope

- Input: private full-stack session metadata for sessions with no structured changed-file references.
- Method: group by git root, map session windows to nearby commits, and record temporal reconstruction leads.
- Attribution boundary: overlapping commits are review leads, not proof that a session authored the commit.
- Redaction boundary: no raw prompt bodies, task bodies, or private transcript text are included here.

## Coverage

- Sessions without structured changed-file refs: `2398`.
- Root groups: `875`.
- Deep-analyzed roots: `20` (cap `20`).
- Commit matching window: `+/-30m` around each session window.

## Agents

| Agent | Sessions |
|---|---:|
| `opencode` | 861 |
| `claude` | 826 |
| `codex` | 418 |
| `agy` | 293 |

## Ideal-Form Gaps

| Gap | Sessions |
|---|---:|
| session outcome lacks verification signal | 1266 |
| session outcome lacks durable receipt signal | 892 |
| likely no-op or unrecorded work | 837 |
| failure/blocker language outweighs done language | 676 |
| prompt missing expected receipt/artifact | 640 |
| prompt missing executable predicate | 532 |
| repeated broad/invariant prompt pressure | 136 |
| prompt broad without concrete owner scope | 4 |

## Root Queue

| Rank | Root | Sessions | Agents | Risk | Prompt events | Top gaps |
|---:|---|---:|---|---:|---:|---|
| 1 | `~/Workspace/limen` | 1126 | opencode:836, claude:242, codex:45, agy:3 | 16065 | 2320 | session outcome lacks verification signal (507); prompt missing expected receipt/artifact (392); prompt missing executable predicate (340); +4 more |
| 2 | `unknown` | 266 | agy:265, codex:1 | 4136 | 264 | failure/blocker language outweighs done language (246); session outcome lacks verification signal (156); prompt missing expected receipt/artifact (36); +3 more |
| 3 | `~/Workspace/.limen-worktrees/cifix-a-organvm-public-record-data-scrapper-d4e6` | 1 | claude:1 | 811 | 782 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 4 | `~` | 17 | agy:10, codex:5, claude:2 | 455 | 203 | session outcome lacks durable receipt signal (11); session outcome lacks verification signal (10); likely no-op or unrecorded work (10); +5 more |
| 5 | `~/Workspace/limen/.claude/worktrees/tender-sniffing-marshmallow` | 1 | claude:1 | 439 | 381 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 6 | `~/Workspace/limen/.claude/worktrees/woolly-forging-sedgewick` | 1 | claude:1 | 271 | 205 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 7 | `~/Workspace/.limen-worktrees/gen-organvm-limen-ci-green-0628-cdb4` | 18 | claude:18 | 269 | 184 | failure/blocker language outweighs done language (8); session outcome lacks verification signal (2); repeated broad/invariant prompt pressure (1); +2 more |
| 8 | `~/Workspace/limen/.claude/worktrees/parsed-finding-fern` | 1 | claude:1 | 263 | 258 | repeated broad/invariant prompt pressure (1); session outcome lacks verification signal (1) |
| 9 | `~/Workspace/limen/.claude/worktrees/giggly-cuddling-quilt` | 2 | claude:2 | 255 | 181 | failure/blocker language outweighs done language (2); repeated broad/invariant prompt pressure (1); prompt missing executable predicate (1); +1 more |
| 10 | `~/Workspace/.limen-worktrees/gen-organvm-limen-test-coverage-0625-1c32` | 13 | claude:13 | 220 | 41 | prompt missing executable predicate (13); session outcome lacks verification signal (13); session outcome lacks durable receipt signal (5); +1 more |
| 11 | `~/Workspace/.limen-worktrees/gen-organvm-limen-security-0625-b412` | 12 | claude:12 | 200 | 39 | prompt missing executable predicate (12); session outcome lacks verification signal (11); session outcome lacks durable receipt signal (5); +1 more |
| 12 | `~/Workspace/.limen-worktrees/gen-organvm-limen-typing-0627-ccac` | 11 | claude:11 | 171 | 102 | failure/blocker language outweighs done language (8); session outcome lacks durable receipt signal (2); repeated broad/invariant prompt pressure (1); +2 more |
| 13 | `~/Workspace/.limen-worktrees/vigilia-face-706a` | 9 | claude:9 | 160 | 27 | prompt missing executable predicate (9); session outcome lacks verification signal (9); session outcome lacks durable receipt signal (5); +1 more |
| 14 | `~/Workspace/limen/.claude/worktrees/temporal-percolating-token` | 1 | claude:1 | 158 | 155 | repeated broad/invariant prompt pressure (1) |
| 15 | `~/Workspace/.limen-worktrees/gen-organvm-limen-ci-green-0627-6659` | 9 | claude:9 | 150 | 107 | failure/blocker language outweighs done language (6); session outcome lacks verification signal (2); repeated broad/invariant prompt pressure (1); +3 more |
| 16 | `~/Workspace/limen/.claude/worktrees/calm-questing-ember` | 1 | claude:1 | 149 | 145 | repeated broad/invariant prompt pressure (1) |
| 17 | `~/Workspace/.limen-worktrees/gen-organvm-limen-security-0624-a9e5` | 6 | claude:6 | 141 | 93 | session outcome lacks verification signal (5); prompt missing executable predicate (4); session outcome lacks durable receipt signal (2); +2 more |
| 18 | `~/Workspace/.limen-worktrees/gh-organvm-limen-352-b4c3` | 6 | claude:6 | 132 | 135 | failure/blocker language outweighs done language (4); repeated broad/invariant prompt pressure (1) |
| 19 | `~/Workspace/.limen-worktrees/gh-organvm-limen-320-6304` | 5 | claude:5 | 130 | 64 | failure/blocker language outweighs done language (3); session outcome lacks durable receipt signal (2); repeated broad/invariant prompt pressure (1); +2 more |
| 20 | `~/Workspace/.limen-worktrees/cifix-4444j99-media-ark-69e1` | 1 | claude:1 | 118 | 98 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 21 | `~/Workspace/.limen-worktrees/gen-organvm-portfolio-test-coverage-0627-2931` | 1 | claude:1 | 116 | 113 | repeated broad/invariant prompt pressure (1); session outcome lacks durable receipt signal (1); failure/blocker language outweighs done language (1) |
| 22 | `~/Workspace/.limen-worktrees/vigilia-vitals-7fb7` | 7 | claude:7 | 108 | 21 | session outcome lacks verification signal (7); prompt missing executable predicate (4); session outcome lacks durable receipt signal (3); +1 more |
| 23 | `~/Workspace/.limen-worktrees/gh-organvm-limen-320-3ee5` | 1 | claude:1 | 102 | 46 | repeated broad/invariant prompt pressure (1) |
| 24 | `~/Workspace/.limen-worktrees/rev-organvm-universal-mail--automation-revenue-ship-0625-56e9` | 1 | claude:1 | 99 | 125 | repeated broad/invariant prompt pressure (1); session outcome lacks verification signal (1) |
| 25 | `~/Workspace/.limen-worktrees/gen-organvm-public-record-data-scrapper-security-0625-ce5f` | 1 | claude:1 | 98 | 98 | repeated broad/invariant prompt pressure (1); session outcome lacks verification signal (1); session outcome lacks durable receipt signal (1); +1 more |
| 26 | `~/Workspace/.limen-worktrees/gen-organvm-my-knowledge-base-simplify-0628-1c73` | 1 | claude:1 | 97 | 94 | repeated broad/invariant prompt pressure (1) |
| 27 | `~/Workspace/.limen-worktrees/gen-organvm-public-record-data-scrapper-ci-green-0625-624b` | 1 | claude:1 | 94 | 111 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 28 | `~/Workspace/.limen-worktrees/gen-organvm-portfolio-ci-green-0626-3ef7` | 1 | claude:1 | 93 | 96 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 29 | `~/Workspace/.limen-worktrees/gh-organvm-limen-330-85f8` | 1 | claude:1 | 93 | 62 | repeated broad/invariant prompt pressure (1) |
| 30 | `~/Workspace/.limen-worktrees/gen-organvm-session-meta-typing-0626-e955` | 1 | claude:1 | 92 | 82 | repeated broad/invariant prompt pressure (1); session outcome lacks durable receipt signal (1) |
| 31 | `~/Workspace/.limen-worktrees/cifix-4444j99-media-ark-2c91` | 1 | claude:1 | 88 | 87 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 32 | `~/Workspace/.limen-worktrees/gen-organvm-universal-mail--automation-docs-0624-8374` | 1 | claude:1 | 87 | 75 | repeated broad/invariant prompt pressure (1) |
| 33 | `~/Workspace/.limen-worktrees/gen-organvm-a-i-chat--exporter-security-0624-c140` | 1 | claude:1 | 86 | 96 | repeated broad/invariant prompt pressure (1) |
| 34 | `~/Workspace/.limen-worktrees/gen-organvm-domus-genoma-ci-green-0628-33ca` | 1 | claude:1 | 86 | 72 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 35 | `~/Workspace/.limen-worktrees/gen-organvm-limen-security-0625-3f93` | 5 | claude:5 | 83 | 20 | session outcome lacks verification signal (5); prompt missing executable predicate (3); session outcome lacks durable receipt signal (3); +2 more |
| 36 | `~/Workspace/.limen-worktrees/gen-organvm-a-i-chat--exporter-docs-0624-8a03` | 1 | claude:1 | 83 | 56 | repeated broad/invariant prompt pressure (1); session outcome lacks durable receipt signal (1) |
| 37 | `~/Workspace/.limen-worktrees/gen-organvm-domus-genoma-security-0627-b9ed` | 1 | claude:1 | 82 | 107 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 38 | `~/Workspace/.limen-worktrees/gen-organvm-session-meta-ci-green-0628-a6ac` | 1 | claude:1 | 81 | 127 | repeated broad/invariant prompt pressure (1) |
| 39 | `~/Workspace/.limen-worktrees/cifix-organvm-i-theoria-studium-generale-58c1` | 1 | claude:1 | 79 | 68 | repeated broad/invariant prompt pressure (1); failure/blocker language outweighs done language (1) |
| 40 | `~/Workspace/.limen-worktrees/rev-organvm-universal-mail--automation-revenue-ship-0629-14ea` | 1 | claude:1 | 79 | 95 | repeated broad/invariant prompt pressure (1) |

## Analyzed Roots

| Root | Sessions | Commits in window | Sessions with commits | Sessions without commits | Top overlapping commits |
|---|---:|---:|---:|---:|---|
| `~/Workspace/limen` | 1126 | 1065 | 774 | 352 | `a7e5425f` (33), `b07cfe28` (31), `b2c63981` (29), `77364276` (27), `a161929e` (27) |
| `unknown` | 266 | 0 | 0 | 266 | none |
| `~/Workspace/.limen-worktrees/cifix-a-organvm-public-record-data-scrapper-d4e6` | 1 | 0 | 0 | 1 | none |
| `~` | 17 | 0 | 0 | 17 | none |
| `~/Workspace/limen/.claude/worktrees/tender-sniffing-marshmallow` | 1 | 0 | 0 | 1 | none |
| `~/Workspace/limen/.claude/worktrees/woolly-forging-sedgewick` | 1 | 0 | 0 | 1 | none |
| `~/Workspace/.limen-worktrees/gen-organvm-limen-ci-green-0628-cdb4` | 18 | 0 | 0 | 18 | none |
| `~/Workspace/limen/.claude/worktrees/parsed-finding-fern` | 1 | 0 | 0 | 1 | none |
| `~/Workspace/limen/.claude/worktrees/giggly-cuddling-quilt` | 2 | 0 | 0 | 2 | none |
| `~/Workspace/.limen-worktrees/gen-organvm-limen-test-coverage-0625-1c32` | 13 | 0 | 0 | 13 | none |
| `~/Workspace/.limen-worktrees/gen-organvm-limen-security-0625-b412` | 12 | 0 | 0 | 12 | none |
| `~/Workspace/.limen-worktrees/gen-organvm-limen-typing-0627-ccac` | 11 | 0 | 0 | 11 | none |
| `~/Workspace/.limen-worktrees/vigilia-face-706a` | 9 | 0 | 0 | 9 | none |
| `~/Workspace/limen/.claude/worktrees/temporal-percolating-token` | 1 | 0 | 0 | 1 | none |
| `~/Workspace/.limen-worktrees/gen-organvm-limen-ci-green-0627-6659` | 9 | 0 | 0 | 9 | none |
| `~/Workspace/limen/.claude/worktrees/calm-questing-ember` | 1 | 0 | 0 | 1 | none |
| `~/Workspace/.limen-worktrees/gen-organvm-limen-security-0624-a9e5` | 6 | 0 | 0 | 6 | none |
| `~/Workspace/.limen-worktrees/gh-organvm-limen-352-b4c3` | 6 | 0 | 0 | 6 | none |
| `~/Workspace/.limen-worktrees/gh-organvm-limen-320-6304` | 5 | 0 | 0 | 5 | none |
| `~/Workspace/.limen-worktrees/cifix-4444j99-media-ark-69e1` | 1 | 0 | 0 | 1 | none |

## Limen Root Detail

- Root `.` has `1126` no-change-ref sessions, `1065` commits in the aggregate window, `774` sessions with at least one temporal commit overlap, and `352` sessions with no nearby commit.

Top overlapping commits:

- `a7e5425f` overlapped `33` session windows: limen: BLD-vulnpulse-harden done - PR #5
- `b07cfe28` overlapped `31` session windows: docs: record domus CI worktree preservation
- `b2c63981` overlapped `29` session windows: docs: record media-ark test preservation
- `77364276` overlapped `27` session windows: ops: realignment follow-on - auto-scale task creation test coverage (#8)
- `a161929e` overlapped `27` session windows: fix: preserve worktree lifecycle receipts
- `c42cef70` overlapped `27` session windows: limen: sync healed task states
- `29dc7a02` overlapped `27` session windows: docs: record universal mail README preservation
- `652f3d85` overlapped `23` session windows: feat(vigilia): no-hardcode gate - the parameter-panel ratchet (build #3) (#285)
- `e72a6c7f` overlapped `23` session windows: Gilgamesh film companion (mortality/grief) (#287)
- `5438c91f` overlapped `23` session windows: Gilgamesh film companion (mortality/grief) (#290)
- `7f21f960` overlapped `23` session windows: fix(dialogs): one predicate for the permission-dialog estate + home the firewall class (#293)
- `d127cc22` overlapped `20` session windows: feat(obligations): lever face gains its own clock - deadlines self-flag (#275)

Top high-risk sessions in this root:

| Agent | Session | Risk | Prompts | Overlap commits | Window | Gaps |
|---|---|---:|---:|---:|---|---|
| `claude` | `c464fb56-f4e3-4858-acfb-72183c506b6b` | 142 | 153 | 28 | `2026-06-20T14:32:17Z`..`2026-06-21T16:47:53Z` | repeated broad/invariant prompt pressure |
| `claude` | `8401e355-8c36-4735-960d-72e4421e5a9f` | 122 | 66 | 7 | `2026-07-03T17:28:25Z`..`2026-07-03T18:32:58Z` | repeated broad/invariant prompt pressure; session outcome lacks durable receipt signal |
| `claude` | `8f791303-a867-4fb5-9254-d04513f1b982` | 49 | 42 | 11 | `2026-06-21T16:33:55Z`..`2026-06-21T16:53:36Z` | repeated broad/invariant prompt pressure |
| `codex` | `019f1802-6c07-74c1-9b22-b328bb04d3bb` | 40 | 14 | 0 | `2026-06-30T10:12:38Z`..`2026-06-30T10:17:09Z` | repeated broad/invariant prompt pressure; failure/blocker language outweighs done language |
| `codex` | `019f27d5-64f5-73e1-a4d3-5d732c8f3065` | 34 | 19 | 10 | `2026-07-03T11:56:49Z`..`2026-07-03T12:50:48Z` | failure/blocker language outweighs done language |
| `codex` | `019f1962-df52-7ad2-a13a-7a2ad2e9c1e2` | 34 | 13 | 3 | `2026-06-30T16:35:40Z`..`2026-06-30T16:47:13Z` | failure/blocker language outweighs done language |
| `codex` | `019f22f7-de14-7723-83ad-740592d7fb90` | 28 | 14 | 24 | `2026-07-02T13:15:00Z`..`2026-07-02T15:00:28Z` |  |
| `claude` | `dbdde73e-f41c-441e-8a10-5386f53bd995` | 27 | 28 | 9 | `2026-07-02T12:41:42Z`..`2026-07-02T12:51:22Z` | failure/blocker language outweighs done language |
| `codex` | `019f2358-ffdd-70f3-aa2a-db3058314b02` | 25 | 18 | 28 | `2026-07-02T15:01:06Z`..`2026-07-02T17:34:11Z` |  |
| `opencode` | `ses_1098f57d2fferS4UoK9pfcP49X` | 23 | 1 | 10 | `2026-06-23T21:44:01Z`..`2026-06-23T21:44:27Z` | prompt missing executable predicate; prompt missing expected receipt/artifact; session outcome lacks verification signal |
| `opencode` | `ses_11465f402ffeubG9gJW0vYbDg0` | 23 | 1 | 7 | `2026-06-21T19:13:21Z`..`2026-06-21T19:13:57Z` | prompt missing executable predicate; prompt missing expected receipt/artifact; session outcome lacks verification signal |
| `opencode` | `ses_11c8f1817ffesj3Sn0ptaT61kn` | 23 | 1 | 0 | `2026-06-20T05:11:30Z`..`2026-06-20T05:11:39Z` | prompt missing executable predicate; prompt missing expected receipt/artifact; session outcome lacks verification signal; failure/blocker language outweighs done language |

## Findings

1. No-change-ref sessions are not no-work by default; many overlap real git activity, but the attribution is temporal and must be verified against prompt intent before crediting closure.
2. The largest root is Limen itself, dominated by OpenCode plus Claude/Codex/Agy sessions. Its reconstruction burden is high enough that session prompts need explicit receipt targets and predicates, not broad autonomous instructions alone.
3. Missing or non-git roots are a separate artifact-loss lane. Those sessions should be inspected through private transcript paths, preserved worktree receipts, or external PR/branch references before being marked absorbed.
4. Sessions with no overlapping commits are likely read-only, interrupted, no-op, off-window, or failed before mutation. They should not be counted as completed implementation work without an independent receipt.

## Commands

- Refresh source review first: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`
- Refresh queue next: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write`
- Refresh this reconstruction review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-reconstruction-review.py --write`
- Private structured output: `~/limen/.limen-private/session-corpus/full-stack-review/agent-reconstruction-review.json`
