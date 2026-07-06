# VLTIMA Absorption Cadence

Generated: `2026-07-06T15:36:28+00:00`
Status: `ok`
Mode: `write`
Materialize private raw inputs: `False`

## Contract

- Local AI app chats, projects, plans, tasks, histories, and app-store movement are continual corpus input.
- The cadence absorbs movement as private/redacted evidence first; brainstorms do not become current authority by default.
- `--materialize-private` is explicit because it copies raw local material into the ignored private object store.
- This runner does not edit `tasks.yaml`, delete repos, clean branches, push remotes, or handle credentials.

## Steps

| Step | Phase | Status | Command | Reason |
|---|---|---|---|---|
| `capture` | `capture` | `ok` | `python3 scripts/session-corpus-ledger.py --write --all` | absorb local AI app movement into redacted corpus/source coverage |
| `crosswalk` | `crosswalk` | `ok` | `python3 scripts/prompt-lifecycle-ledger.py --write --all` | relate brainstorm/session movement to worktrees, tasks, and receipts |
| `blockers` | `classify-pressure` | `ok` | `python3 scripts/session-blockers-ledger.py --write` | surface parked blockers before routing or delegation |
| `pressure` | `classify-pressure` | `ok` | `python3 scripts/session-lifecycle-pressure.py --write` | record local/remote lifecycle pressure as a receipt |
| `attack-paths` | `rank-and-packetize` | `ok` | `python3 scripts/session-attack-paths.py --write` | rank paths from current evidence without making old material authoritative |
| `priority-map` | `rank-and-packetize` | `ok` | `python3 scripts/prompt-priority-map.py --write` | turn ranked paths into priority bands and review batches |
| `command-center` | `distill` | `ok` | `python3 scripts/corpus-command-center.py --write` | distill prompts, artifacts, tasks, products, and inbound positioning |
| `substrate-ledger` | `reconcile-mismatches` | `ok` | `python3 scripts/substrate-ledger.py --write` | publish the tracked substrate result so the surface is not private-only |
| `agent-reconstruction-review` | `reconcile-mismatches` | `ok` | `python3 scripts/agent-reconstruction-review.py --write` | refresh stale reconstruction review output before trusting lineage/dormant rows |
| `prior-excavations` | `register` | `ok` | `python3 scripts/vltima-prior-excavations.py --write` | refresh the map of prior excavations after owner results move |
| `result-digest` | `digest` | `ok` | `python3 scripts/vltima-result-digest.py --write` | refresh temporal authority classification after all result receipts update |

## Receipt Tails

### `capture`

stdout:
```
session-corpus-ledger: 14101 files, 3.5 GiB over all history; wrote ~/Workspace/limen/docs/session-corpus-ledger.md
```

### `crosswalk`

stdout:
```
prompt-lifecycle-ledger: 15291 files, 131758 prompt events over all history; wrote ~/limen/docs/prompt-lifecycle-ledger.md
```

### `blockers`

stdout:
```
session-blockers-ledger: 8 blockers; wrote ~/limen/docs/session-lifecycle-blockers.md
```

### `pressure`

stdout:
```
**Lifecycle pressure** — worktrees 152 roots / 24.3 GiB / debt 5/12 · private corpus 8.5 GiB (13845 objects) · remote branches present/missing 33/110 (unresolved 4) · state: worktree debt open, remote branch gaps, runtime unconfigured
```

### `attack-paths`

stdout:
```
session-attack-paths: 168 candidate paths; wrote ~/limen/docs/session-attack-paths.md
```

### `priority-map`

stdout:
```
prompt-priority-map: 131758 prompt events, 78155 unique hashes, 294 batches; wrote ~/limen/docs/prompt-priority-map.md
```

### `command-center`

stdout:
```
corpus-command-center: 664430 units, 359628 clusters, 24 comparisons
wrote ~/limen/.limen-private/session-corpus/lifecycle/corpus-command-center.private.json
wrote ~/limen/.limen-private/session-corpus/lifecycle/corpus-command-center.public.json
wrote ~/limen/docs/corpus-command-center.md
```

### `substrate-ledger`

stdout:
```
substrate-ledger: ready; wrote ~/limen/docs/substrate-ledger.md and ~/limen/.limen-private/session-corpus/lifecycle/substrate-ledger.json
```

### `agent-reconstruction-review`

stdout:
```
agent-reconstruction-review: 2398 sessions, 875 roots, 20 analyzed
```

### `prior-excavations`

stdout:
```
vltima-prior-excavations: wrote ~/Workspace/limen/docs/vltima-prior-excavations.md and ~/Workspace/limen/.limen-private/session-corpus/lifecycle/vltima-prior-excavations.json
```

### `result-digest`

stdout:
```
vltima-result-digest: wrote ~/Workspace/limen/docs/vltima-result-digest.md and ~/Workspace/limen/.limen-private/session-corpus/lifecycle/vltima-result-digest.json
```
