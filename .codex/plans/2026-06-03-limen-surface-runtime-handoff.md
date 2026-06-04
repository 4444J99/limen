# Agent Handoff: Limen Surface and Runtime Buildout

**From:** Codex session | **Date:** 2026-06-03 09:49 EDT, updated after interrupted schema hardening pass | **Phase:** VERIFY -> FIX

## Current State

Limen is in `/Users/4jp/Workspace/limen`. The worktree is intentionally dirty from the broader buildout; many files are untracked. Do not revert unrelated changes.

Live endpoints:

- Firebase Hosting: `https://device-streaming-067d747a.web.app`
- Cloudflare Worker: `https://limen-runtime.ivixivi.workers.dev`
- Runtime tokens and Worker URL are in `.runtime/limen-worker-tokens.env`; do not print token values.

Current surface model:

- `/` internal owner shell; owner token required; loads `/api/status`.
- `/qa` owner QA shell; owner token required; loads `/api/qa-status`, `/api/surface-manifest`, `/api/readiness`.
- `/client` client shell; client token required; loads `/api/client-status` and `/api/surface-manifest`.
- `/public` public aggregate shell; no token.

Hosted-public boundary:

- Hosted public files should include only public-safe files such as `public-status.json`, `surface-manifest.json`, `public-surface-manifest.json`, and `pr-status.json`.
- Private files should 404 on Firebase: `tasks.json`, `client-status.json`, `internal-status.json`, `qa-status.json`, `owner-surface-manifest.json`, `client-surface-manifest.json`, `readiness.json`.

Latest checked state:

- No `verify-whole`, `next build`, `firebase deploy`, `wrangler dev`, `uvicorn main:app`, `probe-local-runtime`, or `probe-local-worker` process was left running after the interrupted turn.
- The previously interrupted live verifier was recovered in a later pass.
- Static frontend data helpers now read public hosted JSON only.
- Private client/internal/QA/readiness data is runtime-authenticated or generated under `.generated/surfaces/` for validation only.
- Runtime probes now validate live/local API payloads against the portable JSON Schemas, not only hand-checked persona shapes.
- Runtime probes now assert exact manifest surface sanctions and disclosure flags for public/client/owner personas.
- Portable surface-manifest schema now disallows unreviewed extra properties on `source` and individual `surfaces`.
- Export validation now checks client/public source files for owner-only imports and mutation endpoints, not only rendered HTML.
- `scripts/verify-whole.sh` can now require the live runtime schema probe with `LIMEN_VERIFY_LIVE_RUNTIME=1`.
- The dashboard deploy workflow now fails closed if runtime URL or persona tokens are missing, then schema-probes the deployed runtime after Firebase release.
- Current unfinished pass tightened additional portable schemas, but runtime probes now fail on a real leak: owner `/api/status` includes raw top-level `tasks`.

## Completed Work

- Internal, client, public, and QA surfaces were built into token-gated/persona-scoped shells.
- Private JSON artifacts were removed from Firebase hosting and generated under `web/app/.generated/surfaces/` for validation.
- Public manifest is public-only; client manifest exposes only `client` and `public`; owner manifest exposes `internal`, `client`, `public`, `qa`, and `readiness`.
- Cloudflare Worker is live and reads/writes `4444J99/limen:main:tasks.yaml` through GitHub Contents.
- Worker `/api/surface-manifest` now rejects invalid bearer tokens instead of returning a null-persona manifest.
- Runtime probe covers invalid manifest token rejection, persona sanctions, client/public redaction, owner-only mutations, and optional local mutation probes.
- Runtime probe now schema-validates public/client/internal status payloads, public/client/owner manifests, QA status, and readiness.
- Runtime probe now checks exact public/client/owner manifest sanctions plus public/client/QA/readiness disclosure flags and QA endpoint paths.
- FastAPI owner `/api/status` summary now includes `generated_at`, matching the status summary contract already satisfied by the Worker.
- QA lifecycle panels exist for recovery, verification, assignment, and archive.
- QA panels reset stale local intent when selected task changes.
- CI/deploy workflows were hardened so hosted private files are absent and surface contracts are validated.
- `surface-manifest.schema.json` was tightened to type the `internal`, `client`, `public`, `qa`, and `readiness` contract objects.
- `surface-manifest.schema.json` now also sets `additionalProperties: false` on manifest `source` and surface entries.
- Static QA contract now includes `includes_task_urls: false`, matching API/Worker disclosure flags.
- `web/app/app/lib/data.ts` no longer reads `tasks.json`, `client-status.json`, `internal-status.json`, `qa-status.json`, `owner-surface-manifest.json`, `client-surface-manifest.json`, or `readiness.json` from `public/`.
- `web/app/scripts/validate-exported-pages.mjs` now fails the build if `lib/data.ts` reintroduces those private hosted filenames.
- `web/app/scripts/validate-exported-pages.mjs` now fails the build if client/public page sources import QA panels or reference owner-only endpoints such as `/api/status`, `/api/qa-status`, `/api/readiness`, `/api/tasks/*`, `/api/release-stale`, or `/api/dispatch`.
- `scripts/verify-whole.sh` runs API/CLI tests with ambient `LIMEN_API_TOKEN`, `LIMEN_OWNER_TOKEN`, and `LIMEN_CLIENT_TOKEN` cleared, so sourcing live runtime tokens does not break tests that verify no-token behavior.
- `scripts/verify-whole.sh` runs the live runtime schema probe during `LIMEN_VERIFY_LIVE=1` when runtime URL and tokens are present; `LIMEN_VERIFY_LIVE_RUNTIME=1` makes missing runtime probe inputs a hard failure.
- `README.md` and `QUICKSTART.md` document the required live-runtime verification mode.
- `.github/workflows/deploy.yml` verifies the deployed runtime adapter with `scripts/probe-runtime-adapter.py` after Firebase hosted surface verification. It requires `vars.LIMEN_API_URL`, `secrets.LIMEN_API_TOKEN`, and `secrets.LIMEN_CLIENT_TOKEN`.
- `README.md` and `QUICKSTART.md` document the deploy workflow runtime probe inputs.
- Current interrupted pass added strict `additionalProperties: false` coverage to:
  - `spec/contracts/pr-status.schema.json` root and `summary`.
  - `spec/contracts/qa-status.schema.json` root, `lifecycle`, `steering`, `mechanisms[]`, and `$defs.task_lifecycle`.
  - `spec/contracts/readiness.schema.json` root and `checks[]`.
  - `spec/contracts/status-summary.schema.json` root, `$defs.lifecycle`, and `$defs.clientTask`.
- `status-summary.schema.json` also now names internal-only root fields `portal` and `storage`; `summary` remains intentionally open because internal summary carries operational metrics such as `by_agent`, `by_priority`, `by_repo`, `recent_events`, `stale_task_ids`, and `today_events`.

## Most Recent Verification

The following completed successfully after strict surface-manifest schema hardening and before the latest interrupted pass:

```bash
npm --prefix web/app run generate:data
node scripts/validate-contract-schemas.mjs
node web/app/scripts/validate-surface-contracts.mjs
python3 -m py_compile scripts/probe-runtime-adapter.py
PYTHONPATH=/tmp/limen-api-test-deps scripts/probe-local-runtime.sh
scripts/probe-local-worker.sh
set -a
source .runtime/limen-worker-tokens.env
set +a
PYTHONPATH=/tmp/limen-api-test-deps NEXT_PUBLIC_API_URL="$LIMEN_WORKER_URL" LIMEN_VERIFY_LIVE=1 LIMEN_VERIFY_LIVE_RUNTIME=1 scripts/verify-whole.sh
firebase deploy --only hosting --project device-streaming-067d747a
```

Earlier required-live verifier command, preserved for quick reruns:

```bash
bash -n scripts/verify-whole.sh
set -a
source .runtime/limen-worker-tokens.env
set +a
PYTHONPATH=/tmp/limen-api-test-deps NEXT_PUBLIC_API_URL="$LIMEN_WORKER_URL" LIMEN_VERIFY_LIVE=1 LIMEN_VERIFY_LIVE_RUNTIME=1 scripts/verify-whole.sh
firebase deploy --only hosting --project device-streaming-067d747a
```

Verifier facts:

- API/CLI tests: `26 passed`, one Starlette/httpx warning.
- Local runtime probe passed.
- Local Cloudflare Worker adapter probe passed.
- Generated public/private manifests passed strict `source` and `surfaces` schema validation.
- Live Cloudflare Worker runtime probe passed with schema validation inside `scripts/verify-whole.sh`.
- Live Cloudflare Worker runtime probe passed with exact manifest sanction and disclosure flag assertions.
- Next export and exported page persona/runtime validation passed.
- Live Firebase surfaces verified.
- Direct hosted smoke verified public-only manifests and 404s for private artifacts.
- Dashboard deploy workflow YAML parsed after runtime-probe wiring.
- `git diff --check` passed.

Latest interrupted pass verification:

```bash
npm --prefix web/app run generate:data
python3 -m py_compile scripts/probe-runtime-adapter.py
node scripts/validate-contract-schemas.mjs
node web/app/scripts/validate-surface-contracts.mjs
```

Results:

- Static generation passed and produced 100-task private validation snapshots.
- `python3 -m py_compile scripts/probe-runtime-adapter.py` passed.
- `node scripts/validate-contract-schemas.mjs` passed after adding named `portal` and `storage` root fields to `status-summary.schema.json`.
- `node web/app/scripts/validate-surface-contracts.mjs` passed.
- `PYTHONPATH=/tmp/limen-api-test-deps scripts/probe-local-runtime.sh` failed with `runtime adapter probe failed: owner status.tasks is not allowed`.
- `scripts/probe-local-worker.sh` failed with the same `owner status.tasks is not allowed`.
- No Firebase redeploy was performed after this latest schema-hardening pass.

## Latest Deployment State

Firebase was redeployed from the export produced by the passing live-verification run.

Direct hosted smoke after redeploy:

```text
surface-manifest.json public ['public'] ['public']
public-surface-manifest.json public ['public'] ['public']
tasks.json 404
client-status.json 404
internal-status.json 404
qa-status.json 404
owner-surface-manifest.json 404
client-surface-manifest.json 404
readiness.json 404
```

Use `/usr/bin/curl -q` for hosted 404 smoke loops on this machine; local curl config may otherwise treat 404 as an error and abort under `set -e`.

## Key Decisions

| Decision | Rationale |
|---|---|
| Keep Firebase public-only and token-gate runtime surfaces through the Worker | Static hosting cannot safely expose task details; runtime contracts carry sanctioned access. |
| Keep client persona away from `/api/readiness` and from readiness manifest contract | Client token is denied `/api/readiness`; manifests must not advertise inaccessible owner-only contracts. |
| Treat QA as owner-only | QA contains steering, assignment, verification, recovery, and archive controls. |
| Use dry-run/preview for recovery and dispatch in normal verification | Live task-board mutation must not happen unless explicitly approved. |
| Generate private snapshots under `.generated/surfaces` | They are validation inputs, not hosted artifacts. |
| Add source-level validator checks for frontend lifecycle controls | Static HTML cannot prove client-side panel behavior after hydration. |

## Critical Context

- The user explicitly does not want extra manual work, sprawling TODOs, or client access to internal/QA tabs.
- Work should continue as concrete source/runtime hardening, not planning-only.
- No live task-board mutations have been performed during these verification passes.
- `web/app/app/lib/data.ts` is now public-only for static JSON reads.
- `web/app/public/tasks.json` is deleted and should stay deleted from hosting.
- `web/app/.generated/` is untracked but intentionally produced by the build/verification workflow.
- The repo is dirty; do not assume `git diff` shows all changed frontend files because many are untracked.

## Next Actions

1. Fix the concrete leak found by the latest strict runtime probe:

   - In `web/api/main.py`, change owner `GET /api/status` so it no longer returns top-level raw `tasks`.
   - In `web/worker/src/index.js`, change Worker `GET /api/status` so it no longer returns top-level raw `tasks`.
   - Keep `/api/tasks` owner-only for raw task listing if that endpoint is still needed.
   - Do not weaken `scripts/probe-runtime-adapter.py`; the failure is valid.

2. Rerun focused verification:

   ```bash
   npm --prefix web/app run generate:data
   node scripts/validate-contract-schemas.mjs
   node web/app/scripts/validate-surface-contracts.mjs
   python3 -m py_compile scripts/probe-runtime-adapter.py
   PYTHONPATH=/tmp/limen-api-test-deps scripts/probe-local-runtime.sh
   scripts/probe-local-worker.sh
   ```

3. Then run full/live verifier and redeploy only if it passes:

   ```bash
   set -a
   source .runtime/limen-worker-tokens.env
   set +a
   PYTHONPATH=/tmp/limen-api-test-deps NEXT_PUBLIC_API_URL="$LIMEN_WORKER_URL" LIMEN_VERIFY_LIVE=1 LIMEN_VERIFY_LIVE_RUNTIME=1 scripts/verify-whole.sh
   firebase deploy --only hosting --project device-streaming-067d747a
   ```

4. Refresh direct hosted smoke after redeploy.

5. Continue hardening candidates:

   - Add a CI/source guard for server-side persona tables if the surface list expands beyond internal/client/public/QA.
   - Continue improving QA/client ergonomics without exposing owner-only contracts to clients.
   - Keep each change tied to `scripts/verify-whole.sh` and live smoke when hosted behavior changes.

## Risks & Warnings

- Do not mutate live `tasks.yaml` unless the user explicitly approves a live action.
- Do not restore `web/app/public/tasks.json`.
- Do not weaken persona sanctions to make a page easier to load.
- Do not weaken the new `owner status.tasks is not allowed` probe; it found a real raw-task exposure in owner status.
- Do not treat old interrupted live verification notes as current; a later live verifier passed and Firebase was redeployed from that export.
- Do not commit from `/Users/4jp`; this is a child repo and commit decisions should be explicit.
- Avoid LaunchAgents; home AGENTS rules prohibit them.

## Conflict Zones

| Path | Rule |
|---|---|
| `tasks.yaml` | Live source of task board; do not mutate without explicit approval. |
| `web/app/out/` | Generated by Next export; redeploy after verifier rebuilds it. |
| `web/app/.generated/surfaces/` | Generated validation snapshots; do not hand-edit. |
| `.runtime/limen-worker-tokens.env` | Contains live tokens; never print token values. |
| `.github/workflows/*` | CI/deploy hardening is active; keep hosted privacy checks intact. |

## Recovery Protocol

1. Read this handoff.
2. Verify `git status --short` rather than assuming tracked/untracked state.
3. Pick one concrete contract/runtime/frontend mismatch and carry it through verification.
4. Redeploy Firebase only after a passing verifier rebuild if hosted static output changes.
5. Refresh direct hosted smoke with `/usr/bin/curl -q` if checking expected 404s.
