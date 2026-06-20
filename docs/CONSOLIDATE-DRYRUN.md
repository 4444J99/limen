# GitHub Consolidation — Dry-Run Report

> Subject: settled-but-unexecuted decision in `START-HERE.md` §4 — collapse the
> fragmented multi-owner GitHub estate into ONE org `organvm`, with source
> "spheres" demoted from org boundaries to repo **topics**.
> Tool: `scripts/consolidate-github.py` (executes nothing without `--apply`).
> Mode: **DRY-RUN ONLY. Nothing was executed. No transfer, no topic, no write.**
> Date: 2026-06-19 · gh authed as `4444J99` (scopes `gist, read:org, repo`).

## 1. Verified current state (read-only `gh` queries)

| Owner | Repos |
|---|---:|
| 4444J99 (personal) | 84 |
| a-organvm | 143 |
| meta-organvm | 10 |
| organvm-i-theoria | 23 |
| organvm-ii-poiesis | 6 |
| organvm-iii-ergon | 8 |
| organvm-iv-taxis | 4 |
| organvm-v-logos | 3 |
| organvm-vi-koinonia | 3 |
| organvm-vii-kerygma | 3 |
| **TOTAL (source)** | **287** |
| `organvm` (TARGET) | **0 (empty)** |

- **Current owners: 11** (10 source owners + the empty target `organvm`). The
  script's `OWNERS` list enumerates the 10 sources and excludes `organvm` itself.
- **Current repos: 287** across the 10 source owners. (The "287 across 11 owners"
  framing in START-HERE counts the empty target as the 11th owner.)
- Target `organvm` exists, is empty, plan = **free** (private-repo cap 10000), and
  `4444J99` is an **active admin** on it.

## 2. What the dry-run printed

```
=== consolidation plan → organvm ===
  287 repos across 10 owners
  name collisions (must rename before transfer): 15
```

The tool reports **15 collision name-groups**. The headline number understates the
blast radius: `--apply` skips **every repo whose name appears in any collision
group**, on both sides of the collision. Recomputed from the same data:

- **Repos that WOULD MOVE on `--apply`: 250**
- **Repos SKIPPED (name in a collision group): 37** (not 15)

So a single `--apply` run is **partial by design**: it would leave 37 repos behind
across their original owners until the collisions are hand-resolved (rename one side
first). The 15 collision groups:

- `.github` — 9 owners share this special org-profile repo (the worst collision;
  these are not "products", they are per-org profile/default repos)
- `*.github.io` Pages repos: `4444J99.github.io`, `meta-organvm.github.io`, and the
  seven `organvm-*.github.io` (each duplicated under `organvm-i-theoria`)
- product/contrib dups: `content-engine--asset-amplifier`, `contrib--dapr-dapr`,
  `contrib--notion-mcp-server`, `hokage-chess`, `sovereign--ground`,
  `studium-generale`

## 3. Risk surface (verified across all 287)

| Risk | Measure | Note |
|---|---|---|
| **Token scope (BLOCKER)** | scopes = `gist, read:org, repo` | **No `admin:org`.** Repo transfer (`POST /repos/{o}/{r}/transfer`) needs admin on source AND ability to create in the target org. Org-owned → org-owned transfers typically require `admin:org`. **`--apply` will likely fail or partially fail with the current token.** |
| **Collisions** | 15 groups → **37 repos skipped** | `--apply` is partial; collisions need manual rename first. `.github` (9-way) and the Pages repos can't all land at `organvm/<name>`. |
| **Forks** | 29 repos are forks | Transferring forks can sever the upstream fork relationship / network; behavior varies. Review the 29 before moving. |
| **Stars** | 54 total, 32 repos starred | Transfer **preserves** stars and watchers (GitHub moves them). Low absolute count; low risk. Top: `a-organvm/a-i--skills` (8), `4444J99.github.io` (5), `agentic-titan` (5). |
| **Inbound forks** | 11 repos have forks (19 total) | Downstream forks keep working via redirect; relationship preserved. |
| **Issue/PR refs** | preserved by transfer | Cross-repo `owner/repo#N` references auto-redirect. Plain-text mentions of the old `owner/repo` in code/docs do **not** rewrite. |
| **CI coupling (real)** | `.github/workflows/deploy-api.yml:53` hardcodes `LIMEN_GITHUB_REPO=4444J99/limen` | Workflow files transfer with the repo but this **literal env string** does not redirect — Cloud Run would point at the old owner string. Must be edited post-move. |
| **Source coupling** | tasks.yaml has **678 `repo:` refs** to old owners (a-organvm 331, 4444J99 165, theoria 77, ergon 55, …) | Git/API URLs redirect, but the fleet's local-checkout + PR logic keys on these literal `owner/repo` strings. High churn; needs a coordinated rewrite of tasks.yaml + a re-clone/remote-update of `~/Workspace` checkouts. |
| **Visibility** | 203 public / 84 private | Private repos move into a free org (cap 10000, fine). No public→private surprise; transfer keeps visibility. |
| **Archived** | 12 archived | Archived repos can be transferred but topic-set may fail while archived; low value to move. |
| **`limen` self-move** | repo `limen` is in the move set (topic:personal) | Moving the conductor's own repo mid-flight risks the running daemon, deploy workflows, and the auto-scale cron that pushes tasks.yaml. Move `limen` **last**, deliberately, not in a bulk pass. |

## 4. Reversibility

**Reversible — with caveats.**
- GitHub repo transfer is reversible: transfer back to the original owner, and old
  URLs auto-redirect in the meantime. Stars/issues/PRs/wiki travel both ways. The
  tool **never deletes** (no `delete_repo` scope, no delete call in source).
- **Not auto-reverted:** topics added by the tool (`+topic:sphere-*`) and any
  manual collision renames stay until undone by hand. The 678 tasks.yaml refs and
  the `deploy-api.yml` literal would need to be edited forward and (if reverting)
  edited back. So the *org membership* is cleanly reversible; the *config rewrites
  it forces* are manual on both legs.

## 5. Recommendation: DO NOT `--apply` yet — fix three things first

The decision (one org, spheres-as-topics, one repo per product) is sound and the
tool is safe (dry-run, no-delete, transfer-not-copy). But running `--apply` today
would (a) likely **fail on auth** and (b) even if it worked, **break the live fleet**
via the 678 tasks.yaml refs and the hardcoded deploy env. Prerequisites:

1. **Grant `admin:org` (or `workflow`) scope** to the gh token, or run the transfer
   with a GitHub App / PAT that has org-admin on `organvm`. Verify with a single
   manual transfer of one low-stakes repo before any bulk run. This aligns with the
   `limen[bot]` GitHub-App-as-fleet-identity goal in START-HERE §4.
2. **Resolve the 15 collisions first** (rename the loser side, especially the 9-way
   `.github` and the `*.github.io` Pages repos) so `--apply` moves 287 not 250.
   Decide which `.github`/Pages repo is canonical for `organvm`.
3. **Plan the config rewrite as part of the cutover**, not after: a follow-up pass
   to rewrite tasks.yaml `repo:` owners → `organvm/...`, fix
   `deploy-api.yml:LIMEN_GITHUB_REPO`, and update `~/Workspace` git remotes. Move
   `limen` itself LAST.

Sequence: scope-fix → resolve collisions → dry-run again (expect 287/0 skipped) →
`--apply` in waves (archived + low-value first, `limen` last) → rewrite configs →
verify fleet → confirm reversibility on one repo.

This is one of the four human-gated triggers named in START-HERE ("`consolidate-github
--apply`"). It stays gated.

## 6. Exact apply command (DO NOT RUN — gated on the user)

```bash
cd ~/Workspace/limen && export LIMEN_ROOT="$PWD" LIMEN_TASKS="$PWD/tasks.yaml" \
  LIMEN_WORKDIR="$HOME/Workspace" PYTHONPATH="$PWD/cli/src"
python3 scripts/consolidate-github.py --apply
```

(With the current token this would transfer the 250 non-colliding repos, skip 37,
and — per §3 — likely error on org-owned source transfers for lack of `admin:org`.
Do not run until §5 prerequisites are met.)
