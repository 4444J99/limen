# Agy / Antigravity Session Review

Generated: `2026-07-04T02:38:00Z`

## Scope

- Input: private full-stack session review plus local Agy CLI / Antigravity inventory.
- Prompt bodies remain private under `.limen-private/session-corpus/full-stack-review/`.
- This report records session/receipt shape, changed-file surfaces, and failure modes only.

## Coverage

- Agy sessions reviewed: `528`.
- Agy prompt events: `554`.
- Structured-change sessions: `225`.
- Sessions with no structured changed-file refs: `303`.
- Unique changed-file targets: `401`.
- Agy CLI conversation DBs decoded: `501` files, `894586880` bytes.
- Agy CLI `steps` rows scanned for metadata: `28401`.
- Prompt-bearing Agy CLI step type `14` rows: `504`.
- Steps with non-empty error details: `204`.
- Native Antigravity IDE conversation dirs checked: `0` conversation files on this host.

## Attribution Shape

| Shape | Count |
|---|---:|
| `cwd=None` sessions | 499 |
| `/Users/4jp` sessions | 10 |
| `/Users/4jp/Workspace/limen` sessions | 4 |
| `gemini-tmp-agy` source sessions | 15 |
| `agy-cli-history` source sessions | 12 |
| `agy-cli-conversations` source sessions | 499 |

The dominant issue is root attribution. Agy has real CLI trajectory data, but most rows do not name a repo cwd, so prompt-vs-done review must start from DB trajectory IDs, `TargetFile` spans, scratch paths, and bridge receipts.

## Top Changed Targets

| Count | Target |
|---:|---|
| 15 | `/Users/4jp/Workspace/limen/cli/src/limen/dispatch.py` |
| 12 | `/Users/4jp/Workspace/limen/tasks.yaml` |
| 4 | `/Users/4jp/Workspace/limen/cli/src/limen/capacity.py` |
| 4 | `/Users/4jp/Workspace/limen/README.md` |
| 3 | `/Users/4jp/Workspace/mirror-mirror/src/components/MirrorPlusSubscription.tsx` |
| 3 | `/Users/4jp/Workspace/session-meta/analysis/federated_friction.py` |
| 3 | `/Users/4jp/Workspace/session-meta/ingest/manifest.py` |
| 3 | `/Users/4jp/Workspace/mirror-mirror/README.md` |

Scratch-space targets also appear, including `.gemini/antigravity-cli/scratch/...`. Those are not absorbed work unless a later bridge receipt or commit ties the scratch delta into the owner worktree.

## Step Metadata

| Metric | Count |
|---|---:|
| Conversation DBs scanned | 501 |
| Total `steps` rows | 28401 |
| Non-empty `error_details` rows | 204 |
| Largest trajectory | `2fe3adee-4947-443b-8ad8-6bda2a22fb90` with 415 steps |
| Highest error-count trajectory | `7bc94835-2153-4cdb-8de8-3ff29421ae61` with 9 error rows |

Top numeric step types:

| Step type | Rows |
|---:|---:|
| 15 | 8771 |
| 90 | 8028 |
| 21 | 2835 |
| 8 | 2280 |
| 9 | 1246 |
| 101 | 865 |
| 132 | 830 |
| 17 | 723 |
| 5 | 644 |
| 98 | 630 |
| 14 | 504 |

Step status values are still numeric in the local DB schema: `3` dominates with `27761` rows; other values are `5` with `355`, `7` with `127`, `2` with `78`, `6` with `77`, and `8` with `3`.

## Highest-Risk Agy Rows

| Session | Risk | Prompts | Changed refs | Cwd | Gaps |
|---|---:|---:|---:|---|---|
| `2fe3adee-4947-443b-8ad8-6bda2a22fb90` | 28 | 15 | 7 | `/Users/4jp/Workspace/limen` | failure/blocker language outweighs done language |
| `29710611-0380-4293-81b7-796542be4e47` | 26 | 12 | 0 | `/Users/4jp` | missing receipt; no verification; no durable receipt; likely no-op |
| `df622cf7-dbab-402d-bf3c-17457aa12931` | 23 | 1 | 0 | none | missing predicate; missing receipt; no verification; failure/blocker |
| `8e4f49f0-efed-4461-a583-ccd32a37df67` | 23 | 1 | 0 | none | missing predicate; missing receipt; no verification; failure/blocker |
| `a08e0522-6a3b-4c4d-a374-38be3643c918` | 22 | 1 | 0 | none | missing receipt; no verification; failure/blocker |
| `d7d9e976-9a0c-4af1-8db2-02bb8207c30a` | 22 | 1 | 0 | none | missing receipt; no verification; failure/blocker |
| `7972f691-630a-46f9-bbd6-3c1c587b6015` | 22 | 1 | 1 | none | missing receipt; no verification; failure/blocker |
| `80b77a44-b878-408f-8eb4-c8c97e4b2f17` | 22 | 1 | 1 | none | missing receipt; no verification; failure/blocker |

## What Went Wrong

1. Native Antigravity IDE state is not a usable prompt/session source on this host yet. The checked IDE conversation directories are empty, so the usable evidence is Agy CLI history and per-conversation SQLite trajectories.
2. Agy root attribution is weak: `499/528` sessions have `cwd=None`. That makes repo ownership, task scope, and acceptance predicates hard to reconstruct after the fact.
3. Receipt signals over-credit Agy if taken literally. File paths, DB paths, and `TargetFile` spans prove a trajectory surface existed; they do not prove that the owner worktree absorbed and verified the delta.
4. Scratch-space work is a bridge obligation. Anything under `.gemini/antigravity-cli/scratch` needs a later commit, copied delta, or explicit blocker receipt before it counts as done.
5. Provider quota is still not a native receipt. Board-level Agy run counts are not the same thing as a provider-backed quota/rate-limit proof.

## Improvements

1. Agy work packets should require `owner_scope`, `repo_root`, `predicate`, `expected_receipt`, and `bridge_target` before launch.
2. Every Agy scratch run should end with a machine-readable receipt listing scratch root, changed targets, verification command/result, and whether each delta was bridged.
3. The full-stack extractor should keep the current conservative `TargetFile` changed-ref logic, but downstream review should treat it as a lead until a commit/PR/receipt confirms absorption.
4. Re-check native Antigravity IDE stores only after `.gemini/antigravity-ide/conversations` or `.gemini/antigravity/conversations` becomes non-empty.
5. Add an Agy provider-clock receipt separate from board run counts, with explicit rate-limit/quota evidence when failures are quota-driven.

## Commands

- Refresh full-stack source: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write`
- Refresh reconstruction queue: `env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-reconstruction-review.py --write`
- Inspect private Agy prompt rows locally: `jq 'select(.agent=="agy")' .limen-private/session-corpus/full-stack-review/verbatim-prompts.jsonl`
