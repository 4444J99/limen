# Estate Closeout Audit

Generated: `2026-07-10T15:24:12Z`
Status: `blocked`

## Verdict

- Whole-estate closeout is not done.
- Internal free space is `109.3 GiB`; target is `200.0 GiB`; shortfall is `90.7 GiB`.
- Worktree debt is `418` debt roots / `699` scanned; reapable roots `0`.
- Remote PR search returned `1000` open PRs across `106` repos; query hit limit `True`.
- Live root gate is `blocked`; dispatch health is `blocked`.

## Contract

- This receipt is read-only. It does not merge PRs, delete roots, reset branches, stash work, or edit `tasks.yaml`.
- Deletion stays gated by merged, patch-equivalent, idle, externally preserved, or explicit owner-accepted proof.
- PR merges remain owner-gated; merge-ready means candidate for Anthony/owner review, not auto-merged.

## Disk

| Path | Free GiB | Total GiB |
|---|---:|---:|
| `/System/Volumes/Data` | `109.3` | `460.4` |
| `~/.` | `109.3` | `460.4` |
| `~/Workspace` | `109.3` | `460.4` |
| `/Volumes/Scratch` | `233.2` | `279.4` |
| `/Volumes/Archive4T` | `2872.0` | `3725.8` |

## Worktree / Reclaim

- Debt cap: `12`; reapable cap: `0`.
- Reclaim dry-run reapable count: `0`.

| Reason | Roots |
|---|---:|
| `active(<24h)` | `26` |
| `active(<6h)` | `87` |
| `antigravity-scratch-managed` | `48` |
| `dirty` | `112` |
| `documented-residue` | `2` |
| `not-merged-to-default` | `220` |
| `owner-blocker` | `35` |
| `remote-merged` | `5` |
| `remote-pr-open` | `77` |
| `remote-superseded` | `1` |
| `unpushed-commits` | `86` |

## Local Git Estate

- Git roots discovered: `1221`.
- Git roots probed in detail: `700`.
- Discovery truncated: `True` (`scan-timeout`).
- Dirty roots among probed roots: `174`.
- Unpushed or unpreserved roots among probed roots: `42`.

| Deletion Eligibility | Roots |
|---|---:|
| `blocked_not_merged_to_default` | `340` |
| `blocked_dirty` | `174` |
| `owner_review_required` | `156` |
| `blocked_unpushed_or_unpreserved` | `30` |

### Sample Dirty Roots

| Path | Repo | Dirty Entries |
|---|---|---:|
| `~/Workspace/organvm/digital-income-organism-inquiry` | `organvm/digital-income-organism-inquiry` | `1` |
| `~/Workspace/organvm/recursive-engine--generative-entity` | `organvm/recursive-engine--generative-entity` | `3` |
| `~/Workspace/organvm/4444J99.github.io` | `organvm/4444J99.github.io` | `2` |
| `~/Workspace/organvm/a-mavs-olevm` | `organvm/a-mavs-olevm` | `3` |
| `~/Workspace/organvm/your-fit-tailored` | `organvm/your-fit-tailored` | `2` |
| `~/Workspace/organvm/brainstorm-20260423` | `organvm/brainstorm-20260423` | `22` |
| `~/Workspace/organvm/dot-github--theoria` | `organvm/dot-github--theoria` | `1` |
| `~/Workspace/organvm/dot-github--theoria/.claude/worktrees/agent-a9ca0d473436e9943` | `organvm/dot-github--theoria` | `21` |
| `~/Workspace/organvm/portfolio` | `organvm/portfolio` | `4` |
| `~/Workspace/organvm/vigiles-aeternae--theatrum-mundi` | `organvm/vigiles-aeternae--theatrum-mundi` | `2` |
| `~/Workspace/organvm/universal-mail--automation` | `organvm/universal-mail--automation` | `6` |
| `~/Workspace/organvm/organon-noumenon--ontogenetic-morphe` | `organvm/organon-noumenon--ontogenetic-morphe` | `40` |
| `~/Workspace/organvm/org-dotgithub` | `organvm/org-dotgithub` | `3` |
| `~/Workspace/organvm-i-theoria/studium-generale` | `organvm/studium-generale` | `1` |
| `~/Workspace/organvm-v-logos/.github` | `organvm/.github` | `5` |
| `~/Workspace/4444J99/writelens` | `organvm/writelens` | `6` |
| `~/Workspace/4444J99/hokage-chess` | `organvm/hokage-chess` | `13` |
| `~/Workspace/4444J99/edgarflash` | `organvm/edgarflash` | `5` |
| `~/Workspace/4444J99/media-ark` | `organvm/media-ark` | `6` |
| `~/Workspace/4444J99/portfolio` | `organvm/portfolio` | `30` |

## Remote PR Estate

- Owners queried: `4444J99, a-organvm, organvm, organvm-i-theoria, organvm-ii-officium, organvm-iii-ergon, organvm-iv-taxis, organvm-v-biblos, organvm-v-logos, organvm-vi-koinonia, organvm-vii-physis`.
- Query status: `ok`.
- Open PRs returned: `1000`; draft `456`; non-draft `544`.
- Search hit limit: `True`; unclassified due to bounds: `920`.

| Classification | PRs In Deep Sample |
|---|---:|
| `ci_blocked` | `41` |
| `mergeable_needs_owner_review` | `25` |
| `owner_blocked_or_unclassified` | `5` |
| `conflict_blocked` | `9` |

### Merge-Ready Candidate Sample

| PR | Title | Classification |
|---|---|---|
| `organvm/sign-signal--voice-synth#17` | [chore(deps): bump the npm-deps group across 4 directories with 2 updates](https://github.com/organvm/sign-signal--voice-synth/pull/17) | `mergeable_needs_owner_review` |
| `organvm/vigiles-aeternae--corpus-mythicum#12` | [chore(deps): bump actions/stale from 10.3.0 to 10.4.0 in the github-actions-deps group across 1 directory](https://github.com/organvm/vigiles-aeternae--corpus-mythicum/pull/12) | `mergeable_needs_owner_review` |
| `organvm/hokage-chess#12` | [chore(deps-dev): bump the npm-deps group across 1 directory with 3 updates](https://github.com/organvm/hokage-chess/pull/12) | `mergeable_needs_owner_review` |
| `organvm/shared-remembrance-gateway#10` | [chore(deps-dev): bump the npm-deps group across 1 directory with 3 updates](https://github.com/organvm/shared-remembrance-gateway/pull/10) | `mergeable_needs_owner_review` |
| `organvm/tab-bookmark-manager#33` | [chore(deps): bump the pip-deps group across 1 directory with 5 updates](https://github.com/organvm/tab-bookmark-manager/pull/33) | `mergeable_needs_owner_review` |
| `organvm/object-lessons#24` | [chore(deps): bump the npm-deps group across 1 directory with 9 updates](https://github.com/organvm/object-lessons/pull/24) | `mergeable_needs_owner_review` |
| `organvm/classroom-rpg-aetheria#147` | [chore(deps): bump the npm-deps group across 1 directory with 34 updates](https://github.com/organvm/classroom-rpg-aetheria/pull/147) | `mergeable_needs_owner_review` |
| `organvm/a-i-chat--exporter#124` | [build(deps): bump the github-actions-deps group across 1 directory with 4 updates](https://github.com/organvm/a-i-chat--exporter/pull/124) | `mergeable_needs_owner_review` |
| `organvm/my-knowledge-base#77` | [build(deps): bump the npm-deps group across 2 directories with 25 updates](https://github.com/organvm/my-knowledge-base/pull/77) | `mergeable_needs_owner_review` |
| `organvm/krypto-velamen#13` | [chore(deps-dev): bump typescript from 6.0.3 to 7.0.2 in /apps/web-platform in the npm-deps group across 1 directory](https://github.com/organvm/krypto-velamen/pull/13) | `mergeable_needs_owner_review` |
| `organvm/gamified-coach-interface#153` | [build(deps-dev): bump the npm-deps group across 1 directory with 2 updates](https://github.com/organvm/gamified-coach-interface/pull/153) | `mergeable_needs_owner_review` |
| `organvm/trade-perpetual-future#77` | [chore(deps): bump the npm-deps group across 2 directories with 18 updates](https://github.com/organvm/trade-perpetual-future/pull/77) | `mergeable_needs_owner_review` |
| `organvm/narratological-algorithmic-lenses#49` | [chore(deps-dev): bump the pip-deps group across 1 directory with 3 updates](https://github.com/organvm/narratological-algorithmic-lenses/pull/49) | `mergeable_needs_owner_review` |
| `organvm/narratological-algorithmic-lenses#48` | [chore(deps): bump the github-actions-deps group across 1 directory with 2 updates](https://github.com/organvm/narratological-algorithmic-lenses/pull/48) | `mergeable_needs_owner_review` |
| `organvm/audio-synthesis-bridge#13` | [chore(deps-dev): bump typescript from 6.0.3 to 7.0.2 in the npm-deps group across 1 directory](https://github.com/organvm/audio-synthesis-bridge/pull/13) | `mergeable_needs_owner_review` |
| `organvm/sema-metra--alchemica-mundi#26` | [chore(deps-dev): bump the npm-deps group across 1 directory with 4 updates](https://github.com/organvm/sema-metra--alchemica-mundi/pull/26) | `mergeable_needs_owner_review` |
| `organvm/example-choreographic-interface#12` | [chore(deps-dev): bump typescript from 6.0.3 to 7.0.2 in the npm-deps group across 1 directory](https://github.com/organvm/example-choreographic-interface/pull/12) | `mergeable_needs_owner_review` |
| `organvm/client-sdk#18` | [chore(deps-dev): bump the npm-deps group across 1 directory with 3 updates](https://github.com/organvm/client-sdk/pull/18) | `mergeable_needs_owner_review` |
| `organvm/sovereign-ecosystem--real-estate-luxury#52` | [chore(deps): bump the npm-deps group across 1 directory with 42 updates](https://github.com/organvm/sovereign-ecosystem--real-estate-luxury/pull/52) | `mergeable_needs_owner_review` |
| `organvm/recursive-engine--generative-entity#24` | [chore(deps): bump the github-actions-deps group across 1 directory with 3 updates](https://github.com/organvm/recursive-engine--generative-entity/pull/24) | `mergeable_needs_owner_review` |

## Prompt / Session Lifecycle

- Gate action: `continue_direct_product_work`.
- Reason: No open prompt-review batches or prompt packets remain; continue value-gated direct product dispatch on PROD-repo-15d6ae803e4a12e2 (organvm/a-i-chat--exporter).
- Follow-up roots: `25`.
- Done or routed roots: `416`.

## Current Blockers

- Live root: `blocked`; blockers: `live-root-not-at-release`.
- Dispatch health: `blocked`; blockers: `live-root-not-at-origin-main, live-root-dirty, always-working-required-work-open`.
- Remote PR classification is incomplete because search returned the cap or failed: `True`.
- Local Git estate classification is bounded; truncated: `True`.

## Next Owner Commands

- `python3 scripts/estate-closeout-audit.py --write --remote-pr-classify-limit 250`
- `python3 scripts/worktree-pr-receipts.py --apply` only for clean local work that needs draft PR custody.
- `python3 scripts/self-heal.py --dry-run --scan 1000 --scan-max 1000` to queue exact PR repair candidates without mutating.
- `python3 scripts/merge-drain.py --dry-run --scan 1000 --scan-max 1000 --limit 0` to refresh merge-ready candidates without merging.
- `python3 scripts/substrate-storage-pressure.py --write` to keep byte owners current.
