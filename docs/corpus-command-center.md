# Corpus Command Center

Generated: `2026-06-29T17:42:28+00:00`

## Canonical Decision

- Prompts, replies, artifacts, tasks, Aug-1 state, and inbound positioning are one corpus surface.
- Raw bodies stay in `.limen-private/session-corpus/corpus-command-center/objects`; tracked output is redacted.
- The dashboard surfaces work candidates and pressure; it does not claim tasks or mutate `tasks.yaml`.

## Coverage

- Units indexed: `353277`.
- Unique hashes: `219803`.
- Clusters: `202168`.
- Side-by-side comparisons: `24`.
- Private body objects: `219803`.

## Kind Mix

| Kind | Units |
|---|---:|
| `tool` | 165972 |
| `prompt` | 93079 |
| `response` | 86272 |
| `system` | 3753 |
| `artifact` | 2701 |
| `task` | 1500 |

## Goal Panels

- Aug-1 gate: `false`; legs `0` / `5`; deadline `2026-08-01`.
- Inbound magnet: value repos `12`, seeded repos `9`, scraper model present `True`.

## Private Outputs

- Private index: `.limen-private/session-corpus/lifecycle/corpus-command-center.private.json`.
- Private local explorer: `.limen-private/session-corpus/lifecycle/corpus-command-center.private.html`.
- Public/redacted index: `.limen-private/session-corpus/lifecycle/corpus-command-center.public.json`.

## Commands

- Refresh the command center: `python3 scripts/corpus-command-center.py --write`
- Run the full local corpus intentionally: `python3 scripts/corpus-command-center.py --write --all-sessions`
- Refresh upstream ledgers first when needed: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/prompt-priority-map.py --write`
