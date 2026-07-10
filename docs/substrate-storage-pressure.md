# Substrate Storage Pressure

Generated: `2026-07-10T02:12:21Z`
Status: `needs-owner-gates`
Internal free: `88.9 GiB`
Target free: `200.0 GiB`
Shortfall: `111.1 GiB`

## Safe Reclaim Already Run

- `generated-state`: `26.6 GiB` over `4` apply event(s); latest `2026-07-10T02:11:41Z`.
- `tool-cache`: `5.1 GiB` over `3` apply event(s); latest `2026-07-10T02:11:27Z`.
- `ollama-models`: `9.3 GiB` over `3` apply event(s); latest `2026-07-10T02:11:27Z`.

## Scratch / Worktree Lifecycle

- Summary: `0 debt roots / 497 scanned; 0 reapable roots`.
- Debt cap: `12`; reapable cap: `0`.

| Reason | Roots |
|---|---:|
| `active(<6h)` | `302` |
| `remote-pr-open` | `72` |
| `antigravity-scratch-managed` | `48` |
| `active(<24h)` | `46` |
| `owner-blocker` | `27` |
| `remote-merged` | `1` |
| `remote-superseded` | `1` |

## Remaining Large Buckets

| Bucket | Size | Class | Owner | Gate |
|---|---:|---|---|---|
| `~/.local/share/opencode/opencode.db` | `10.9 GiB` | `protected-agent-state` | `aw-opencode-db-corpus-intake-0709` | external archive and private intake verified; local retention decision remains; never delete outright |
| `~/Workspace/limen/.limen-private/session-corpus` | `10.2 GiB` | `protected-private-corpus` | `docs/session-corpus-ledger.md` | two-copy/restore archive gate before move or purge |
| `~/Pictures/Photos Library.photoslibrary` | `8.6 GiB` | `personal-media` | `media/photos custody` | personal-data human gate plus two-copy restore proof |
| `~/Workspace/.limen-worktrees` | `8.3 GiB` | `worktree-cache` | `docs/worktree-reclaim-acceptance.md` | clean+merged+idle or explicit acceptance; current worktree-debt gate reports zero reapable |
| `~/Library/Messages` | `7.3 GiB` | `personal-communications` | `communications custody` | personal-data human gate plus two-copy restore proof |
| `~/.gemini/antigravity-cli` | `6.7 GiB` | `protected-agent-state` | `agy conductor` | preserve conversations/brain before eviction; scratch handled separately |
| `~/Workspace/session-meta` | `5.1 GiB` | `repo-corpus-state` | `organvm/session-meta` | repo/archive custody proof before local cache eviction |
| `~/.gemini/antigravity-cli/scratch` | `4.2 GiB` | `agy-scratch` | `docs/antigravity-scratch-bridge.md` | antigravity scratch archive/redaction acceptance ledger before removal |

## OpenCode DB Intake

- Status: `archived_private_intake`.
- Archive status: `verified`.
- Receipt: `~/Workspace/limen/docs/opencode-db-corpus-intake.md`.
- Private manifest: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/opencode-db-intake/20260710T010237Z/manifest.json`.

## Contract

- Do not delete personal communications, photos, private corpus, or agent session databases as cache.
- Worktree and Agy scratch removal stay behind their acceptance ledgers.
- More disk reduction now requires owner gates, archive/restore proof, or explicit product decision to lower the hot-cache target.
