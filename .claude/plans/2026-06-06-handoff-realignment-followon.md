# Agent Handoff: _limen/limen realignment → follow-on ops

**From:** Session e95eb0c4 (bg job; transcript 5330f128, scope `-Users-4jp--limen`) | **Date:** 2026-06-06 | **Phase:** realignment CLOSED → steady-state ops
**Reciprocal to:** `.claude/plans/2026-06-04-handoff-limen-greenline-complete.md` (greenline chain) and `~/Workspace/4444J99/portvs/config/_limen/decisions/2026-06-05-charter-restoration.md` (governance-side record)

## Current State (verified against disk/remote 2026-06-06)

- **Two repos, namesakes, NOT one organ:**
  - `limen` (this repo) — task-runtime product, `~/Workspace/limen`, remote `4444J99/limen`. HEAD `119bf64`, working tree clean, main even with origin.
  - `_limen` — home-spatial governance, canonical `~/_portal/config/_limen` (physical `~/Workspace/4444J99/portvs/config/_limen`), remote `4444J99/_limen`. HEAD `8474ea1`, main even with origin. Working tree carries **other-agent state** (staged `sessions/handoff-2026-06-05-heartbeat-genealogy-closeout.md`; untracked `decisions/2026-06-01-portal-out-items.md`, `.MOVED-TO.md`, `.claude/`) — not this arc's; do not absorb or revert.
  - Home-root `/Users/4jp/_limen` is a **tombstone husk** (`.MOVED-TO.md`, 3 stanzas). Never write there; never anchor anything to it.
- **Auto-scaler live:** `scripts/auto-scale.py` + `.github/workflows/auto-scale.yml` (workflow ID 290088687, cron `0 */4 * * *`, `permissions: contents: write`). Three consecutive scheduled runs green: 27049795293 (02:15Z), 27055383859 (06:47Z), 27059185004 (09:55Z) — all correct no-ops at depth 100, no spurious commits.
- **Task board:** `tasks.yaml` dict `{version, portal, tasks}` (NOT a bare list), 100 LIMEN-XXX entries, depth target `portal.budget.daily`.

## Completed Work (the realignment arc — all pushed)

- [x] Diagnosed namesake conflation; routed 10 product artifacts out of the governance repo into this repo's conventions (`.claude/plans/` 2026-06-01 docs, `GEMINI.md`, `.gemini/`) — product commit landed as `119bf64`.
- [x] Restored governance charter: `decisions/2026-06-05-charter-restoration.md` + 11 LEDGER.tsv rows; registry/namespaces.yaml re-narrowed; MANIFEST operational-axis trued — governance commits `6c34020`, `8474ea1`.
- [x] Shut all four husk-accretion valves: `bin/scan-home.sh` BASH_SOURCE anchor (was `PORTAL=$HOME/_limen` hardcode), archiver `archive_dir`, Gemini project anchors (`~/.gemini/projects.json` + `.project_root`), scheduler routine path (`session-meta` commit `b19a361e`, **local-only — session-meta push is the user's**).
- [x] Extracted the auto-scaler from an inline workflow blob to `scripts/auto-scale.py`, schema-adapted (dict schema, §2.2 fields, `status: open`, pagination, idempotent URL dedup), adversarially reviewed and fixed (`permissions: contents: write`, pull-rebase-push idiom, no `dispatched` without claim).
- [x] End-to-end production proof: remote bytes byte-identical to verified local; 3 scheduled runs green.
- [x] Memories trued: home-scope `project_artifact_2026_05_26_limen_portal.md`; limen-scope `limen-vs-limen-underscore-namesakes.md`.

## Key Decisions (do not re-litigate)

| Decision | Rationale |
|----------|-----------|
| `_limen` ≠ `limen` — reference, never absorb | Same Latin word, different organs; conflation was the root failure |
| New task entries start `status: open`, never `dispatched` | SCHEMA.md §2.3 state machine: `dispatched` requires an agent claim + dispatch_log |
| Workflow needs `permissions: contents: write` | Default GITHUB_TOKEN is read-only; scheduled push 403s without it |
| `scan-home.sh` anchors via `BASH_SOURCE`, never `$HOME/_limen` | The hardcode was the valve that kept re-creating the retired husk |
| Move-with-retirement + MOVED-TO breadcrumbs, never `rm` | "Nothing is junk by default" — governance prime directive |
| Pathspec-limited commits (`git commit -- <paths>`) | Avoids bundling the user's in-flight staged/dirty work |
| `# allow-secret — env read, no literal` on auto-scale.py:31 | Secret-scan hook false-positives on `os.getenv("GITHUB_TOKEN")` |

## Critical Context

- **Push-to-main authorization does NOT carry over between sessions** — re-ask before any push to main (branch-governance contract; also: public-ORGANVM rule).
- Never print `.runtime/limen-worker-tokens.env` values; never restore `web/app/public/tasks.json`; never weaken `scripts/probe-runtime-adapter.py`.
- Protected data files (`registry-v2.json`, `governance-rules.json`, `system-metrics.json`, any `seed.yaml`, `prompt-atoms.json`): read-before-write, targeted edits only.
- `session-meta/clean-main` holds `b19a361e` plus the user's ~40-commit backlog — its push is the user's, not an agent's.
- GitHub cron ticks at high-load minutes get delayed (the 00:00Z tick fired 02:15Z) — a "late" run is normal, not a failure.
- zsh reserves `status` as read-only — monitor/eval scripts must use other variable names.
- 16GB RAM machine with logged jetsam kills — cap concurrent heavy processes.

## Next Actions

1. **Verification sweep:** `git fetch` + status both repos; `gh run list -R 4444J99/limen --workflow=auto-scale.yml --limit 5`; confirm runs since 27059185004 stay green and `tasks.yaml` remains SCHEMA §2.2/§2.3-conformant.
2. **Objective (conductor fills/confirms):** advance the LIMEN-XXX board per SCHEMA.md §2.3, or add tests around `scripts/auto-scale.py`.
3. Commit atomically on the worktree branch (`ops/2026-06-06-realignment-followon` under `.claude/worktrees/`); ask before any push to main.
4. User-held items — surface only if they block: `GCP_SA_KEY` provisioning (enables CI Cloud Run deploys), PyPI token (CLI publishing).

### Launch recipe (terminal)

```zsh
cd ~/Workspace/limen && git fetch origin
grep -qx '.claude/worktrees/' .git/info/exclude 2>/dev/null || echo '.claude/worktrees/' >> .git/info/exclude
git worktree add .claude/worktrees/limen-ops-2026-06-06 -b ops/2026-06-06-realignment-followon origin/main
cd .claude/worktrees/limen-ops-2026-06-06 && claude
```

## Risks & Warnings

- The scaler writes `tasks.yaml` via `yaml.dump` — any hand-edits relying on comments/ordering inside `tasks:` will be normalized away on the next non-no-op run.
- Auto-scale push races a concurrent main commit → the workflow's `git pull --rebase origin main` handles it, but check run logs if one ever fails.
- The governance repo's untracked working-tree items (see Current State) belong to another arc — coordinate before any cleanup there.
- Launch limen-scope sessions from `~/_portal/config/_limen` or `~/Workspace/limen` only — a session anchored at the husk re-opens the accretion valve behaviorally.
