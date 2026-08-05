# GitHub Consolidation Runbook - current gate packet

Live status verified 2026-06-28 from this checkout with read-only `gh` and script probes.

## Current State

- `gh auth status` is logged in as `4444J99` and now has `admin:org`, `workflow`, `repo`, and `gist`.
- `organvm` exists and already holds 264 repos.
- The old source owners still hold 34 repos total:
  - `4444J99`: 9
  - `a-organvm`: 4
  - `meta-organvm`: 1
  - `organvm-i-theoria`: 9
  - `organvm-ii-poiesis`: 2
  - `organvm-iii-ergon`: 3
  - `organvm-iv-taxis`: 1
  - `organvm-v-logos`: 1
  - `organvm-vi-koinonia`: 3
  - `organvm-vii-kerygma`: 1
- `scripts/consolidate-github.py` dry-run reports 13 remaining name-collision groups.
- `scripts/consolidate-github.py --apply` now aborts while collisions remain. A partial move requires the extra explicit `--allow-partial` gate.
- `scripts/rewrite-owners.py` dry-run reports 49 `tasks.yaml` refs still on `4444J99` and 8 local remotes on old owners. Do not apply that rewrite until after the corresponding repos transfer.
- `limen[bot]` is not installed/wired. `gh api /orgs/organvm/installations` shows `claude`, `google-labs-jules`, `oz-by-warp`, and `chatgpt-codex-connector`; `bash scripts/gh-app-token.sh --which` reports `pat (GITHUB_TOKEN fallback)`.

## Hard Gates

1. Do not run irreversible GitHub renames, transfers, App install, or credential writes from an unattended model session.
2. Resolve the 13 collision groups first using `docs/consolidation/COLLISION-RENAMES.md`.
3. Re-run:
   ```bash
   cd ~/Workspace/limen
   PYTHONPATH=cli/src python3 scripts/consolidate-github.py
   ```
   Required output: `name collisions (must rename before transfer): 0`.
4. Only after collision count is 0, run the transfer gate:
   ```bash
   PYTHONPATH=cli/src python3 scripts/consolidate-github.py --apply
   ```
   This transfers the remaining source repos to `organvm` and applies source-owner topics.
5. After transfers, run the owner rewrite gate:
   ```bash
   PYTHONPATH=cli/src python3 scripts/rewrite-owners.py --apply --emit-remotes /tmp/limen-remotes.sh
   ```
   Review `/tmp/limen-remotes.sh`, then run it to repoint local checkouts. This is post-transfer only.
6. Wire `limen[bot]` only after the GitHub App exists and its secrets are hydrated:
   ```bash
   scripts/bootstrap-github-app.py
   # or, for a manually created App:
   bash scripts/set-credential.sh GITHUB_APP_ID
   bash scripts/set-credential.sh GITHUB_APP_PRIVATE_KEY
   bash scripts/gh-app-token.sh --verify-app
   ```
   Required output: `app verified (limen[bot] installation token mint succeeds)`.

## Verification Receipts

Use these before and after the transfer window:

```bash
gh auth status
gh api /orgs/organvm/installations --jq '.installations[] | .app_slug'
PYTHONPATH=cli/src python3 scripts/consolidate-github.py
PYTHONPATH=cli/src python3 scripts/rewrite-owners.py
pytest -q cli/tests/test_async_dispatch.py
python3 scripts/watchdog.py --dry-run
```

As of 2026-06-28, the async dispatch test predicate passes and the watchdog reports heartbeat healthy. Async dispatch is implemented but not enabled; the installed plist records `LIMEN_DISPATCH_ASYNC=0`, and the loaded launchd job still needs a between-beats reload to pick up the repaired `KeepAlive=true` plist.
