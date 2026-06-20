# Collision Rename Plan — make `consolidate-github --apply` move 287, skip 0

> Companion to `docs/CONSOLIDATE-DRYRUN.md` §2 (the 15 name-collision groups).
> Goal: resolve every collision by **renaming the loser side** so that after the
> renames each colliding name is globally unique → `scripts/consolidate-github.py
> --apply` transfers **all** repos and **skips 0** (today it would skip 37 across
> 15 groups).
> Mode: **PLAN ONLY. Nothing executed here. No rename, transfer, or push.**
> Source of truth: live `gh repo list` across the 10 source owners
> (read-only, GraphQL/core API — does NOT consume the scarce `search` quota).
> Date: 2026-06-20 · gh authed as `4444J99`.

## 0. How the collision logic actually works (why renaming is the only lever)

`scripts/consolidate-github.py` groups repos by **lowercased name** (`by_name[name.lower()]`)
and, on `--apply`, **skips every repo whose lowercased name appears in any group with >1
member** — on *both* sides of the collision (`if name.lower() in colliding_names: skipped += 1`).

The script has **no skip-and-transfer-as-org-prefixed path**; the only mechanism that
clears a collision is to make the names unique. Therefore for each group of N colliding
repos we keep **one canonical** (it keeps its name and lands at `organvm/<name>`) and
**rename the other N−1 losers** to globally-unique disambiguated names. After the rename
the canonical *and* every renamed loser transfer — so the whole estate lands.

`gh repo rename` performs an in-place rename and GitHub keeps a redirect from the old
name, so existing clones/links keep resolving. It is reversible (rename back). It does
**not** move the repo between owners — the subsequent `--apply` does the move.

## 1. Live collision counts (recomputed 2026-06-20)

| | Count |
|---|---:|
| Source repos (10 owners) | **288** (dossier said 287; +1 new repo under `4444J99` since the 06-19 dry-run) |
| Collision groups | **15** |
| Repos currently skipped by `--apply` (name in a group) | **37** |
| Loser-side renames in this plan | **22** |
| Repos that move after renames | **288 / skip 0** |

The 22 renames break down as: `.github` 9-way → keep 1, rename 8 · the 8 `*.github.io`
Pages groups → keep 1 each, rename 8 · the 6 product/contrib dups → keep 1 each, rename 6.
(8 + 8 + 6 = 22.) Every rename target below was checked against all 288 existing
lowercased names and is **globally unique** — no secondary collisions are introduced.

---

## 2. Group-by-group decisions

Naming convention for losers: `<name>--<disambiguator>` where the disambiguator encodes
**why this side lost** (owner / `-fork` / `-archived` / `-copy`). The `.github` losers use
`dot-github--<sphere>` because a leading-dot repo name is reserved for the special profile
repo and we are demoting these to ordinary repos.

### Group 1 — `.github` (9-way) — the org-profile repos
Members: `4444J99/.github`, `meta-organvm/.github`, `organvm-i-theoria/.github`,
`organvm-ii-poiesis/.github`, `organvm-iii-ergon/.github`, `organvm-iv-taxis/.github`,
`organvm-v-logos/.github`, `organvm-vi-koinonia/.github`, `organvm-vii-kerygma/.github`
(all public, none archived/forked).

- **CANONICAL → keeps name → `organvm/.github`:** `meta-organvm/.github`.
  Rationale: a `.github` repo only has org-profile/default-config meaning at the org root.
  After consolidation the single org is `organvm`, so exactly **one** `.github` may keep
  the name and act as `organvm`'s profile. `meta-organvm` is the *meta/umbrella* org —
  its profile is the most org-wide, generic default (vs. the sphere-specific ones), so it
  is the right one to become `organvm`'s profile.
- **LOSERS (rename, 8):** the per-sphere and personal `.github` repos are demoted to
  ordinary content repos under disambiguated names, then transferred (their profile role
  dies with their source org, which is the intended outcome of the consolidation).

### Groups 2–9 — `*.github.io` Pages repos (8 two-way groups)
Pattern: the **correctly-owned** Pages site (`<owner>/<owner>.github.io`, where the repo
name matches its owner — the only place GitHub Pages user/org sites actually serve from)
is canonical; the **misfiled duplicate copy living under `organvm-i-theoria`** is the
loser. (`organvm-i-theoria` is holding a shadow copy of nearly every other org's Pages
repo; those copies cannot serve as Pages from `theoria` anyway, so they lose.)

| Group | CANONICAL (keeps name → `organvm/<name>`) | LOSER (rename + move) | Note |
|---|---|---|---|
| 2 `4444j99.github.io` | `4444J99/4444J99.github.io` | `organvm-i-theoria/4444J99.github.io` | theoria copy |
| 3 `meta-organvm.github.io` | `meta-organvm/meta-organvm.github.io` | `organvm-i-theoria/meta-organvm.github.io` | theoria copy |
| 4 `organvm-ii-poiesis.github.io` | `organvm-ii-poiesis/organvm-ii-poiesis.github.io` | `organvm-i-theoria/organvm-ii-poiesis.github.io` | theoria copy |
| 5 `organvm-iii-ergon.github.io` | `organvm-iii-ergon/organvm-iii-ergon.github.io` | `organvm-i-theoria/organvm-iii-ergon.github.io` | theoria copy is **archived** → safe loser |
| 6 `organvm-iv-taxis.github.io` | `organvm-iv-taxis/organvm-iv-taxis.github.io` | `organvm-i-theoria/organvm-iv-taxis.github.io` | theoria copy |
| 7 `organvm-v-logos.github.io` | `organvm-v-logos/organvm-v-logos.github.io` | `organvm-i-theoria/organvm-v-logos.github.io` | theoria copy |
| 8 `organvm-vi-koinonia.github.io` | `organvm-vi-koinonia/organvm-vi-koinonia.github.io` | `organvm-i-theoria/organvm-vi-koinonia.github.io` | theoria copy |
| 9 `organvm-vii-kerygma.github.io` | `organvm-vii-kerygma/organvm-vii-kerygma.github.io` | `organvm-i-theoria/organvm-vii-kerygma.github.io` | theoria copy |

Note: `organvm-i-theoria.github.io` is **not** a collision — only `organvm-i-theoria`
owns it — so it moves untouched and is not in this plan.

### Group 10 — `content-engine--asset-amplifier`
Members: `a-organvm/...` (**archived, private**) vs `organvm-iii-ergon/...` (public, active).
- **CANONICAL:** `organvm-iii-ergon/content-engine--asset-amplifier` (active, public, in
  the ergon "product" sphere where it belongs).
- **LOSER (rename):** `a-organvm/content-engine--asset-amplifier` (archived dup).
  ⚠ **Archived repos cannot be renamed** — unarchive first (command included below),
  rename, then it transfers; re-archive after the move if desired.

### Group 11 — `contrib--dapr-dapr`
Members: `4444J99/...` (**fork**, public) vs `a-organvm/...` (public, not a fork).
- **CANONICAL:** `a-organvm/contrib--dapr-dapr` (the canonical non-fork copy).
- **LOSER (rename):** `4444J99/contrib--dapr-dapr` (personal fork). ⚠ Renaming a fork is
  fine; the upstream-fork relationship is unaffected by rename (it is the *transfer* that
  may touch the fork network — see dossier §3 "Forks").

### Group 12 — `contrib--notion-mcp-server`
Members: `4444J99/...` (**fork**, public) vs `a-organvm/...` (public, not a fork).
- **CANONICAL:** `a-organvm/contrib--notion-mcp-server`.
- **LOSER (rename):** `4444J99/contrib--notion-mcp-server` (personal fork).

### Group 13 — `hokage-chess`
Members: `4444J99/...` (private) vs `a-organvm/...` (public).
- **CANONICAL:** `a-organvm/hokage-chess` (public, in the org).
- **LOSER (rename):** `4444J99/hokage-chess` (personal private dup).

### Group 14 — `sovereign--ground`
Members: `4444J99/...` (private) vs `organvm-i-theoria/...` (private).
- **CANONICAL:** `organvm-i-theoria/sovereign--ground` (lives in a sphere org, not the
  personal account; identity-from-remote prefers the org placement).
- **LOSER (rename):** `4444J99/sovereign--ground` (personal dup).

### Group 15 — `studium-generale`
Members: `4444J99/...` (public) vs `organvm-i-theoria/...` (private).
- **CANONICAL:** `organvm-i-theoria/studium-generale` (org placement preferred over the
  personal account, consistent with the other dups).
- **LOSER (rename):** `4444J99/studium-generale` (personal dup).

---

## 3. EXACT executable commands (LOSER side only — GATED, do not run until cutover)

Run from anywhere with `gh` authed as an admin of the listed owners. These are **renames
only** (in-place, reversible, redirect preserved) — they do **not** move repos; the
subsequent `consolidate-github.py --apply` does the move. One archived loser needs an
unarchive first (flagged).

```bash
# ── Group 1: .github 9-way — keep meta-organvm/.github, rename the other 8 ──
gh repo rename dot-github--4444j99   --repo 4444J99/.github
gh repo rename dot-github--theoria   --repo organvm-i-theoria/.github
gh repo rename dot-github--poiesis   --repo organvm-ii-poiesis/.github
gh repo rename dot-github--ergon     --repo organvm-iii-ergon/.github
gh repo rename dot-github--taxis     --repo organvm-iv-taxis/.github
gh repo rename dot-github--logos     --repo organvm-v-logos/.github
gh repo rename dot-github--koinonia  --repo organvm-vi-koinonia/.github
gh repo rename dot-github--kerygma   --repo organvm-vii-kerygma/.github

# ── Groups 2–9: *.github.io Pages — keep the correctly-owned site, rename the theoria copies ──
gh repo rename pages--theoria-copy--4444j99       --repo organvm-i-theoria/4444J99.github.io
gh repo rename pages--theoria-copy--meta-organvm  --repo organvm-i-theoria/meta-organvm.github.io
gh repo rename pages--theoria-copy--poiesis       --repo organvm-i-theoria/organvm-ii-poiesis.github.io
# Group 5 loser is ARCHIVED — unarchive, rename, (optionally re-archive after the move):
gh repo unarchive organvm-i-theoria/organvm-iii-ergon.github.io --yes
gh repo rename pages--theoria-copy--ergon         --repo organvm-i-theoria/organvm-iii-ergon.github.io
gh repo rename pages--theoria-copy--taxis         --repo organvm-i-theoria/organvm-iv-taxis.github.io
gh repo rename pages--theoria-copy--logos         --repo organvm-i-theoria/organvm-v-logos.github.io
gh repo rename pages--theoria-copy--koinonia      --repo organvm-i-theoria/organvm-vi-koinonia.github.io
gh repo rename pages--theoria-copy--kerygma       --repo organvm-i-theoria/organvm-vii-kerygma.github.io

# ── Group 10: content-engine--asset-amplifier — keep ergon, rename the a-organvm archived dup ──
gh repo unarchive a-organvm/content-engine--asset-amplifier --yes
gh repo rename content-engine--asset-amplifier--a-organvm-archived --repo a-organvm/content-engine--asset-amplifier

# ── Groups 11–15: product/contrib dups — keep the org/non-fork side, rename the loser ──
gh repo rename contrib--dapr-dapr--4444j99-fork          --repo 4444J99/contrib--dapr-dapr
gh repo rename contrib--notion-mcp-server--4444j99-fork  --repo 4444J99/contrib--notion-mcp-server
gh repo rename hokage-chess--4444j99                     --repo 4444J99/hokage-chess
gh repo rename sovereign--ground--4444j99                --repo 4444J99/sovereign--ground
gh repo rename studium-generale--4444j99                 --repo 4444J99/studium-generale
```

## 4. Verification (after renames, before `--apply`)

```bash
cd ~/Workspace/limen && export LIMEN_ROOT="$PWD" LIMEN_TASKS="$PWD/tasks.yaml" \
  PYTHONPATH="$PWD/cli/src"
python3 scripts/consolidate-github.py        # expect: "name collisions ... : 0"
# then the gated --apply (still subject to the dossier §5 admin:org token prereq):
# python3 scripts/consolidate-github.py --apply   # expect: moved 288, skipped 0
```

## 5. Canonical-keeper summary (the repos that retain their name → `organvm/<name>`)

| Group | Canonical keeper |
|---|---|
| `.github` | `meta-organvm/.github` |
| `4444j99.github.io` | `4444J99/4444J99.github.io` |
| `meta-organvm.github.io` | `meta-organvm/meta-organvm.github.io` |
| `organvm-ii-poiesis.github.io` | `organvm-ii-poiesis/organvm-ii-poiesis.github.io` |
| `organvm-iii-ergon.github.io` | `organvm-iii-ergon/organvm-iii-ergon.github.io` |
| `organvm-iv-taxis.github.io` | `organvm-iv-taxis/organvm-iv-taxis.github.io` |
| `organvm-v-logos.github.io` | `organvm-v-logos/organvm-v-logos.github.io` |
| `organvm-vi-koinonia.github.io` | `organvm-vi-koinonia/organvm-vi-koinonia.github.io` |
| `organvm-vii-kerygma.github.io` | `organvm-vii-kerygma/organvm-vii-kerygma.github.io` |
| `content-engine--asset-amplifier` | `organvm-iii-ergon/content-engine--asset-amplifier` |
| `contrib--dapr-dapr` | `a-organvm/contrib--dapr-dapr` |
| `contrib--notion-mcp-server` | `a-organvm/contrib--notion-mcp-server` |
| `hokage-chess` | `a-organvm/hokage-chess` |
| `sovereign--ground` | `organvm-i-theoria/sovereign--ground` |
| `studium-generale` | `organvm-i-theoria/studium-generale` |

## 6. Caveats

- **Two archived losers** (`organvm-i-theoria/organvm-iii-ergon.github.io` and
  `a-organvm/content-engine--asset-amplifier`) must be **unarchived before rename** —
  `gh repo rename` fails on archived repos. Re-archive after the move if desired.
- **`gh repo rename` requires admin** on each source owner; the consolidation `--apply`
  additionally needs `admin:org` (dossier §3 BLOCKER) — resolve the token scope first.
- **Pages serving:** the renamed theoria `*.github.io` copies stop being valid Pages
  sites (a user/org Pages site must be named `<owner>.github.io`). They were shadow
  copies under the wrong owner and never served, so nothing live breaks; the canonical
  keepers continue to serve until/after the move.
- Renames create GitHub **redirects** from the old name, so existing links/clones keep
  resolving — the operation is reversible (`gh repo rename` back).
- This plan is keyed to the **live** 2026-06-20 estate (288 repos). Re-run the
  collision recompute if the estate changes before execution.
