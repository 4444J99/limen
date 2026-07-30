# MERGE-READY-NOW

> **Generated:** 2026-06-19 13:18 UTC (read-only sweep, nothing merged).
> **Scope:** all open PRs across fleet owners with open PRs:
> a-organvm, organvm-i-theoria, 4444J99, meta-organvm, organvm-iii-ergon.
> (`organvm` owner: not searchable / no open PRs.)
> **Method:** GraphQL bulk fetch of `mergeable` + `mergeStateStatus` + last-commit
> `statusCheckRollup`; 55 lazy-`UNKNOWN` mergeables force-resolved by re-poll
> (0 left UNKNOWN); 12-PR live spot-recheck = 11/12 still CLEAN.

## One-line state

**746 open PRs.** **113 are merge-READY** (non-draft, MERGEABLE, mergeStateStatus
CLEAN, CI green-or-none). The rest: **366 DRAFT** (WIP, mostly Jules), **78
non-draft CONFLICTING**, **189 non-draft CI-blocked**.

⚠ **Reality vs. the stale memory map:** memory said "~111 merge-ready, exporter
revenue chain #26-#33 = highest-value." That is **no longer true.** The exporter
chain renumbered to **#29-#33 and is now CONFLICTING/DIRTY** (CI green, but the
stacked PRs conflict with master and each other). Of the 113 READY, **98 are
Dependabot** dependency bumps, **12 are Limen duplicate-noise** (repeated
"Open Codex task one/two" — should be CLOSED, not merged), leaving **only 3
real-substance feature/content PRs.** No revenue-product PR is currently
green-light mergeable.

## Top-value to merge FIRST

The high-revenue chains are blocked by conflicts, so the genuine first-merge value
is small. In priority order:

### Tier A — real substance (merge first, 3 PRs)

| Repo | PR | Title | Author | CI |
|------|----|-------|--------|----|
| a-organvm/my--father-mother | #4 | [limen jules GH-a-organvm-my-father-mother-1] ACTIVATION AUDIT: ship-now | 4444J99 | SUCCESS |
| organvm-i-theoria/conversation-corpus-engine | #49 | [limen LIMEN-056] IRF-CCE-035: Omega evidence map — note commercial spec for cri | 4444J99 | SUCCESS |
| organvm-i-theoria/rules-system-bound | #9 | [limen RESOLVE-organvm-i-theoria-rules-system-bound-8] resolve rules-system-boun | 4444J99 | SUCCESS |

Notes:
- `organvm-i-theoria/conversation-corpus-engine #49` — live mergeStateStatus
  **CLEAN**, truly green-light (corpus legibility content).
- `a-organvm/my--father-mother #4` & `organvm-i-theoria/rules-system-bound #9`
  — content-ready (no conflicts, CI fine) but live state drifted to **BLOCKED**:
  these repos require named status contexts (`test-matrix (py3.x)` / `test (3.x)`)
  that haven't all reported on the head commit. Re-run the required check or
  admin-merge.

### Tier B — Dependabot dependency/security bumps (98 PRs, safe-batch)

All MERGEABLE + CLEAN + CI green. These are the bulk of the "ready" count.
High-leverage to clear in one batch (security/supply-chain hygiene), low product
risk. Heaviest repos: limen, public-record-data-scrapper, tab-bookmark-manager,
my-block-warfare, sovereign-ecosystem--real-estate-luxury. Full list in the
"All 113 READY" table below (rows with a `chore(deps)`/`build(deps)` title).

### Tier C — CLOSE, do not merge (12 Limen duplicate-noise PRs)

These are repeated identical "[limen LIMEN-003/004] Open Codex task one/two" PRs in
`4444J99/limen` — dispatch dedup misfires. They are technically mergeable but
add nothing; recommend `gh pr close` (not merge).

| Repo | PR | Title |
|------|----|-------|
| 4444J99/limen | #20 | [limen LIMEN-003] Open Codex task one |
| 4444J99/limen | #21 | [limen LIMEN-004] Open Codex task two |
| 4444J99/limen | #22 | [limen LIMEN-003] Open Codex task one |
| 4444J99/limen | #23 | [limen LIMEN-003] Open Codex task one |
| 4444J99/limen | #24 | [limen LIMEN-004] Open Codex task two |
| 4444J99/limen | #25 | [limen LIMEN-004] Open Codex task two |
| 4444J99/limen | #26 | [limen LIMEN-003] Open Codex task one |
| 4444J99/limen | #27 | [limen LIMEN-004] Open Codex task two |
| 4444J99/limen | #28 | [limen LIMEN-003] Open Codex task one |
| 4444J99/limen | #29 | [limen LIMEN-004] Open Codex task two |
| 4444J99/limen | #30 | [limen LIMEN-003] Open Codex task one |
| 4444J99/limen | #31 | [limen LIMEN-004] Open Codex task two |

## Why the revenue chains are NOT ready (the real blocker)

Every revenue-product PR is conflict- or CI-blocked right now:

| Repo | Revenue PRs | State |
|------|-------------|-------|
| a-organvm/a-i-chat--exporter | #29 #30 #31 #32 #33 | all DIRTY (conflict); CI green |
| a-organvm/the-invisible-ledger | #4 #7 #8 | all DIRTY; CI green |
| a-organvm/my--father-mother | #8 #9 #14 | all DIRTY; CI green |
| a-organvm/mirror-mirror | #7 | DIRTY; CI green |
| a-organvm/universal-mail--automation | #53 | DIRTY; CI fail |
| 4444J99/media-ark | #26 #29 #30 #31 #33 #34 | BLOCKED/DIRTY; CI pending/fail |
| 4444J99/domus-genoma | #110 #111 | UNSTABLE; CI fail |

**Root cause:** each product's REV-* PRs are a *stack* of commits all editing the
same files (`src/providers/*`, `src/platform/*`, checkout/license code), dispatched
in parallel and never merged — so each conflicts with master and with its
siblings. CI is green on its own branch but the merge is DIRTY.

**Unblock path (highest revenue leverage):** resolve the exporter chain (already a
live product) by merging/rebasing **sequentially**: take #29 first, rebase #30 onto
the new master, repeat through #33. Or squash the whole chain into one PR. This is
the single highest-value action for first-dollar (monetize the live ChatGPT
Exporter). Same pattern unblocks invisible-ledger and my--father-mother.

## Recommendation (when the user opens the merge gate)

1. **Batch-merge Tier B Dependabot (98)** — one safe sweep, supply-chain hygiene,
   zero product risk.
2. **Merge Tier A #49** immediately (CLEAN); re-run required checks on #4/#9 then
   merge.
3. **Close Tier C (12)** Limen dup-noise PRs.
4. **Then attack revenue:** resolve the exporter #29→#33 conflict stack
   sequentially — that is where first-dollar lives, and it needs conflict
   resolution work, not a merge click.

---

## All 113 READY (repo, pr#, title, status)

| Repo | PR | Title | Status |
|------|----|-------|--------|
| 4444J99/bountyscope | #6 | chore(deps-dev): bump vitest from 2.1.9 to 4.1.9 in the npm_and_yarn group  | READY |
| 4444J99/edgarflash | #6 | chore(deps-dev): bump vitest from 2.1.9 to 4.1.9 in the npm_and_yarn group  | READY |
| 4444J99/limen | #14 | chore(deps): bump the docker-deps group across 2 directories with 2 updates | READY |
| 4444J99/limen | #15 | chore(deps): bump the pip-deps group across 1 directory with 6 updates | READY |
| 4444J99/limen | #16 | chore(deps): bump the npm-deps group across 2 directories with 7 updates | READY |
| 4444J99/limen | #19 | chore(deps): bump python-multipart from 0.0.30 to 0.0.31 in /mcp in the uv  | READY |
| 4444J99/limen | #20 | [limen LIMEN-003] Open Codex task one | READY |
| 4444J99/limen | #21 | [limen LIMEN-004] Open Codex task two | READY |
| 4444J99/limen | #22 | [limen LIMEN-003] Open Codex task one | READY |
| 4444J99/limen | #23 | [limen LIMEN-003] Open Codex task one | READY |
| 4444J99/limen | #24 | [limen LIMEN-004] Open Codex task two | READY |
| 4444J99/limen | #25 | [limen LIMEN-004] Open Codex task two | READY |
| 4444J99/limen | #26 | [limen LIMEN-003] Open Codex task one | READY |
| 4444J99/limen | #27 | [limen LIMEN-004] Open Codex task two | READY |
| 4444J99/limen | #28 | [limen LIMEN-003] Open Codex task one | READY |
| 4444J99/limen | #29 | [limen LIMEN-004] Open Codex task two | READY |
| 4444J99/limen | #30 | [limen LIMEN-003] Open Codex task one | READY |
| 4444J99/limen | #31 | [limen LIMEN-004] Open Codex task two | READY |
| 4444J99/portfolio | #135 | chore(deps): bump @astrojs/mdx from 5.0.6 to 6.0.3 | READY |
| 4444J99/portfolio | #136 | chore(deps): bump dompurify from 3.4.5 to 3.4.11 | READY |
| 4444J99/vulnpulse | #7 | build(deps-dev): bump vitest from 2.1.9 to 4.1.9 in the npm_and_yarn group  | READY |
| a-organvm/a-i-chat--exporter | #38 | build(deps): bump the npm-deps group across 1 directory with 33 updates | READY |
| a-organvm/art-from--auto-revision-epistemic-engine | #5 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/art-from--narratological-algorithmic-lenses | #5 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/audio-synthesis-bridge | #10 | chore(deps): bump actions/checkout from 6.0.3 to 7.0.0 in the github-action | READY |
| a-organvm/chthon-oneiros | #7 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/classroom-rpg-aetheria | #142 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/classroom-rpg-aetheria | #143 | chore(deps): bump the npm-deps group across 1 directory with 4 updates | READY |
| a-organvm/client-sdk | #10 | chore(deps): bump actions/checkout from 6.0.3 to 7.0.0 in the github-action | READY |
| a-organvm/collective-persona-operations | #11 | chore(deps): bump actions/checkout from 4 to 7 | READY |
| a-organvm/editorial-standards | #9 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/essay-pipeline | #12 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/example-ai-collaboration | #6 | build(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/example-choreographic-interface | #11 | chore(deps): bump actions/checkout from 6.0.3 to 7.0.0 in the github-action | READY |
| a-organvm/fetch-familiar-friends | #219 | chore(deps): bump postcss and expo in /ios-app | READY |
| a-organvm/fetch-familiar-friends | #221 | chore(deps): bump brace-expansion and expo in /ios-app | READY |
| a-organvm/fetch-familiar-friends | #222 | chore(deps): bump node-forge from 1.3.3 to 1.4.0 in /ios-app | READY |
| a-organvm/fetch-familiar-friends | #223 | chore(deps): bump the npm-deps group across 1 directory with 7 updates | READY |
| a-organvm/gamified-coach-interface | #137 | build(deps): bump ws, engine.io, socket.io-adapter and engine.io-client in  | READY |
| a-organvm/gamified-coach-interface | #138 | build(deps): bump lodash from 4.17.21 to 4.18.1 in /backend | READY |
| a-organvm/gamified-coach-interface | #139 | build(deps): bump qs and express in /backend | READY |
| a-organvm/gamified-coach-interface | #140 | build(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/gamified-coach-interface | #141 | build(deps-dev): bump vitest from 4.1.8 to 4.1.9 in the npm-deps group acro | READY |
| a-organvm/hokage-chess | #5 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/hokage-chess | #6 | chore(deps-dev): bump the npm-deps group across 1 directory with 3 updates | READY |
| a-organvm/krypto-velamen | #10 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/life-my--midst--in | #133 | build(deps): Bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/linguistic-atomization-framework | #9 | chore(deps): update pdfplumber requirement from >=0.11.9 to >=0.11.10 in th | READY |
| a-organvm/my--father-mother | #4 | [limen jules GH-a-organvm-my-father-mother-1] ACTIVATION AUDIT: ship-now | READY |
| a-organvm/my-block-warfare | #22 | chore(deps): bump the npm_and_yarn group across 3 directories with 8 update | READY |
| a-organvm/my-block-warfare | #24 | chore(deps): bump codecov/codecov-action from 5 to 7 in the github-actions- | READY |
| a-organvm/my-block-warfare | #25 | chore(deps): bump the npm-deps group across 1 directory with 18 updates | READY |
| a-organvm/my-block-warfare | #26 | chore(deps-dev): bump vitest from 4.0.18 to 4.1.0 | READY |
| a-organvm/my-block-warfare | #27 | chore(deps-dev): bump postcss from 8.5.6 to 8.5.15 | READY |
| a-organvm/my-block-warfare | #28 | chore(deps): bump fast-uri from 3.1.0 to 3.1.2 | READY |
| a-organvm/my-block-warfare | #29 | chore(deps): bump the npm_and_yarn group across 2 directories with 8 update | READY |
| a-organvm/my-knowledge-base | #57 | build(deps): bump the github-actions-deps group across 1 directory with 3 u | READY |
| a-organvm/my-knowledge-base | #58 | build(deps): bump the npm-deps group across 1 directory with 17 updates | READY |
| a-organvm/narratological-algorithmic-lenses | #27 | chore(deps): bump the github-actions-deps group across 1 directory with 5 u | READY |
| a-organvm/narratological-algorithmic-lenses | #29 | chore(deps): bump esbuild, @vitejs/plugin-react and vite | READY |
| a-organvm/narratological-algorithmic-lenses | #30 | chore(deps-dev): bump the pip-deps group across 1 directory with 7 updates | READY |
| a-organvm/ops-witness | #4 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/orchestration-start-here | #171 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/parlor-games--ephemera-engine | #266 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/public-record-data-scrapper | #256 | chore(deps): bump the github-actions-deps group across 1 directory with 13  | READY |
| a-organvm/public-record-data-scrapper | #257 | chore(deps): bump node from 20-alpine to 26-alpine in the docker-deps group | READY |
| a-organvm/public-record-data-scrapper | #258 | chore(deps): bump undici from 5.29.0 to 7.24.8 in /cloudflare in the npm_an | READY |
| a-organvm/public-record-data-scrapper | #259 | chore(deps): bump ip-address from 10.1.0 to 10.2.0 | READY |
| a-organvm/public-record-data-scrapper | #260 | chore(deps): bump basic-ftp from 5.3.0 to 5.3.1 | READY |
| a-organvm/public-record-data-scrapper | #261 | chore(deps): bump qs and body-parser | READY |
| a-organvm/public-record-data-scrapper | #262 | chore(deps-dev): bump axios from 1.15.2 to 1.16.0 | READY |
| a-organvm/public-record-data-scrapper | #266 | chore(deps): bump ws from 6.2.3 to 6.2.4 | READY |
| a-organvm/public-record-data-scrapper | #267 | chore(deps): bump dompurify from 3.4.1 to 3.4.11 | READY |
| a-organvm/public-record-data-scrapper | #275 | chore(deps): bump js-yaml and react-native | READY |
| a-organvm/public-record-data-scrapper | #276 | chore(deps): bump form-data from 4.0.5 to 4.0.6 | READY |
| a-organvm/public-record-data-scrapper | #277 | chore(deps-dev): bump undici from 6.25.0 to 6.27.0 | READY |
| a-organvm/public-record-data-scrapper | #278 | chore(deps-dev): bump vite from 7.3.2 to 7.3.5 | READY |
| a-organvm/public-record-data-scrapper | #279 | chore(deps): bump tar from 7.5.13 to 7.5.16 | READY |
| a-organvm/reading-observatory | #9 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/reverse-engine-recursive-run | #11 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/search-local--happy-hour | #29 | chore(deps): bump the npm_and_yarn group across 1 directory with 2 updates | READY |
| a-organvm/search-local--happy-hour | #31 | chore(deps): bump the github-actions-deps group across 1 directory with 3 u | READY |
| a-organvm/search-local--happy-hour | #32 | chore(deps): bump the npm-deps group across 1 directory with 64 updates | READY |
| a-organvm/search-local--happy-hour | #33 | chore(deps): bump postcss from 8.5.3 to 8.5.15 | READY |
| a-organvm/search-local--happy-hour | #34 | chore(deps-dev): bump vitest from 4.0.18 to 4.1.0 | READY |
| a-organvm/shared-remembrance-gateway | #5 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/showcase-portfolio | #8 | chore(deps): bump rollup from 4.57.1 to 4.62.0 in /docs/source-materials/sp | READY |
| a-organvm/showcase-portfolio | #9 | chore(deps): bump astro from 6.4.6 to 6.4.8 in /docs/source-materials/specs | READY |
| a-organvm/sovereign-ecosystem--real-estate-luxury | #36 | chore(deps): bump the npm_and_yarn group across 1 directory with 4 updates | READY |
| a-organvm/sovereign-ecosystem--real-estate-luxury | #40 | chore(deps): bump the github-actions-deps group across 1 directory with 4 u | READY |
| a-organvm/sovereign-ecosystem--real-estate-luxury | #41 | chore(deps): bump the npm-deps group across 1 directory with 60 updates | READY |
| a-organvm/sovereign-ecosystem--real-estate-luxury | #42 | chore(deps): bump uuid from 11.1.0 to 14.0.0 | READY |
| a-organvm/sovereign-ecosystem--real-estate-luxury | #43 | chore(deps-dev): bump vitest from 4.0.18 to 4.1.0 | READY |
| a-organvm/sovereign-ecosystem--real-estate-luxury | #45 | chore(deps-dev): bump vite from 7.3.0 to 7.3.5 | READY |
| a-organvm/tab-bookmark-manager | #13 | chore(deps): bump qs and express in /backend | READY |
| a-organvm/tab-bookmark-manager | #15 | chore(deps): bump tmp and fengari in /backend | READY |
| a-organvm/tab-bookmark-manager | #16 | chore(deps): bump ip-address from 10.0.1 to 10.2.0 in /backend | READY |
| a-organvm/tab-bookmark-manager | #17 | chore(deps): bump lodash from 4.17.21 to 4.18.1 in /backend | READY |
| a-organvm/tab-bookmark-manager | #19 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/tab-bookmark-manager | #20 | chore(deps): bump the pip-deps group across 1 directory with 3 updates | READY |
| a-organvm/tab-bookmark-manager | #8 | chore(deps): bump ws and puppeteer in /backend | READY |
| a-organvm/trade-perpetual-future | #69 | chore(deps): bump actions/checkout from 6 to 7 in the github-actions-deps g | READY |
| a-organvm/trade-perpetual-future | #70 | chore(deps): bump the npm-deps group across 2 directories with 11 updates | READY |
| meta-organvm/glyph-cascade | #4 | chore(deps): bump the github-actions-deps group across 1 directory with 5 u | READY |
| meta-organvm/glyph-cascade | #5 | chore(deps): bump the npm-deps group across 1 directory with 6 updates | READY |
| meta-organvm/glyph-cascade | #6 | chore(deps): bump esbuild, @vitejs/plugin-react and vite | READY |
| meta-organvm/glyph-cascade-tapes | #6 | chore(deps): bump the npm-deps group across 1 directory with 7 updates | READY |
| meta-organvm/glyph-cascade-tapes | #7 | chore(deps): bump esbuild, @vitejs/plugin-react and vite | READY |
| organvm-i-theoria/conversation-corpus-engine | #49 | [limen LIMEN-056] IRF-CCE-035: Omega evidence map — note commercial spec fo | READY |
| organvm-i-theoria/rules-system-bound | #9 | [limen RESOLVE-organvm-i-theoria-rules-system-bound-8] resolve rules-system | READY |
| organvm-i-theoria/vigiles-aeternae--corpus-mythicum | #8 | chore(deps): bump actions/checkout from 6.0.3 to 7.0.0 in the github-action | READY |
| organvm-iii-ergon/content-engine--asset-amplifier | #28 | chore(deps): bump axios from 1.13.6 to 1.16.0 | READY |
| organvm-iii-ergon/sovereign-systems--elevate-align | #247 | chore(deps): bump the npm-deps group across 1 directory with 5 updates | READY |

---
*Read-only. No PR was merged, closed, or modified to produce this file.*
