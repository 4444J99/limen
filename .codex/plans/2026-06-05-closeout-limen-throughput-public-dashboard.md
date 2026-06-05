# Session Close-Out: Limen Throughput Ledger + Public Dashboard

**Date:** 2026-06-05T01:11:56Z

## Outputs

- 17 source files changed in PR #7 before closeout/handoff artifacts:
  - `cli/src/limen/status.py`
  - `cli/tests/test_dispatch.py`
  - `spec/contracts/status-summary.schema.json`
  - `web/api/main.py`
  - `web/api/tests/test_main.py`
  - `web/app/app/authenticated-dashboard.tsx`
  - `web/app/app/dashboard-client.tsx`
  - `web/app/app/globals.css`
  - `web/app/app/internal/page.tsx`
  - `web/app/app/lib/data.ts`
  - `web/app/app/page.tsx`
  - `web/app/app/public-surface.tsx`
  - `web/app/app/public/page.tsx`
  - `web/app/app/surface-nav.tsx`
  - `web/app/scripts/generate-static-data.mjs`
  - `web/app/scripts/validate-exported-pages.mjs`
  - `web/worker/src/index.js`
- 2 session artifacts authored:
  - `.codex/plans/2026-06-05-handoff-limen-throughput-public-dashboard.md`
  - `.codex/plans/2026-06-05-closeout-limen-throughput-public-dashboard.md`
- Commit before closeout artifact commit: `a4482d0` (`limen: surface throughput ledger on public dashboard`)
- Pull request: `https://github.com/4444J99/limen/pull/7`

## Closure Marks

- EXECUTED:
  - User directive: commit local fix and open/push PR.
  - User directive: deploy Firebase dashboard so live URL stops being garbage.
  - User directive: tighten wording before shipping.
  - User directive: produce cross-agent handoff.
  - User directive: produce closeout.
- IN-PROGRESS:
  - PR #7 remains unmerged to `main`.
- ABANDONED:
  - None.

## What Shipped

- Public root now serves an aggregate-only cockpit instead of an owner token gate.
- Owner dashboard moved to `/internal`.
- Runtime owner dashboard now fetches raw rows from `/api/tasks`, preserving `/api/status` as summary-only.
- Throughput ledger is available in API, Worker, CLI, static generation, and schema contracts.
- Visible copy uses `Unrecorded capacity` / `starts not recorded`, not debt language.
- Worker and Firebase were deployed from the PR branch after verification.

## Live State

- Firebase Hosting: `https://device-streaming-067d747a.web.app`
- Cloudflare Worker: `https://limen-runtime.ivixivi.workers.dev`
- Worker version deployed this session: `46a8179b-6682-4912-b521-6d1bfca2e6fc`
- Hosted boundary:
  - `public-status.json` -> `HTTP/2 200`
  - `tasks.json` -> `HTTP/2 404`
- Live throughput:
  - first created: `2026-05-31`
  - generated/current date: `2026-06-05`
  - expected capacity: `600`
  - recorded starts: `12`
  - unrecorded capacity: `588`
  - done / not done: `20 / 80`

## Verification

Passed:

```bash
python3 -m pytest cli/tests/test_dispatch.py
PYTHONPATH=/tmp/limen-api-test-deps python3 -m pytest web/api/tests/test_main.py
python3 -m compileall cli/src web/api/main.py
scripts/probe-local-worker.sh
npm --prefix web/worker run check
npm --prefix web/app run build
```

Whole-system live verification passed:

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

PR #7 checks passed:

- CI `python`
- CI `worker`
- CI `web`
- Sourcery review
- Semgrep scan

## Pending

- Merge PR #7 to `main`.
- After merge, confirm `main` workflows remain green and live deploy state is still correct.
- No task-board mutation was performed; `tasks.yaml` remains untouched by this session.
- `GCP_SA_KEY` remains deliberately unprovisioned unless the user explicitly asks to provision GCP.

## Hand-Off Note For Next Session

Continue from PR #7. The implementation and production deploy are complete and verified, but `main` has not yet absorbed the branch. The next agent should merge PR #7 if authorized, verify main CI/deploy status, and smoke `public-status.json` 200 / `tasks.json` 404 / Worker public throughput. Do not reintroduce raw tasks into public or owner status envelopes, and do not restore hosted `tasks.json`.
