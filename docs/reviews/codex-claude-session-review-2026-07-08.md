# Codex/Claude Session Review - 2026-07-08

Generated: `2026-07-09T01:15:22Z`
Window: `2026-07-08T04:00:00Z` to `2026-07-09T04:00:00Z` (America/New_York)
Snapshot cutoff: `2026-07-09T01:15:22Z`; transcript rows newer than this are excluded from guard totals.

## Verdict

High activity created code movement, but session-lifecycle closure did not justify the premium-model spend.

## Spend And Fanout

- Codex: `59` sessions, `14.2M` budget tokens, `12.1M` uncached input, `1.5M` output, `0.6M` reasoning.
- Codex guard state: active `ok`, active failures `0`, historical failures `3`.
- Claude: `15` top-level sessions, `12` failed guard, `136.9M` billable, `44.3M` Opus, `25.6M` Fable, `98` agent/workflow calls.
- Claude subagents: `24` expensive-tier subagents, `5` Fable subagents.
- Value context: `216` commits, `0` prompt-batch receipts, `0` prompt events recorded.

## Ask Vs Done Critique

- `claude_fable_without_acceptance`: 8 Claude session(s) used Fable without acceptance evidence.
- `claude_thresholds`: 9 Claude session(s) crossed spend or fanout guard thresholds.
- Commits moved, but prompt-batch receipts did not; work happened is not the same as lifecycle closure.
- Historical Codex failures remain visible but do not block this gate unless they are active.
- Fable usage must be acceptance-receipted before it is allowed to count as legitimate premium spend.

## Evolution Actions

- Run this bounded review directly: `python3 scripts/codex-claude-daily-review.py --date 2026-07-08 --until 2026-07-09T04:00:00Z --generated-at 2026-07-09T01:15:22Z --fail-on-violations`.
- Keep Codex historical budget failures visible, but fail only on active budget breakers unless a future `--strict-history` mode is added.
- Gate Claude Fable on written acceptance and cap Opus/Fable fanout at the transcript guard layer before dispatching broad verifier fleets.
- Treat any long session without verification or durable receipt signals as an incomplete lifecycle, not as closed work.

## Top Claude Guard Violations

- `8` x Fable run lacks written acceptance command
- `2` x opus subagent fanout (5 subagents on opus; max 1) - tier each fan-out agent by job, don't inherit the session model
- `2` x unbounded goal phrase detected (2 occurrence(s))
- `1` x Fable billable budget exceeded (1174760 > 1000000)
- `1` x Fable billable budget exceeded (1685976 > 1000000)
- `1` x Fable billable budget exceeded (3647480 > 1000000)
- `1` x Fable billable budget exceeded (4090897 > 1000000)
- `1` x Fable billable budget exceeded (4618553 > 1000000)

## Largest Codex Sessions

| Session | Budget | Uncached | Output | Reasoning | Active |
|---|---:|---:|---:|---:|---|
| `019f4376-01a...` | 1,426,167 | 1,264,663 | 116,511 | 44,993 | `false` |
| `019f41f4-85f...` | 794,119 | 722,296 | 54,743 | 17,080 | `false` |
| `019f42e5-c1e...` | 447,568 | 390,611 | 41,372 | 15,585 | `false` |
| `019f4330-e87...` | 371,978 | 335,328 | 26,698 | 9,952 | `false` |
| `019f422d-93a...` | 359,957 | 322,978 | 27,952 | 9,027 | `false` |
| `019f4404-66b...` | 345,744 | 298,853 | 34,399 | 12,492 | `false` |
| `019f4451-8bd...` | 342,951 | 274,159 | 48,730 | 20,062 | `true` |
| `019f416c-b2b...` | 330,624 | 292,789 | 27,518 | 10,317 | `false` |
| `019f405c-c4a...` | 317,598 | 279,799 | 25,993 | 11,806 | `false` |
| `019f436d-e7c...` | 313,046 | 271,092 | 28,427 | 13,527 | `false` |

## Largest Claude Sessions

| Session | Billable | Opus | Fable | Agent Calls | Guard |
|---|---:|---:|---:|---:|---|
| `0305e50a-e5b...` | 35,042,619 | 18,202,912 | 0 | 22 | `fail` |
| `4a4c2aa8-d45...` | 29,379,738 | 13,495,868 | 0 | 11 | `fail` |
| `6a48ce1d-1de...` | 17,053,907 | 1,034,750 | 9,645,361 | 16 | `fail` |
| `9959a3bf-646...` | 15,081,255 | 1,210,159 | 0 | 0 | `fail` |
| `e0f151ab-5ba...` | 10,163,645 | 706,275 | 0 | 1 | `fail` |
| `9959a3bf-646...` | 7,385,636 | 2,744,673 | 4,090,897 | 17 | `fail` |
| `75f8c1d0-30c...` | 7,225,273 | 4,835,052 | 434,296 | 9 | `fail` |
| `0146de0a-724...` | 5,237,140 | 0 | 4,618,553 | 6 | `fail` |
| `544e1a06-b24...` | 4,455,932 | 0 | 3,647,480 | 10 | `fail` |
| `8401e355-8c3...` | 3,264,411 | 2,089,651 | 1,174,760 | 0 | `fail` |

## Evidence Commands

- Daily review: `python3 scripts/codex-claude-daily-review.py --date 2026-07-08 --until 2026-07-09T04:00:00Z --generated-at 2026-07-09T01:15:22Z --write`
- Codex accounting: `python3 scripts/codex-token-accounting.py <daily-files> --since-hours 0 --limit-sessions 0 --max-phases 100000 --no-write --json`
- Claude transcript guard: `python3 scripts/claude-workflow-guard.py audit-transcript <filtered-session.jsonl>`
- Value context: `python3 scripts/session-value-review.py --since 2026-07-08T04:00:00Z --until 2026-07-09T04:00:00Z`
- Private JSON snapshot: `.limen-private/session-corpus/daily-reviews/codex-claude-2026-07-08.json`

## Privacy

- This tracked report contains no raw prompt or transcript bodies.
- Evidence is limited to session ids, home-relative paths in the private JSON, token counts, guard strings, command names, and receipt metadata.
