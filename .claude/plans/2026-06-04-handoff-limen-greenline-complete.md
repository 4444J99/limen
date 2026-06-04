# Agent Handoff: Limen Buildout Shipped + CI/Deploy Greenline

**From:** Claude Code session (scope `-Users-4jp-Workspace-limen-runtime-status-fix-followup`) | **Date:** 2026-06-04 | **Phase:** COMPLETE → MONITOR
**Reciprocal to:** `.codex/plans/2026-06-03-limen-runtime-status-fix-handoff.md`

## Current State

- Repo: `/Users/4jp/Workspace/limen`, branch `main` at `ab2b583`, tracking `origin/main`, **worktree clean**.
- Worktree `/Users/4jp/Workspace/limen-runtime-status-fix-followup` (branch lineage merged): disposable; all content merged to main.
- **All four GitHub workflows green on main:** CI (`ab2b583`), validate (`2b5ddb9`), Deploy Dashboard (`64bd1c1`), Deploy API (`2d03833`).
- Live endpoints (verified this session):
  - Firebase Hosting `https://device-streaming-067d747a.web.app` — `public-status.json` 200, `tasks.json` 404.
  - Cloudflare Worker `https://limen-runtime.ivixivi.workers.dev` — passes strict probe (Deploy Dashboard live step).
- Repo secrets set: `LIMEN_API_TOKEN`, `LIMEN_CLIENT_TOKEN` (values from `.runtime/limen-worker-tokens.env`, never printed). Repo var: `LIMEN_API_URL` → Worker URL.

## Completed Work (PRs #1–#6, all merged to main)

- [x] **PR #1** — buildout commit `26b811e` (62 files: runtime adapters, spec/contracts, persona surfaces, CI/CD, tests, docs) + `77f3781` task states (Jules dispatch logs) + `38956ca` session handoff plans. Pre-commit secret-scan false positives resolved via 23 per-line `allow-secret` markers (verified parameter wiring only).
- [x] **PR #2** — fresh-checkout fixes: `mkdirSync` for `public/`; prebuild reorder (fetch-pr-status before validate:surfaces); validate.yaml rewritten in python3 (snap-yq lexer rejected `add`; required-fields step was always-fail by design); firebase-action pinned `v13`→`v15.19.1`; GCP-step guards.
- [x] **PR #3** — `secrets` context is invalid in step `if:` (workflows failed 0s at validation); mapped to job-level `env.GCP_SA_KEY_SET`.
- [x] **PR #4** — `web/app/app/public/page.tsx` was never committed: machine-global gitignore line 320 `public/` silently swallowed it from `git add -A`. Repo-level `!web/app/app/public/` negation + explicit `web/app/public/` ignore.
- [x] **PR #5** — CI python job generates surface snapshots before `validate-lifecycle-adapters.py` (reads gitignored `.generated/`).
- [x] **PR #6** — dropped redundant contract-schema check from python job (web job covers it post-generation).
- [x] Worktree divergence repaired at session start: rsync without `--delete` had resurrected `web/app/public/tasks.json` from HEAD; deletion restored, byte-parity with source verified.
- [x] Full live `verify-whole.sh` passed from the followup worktree (tokens sourced silently).
- [x] Merged remote+local fix branches deleted; source repo fast-forwarded; pre-reconcile stash verified-then-dropped.
- [x] Scope memory `limen-architecture-runtime-adapters` written + indexed (`~/.claude/projects/-Users-4jp-Workspace-limen/`).
- [x] Chezmoi template anchored summary refreshed (commit `410b958` in domus-semper-palingenesis, pushed; constitution-budget gate passed 2735/3500).

## Key Decisions

| Decision | Rationale |
|---|---|
| Three atomic commits in PR #1 (buildout / task states / plans) | Rule #11; revert-safety; `git log --grep` findability. Unique data (dispatch logs, plans) must never stay local-only (Rule #2). |
| `allow-secret` markers over `--no-verify` | Auditable per-line bypass trail; hook's own sanctioned mechanism. |
| Skip-with-notice when `GCP_SA_KEY` absent (not red, not silent) | Hourly scheduled deploy would alert-fatigue red; silent skip hides state. `::notice::` is honest. |
| Each validator runs once, where its inputs exist | python job: lifecycle (needs CLI + snapshots); web job: schemas (needs full generation incl. pr-status.json). |
| Did NOT provision `GCP_SA_KEY` | Requires minting a GCP SA key + Secret Manager entries incl. a GitHub PAT — credentials only the human can mint. Genuine blocker class. |
| Repo-local gitignore hardening (node_modules/.next/out/.wrangler/.generated) | Machine-global ignore is invisible to CI/other clones; repo .gitignore is the contract. |

## Critical Context

- **Machine-global gitignore (`~/.config/git/ignore`) has broad rules (`public/` L320, `out/` L144, `node_modules/` L279, `.next/` L312).** Any new route/dir named `public`, `out`, etc. will be silently excluded from `git add` unless the repo negates it. Sweep with `git status --porcelain --ignored=matching` when adding routes.
- Owner `/api/status` is summary-only; raw tasks ONLY via owner-only `/api/tasks`. Never restore `web/app/public/tasks.json`. Never weaken `scripts/probe-runtime-adapter.py` (`owner status.tasks is not allowed` is correct).
- `web/app/.generated/` and `web/app/public/*.json` are regenerated artifacts (gitignored); only generators are source.
- The repo pre-commit hook (global, `~/.config/git/hooks/pre-commit`) flags any `token=value` assignment; `allow-secret` per line is the bypass; values starting `$`/`op://` are exempt.
- Dependabot uv dependency-graph job fails on `mcp/uv.lock` — `uv lock --check` passes locally (lock revision 3); GitHub-side parser limitation, gates nothing.
- Worker deploys: `npm --prefix web/worker run deploy` (Wrangler). Hosting deploys: manual `firebase deploy --only hosting --project device-streaming-067d747a` AFTER `verify-whole.sh` passes.
- 16GB machine: sequential installs/builds; no LaunchAgents ever.

## Next Actions

1. **Nothing is required for green.** System is verified end-to-end.
2. If/when CI-driven deploys are wanted: provision GCP service account (Firebase Hosting admin at minimum; Cloud Run additionally needs Secret Manager entries `limen-github-token`/`limen-api-token`/`limen-client-token` and a GitHub PAT) → `gh secret set GCP_SA_KEY --repo 4444J99/limen < key.json`. Note: setting it makes deploy-api RUN — it will fail at preflight until Secret Manager is provisioned; do both together or neither.
3. If hosted boundary changes: full live verify → deploy → smoke 200/404 (commands in reciprocal handoff).
4. Optional cleanup: `git worktree remove /Users/4jp/Workspace/limen-runtime-status-fix-followup` (content fully merged) + `git branch -d fix/dedupe-schema-check` (checked out there).
5. PyPI token for CLI publishing remains unconfigured (pre-existing item).

## Risks & Warnings

- Do not re-litigate the greenline fixes — each was CI-verified on merge.
- `tasks.yaml` is the live board; mutations only via sanctioned flows.
- Do not print `.runtime/limen-worker-tokens.env` values; source silently.
- `git add -A` is unsafe in this environment for new dirs named like global-ignored patterns — verify with `git status --ignored` after.

## Conflict Zones

| Path | Rule |
|---|---|
| `tasks.yaml` | Live board; explicit approval for mutation |
| `web/api/main.py`, `web/worker/src/index.js` | Status summary-only contract; keep Worker deploy aligned with source |
| `web/app/public/` | Generated public-safe JSON only; gitignored; never hand-add |
| `web/app/.generated/` | Generated snapshots; never hand-edit |
| `.github/workflows/*` | Green as of `ab2b583`; secrets-in-if is invalid — use job env mapping |
| `.runtime/limen-worker-tokens.env` | Secret-bearing; source silently |

## Recovery Protocol

1. Read this handoff + reciprocal `.codex/plans/2026-06-03-limen-runtime-status-fix-handoff.md`.
2. Verify: `git -C ~/Workspace/limen status --short` (expect clean) and `gh run list --repo 4444J99/limen --branch main --limit 4` (expect green).
3. Live smoke: `public-status.json` 200 / `tasks.json` 404 on the hosting domain.
4. Treat any red as new regression, not as this session's residue.
