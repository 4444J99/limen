# Agent Session Full-Stack Review

Generated: `2026-07-03T22:31:32Z`

## Scope

- Prompt layer first: every extracted prompt event is stored verbatim in the private cartridge.
- Session layer second: sessions are scored against ideal-form requirements and observed outcome signals.
- Tracked output is redacted and receipt-oriented; raw prompt text remains process input under `.limen-private/`.

## Private Prompt Corpus

- Verbatim prompt events: `.limen-private/session-corpus/full-stack-review/verbatim-prompts.jsonl`
- Structured review: `.limen-private/session-corpus/full-stack-review/agent-session-review.json`
- Prompt events extracted: `125314`
- Unique prompt hashes: `74318`
- Unique normalized task-body hashes: `74239`
- Sessions reviewed: `3846`
- Outcome text scanned: `529628612` bytes

## Agent Coverage

| Agent | Sessions | Prompt events | Prompt bytes | Task-body bytes | Verified sessions | Receipt sessions | Likely no-op/unrecorded |
|---|---:|---:|---:|---:|---:|---:|---:|
| `agy` | 15 | 30 | 273370 | 10095 | 0 | 0 | 15 |
| `claude` | 1270 | 115915 | 247630632 | 243688433 | 765 | 847 | 340 |
| `codex` | 1294 | 8095 | 18603686 | 13655980 | 1030 | 1056 | 238 |
| `opencode` | 1267 | 1274 | 2972700 | 2972694 | 866 | 1039 | 227 |

## Prompt Body Mix

| Body kind | Prompt events |
|---|---:|
| `direct` | 121360 |
| `flame_scaffold` | 2262 |
| `flame_with_task_body` | 1677 |
| `session_context` | 15 |

## Source Coverage

| Source | Prompt events |
|---|---:|
| `claude-projects` | 115915 |
| `codex-sessions` | 7117 |
| `opencode-db` | 1274 |
| `codex-history` | 978 |
| `gemini-tmp-agy` | 30 |

## Ideal-Form Diff Rules

Each session is compared to this ideal form:

- Prompt names concrete owner scope: repo/path/task/lane.
- Prompt names an executable predicate or acceptance condition.
- Prompt names the expected durable receipt: changed path, commit, PR, artifact, or blocker record.
- Prompt separates reversible execution from human-gated outward/irreversible action.
- Session outcome records verification and a durable receipt, or a precise blocker.

## Ask-vs-Done Diff

- Asked for every prompt verbatim: done in the private prompt corpus with hashes in the tracked report.
- Asked for Codex, Claude, Agy/Antigravity, and OpenCode: covered Codex session/history JSONL, Claude project/task JSONL, OpenCode SQLite, and Agy/Gemini capfill JSONL; native Antigravity IDE state is inventoried but not fully decoded.
- Asked for prompt layer first and session layer second: prompt events are normalized into raw prompt hashes plus task-body hashes, then sessions are scored against ideal-form outcome rules.
- Asked for the diff between the ask and actual work: tracked at session level through missing scope, predicate, receipt, gate handling, verification, changed-file, token, and blocker signals.
- Asked for a full work review: this pass is the corpus-wide receipt/outcome review; line-level code review should be driven next from the highest-risk session list rather than attempted as an unbounded manual sweep.

## What Broke

- `1185` sessions with prompts had no verification signal in the reviewed outcome text.
- `904` sessions had no durable receipt signal or changed-file receipt.
- `820` sessions look like no-op or unrecorded work because prompts exist but the outcome surface has no verification/receipt/change signal.
- `3939` prompt events carried FLAME scaffolding; the task body is now separated, but older ledger views overcounted repeated invariant prompt mass as fresh work.
- OpenCode had many sessions that only become trustworthy when its DB-backed token clock and receipt handshake are present; session rows alone are not enough.
- Agy/Antigravity remains the weakest source surface because provider quota and native IDE conversations are not yet decoded as first-class prompt/session records.

## Highest-Risk Session Diffs

| Rank | Agent | Session | Prompt events | Risk | Gaps | Paths |
|---:|---|---|---:|---:|---|---|
| 1 | `claude` | `9750bef7-8829-4373-916a-f86338b2e20a` | 5021 | 4282 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Volumes-Archive4T/9750bef7-8829-4373-916a-f86338b2e20a.jsonl<br>~/.claude/projects/-Volumes-Archive4T/9750bef7-8829-4373-916a-f86338b2e20a/subagents/agent-a057ef0618bc1e5fb.jsonl |
| 2 | `claude` | `eb3b624c-206f-4c9e-91aa-f069967a3796` | 3593 | 3622 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-rippling-launching-trinket/eb3b624c-206f-4c9e-91aa-f069967a3796.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-rippling-launching-trinket/eb3b624c-206f-4c9e-91aa-f069967a3796/subagents/agent-a366d79c31281e1c2.jsonl |
| 3 | `claude` | `7c761a22-5bdf-42e8-bfb6-e8988530303f` | 1719 | 2233 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Volumes-Archive4T/7c761a22-5bdf-42e8-bfb6-e8988530303f.jsonl<br>~/.claude/projects/-Volumes-Archive4T/7c761a22-5bdf-42e8-bfb6-e8988530303f/subagents/agent-a04e268bdf7dea7d3.jsonl |
| 4 | `claude` | `343d6769-bdee-480f-88d9-981eec736b87` | 2567 | 2137 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-fluttering-wandering-wilkes/343d6769-bdee-480f-88d9-981eec736b87.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-fluttering-wandering-wilkes/343d6769-bdee-480f-88d9-981eec736b87/subagents/agent-a03018c613f6d9f68.jsonl |
| 5 | `claude` | `a290329e-a778-478f-a7a7-9afa79709221` | 2226 | 2002 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-glimmering-mapping-whistle/a290329e-a778-478f-a7a7-9afa79709221.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-glimmering-mapping-whistle/a290329e-a778-478f-a7a7-9afa79709221/subagents/agent-a41b8f1587a4d2341.jsonl |
| 6 | `claude` | `dc879846-e9bf-41c0-b25d-5cebab230983` | 2594 | 1858 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-nested-humming-mochi/dc879846-e9bf-41c0-b25d-5cebab230983.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-nested-humming-mochi/dc879846-e9bf-41c0-b25d-5cebab230983/subagents/agent-a120e9fec105aff82.jsonl |
| 7 | `claude` | `34d17b80-3af9-41d6-8c52-231ddce47064` | 2046 | 1684 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen/34d17b80-3af9-41d6-8c52-231ddce47064.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen/34d17b80-3af9-41d6-8c52-231ddce47064/subagents/agent-a214fdddae40bb120.jsonl |
| 8 | `claude` | `a39889c7-0aae-4348-84ed-19612cb0daa2` | 1712 | 1675 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen/a39889c7-0aae-4348-84ed-19612cb0daa2.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen/a39889c7-0aae-4348-84ed-19612cb0daa2/subagents/agent-a247af5bfed85d756.jsonl |
| 9 | `claude` | `0305e50a-e5ba-48e6-8fb1-6fb61264470d` | 1796 | 1543 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-ticklish-bubbling-robin/0305e50a-e5ba-48e6-8fb1-6fb61264470d.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-ticklish-bubbling-robin/0305e50a-e5ba-48e6-8fb1-6fb61264470d/subagents/agent-a0467340f188db4f8.jsonl |
| 10 | `claude` | `4693c425-3c29-4a48-9a0b-54fd9fd37753` | 1525 | 1492 | repeated broad/invariant prompt pressure; failure/blocker language outweighs done language | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-piped-booping-kettle/4693c425-3c29-4a48-9a0b-54fd9fd37753.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-piped-booping-kettle/4693c425-3c29-4a48-9a0b-54fd9fd37753/subagents/agent-a0557b6700135bd60.jsonl |
| 11 | `claude` | `3d972c29-36c6-4803-b94b-255df104f644` | 1530 | 1459 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-integration-organs/3d972c29-36c6-4803-b94b-255df104f644.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-integration-organs/3d972c29-36c6-4803-b94b-255df104f644/subagents/agent-a0520000a299cee80.jsonl |
| 12 | `claude` | `b7efae9c-af24-4c2c-9288-d2fa860ba974` | 4098 | 1450 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Volumes-Archive4T/b7efae9c-af24-4c2c-9288-d2fa860ba974.jsonl<br>~/.claude/projects/-Volumes-Archive4T/b7efae9c-af24-4c2c-9288-d2fa860ba974/subagents/workflows/wf_12b30531-cf8/agent-a022f1572abeac617.jsonl |
| 13 | `claude` | `f9c6b1e7-2c05-4d42-9d6a-8b08ee98a155` | 1708 | 1387 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-integration-organs/f9c6b1e7-2c05-4d42-9d6a-8b08ee98a155/subagents/agent-a42604aaa1aeb9fb5.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-integration-organs/f9c6b1e7-2c05-4d42-9d6a-8b08ee98a155/subagents/agent-a4590ce4995abceb9.jsonl |
| 14 | `claude` | `3be1f3a6-e00e-403d-a967-6d86c55deb56` | 1292 | 1216 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-feat-workstream-channels/3be1f3a6-e00e-403d-a967-6d86c55deb56/subagents/agent-a5c42b2a74c922eb5.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-feat-workstream-channels/3be1f3a6-e00e-403d-a967-6d86c55deb56/subagents/agent-a83e5c825cb67363c.jsonl |
| 15 | `claude` | `4a4c2aa8-d455-431e-b18c-3ac1d5824741` | 1869 | 1192 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-linear-conjuring-bear/4a4c2aa8-d455-431e-b18c-3ac1d5824741.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-linear-conjuring-bear/4a4c2aa8-d455-431e-b18c-3ac1d5824741/subagents/agent-a0f59b52ab3fc4cca.jsonl |
| 16 | `claude` | `5e1004b3-b917-4a9d-a1ca-0f9b2b8dba45` | 958 | 1132 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen/5e1004b3-b917-4a9d-a1ca-0f9b2b8dba45.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen/5e1004b3-b917-4a9d-a1ca-0f9b2b8dba45/subagents/agent-a933da4a2cb8d55d3.jsonl |
| 17 | `claude` | `57fa1ead-aabf-4c2e-b62e-6843cf74a66a` | 1280 | 1117 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-indexed-baking-breeze/57fa1ead-aabf-4c2e-b62e-6843cf74a66a.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-indexed-baking-breeze/57fa1ead-aabf-4c2e-b62e-6843cf74a66a/subagents/agent-a3e667029c14d3b93.jsonl |
| 18 | `claude` | `84a89bbb-ecd3-4e22-8148-f9b683bd2d92` | 1116 | 1096 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-melodic-riding-hinton/84a89bbb-ecd3-4e22-8148-f9b683bd2d92.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-melodic-riding-hinton/84a89bbb-ecd3-4e22-8148-f9b683bd2d92/subagents/agent-a493c8070e9bd376f.jsonl |
| 19 | `claude` | `95f5e850-1274-40de-8a32-8ade3192b22a` | 1083 | 1093 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-peaceful-plotting-fern/95f5e850-1274-40de-8a32-8ade3192b22a.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-peaceful-plotting-fern/95f5e850-1274-40de-8a32-8ade3192b22a/subagents/agent-a1f0dccce24e75951.jsonl |
| 20 | `claude` | `06d2559b-05e9-4ff3-b1bf-4473bd935228` | 1097 | 1090 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-goofy-meandering-crayon/06d2559b-05e9-4ff3-b1bf-4473bd935228.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-goofy-meandering-crayon/06d2559b-05e9-4ff3-b1bf-4473bd935228/subagents/agent-a2c820dc8995b0cdf.jsonl |
| 21 | `claude` | `ce278978-35f1-4b6c-a511-41f5d1de75cf` | 999 | 1078 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen/ce278978-35f1-4b6c-a511-41f5d1de75cf.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen/ce278978-35f1-4b6c-a511-41f5d1de75cf/subagents/agent-a0d7d094c1714d01a.jsonl |
| 22 | `claude` | `685b48b0-94fa-4537-a327-453a6ba01238` | 723 | 1066 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-calm-questing-ember/5226c10b-cc0b-4589-b74e-b31b03976fd9/subagents/agent-a262d8c12951718c1.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-calm-questing-ember/5226c10b-cc0b-4589-b74e-b31b03976fd9/subagents/agent-a262d8c12951718c1.jsonl |
| 23 | `claude` | `f38f4b2a-5c49-4d13-9b36-24bf31c941cc` | 1383 | 1030 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Volumes-Archive4T/f38f4b2a-5c49-4d13-9b36-24bf31c941cc.jsonl<br>~/.claude/projects/-Volumes-Archive4T/f38f4b2a-5c49-4d13-9b36-24bf31c941cc/subagents/workflows/wf_05cd5864-85d/agent-a40dccde2796d7b5e.jsonl |
| 24 | `claude` | `71d46003-4cfa-402e-b09e-fe0b99f0c702` | 1098 | 961 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-jolly-knitting-lovelace/71d46003-4cfa-402e-b09e-fe0b99f0c702.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-jolly-knitting-lovelace/71d46003-4cfa-402e-b09e-fe0b99f0c702/subagents/agent-a00256d5f47f9a50f.jsonl |
| 25 | `claude` | `1cea38f6-3455-4202-9c45-189a9f26d6dc` | 1577 | 928 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-dazzling-knitting-donut/1cea38f6-3455-4202-9c45-189a9f26d6dc.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-dazzling-knitting-donut/1cea38f6-3455-4202-9c45-189a9f26d6dc/subagents/agent-a03e879fb6bd7f826.jsonl |
| 26 | `claude` | `04d49f5a-c88d-4588-a5d9-90f64d06eacc` | 1285 | 910 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-feat-cvstos-vvltvs-organs/04d49f5a-c88d-4588-a5d9-90f64d06eacc/subagents/agent-a15c31c0d2df4b5f9.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-feat-cvstos-vvltvs-organs/04d49f5a-c88d-4588-a5d9-90f64d06eacc/subagents/workflows/wf_bd77efb3-0bb/agent-a019368ae0b9b835b.jsonl |
| 27 | `claude` | `ec251ec3-e2e5-405b-a7ea-c93d93c255a3` | 1038 | 859 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-parsed-finding-fern/70b7dbdd-d715-4d44-8812-98901dfed535/subagents/workflows/wf_4252c7cf-4f5/agent-a52593f8506c335ec.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-parsed-finding-fern/70b7dbdd-d715-4d44-8812-98901dfed535/subagents/workflows/wf_4252c7cf-4f5/agent-a54909479c7fd6f7a.jsonl |
| 28 | `claude` | `08929862-d3f1-4a09-8903-277707a8524b` | 869 | 829 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-fix-wrangler-cred-one-spot/08929862-d3f1-4a09-8903-277707a8524b/subagents/agent-af668bf26a4f07116.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen/08929862-d3f1-4a09-8903-277707a8524b.jsonl |
| 29 | `claude` | `e31aaccb-1389-4079-aa0e-dc82dd6027a6` | 1343 | 820 | repeated broad/invariant prompt pressure | ~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-quiet-bubbling-hejlsberg/e31aaccb-1389-4079-aa0e-dc82dd6027a6.jsonl<br>~/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-quiet-bubbling-hejlsberg/e31aaccb-1389-4079-aa0e-dc82dd6027a6/subagents/agent-a2d0a806568922c28.jsonl |
| 30 | `claude` | `c05f8cf3-2a05-4738-88b1-e6514bde04a9` | 782 | 811 | repeated broad/invariant prompt pressure; failure/blocker language outweighs done language | ~/.claude/projects/-Users-4jp-Workspace--limen-worktrees-cifix-a-organvm-public-record-data-scrapper-d4e6/c05f8cf3-2a05-4738-88b1-e6514bde04a9.jsonl<br>~/.claude/projects/-Users-4jp-Workspace--limen-worktrees-cifix-a-organvm-public-record-data-scrapper-d4e6/c05f8cf3-2a05-4738-88b1-e6514bde04a9/subagents/agent-a204f48163c93bb19.jsonl |

## Findings

1. Codex and Claude are now covered by the refreshed Limen prompt ledger, but the old prompt ledger did not directly ingest OpenCode's SQLite prompt store or Agy/Gemini capfill chat files. This review closes that local gap for the four requested agents.
2. Repeated fleet prompts carry a large invariant preamble before narrow work. That makes the prompt layer expensive and blurs the ideal diff: many sessions look like they were asked to preserve the whole organism when the real task was a narrow repo predicate.
3. Broad autonomy language and closeout language are fighting each other. The ideal form should require a named owner scope and receipt before any lane gets a broad prompt.
4. OpenCode has many recent sessions with no summary diffs and no token accounting in the session row; those need a live clock/receipt handshake or they read as no-op/unrecorded work even when the model saw a prompt.
5. Agy/Antigravity provider quota remains a weak surface: this review can see capfill-agy prompt JSONL and local Antigravity state files, but not a decoded native conversation DB for every IDE conversation.

## Agent Notes

- `agy`: top gaps: session outcome lacks verification signal (15), session outcome lacks durable receipt signal (15), likely no-op or unrecorded work (15).
- `claude`: top gaps: session outcome lacks verification signal (505), session outcome lacks durable receipt signal (423), repeated broad/invariant prompt pressure (367), failure/blocker language outweighs done language (362), likely no-op or unrecorded work (340).
- `codex`: top gaps: failure/blocker language outweighs done language (754), session outcome lacks verification signal (264), prompt missing executable predicate (252), session outcome lacks durable receipt signal (238), likely no-op or unrecorded work (238).
- `opencode`: top gaps: prompt missing expected receipt/artifact (549), session outcome lacks verification signal (400), prompt missing executable predicate (396), session outcome lacks durable receipt signal (227), likely no-op or unrecorded work (227).

## Antigravity/Agy Native Surface

- Known native state files: `2`.
- Local support files inventoried: `621079` files, `33497202623` bytes.
- Coverage note: Native Antigravity IDE prompt bodies were not decoded here; Agy prompt coverage comes from Gemini CLI capfill-agy chat JSONL plus local support inventory.

## Next Repairs

1. Add OpenCode and Agy sources to `prompt-lifecycle-ledger.py` so the standard ledger stops undercounting those agents.
2. Promote this compact prompt normalizer into the standard ledger so it separates invariant preamble hash from task body hash everywhere.
3. Require lane packets to include `owner_scope`, `predicate`, `expected_receipt`, and `gate_class` fields before dispatch to OpenCode/Agy/Claude/Jules.
4. Add a native Agy provider clock or explicit quota receipt. The existing board-run clock is not equivalent to provider quota exhaustion.
5. Flag sessions with `prompt_events > 0` and no verification/receipt as failed-unrecorded until a receipt or blocker is written.
6. Use the top-risk session list as the queue for deeper code-diff review, starting with broad Claude sessions and no-receipt OpenCode/Agy sessions.

## Commands

- Refresh this review: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`
- Inspect raw prompts locally: `less .limen-private/session-corpus/full-stack-review/verbatim-prompts.jsonl`
