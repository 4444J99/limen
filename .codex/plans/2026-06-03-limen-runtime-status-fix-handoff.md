# Agent Handoff: Limen Runtime Status Leak Fix

**From:** Codex session | **Date:** 2026-06-03T18:10:33Z | **Phase:** COMPLETE -> MONITOR

## Current State

Repo: `/Users/4jp/Workspace/limen`

Branch: `main` at `2467af5` tracking `origin/main`.

The worktree is intentionally broad and dirty from the larger Limen surface/runtime buildout. Do not revert unrelated changes. `tasks.yaml` is modified from prior work and was not intentionally mutated by this status-leak fix.

Live endpoints:

- Firebase Hosting: `https://device-streaming-067d747a.web.app`
- Cloudflare Worker: `https://limen-runtime.ivixivi.workers.dev`

Runtime tokens remain in `.runtime/limen-worker-tokens.env`; do not print token values.

## Completed Work

- [x] Removed top-level raw `tasks` from FastAPI owner `/api/status`.
  - File: `web/api/main.py`
  - Current owner status payload includes `status`, `surface`, `portal`, `summary`, and `storage`.
- [x] Removed top-level raw `tasks` from Cloudflare Worker owner `/api/status`.
  - File: `web/worker/src/index.js`
  - Current owner status payload includes `status`, `surface`, `portal`, `summary`, and `storage`.
- [x] Kept `/api/tasks` owner-only for raw task access.
  - FastAPI and Worker still expose raw tasks only through `/api/tasks` after owner auth.
- [x] Repaired `/tmp/limen-api-test-deps` for the active Python 3.14 runtime.
  - Previous local FastAPI probe failed because `/tmp/limen-api-test-deps` contained a Python 3.13 `pydantic_core` binary.
  - Refreshed with `python3 -m pip install --upgrade --target /tmp/limen-api-test-deps -r web/api/requirements.txt`.
- [x] Deployed the patched Cloudflare Worker after full verification initially failed against the stale live Worker.
  - Command: `npm --prefix web/worker run deploy`
  - Deployed URL: `https://limen-runtime.ivixivi.workers.dev`
  - Wrangler reported Worker version ID: `f66b2711-79ed-4c54-ae84-660cbeb0a59f`
- [x] Reran full live verification after Worker deploy; it passed.
- [x] Deployed Firebase Hosting after the full verifier passed.
  - Command: `firebase deploy --only hosting --project device-streaming-067d747a`
  - Hosting URL: `https://device-streaming-067d747a.web.app`
- [x] Smoked public/private hosted JSON boundary.
  - `public-status.json`: `HTTP/2 200`
  - `tasks.json`: `HTTP/2 404`

## Verification Evidence

Focused verification passed:

```bash
npm --prefix web/app run generate:data
node scripts/validate-contract-schemas.mjs
node web/app/scripts/validate-surface-contracts.mjs
python3 -m py_compile scripts/probe-runtime-adapter.py
PYTHONPATH=/tmp/limen-api-test-deps scripts/probe-local-runtime.sh
scripts/probe-local-worker.sh
```

Full live verification passed after the Worker deploy:

```bash
set -a
source .runtime/limen-worker-tokens.env
set +a
PYTHONPATH=/tmp/limen-api-test-deps \
  NEXT_PUBLIC_API_URL="$LIMEN_WORKER_URL" \
  LIMEN_VERIFY_LIVE=1 \
  LIMEN_VERIFY_LIVE_RUNTIME=1 \
  scripts/verify-whole.sh
```

Verifier output included:

- Python module compile and shell syntax checks passed.
- GitHub workflow YAML parsed.
- Static and private surface contracts regenerated.
- Lifecycle adapter contracts verified.
- Portable JSON schemas verified.
- API/CLI tests passed: `26 passed`, one Starlette/httpx deprecation warning.
- Local FastAPI runtime adapter probe passed.
- Local Cloudflare Worker adapter probe passed.
- Next production build/export passed.
- Exported page persona/runtime checks passed.
- Live Firebase surfaces verified.
- Live runtime adapter schema probe passed.
- Diff hygiene check passed.
- Final line: `Whole-system verification passed`.

Hosted smoke after Firebase deploy:

```bash
/usr/bin/curl -q -I https://device-streaming-067d747a.web.app/public-status.json
/usr/bin/curl -q -I https://device-streaming-067d747a.web.app/tasks.json
```

Observed:

- `public-status.json`: `HTTP/2 200`, `content-type: application/json`
- `tasks.json`: `HTTP/2 404`, `content-type: text/html; charset=utf-8`

## Key Decisions

| Decision | Rationale |
|---|---|
| Removed raw task arrays from `/api/status` rather than weakening the probe | The probe caught a real owner status envelope leak; owner summary should not duplicate raw task access. |
| Kept `/api/tasks` as the owner-only raw task endpoint | Existing owner workflows still need explicit raw task access, but through a clearly named and sanctioned endpoint. |
| Deployed the Worker before rerunning full verification | Source and local Worker were fixed, but the live Worker still had stale code and blocked required live verification. |
| Deployed Firebase only after full live verification passed | Hosted output should only be released from a verifier-clean export. |
| Did not commit | User explicitly said not to commit unless asked. |
| Did not mutate live `tasks.yaml` | User explicitly prohibited live board mutation without approval. |
| Did not create LaunchAgents | Global AGENTS rule prohibits LaunchAgents on this machine. |

## Critical Context

- The initial full live verifier failed at `Verify live runtime adapter schemas` with `runtime adapter probe failed: owner status.tasks is not allowed`.
- That failure was against stale deployed Worker code, not current local source.
- The live Worker has now been redeployed with the source fix and passes the strict probe.
- Runtime tokens were sourced but not printed.
- `web/app/public/tasks.json` remains deleted and must stay absent from Firebase hosting.
- `web/app/.generated/surfaces/tasks.json` is a private validation snapshot, not a hosted public artifact.
- The worktree is still dirty from the broader buildout; many modified and untracked files predate this narrow fix.

## Next Actions

1. If continuing this lane, do not re-litigate the `/api/status` leak; it is fixed locally and live.
2. If asked to prepare a commit, stage only the intended buildout files after a fresh review of the broad dirty tree.
3. If asked to verify again, run:

   ```bash
   PYTHONPATH=/tmp/limen-api-test-deps \
     NEXT_PUBLIC_API_URL="$LIMEN_WORKER_URL" \
     LIMEN_VERIFY_LIVE=1 \
     LIMEN_VERIFY_LIVE_RUNTIME=1 \
     scripts/verify-whole.sh
   ```

   Source `.runtime/limen-worker-tokens.env` first, without printing token values.

4. If hosted boundary changes again, redeploy Firebase only after the full verifier passes, then smoke:

   ```bash
   /usr/bin/curl -q -I https://device-streaming-067d747a.web.app/public-status.json
   /usr/bin/curl -q -I https://device-streaming-067d747a.web.app/tasks.json
   ```

## Risks & Warnings

- Do not weaken `scripts/probe-runtime-adapter.py`; the `owner status.tasks is not allowed` assertion is correct.
- Do not restore `web/app/public/tasks.json`.
- Do not expose private client/internal/QA/readiness artifacts through Firebase Hosting.
- Do not mutate live `tasks.yaml` through runtime endpoints without explicit approval.
- Do not assume `git diff` represents only this session; the repo was already broadly dirty.
- Do not print runtime token values from `.runtime/limen-worker-tokens.env`.
- Do not create LaunchAgents.

## Conflict Zones

| Path | Rule |
|---|---|
| `tasks.yaml` | Live task board; avoid mutation unless explicitly approved. |
| `web/api/main.py` | Status leak fixed; keep `/api/status` summary-only and `/api/tasks` owner-only. |
| `web/worker/src/index.js` | Status leak fixed and deployed; keep live Worker aligned with local source. |
| `web/app/public/` | Public-safe JSON only; no raw tasks or private persona snapshots. |
| `web/app/.generated/surfaces/` | Generated validation snapshots; do not hand-edit. |
| `.runtime/limen-worker-tokens.env` | Secret-bearing env file; source silently only when required. |

## Recovery Protocol

1. Read this handoff and the previous active handoff:
   - `.codex/plans/2026-06-03-limen-surface-runtime-handoff.md`
2. Verify current local source still omits top-level raw `tasks` from:
   - `web/api/main.py` owner `/api/status`
   - `web/worker/src/index.js` Worker `/api/status`
3. Run local probes before any deploy.
4. Run full live verification before any Firebase deploy.
5. Treat stale live Worker behavior as a deploy issue, not a reason to weaken the contract probe.
