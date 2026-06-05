# Agent Handoff: Limen Throughput Ledger + Public Dashboard

**From:** Codex session | **Date:** 2026-06-05T01:11:56Z | **Phase:** COMPLETE -> MERGE/MONITOR

## Current State

- Repo: `/Users/4jp/Workspace/limen-next`
- Branch: `claude/limen-next`
- Head: `a4482d0` before this handoff artifact; PR branch tracks `origin/claude/limen-next`.
- PR: `https://github.com/4444J99/limen/pull/7`
- PR status at handoff: `CLEAN`.
- PR checks green: CI `python`, CI `worker`, CI `web`, Sourcery review, Semgrep scan.
- Main remains at `37f45ac`; PR #7 is not merged yet.
- Live Worker deployed from this PR branch:
  - URL: `https://limen-runtime.ivixivi.workers.dev`
  - Worker version: `46a8179b-6682-4912-b521-6d1bfca2e6fc`
- Live Firebase dashboard deployed from this PR branch:
  - URL: `https://device-streaming-067d747a.web.app`
  - Root now shows the aggregate-only public cockpit instead of the owner token gate.
- Live public boundary:
  - `https://device-streaming-067d747a.web.app/public-status.json` -> `HTTP/2 200`
  - `https://device-streaming-067d747a.web.app/tasks.json` -> `HTTP/2 404`

## Completed Work

- [x] Added throughput accounting to FastAPI owner/public summary.
- [x] Added throughput accounting to Cloudflare Worker owner/public summary.
- [x] Added throughput accounting to CLI `limen status`.
- [x] Added `throughput` to `spec/contracts/status-summary.schema.json`.
- [x] Added static generation support for throughput in public/internal generated contracts.
- [x] Changed public visible wording from debt language to `Unrecorded capacity`.
- [x] Made `/` the aggregate-only public cockpit.
- [x] Kept `/public` as the same aggregate-only public surface by sharing `PublicSurface`.
- [x] Moved owner token dashboard to `/internal`.
- [x] Fixed runtime owner dashboard loader to fetch summary from `/api/status` and raw rows from `/api/tasks`.
- [x] Updated exported page validation so `/` and `/public` stay public-only and `/internal` owns the token gate.
- [x] Deployed Worker and Firebase after whole-system verification passed.

## Verification Evidence

Focused checks passed:

```bash
python3 -m pytest cli/tests/test_dispatch.py
PYTHONPATH=/tmp/limen-api-test-deps python3 -m pytest web/api/tests/test_main.py
python3 -m compileall cli/src web/api/main.py
scripts/probe-local-worker.sh
npm --prefix web/worker run check
npm --prefix web/app run build
```

Whole-system verification passed after sourcing runtime tokens silently from:

```bash
/Users/4jp/Workspace/limen/.runtime/limen-worker-tokens.env
```

Verifier command:

```bash
set -a
source /Users/4jp/Workspace/limen/.runtime/limen-worker-tokens.env
set +a
PYTHONPATH=/tmp/limen-api-test-deps \
  NEXT_PUBLIC_API_URL="$LIMEN_WORKER_URL" \
  LIMEN_VERIFY_LIVE=1 \
  LIMEN_VERIFY_LIVE_RUNTIME=1 \
  scripts/verify-whole.sh
```

Final verifier line:

```text
Whole-system verification passed
```

Live throughput matches across Firebase static and Worker runtime:

```json
{
  "current_date": "2026-06-05",
  "expected_capacity_runs": 600,
  "recorded_starts": 12,
  "unrecorded_capacity_runs": 588,
  "done": 20,
  "not_done": 80
}
```

## Key Decisions

| Decision | Rationale |
|---|---|
| Use `unrecorded_capacity_runs` instead of `run_debt` | It is more accurate and less accusatory. The metric means expected capacity slots without a recorded start event, not necessarily failed work. |
| Include throughput in Worker and FastAPI | Static Firebase and runtime refresh must agree; Worker parity was required before deploy. |
| Keep raw tasks out of `/api/status` | Existing contract says owner status is summary-only; raw task rows remain behind owner-only `/api/tasks`. |
| Move owner dashboard to `/internal` | Public root was garbage because it showed an owner token gate. The root URL should be immediately useful publicly. |
| Do not restore hosted `tasks.json` | The live public boundary must remain aggregate-only; `tasks.json` 404 is intentional. |
| Deploy Worker before Firebase | Firebase public runtime refresh calls Worker; runtime needed the new throughput contract first. |

## Critical Context

- `tasks.yaml` was not mutated in this session.
- `.runtime/limen-worker-tokens.env` is secret-bearing. Do not print it. This worktree does not contain it; the existing token file is at `/Users/4jp/Workspace/limen/.runtime/limen-worker-tokens.env`.
- Main is still behind PR #7. Live production currently reflects PR branch code, not `main`, until PR #7 is merged.
- The local Worker probe originally hung because an old `wrangler dev` process from `/Users/4jp/Workspace/limen-runtime-status-fix-followup` held port `8787` for over a day. That stale local process was killed. Do not infer that as a source regression.
- `HEAD` probes against Worker paths can return 404 because the Worker routes are GET-oriented. Use GET/body probes for runtime contract checks.
- Current date matters: generated ledger date is `2026-06-05`, so inclusive age from `2026-05-31` is 6 days, not 5.

## Next Actions

1. Merge PR #7 when ready:

   ```bash
   gh pr merge 7 --repo 4444J99/limen --merge
   ```

2. After merge, confirm `main` checks/deploys stay green:

   ```bash
   gh run list --repo 4444J99/limen --branch main --limit 6
   ```

3. Smoke live boundary again:

   ```bash
   curl -sI https://device-streaming-067d747a.web.app/public-status.json | head -1
   curl -sI https://device-streaming-067d747a.web.app/tasks.json | head -1
   curl -fsSL https://limen-runtime.ivixivi.workers.dev/api/public-status
   ```

4. If a future agent updates the throughput contract, update all four surfaces together:
   - `web/api/main.py`
   - `web/worker/src/index.js`
   - `web/app/scripts/generate-static-data.mjs`
   - `spec/contracts/status-summary.schema.json`

## Risks & Warnings

- Do not weaken `scripts/probe-runtime-adapter.py`; its summary-only assertions are correct.
- Do not put raw task rows on public/static routes.
- Do not provision `GCP_SA_KEY` unless the user explicitly says `provision GCP`.
- If `GCP_SA_KEY` is provisioned later, deploy-api preflight requires Secret Manager secrets `limen-github-token`, `limen-api-token`, and `limen-client-token` to land together.
- Global gitignore can hide dirs named `public/`; keep using explicit `git status --short` and `git status --ignored=matching` when adding route dirs.

## Conflict Zones

| Path | Rule |
|---|---|
| `tasks.yaml` | Live board; do not mutate without explicit approval. |
| `web/api/main.py` | Keep `/api/status` summary-only and `/api/tasks` owner-only. |
| `web/worker/src/index.js` | Keep runtime schema aligned with FastAPI/static contracts before deploy. |
| `web/app/app/page.tsx` | Root is public cockpit, not owner gate. |
| `web/app/app/internal/page.tsx` | Owner token workflow belongs here. |
| `web/app/public/` | Generated public-safe JSON only; never restore `tasks.json`. |
| `web/app/.generated/` | Generated validation snapshots; never hand-edit. |
| `.runtime/limen-worker-tokens.env` | Secret-bearing; source silently only when needed. |

## Recovery Protocol

1. Read this handoff and `.codex/plans/2026-06-05-closeout-limen-throughput-public-dashboard.md`.
2. Verify branch and PR state:

   ```bash
   git status --short
   git branch --show-current
   gh pr view 7 --repo 4444J99/limen --json mergeStateStatus,statusCheckRollup
   ```

3. Verify live public boundary:

   ```bash
   curl -sI https://device-streaming-067d747a.web.app/public-status.json | head -1
   curl -sI https://device-streaming-067d747a.web.app/tasks.json | head -1
   ```

4. Treat any red after this point as a new regression unless it is the known unprovisioned `GCP_SA_KEY` skip behavior.
