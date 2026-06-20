# Limen — Master Backlog (from full-transcript audit wk3h4v06m, 2026-06-18)

43 directives extracted from the whole session · 29 done · 7 ongoing · 6 partial · 1 open.
This is the tracked backlog so work is systematic, not reactive.

## Fixed THIS pass (audit top actions)
- [x] **Kill racing daemons + singleton guard** — found 3 live loops; now exactly 1 (launchd, pid-guarded).
- [x] **Cheap-first routing enforced** — jules-routed-but-cloned tasks moved to free local lanes; queue balanced 16/15/15/15/15 across codex/opencode/agy/claude/gemini.
- [x] **Run-caps raised** 50→100 local, daily 300→600 — run-count no longer throttles free local compute; the real rate-limit detector is the brake.
- [x] **Faster recycle** — C_DRAIN 5→3 (close in-flight sooner); LOCAL_LIMIT 50→3 (no lane hogs a beat; fast rotation).

## OPEN / PARTIAL (ranked)
- [x] **(DONE) Usage-window + token telemetry** — scripts/usage-telemetry.py emits logs/usage.json (codex/claude real tokens/5h, jules count, rest dispatch-count+rate-limit); shown in board.py REAL USAGE panel; wired as a daemon voice. ~~Original:~~ — replace fictional run-counts with real per-vendor signals: codex `~/.codex/sessions` token_count + `/status` 5h/weekly; claude `anthropic-ratelimit-*` headers (5h rolling); gemini 429 `retryDelay` + RPD@00:00 PT; jules count-vs-100 (the one true proxy); opencode in-TUI cost; agy IDE meter. Feed into the router so it times dispatch against real windows.
- [x] **(DONE) True parallel dispatch** — dispatch_parallel() reserve→run(threadpool)→commit; tasks.yaml written twice/process (no race), git plumbing lock-guarded; proven live (PR #232, concurrent, no corruption). Heartbeat uses scripts/dispatch-parallel.py; atomic singleton guard. ~~was:~~ — biggest wall-clock lever. Dispatcher runs lanes serially; naive `&` corrupts tasks.yaml (whole-file save = lost updates). Needs the reserve→run(parallel)→commit refactor of dispatch.py. Do with the user watching.
- [ ] **(partial, gated by disk) Clone more task-bearing repos** — only ~3-32 of ~70 repos cloned; disk at ~81-83 GiB (near the 80 floor). Needs reclaim or go-ahead before volume cloning.
- [ ] **(partial) One-container migration finish** — agent homes (~/.claude, ~/.codex, ~/.gemini) still on internal home; fold behind symlinks when sessions can pause. `container/migrate.sh` staged.
- [ ] **(partial) gh workflow-scope auth + scrub leaked key from shell rc** — non-interactive `gh auth refresh -s workflow` still pending; remove GEMINI_API_KEY copies from .zshrc/.zshenv/.zprofile/.bashrc.
- [x] **(DONE) Credential onboarding generalized** — `scripts/set-credential.sh KEY` is the ONE safe path: silent prompt (never argv/history/echo/cat), writes to ~/.limen.env ONLY (never a shell rc), chmod 600, atomic add-or-replace (idempotent/re-runnable). `--check` reports expected-key presence (names only), `--list` lists key names. Tested: no value leak, idempotent, bad-name rejected. ~~was:~~ make ALL future key setup one-shot/idempotent/un-fuck-up-able (only the one gemini key was solved).
- [ ] **(partial) Portal ladder finish** — per-vendor sparklines, PR-panel widen, reconcile/clones panels, then gated live-interact.
- [ ] **(partial) gemini → email/OAuth (GCA)** — switch off the API key to the Google-login (GCA) path so no secret on disk.
- [ ] **(low) Auto-scaler dispatches (not feed-only) + de-jules-bias**; CI/billing-locked orgs dead-end PRs; per-tick iceberg surfacing.

## Vendor truth (run-count is a FICTION for 5 of 6)
| vendor | real limit | refresh | observe |
|---|---|---|---|
| jules | session/task count | rolling 24h | count vs 100 (only true proxy) |
| codex | token | 5h rolling + weekly | `/status`; `~/.codex/sessions` |
| claude | token/compute | 5h rolling + weekly | `anthropic-ratelimit-*` headers |
| gemini | request + token | RPM/TPM per-min, RPD@midnight PT | 429 `retryDelay` |
| opencode | dollar-budget | 5h (Zen) | in-TUI cost |
| agy | credit/work | 5h/weekly mixed | IDE meter |
