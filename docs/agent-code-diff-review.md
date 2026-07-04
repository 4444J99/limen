# Agent Code Diff Review

Generated: `2026-07-04T01:48:46Z`

## Scope

- Input queue: `docs/agent-code-review-queue.md` plus private queue metadata under `.limen-private/session-corpus/full-stack-review/`.
- Review method: start from high-risk prompt/session rows, reconstruct the matching git window, inspect the actual code diff, and record concrete implementation findings.
- Redaction boundary: no raw prompt bodies are included here; prompt bodies remain in the ignored private corpus.

## Reviewed Windows

| Queue rank | Agent | Session | Result |
|---:|---|---|---|
| refreshed 1 | `claude` | `9750bef7-8829-4373-916a-f86338b2e20a` | Archive4T conductor/session-foundation run. Temp job files were gone, durable transcripts and workflow JSON remained. Patched the audit redaction boundary after the session exposed raw prompt text in `unboundedGoalEvidence`. |
| refreshed 2 | `claude` | `eb3b624c-206f-4c9e-91aa-f069967a3796` | Studium transmission-curriculum run. Original worktree was gone, but the scripts and corpus are live on `main`; fixed a state-loader crash that violated the prompt's fail-open daily-face contract. |
| refreshed 3 | `claude` | `343d6769-bdee-480f-88d9-981eec736b87` | Evocator/SVMMONER run. Worktree and temp activation files were gone, but `scripts/evocator.py` and `spec/evocator` landed on `main`; fixed canon-shape crash paths that violated the organ's fail-open beat contract. |
| refreshed 4 | `claude` | `7c761a22-5bdf-42e8-bfb6-e8988530303f` | Archive4T convergence/knowledge-corpus planning run. Durable evidence is transcripts and memory docs; the referenced `converge-build` worktree was gone and no matching in-window `converge.py` commit survived, so this row is recorded as report-only. |
| refreshed 5 | `claude` | `a290329e-a778-478f-a7a7-9afa79709221` | UMA/mail obligations run. Original worktree and temp atlas outputs were gone, but the mail beat and obligations face landed on `main`; fixed wrong-shaped ledger crash paths in the obligations renderer. |
| refreshed 6 | `claude` | `dc879846-e9bf-41c0-b25d-5cebab230983` | Education-organism buildout run. Limen worktree, temp PR files, and the referenced external `~/Workspace/edu-organism` root were all absent on this host; recorded as transcript-only/off-host artifact loss. |
| 1 | `opencode` | `ses_11427e08affe3D8jAAl5W43viB` | Exact window had no matching commits on `main`, but the matching unmerged branch is `limen/gen-organvm-limen-security-0625-57ce` at `02f256e` (`Security hardening pass on organvm/limen`). Reviewed as a reject/do-not-merge artifact. |
| 2 | `opencode` | `ses_114c8f0c6ffeixS8gn4VxGqoHb` | Exact window matched `80d4e21f` (`feat(route): consume self-improve lane weights`). Widened window also showed related routing/meter/queue commits including `0146190` and `a6488c9`. |
| 3 | `opencode` | `ses_1095e9b19ffe4yg9h4la7tGU4d` | Exact window had no matching commits on `main`; widened window was mostly Studium content-generation churn, not the control-plane code path reviewed here. |
| 7 | `claude` | `34d17b80-3af9-41d6-8c52-231ddce47064` | Listed temp artifacts under `~/.claude/jobs/34d17b80/tmp` were no longer present, so no durable repo diff could be attributed to those paths. Same review pass inspected an adjacent landed usage-gate commit and fixed residual dispatch-gate gaps below. |
| 8 | `claude` | `0305e50a-e5ba-48e6-8fb1-6fb61264470d` | Usage-gauge / publication-policy / branch-reap window. Reviewed landed `main` code and fixed remaining malformed local telemetry/env crash paths in Claude gauge, branch reap, and budget-gauge display. |
| 9 | `claude` | `a39889c7-0aae-4348-84ed-19612cb0daa2` | Census/vendor-registry and stale-budget-reset window. Census/register and reset tests passed; fixed adjacent census-derived usage telemetry reserve parsing so malformed local percentages cannot poison pacing math. |
| 10 | `claude` | `3d972c29-36c6-4803-b94b-255df104f644` | Integration-organ window landed value ledger, score-dispatch, omni, ingest coverage, media atomization, and accelerator surfaces. Reviewed current `main` and found remaining malformed numeric crash paths in fail-open organs. |
| 11 | `claude` | `f9c6b1e7-2c05-4d42-9d6a-8b08ee98a155` | Window touched watchdog, self-heal, and self-improve organs. Reviewed current `main` implementations and found remaining malformed-env crash paths in watchdog/self-heal. |
| 12 | `claude` | `b7efae9c-af24-4c2c-9288-d2fa860ba974` | Off-repo `/Volumes/Archive4T` PR-healing fanout. Temp scratch artifacts were gone, but the persistent Claude workflow transcripts exposed a guard blind spot: nested workflow subagents were not included in transcript audits. |
| refreshed 13 | `claude` | `4693c425-3c29-4a48-9a0b-54fd9fd37753` | Revenue backlog / model-tier run. Original `piped-booping-kettle` worktree was gone, but revenue-backlog commits landed on `main`; fixed malformed ladder, usage, and env inputs that could abort the revenue feed beat. |
| refreshed 14 | `claude` | `4a4c2aa8-d455-431e-b18c-3ac1d5824741` | Moneta checkout / order-persistence run. Worktree and live `moneta` root exist; fixed a valid-JSON order-book shape crash that could break the restart-survival promise for pooled demand. |
| refreshed 15 | `claude` | `95f5e850-1274-40de-8a32-8ade3192b22a` | Course-recapitulation / education-organism run. Surviving evidence is transcript, plan, and Claude memory files; the `peaceful-plotting-fern` worktree, temp converter, and external `~/Workspace/edu-organism` root are absent, so code attribution is report-only. |
| refreshed 16 | `claude` | `06d2559b-05e9-4ff3-b1bf-4473bd935228` | Credential/his-hand wall and dialog-silencing run. Reviewed landed credential-wall generator and fixed an import-time malformed env crash in the wall predicate. |
| refreshed 17 | `claude` | `3be1f3a6-e00e-403d-a967-6d86c55deb56` | Workstream-channel run. Reviewed landed channel partition code and fixed the scoped cell conductor fallback so a failed channel projection cannot hand a worker the full mixed board. |
| refreshed 18 | `claude` | `57fa1ead-aabf-4c2e-b62e-6843cf74a66a` | Insights/censor/session-meta reanchor run. Surviving artifacts are split across a Claude hook, plan/settings/memory files, and one external session-meta worktree; temp scripts and two named side worktrees are absent, so no Limen code patch was made. |
| refreshed 19 | `claude` | `5e1004b3-b917-4a9d-a1ca-0f9b2b8dba45` | Mail audit / flagged-newsletter-storm run. Reviewed surviving private audit artifacts and external `universal-mail--automation` commit `39bf80d`; newsletter classifier tests pass, while ledger reconciliation after sent/withheld replies remains a recorded residual. |
| refreshed 20 | `claude` | `ce278978-35f1-4b6c-a511-41f5d1de75cf` | Pre-build excavation / private venture run. Reviewed landed `pre-build-excavate.sh` gate and fixed regex keyword matching so duplicate detection uses literal user keywords; private venture/temp artifacts are absent or outside Limen and remain report-only. |
| refreshed 21 | `claude` | `84a89bbb-ecd3-4e22-8148-f9b683bd2d92` | Agy bridge / Jules autonomous-dispatch run. The original `melodic-riding-hinton` worktree and temp job files were gone, but the landed Agy/Jules dispatch code was live on `main`; fixed a remaining Agy bridge gap where folder-shaped untracked deltas were silently skipped. |
| refreshed 22 | `claude` | `f38f4b2a-5c49-4d13-9b36-24bf31c941cc` | Archive4T conductor/relay incident run. The `/Volumes/Archive4T` docs/tests/scripts listed in the changed-file ledger are absent; only home-state memory, handoff, and static status artifacts survive. Current `main` has the scripts/watchdog/import fixes the static handoffs called missing, so this is recorded as stale-handoff/artifact-loss rather than a live code patch. |
| refreshed 23 | `claude` | `685b48b0-94fa-4537-a327-453a6ba01238` | External `etceter4-revival` winter-build run. Temp extractors are gone, but the revival docs and image-manifest generator survived in `~/Workspace/organvm/etceter4-revival`; fixed the generator so archive folders with nonmatching filename stems are actually inventoried. |
| 17 | `claude` | `branch:limen/gen-organvm-limen-security-0624-a9e5` | Reconstructed stale security branch family. Whole branches are destructive against current `main`; one minimal model-validation hunk was salvaged into current code. |
| 393 | `codex` | `019f2413-801b-7cd2-bb1e-c226d96c6355` | Private review metadata row 393; exact window included `1e964a9` (`limen: add safe task claim helper`) plus related board/receipt commits. Reviewed the manual claim helper against the board-accounting prompt intent. |

## Rejected Artifacts

### OpenCode security hardening branch disabled core gates

Severity: high if merged; current `main` is not affected.

Evidence:

- OpenCode session `ses_11427e08affe3D8jAAl5W43viB` maps to branch `limen/gen-organvm-limen-security-0625-57ce`, commit `02f256e` (`Security hardening pass on organvm/limen`).
- The session prompt was a security hardening pass, but the branch removes or weakens multiple safety gates: Python mypy, ruff format, MCP/Ianva type checks, shellcheck, the whole-repo verify job, Python 3.11 tests, npm audit, and TypeScript type-check.
- The branch reverts `capacity.py` from the census-derived vendor registry to hand-maintained literals and removes the `ollama` local floor lane.
- The branch removes dispatch environment hydration (`_load_limen_env`), which would make daemon-launched local agents miss credentials landed in `~/.limen.env`.
- The branch rewrites `tasks.yaml` heavily and is now stale enough that `main..02f256e` would delete many current agent-review, Tabularius, Vigilia, census, and workstream files.

Disposition:

- Do not merge branch `limen/gen-organvm-limen-security-0625-57ce`.
- Current `main` preserves the relevant gates and surfaces: CI still has mypy, nomenclator, TypeScript checks, and broader compile/test coverage; `capacity.py` still exposes `ollama_model`; `dispatch.py` still exposes `_load_limen_env`.
- Salvage should be by cherry-picking any independently reviewed, minimal hunks from the branch, not by rebasing or merging the branch.

Review commands:

```bash
git show --stat --oneline --name-only 02f256ed268320b242789a2c268e0fc40c44c8a8
git diff --name-status main..02f256ed268320b242789a2c268e0fc40c44c8a8
git diff main..02f256ed268320b242789a2c268e0fc40c44c8a8 -- .github/workflows/ci.yml cli/src/limen/dispatch.py cli/src/limen/capacity.py cli/pyproject.toml tasks.yaml
grep -R "def _load_limen_env\|ollama_model\|TypeScript type-check\|Validate naming canon\|mypy" -n cli/src/limen .github/workflows scripts cli/pyproject.toml
```

### Stale security/test-coverage branches would delete current control-plane work

Severity: high if merged or rebased wholesale.

Evidence:

- Branch `limen/gen-organvm-limen-security-0624-a9e5` is `835` commits behind / `1` ahead and would delete `542` files: `693 files changed, 16208 insertions(+), 167332 deletions(-)`.
- Branch `limen/gen-organvm-limen-security-0625-b412` is `782` behind / `2` ahead and would delete `480` files.
- Branch `limen/gen-organvm-limen-security-0626-b91f` is `699` behind / `2` ahead and would delete `275` files.
- Branches `limen/gen-organvm-limen-test-coverage-0625-0153`, `limen/gen-organvm-limen-test-coverage-0625-1c32`, `limen/gen-organvm-limen-test-coverage-0628-139c`, `origin/limen/gen-organvm-limen-test-coverage-0629-f1c2`, `origin/limen/gen-organvm-limen-test-coverage-0701-52e4`, and `origin/limen/gen-organvm-limen-ci-green-0629-e0c3` are also hundreds of commits behind and would delete between `118` and `480` current files.
- The deleted/currently-regressed surface includes current agent review ledgers, Tabularius, Vigilia, census, workstream, model-selection, current-session fanout, and large board-state updates.
- Some tip commits are small and salvageable after independent review: `0d705fe` model/API validation, `dc89769` nomenclator tests, `632e348` capacity tests. At least `cb166bd` also carries generated `.coverage` files and must not be merged as-is.

Disposition:

- Do not merge or rebase these stale branch heads into current `main`.
- Salvage only reviewed single commits or hunks, with generated coverage files excluded.
- `0d705fe` was partly salvaged below; target-agent model validation was not copied because the live board still has four legacy `target_agent: human` rows and would fail current queue parsing.

## Findings Fixed

### Route fail-open paths could still crash on malformed numeric input

Severity: high for daemon reliability, medium for data integrity.

Evidence:

- The reviewed route commit closed the self-improve loop by consuming `logs/self-improve-proposal.json` in `scripts/route.py`.
- The code advertised fail-open behavior, but numeric operator knobs and meter fields were parsed through bare `float(...)`.
- A malformed `LIMEN_SI_WEIGHT_FLOOR`, `LIMEN_SI_WEIGHT_CEILING`, `LIMEN_SI_CADENCE`, `LIMEN_SI_TIMEOUT`, `LIMEN_LEDGER_BIAS_FLOOR`, or `logs/usage.json` `runway_h` value could abort routing before it reached the resilient `tasks.yaml` lock/write path.

Repair:

- Added `_float_or_default()` and `_env_float()` in `scripts/route.py`.
- Made usage runway parsing fail open to `inf` for malformed lane meter values.
- Made learned-weight, self-improve cadence/timeout, and ledger-bias knobs fall back to defaults instead of crashing route.
- Clamped route bias floors to a positive floor so a bad or zero floor cannot fully starve a lane.

Touched paths:

- `scripts/route.py`
- `cli/tests/test_route_bias.py`

Verification:

```bash
python3 -m pytest cli/tests/test_route_bias.py cli/tests/test_dispatch.py::test_self_improve_weight_nudge_steers_local_split cli/tests/test_accelerator.py::test_routing_drains_cliff_edge_lane_first cli/tests/test_accelerator.py::test_routing_no_cliff_data_is_today_behaviour cli/tests/test_route_torn_write.py -q
```

Result: `16 passed in 0.45s`.

### Dispatch numeric knobs could abort hot paths instead of using defaults

Severity: high for daemon reliability.

Evidence:

- The rank 7-12 control-plane queue windows include async dispatch, local lane isolation, OAuth preflight, and accelerator work.
- Several runtime knobs in these hot paths used bare `int(...)` / `float(...)`: `LIMEN_OAUTH_PREFLIGHT_TIMEOUT`, `LIMEN_DISPATCH_TIMEOUT`, `LIMEN_LANE_TIMEOUT`, `LIMEN_ACCEL_TLEFT_FLOOR`, accelerator ceilings, `LIMEN_ASYNC_MAX_AGE`, `LIMEN_LOCAL_LIMIT`, and `LIMEN_ASYNC_MAX`.
- A malformed launchd or shell environment value could abort the dispatch beat before it reached lane gating, reservation, or result harvesting.

Repair:

- Added tolerant env parsing helpers to `cli/src/limen/dispatch.py`.
- Hardened OAuth preflight timeout, agent command timeout, isolated lane timeout, and accelerator floor/ceiling parsing.
- Added tolerant async-dispatch env parsing in `scripts/dispatch-async.py`.
- Covered malformed env values in synchronous dispatch and async dispatch tests without invoking real agents or network calls.

Touched paths:

- `cli/src/limen/dispatch.py`
- `scripts/dispatch-async.py`
- `cli/tests/test_dispatch.py`
- `cli/tests/test_async_dispatch.py`

Verification:

```bash
python3 -m pytest cli/tests/test_route_bias.py cli/tests/test_dispatch.py::test_dispatch_numeric_env_knobs_fail_open_when_malformed cli/tests/test_dispatch.py::test_run_isolated_agent_retries_transient_claude_auth_blip cli/tests/test_dispatch.py::test_pr_open_receipt_blocks_duplicate_dispatch_and_noop_demotion cli/tests/test_async_dispatch.py cli/tests/test_route_torn_write.py -q
```

Result: `32 passed in 0.61s`.

### Auto-scale workflow could commit unrelated code changes

Severity: medium for repo integrity.

Evidence:

- `scripts/auto-scale.py` states that the scheduled auto-scaler writes only `tasks.yaml`.
- `.github/workflows/auto-scale.yml` also ran ruff/check-params self-healing and then used `git add -A`.
- That let a task-depth workflow commit arbitrary code, docs, generated files, or parameter-baseline changes under the misleading commit message `chore: auto-scale tasks.yaml to 100-task depth`.

Repair:

- Removed the self-healing ruff/check-params step from the auto-scale workflow.
- Changed the commit guard to look only at `tasks.yaml`.
- Changed staging from `git add -A` to `git add tasks.yaml`.

Touched paths:

- `.github/workflows/auto-scale.yml`

### Auto-scale script could clobber live queue updates and hang on duplicate pages

Severity: high for task-board integrity.

Evidence:

- `scripts/auto-scale.py` read `tasks.yaml`, fetched GitHub issues, then atomically wrote the original snapshot plus new tasks without taking the shared queue lock or re-reading before write.
- Atomic write prevented truncation, but not lost updates: a heartbeat/dispatcher change between the initial read and final write could be overwritten.
- The pagination loop also kept running when a later page repeated only already-seen/duplicate issue URLs, because `needed` did not decrease.

Repair:

- Fetch candidate issue refs first, then take `queue_lock(TASKS_FILE)`.
- Re-read `tasks.yaml` under the lock and recompute depth, existing URLs, and next task ID before writing.
- Skip the write entirely when no new tasks survive the final re-read/filter.
- Stop pagination on repeated pages and cap pages per org.

Touched paths:

- `scripts/auto-scale.py`
- `cli/tests/test_auto_scale.py`

Verification:

```bash
python3 -m pytest cli/tests/test_auto_scale.py cli/tests/test_io_atomic.py -q
python3 -m py_compile scripts/auto-scale.py
```

Result: `15 passed in 0.09s`; compile passed.

### Parallel dispatch reservation could clobber live board updates

Severity: high for task-board integrity and duplicate-dispatch prevention.

Evidence:

- The result-commit path in `dispatch_parallel()` reloaded `tasks.yaml` under the queue lock, but the earlier reservation commit did not.
- A caller could load `tasks.yaml`, then a supervisor/heartbeat could add or complete tasks, then `dispatch_parallel()` would save the stale caller snapshot while marking reservations.
- That could erase concurrently added work, revive a stale `open` task that had already become `done`, or reserve work from a board state that was no longer authoritative.

Repair:

- Moved parallel reservation selection into `_select_parallel_reservations()`, which operates on the board supplied to it.
- For live dispatch, take the queue lock first, re-read `tasks.yaml`, reset budget on the fresh board, then select and mark reservations.
- Preserve the old in-memory-board behavior only for dry-run and file-absent test harness cases.
- Track cumulative selected budget across lanes during reservation selection so multi-lane picks do not overrun daily headroom.

Touched paths:

- `cli/src/limen/dispatch.py`
- `cli/tests/test_dispatch.py`

Verification:

```bash
python3 -m pytest cli/tests/test_dispatch.py::test_dispatch_parallel_reloads_under_queue_lock_before_reserve_write cli/tests/test_dispatch.py::test_dispatch_parallel_does_not_dispatch_stale_open_task cli/tests/test_dispatch.py::test_dispatch_parallel_skips_needs_human_label cli/tests/test_dispatch.py::test_dispatch_parallel_debt_gate_skips_routine_generated_buildout cli/tests/test_dispatch.py::test_dispatch_parallel_skips_generated_buildout_outside_value_tier cli/tests/test_accelerator.py::test_dispatch_parallel_accel_tail_is_win_class_only cli/tests/test_dispatch_engine.py -q
python3 -m py_compile cli/src/limen/dispatch.py
```

Result: `20 passed in 24.56s`; compile passed. Broader dispatch/control-plane check:
`python3 -m pytest cli/tests/test_dispatch.py cli/tests/test_accelerator.py cli/tests/test_dispatch_engine.py cli/tests/test_async_dispatch.py cli/tests/test_route_bias.py cli/tests/test_route_torn_write.py -q` returned `98 passed in 31.30s`.

### Async dispatch reservation ignored cumulative picked cost

Severity: high for budget integrity.

Evidence:

- `scripts/dispatch-async.py` counted already-running markers against per-agent budget, but within the current reserve pass it only checked each candidate task's individual `budget_cost <= rem`.
- Because `rem` and global `spent` were not decremented after selecting a task, one beat could reserve multiple tasks whose combined cost exceeded per-agent or daily headroom.
- This directly conflicted with the prompt/session goal of guarding continuation and token spend in the rank 7-12 control-plane windows.

Repair:

- Decrement the lane `rem` and shared daily `spent` as each async reservation is picked.
- Keep the existing local-slot and duplicate-any-task guards intact.
- Added regressions for per-agent headroom and daily headroom accumulation.

Touched paths:

- `scripts/dispatch-async.py`
- `cli/tests/test_async_dispatch.py`

Verification:

```bash
python3 -m pytest cli/tests/test_async_dispatch.py -q
python3 -m py_compile scripts/dispatch-async.py
```

Result: `18 passed in 0.15s`; compile passed.

### Review queue undercounted Codex and Claude changed files

Severity: medium for review completeness.

Evidence:

- The first code-review queue treated OpenCode as the only agent with native structured changed-file refs.
- That left Codex `apply_patch` calls and Claude `Edit` / `Write` tool-use payloads outside the immediate diff queue, pushing those sessions into coarser git-window reconstruction.
- The old queue had `405` structured changed-file sessions, `226` immediate candidates, and `2038` reconstruction roots. After conservative Codex/Claude extraction, the refreshed queue has `1736` structured changed-file sessions, `1556` immediate candidates, and `873` reconstruction roots.

Repair:

- Parse Codex `apply_patch` file headers from structured tool calls.
- Parse Claude mutating tool payload paths for `Edit`, `MultiEdit`, `Write`, and `NotebookEdit`, while ignoring read-only tool paths.
- Wire Codex assistant/tool/function/custom call records and Claude assistant records into `changed_files`.
- Regenerate the full-stack review and code-review queue from the private corpus.

Touched paths:

- `scripts/agent-session-full-stack-review.py`
- `scripts/agent-code-review-queue.py`
- `cli/tests/test_agent_session_full_stack_review.py`
- `docs/agent-session-full-stack-review.md`
- `docs/agent-code-review-queue.md`

Verification:

```bash
python3 -m pytest cli/tests/test_agent_session_full_stack_review.py -q
python3 -m py_compile scripts/agent-session-full-stack-review.py scripts/agent-code-review-queue.py
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write
```

Result: unit test returned `3 passed`; compile passed; full-stack refresh reviewed `125902` prompts and `4371` sessions; queue refresh produced `1556` changed-file candidates and `873` reconstruction roots.

### Agy changed-file evidence was still reconstruction-only

Severity: medium for cross-agent review completeness.

Evidence:

- After the Codex/Claude extractor fix, Agy still had no structured changed-file refs in the review queue.
- Agy CLI conversation SQLite `steps` do carry explicit mutating tool payloads with `TargetFile` fields, but the extractor only turned those spans into outcome text.
- The refreshed queue now has `1963` structured changed-file sessions and `1778` immediate changed-file candidates. Agy contributes `225` changed-file sessions and `493` changed-file refs.

Repair:

- Added conservative Agy `TargetFile` extraction from per-step CLI SQLite spans.
- Classified Agy payloads as mutating only when the `toolAction` looks like edit/write/create/update work or the payload carries replacement/code/edit keys.
- Kept read-only-looking `TargetFile` spans out of the changed-file list.
- Regenerated the full-stack review and code-review queue from the private corpus.

Touched paths:

- `scripts/agent-session-full-stack-review.py`
- `scripts/agent-code-review-queue.py`
- `cli/tests/test_agent_session_full_stack_review.py`
- `docs/agent-session-full-stack-review.md`
- `docs/agent-code-review-queue.md`

Verification:

```bash
python3 -m pytest cli/tests/test_agent_session_full_stack_review.py -q
python3 -m py_compile scripts/agent-session-full-stack-review.py scripts/agent-code-review-queue.py
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-session-full-stack-review.py --write
env LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/agent-code-review-queue.py --write
```

Result: unit test returned `4 passed`; compile passed; full-stack refresh reviewed `125919` prompts and `4375` sessions; queue refresh produced `1778` changed-file candidates and `875` reconstruction roots.

### Task API numeric validation accepted booleans as integers

Severity: medium for API integrity.

Evidence:

- OpenCode session `ses_0f956f11fffepkhlsmcY72qUB3` mapped to `38a976d` (`Security: harden task API validation`) and `47534d5` (`fix: log dispatch reservations durably`).
- The security hardening added integer bounds for `limit` and `budget_cost`, but Pydantic still coerced `True` to `1` for `DispatchRequest.limit`, `TaskCreate.budget_cost`, and `AssignmentRequest.budget_cost`.
- The Cloudflare worker had the same drift because `Number(true)` returns `1`, so boolean dispatch limits and assignment costs could pass validation there too.

Repair:

- Added an explicit boolean-integer rejection helper in the FastAPI surface.
- Applied it before Pydantic coercion for task creation, assignment steering, and dispatch request limits.
- Updated the worker integer validator to reject boolean inputs before `Number(...)`.
- Added focused API regressions for boolean `limit` and `budget_cost`.

Touched paths:

- `web/api/main.py`
- `web/api/tests/test_main.py`
- `web/worker/src/index.js`

Verification:

```bash
python3 -m pytest web/api/tests/test_main.py::test_dispatch_rejects_invalid_agent_limit_and_task_id web/api/tests/test_main.py::test_create_task_rejects_malformed_untrusted_fields web/api/tests/test_main.py::test_assign_task_rejects_boolean_budget_cost -q
npm run check --prefix web/worker
```

Result: `3 passed`; worker syntax check passed.

### Dispatch verification could crash before writing health evidence

Severity: medium for control-plane observability.

Evidence:

- The same OpenCode window touched `scripts/verify-dispatch.py` in `47534d5`.
- `verify-dispatch.py` parsed `LIMEN_LANE_TIMEOUT` with bare `int(...)` at import time. A malformed launchd or shell value crashed the verifier before it could write `logs/dispatch-verify.json`.
- `prompt-lifecycle-ledger.py` had the same bare timeout parse, plus a bare GitHub receipt retry parse, so lifecycle evidence refresh could fail before producing the redacted prompt/session crosswalk.

Repair:

- Added tolerant integer parsing to `verify-dispatch.py`.
- Applied the same fallback parsing to dispatch grace and GitHub receipt retry settings in `prompt-lifecycle-ledger.py`.
- Added import-time regressions for malformed env values.

Touched paths:

- `scripts/verify-dispatch.py`
- `scripts/prompt-lifecycle-ledger.py`
- `cli/tests/test_verify_dispatch.py`
- `cli/tests/test_prompt_lifecycle_ledger.py`

Verification:

```bash
python3 -m pytest cli/tests/test_verify_dispatch.py cli/tests/test_prompt_lifecycle_ledger.py -q
python3 -m py_compile scripts/verify-dispatch.py scripts/prompt-lifecycle-ledger.py
env LIMEN_LANE_TIMEOUT=bad python3 scripts/verify-dispatch.py --quiet
env LIMEN_LANE_TIMEOUT=bad LIMEN_GH_RECEIPT_RETRIES=bad python3 - <<'PY'
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('pll', Path('scripts/prompt-lifecycle-ledger.py'))
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print(mod.DISPATCH_GRACE_SECONDS, mod.GH_RETRIES)
PY
```

Result: `6 passed`; compile passed; malformed-env verifier exited `0`; lifecycle import printed `1500 3`.

### Manual claim helper could write invalid agents or crash mid-claim

Severity: medium for board integrity.

Evidence:

- Codex session `019f2413-801b-7cd2-bb1e-c226d96c6355` maps to the 2026-07-02 window containing `1e964a9` (`limen: add safe task claim helper`).
- The prompt/session intent was safe task reservation with board accounting, but `scripts/claim-task.py` accepted arbitrary agent strings and could write an invalid `target_agent`.
- The helper also parsed `budget_cost`, `portal.budget.track.spent`, and per-agent counters with bare integer coercion after claim mutation was underway. Malformed board fields could crash a library caller with partially-mutated in-memory claim state.

Repair:

- Added a canonical claimable-agent allowlist and reject unknown agents before touching the board.
- Added strict non-negative integer parsing that rejects booleans, malformed values, and negative values while still defaulting absent optional counters to zero.
- Moved budget/counter validation before task status mutation and dispatch-log append.
- Added unit coverage for valid reservation, invalid agents, malformed budgets, and boolean budgets with no mutation on rejection.

Touched paths:

- `scripts/claim-task.py`
- `cli/tests/test_claim_task.py`

Verification:

```bash
python3 -m pytest cli/tests/test_claim_task.py -q
python3 -m py_compile scripts/claim-task.py
```

Result: `4 passed`; compile passed.

### Opencode clock telemetry could crash usage refresh on malformed numerics

Severity: medium for dispatch observability and lane pacing.

Evidence:

- Codex session `019f2413-801b-7cd2-bb1e-c226d96c6355` included the provider-clock commits `ab6d684` and `5b1f84a`.
- The prompt/session intent was stronger lane presence and usage-clock evidence, but `scripts/usage-telemetry.py` trusted `~/.local/share/opencode/clock.json` numeric fields directly.
- If `heavy_used`, `cache_read_used`, `cap_tokens`, or `used_pct` arrived as strings, booleans, `nan`, or malformed values, usage refresh could raise before writing `logs/usage.json`.
- `LIMEN_RL_COOLDOWN_MIN` also used bare float parsing at import time, so one malformed environment value could abort telemetry before it reached the fail-open lane health logic.

Repair:

- Added a non-negative finite numeric coercion helper for telemetry inputs.
- Applied it to cooldown parsing, Opencode clock consumed/cap/percent fields, and generic possible/consumed values before headroom math.
- Made window-label parsing tolerate non-string values.
- Added subprocess regressions for string clock numerics, malformed clock numerics, boolean/nan fields, and malformed cooldown env.

Touched paths:

- `scripts/usage-telemetry.py`
- `cli/tests/test_usage_telemetry_health.py`

Verification:

```bash
python3 -m pytest cli/tests/test_usage_telemetry_health.py -q
python3 -m py_compile scripts/usage-telemetry.py
```

Result: `7 passed`; compile passed.

### Tabularius bad board-level tickets could crash the keeper

Severity: high for the new single-writer board path.

Evidence:

- Codex session `019f2413-801b-7cd2-bb1e-c226d96c6355` included the Tabularius merge `6a28f1a`.
- The prompt/session intent was a beat-safe single writer where one bad ticket is quarantined and the rest of the inbox still lands.
- Task tickets were validated per-ticket, but `board.meta` and `board.order` tickets could carry invalid board-level data through to the final fold.
- A malformed meta ticket, such as a non-mapping `portal.budget`, raised `ValidationError` from `fold(...)` and left the ticket in `inbox/` instead of quarantining it.

Repair:

- Validate `board.meta` candidate state before mutating the in-memory projection.
- Reject non-list or non-string `board.order` ids instead of silently iterating arbitrary values.
- Catch final fold validation failures and quarantine the batch rather than crashing the beat.
- Added tests proving bad meta/order tickets are quarantined while a good task ticket in the same inbox still applies.

Touched paths:

- `cli/src/limen/tabularius.py`
- `cli/tests/test_tabularius.py`

Verification:

```bash
python3 -m pytest cli/tests/test_tabularius.py -q
python3 -m py_compile cli/src/limen/tabularius.py
```

Result: `15 passed`; compile passed.

### Watchdog and self-heal env knobs could abort the beat

Severity: medium for autonomic recovery reliability.

Evidence:

- Claude session `f9c6b1e7-2c05-4d42-9d6a-8b08ee98a155` covers the watchdog/self-heal/self-improve organ window.
- The implementation intent was fail-open, beat-safe detection and repair, but `scripts/watchdog.py` parsed watchdog timing knobs with bare `int(...)` at import time.
- `scripts/self-heal.py` parsed `LIMEN_HEAL_SCAN`, `LIMEN_HEAL_SCAN_MAX`, and `LIMEN_HEAL_LIMIT` with bare `int(...)` while constructing argparse defaults.
- A malformed launchd or shell value could crash watchdog before health checks or crash self-heal before dry-run/live gating.

Repair:

- Added positive integer fallback parsing to `watchdog.py` for loop max, lane timeout, dispatch ceiling, overhead, stale threshold, and max-fails.
- Added positive integer fallback parsing to `self-heal.py` for scan, scan-max, and limit defaults.
- Added regressions proving malformed env values fall back without writing the board or queue lock in dry-run mode.

Touched paths:

- `scripts/watchdog.py`
- `scripts/self-heal.py`
- `cli/tests/test_watchdog.py`
- `cli/tests/test_self_heal.py`

Verification:

```bash
python3 -m pytest cli/tests/test_watchdog.py cli/tests/test_self_heal.py -q
python3 -m py_compile scripts/watchdog.py scripts/self-heal.py
```

Result: `18 passed`; compile passed.

### Integration organs could crash on malformed local numerics

Severity: medium for heartbeat-visible observability and value accounting.

Evidence:

- Claude session `3d972c29-36c6-4803-b94b-255df104f644` covers the integration-organ window that landed value-ledger, score-dispatch, omni-view, ingest-coverage, media-atomize, and accelerator surfaces.
- The prompt/session intent was fail-open, beat-safe organs that make value, context coverage, and media atoms visible without blocking the heartbeat.
- `scripts/ledger.py` parsed ledger record spend/sunk fields and steering thresholds with bare `int(...)` / `float(...)`.
- `scripts/score-dispatch.py` parsed `budget_cost` with bare `int(...)` while grading resolved tasks.
- `scripts/ingest-coverage.py` parsed manifest `atom_count` with bare `int(...)`.
- `scripts/media-atomize.py` parsed chunk, PDF timeout, and default limit env knobs with bare `int(...)` at import or argparse construction time.

Repair:

- Added tolerant numeric helpers for ledger record totals and ledger steering thresholds.
- Made score-dispatch fall back per task when `budget_cost` is malformed or boolean.
- Made ingest coverage treat malformed atom counts as zero and normalize source keys before tallying.
- Made media-atomize env/default numeric parsing fall back to positive defaults before preview/apply mode.
- Added focused regressions for malformed records, board budgets, ingest manifests, and media-atomize env defaults.

Touched paths:

- `scripts/ledger.py`
- `scripts/score-dispatch.py`
- `scripts/ingest-coverage.py`
- `scripts/media-atomize.py`
- `cli/tests/test_ledger.py`
- `cli/tests/test_score_dispatch.py`
- `cli/tests/test_ingest_coverage.py`
- `cli/tests/test_media_atomize.py`

Verification:

```bash
python3 -m pytest cli/tests/test_ledger.py cli/tests/test_score_dispatch.py cli/tests/test_ingest_coverage.py cli/tests/test_media_atomize.py cli/tests/test_omni_view.py cli/tests/test_accelerator.py -q
python3 -m py_compile scripts/ledger.py scripts/score-dispatch.py scripts/omni-view.py scripts/ingest-coverage.py scripts/media-atomize.py scripts/library-preserve.py
bash -n scripts/clone-maintenance.sh scripts/heartbeat-loop.sh
```

Result: `46 passed`; compile and shell syntax checks passed.

### Task model accepted invalid task ids and budget costs

Severity: medium for board integrity.

Evidence:

- Security branch `limen/gen-organvm-limen-security-0624-a9e5` had a valid narrow idea in tip commit `0d705fe`: model/API validation should reject malformed task input.
- Current `web/api` already carried the API-side agent and boolean-integer validation, but `cli/src/limen/models.py` still accepted `budget_cost=True`, `budget_cost=0`, and `budget_cost=-1`.
- Current `Task.id` also had no canonical pattern/length guard even though the API and MCP surfaces already enforce a task-id shape.
- A live-board precheck found `0` invalid ids and `0` invalid budgets across `1677` current tasks, so the model hardening is compatible with current queue data.

Repair:

- Added a canonical task-id pattern/length guard to `Task.id`.
- Added positive bounded `budget_cost` validation and a pre-validator rejecting booleans before Pydantic coerces them to integers.
- Added model-level regressions through `LimenFile.model_validate`.
- Left `target_agent` model validation for a later owner-policy cleanup because current `tasks.yaml` still contains four legacy `target_agent: human` rows.

Touched paths:

- `cli/src/limen/models.py`
- `cli/tests/test_io_atomic.py`

Verification:

```bash
python3 -m pytest cli/tests/test_io_atomic.py cli/tests/test_doctor.py cli/tests/test_dispatch_engine.py cli/tests/test_async_dispatch.py cli/tests/test_dispatch.py -q
python3 -m py_compile cli/src/limen/models.py
PYTHONPATH=cli/src python3 - <<'PY'
from pathlib import Path
from limen.io import load_limen_file
board = load_limen_file(Path('tasks.yaml'))
print(len(board.tasks))
PY
```

Result: `129 passed`; compile passed; live board parsed `1677` tasks.

### Shared board IO env knobs could disable queue safety paths

Severity: medium for board writer reliability.

Evidence:

- Continuing the control-plane review queue found a shared board-write dependency rather than a single leaf agent script.
- The prompt/session intent across board reservation and queue-safety work was race-safe, fail-open board mutation.
- `cli/src/limen/io.py` parsed `LIMEN_QUEUE_LOCK_STALE_SEC`, `LIMEN_BOARD_SHRINK_FLOOR`, and `LIMEN_BOARD_SHRINK_FRACTION` directly from env input.
- Malformed, zero, negative, `nan`, or infinite values could silently weaken the lock stale check or collapse guard before callers reached their own safety logic.

Repair:

- Added shared integer and finite-float fallback parsing in `limen.io`.
- Applied positive minimums to queue-lock stale seconds and collapse-guard floor.
- Rejected non-finite or negative collapse fractions back to the default guard fraction.
- Added focused IO regressions for malformed, non-positive, `nan`, and infinite env values.

Touched paths:

- `cli/src/limen/io.py`
- `cli/tests/test_io_atomic.py`

Verification:

```bash
python3 -m pytest cli/tests/test_io_atomic.py cli/tests/test_board_integrity.py -q
python3 -m py_compile cli/src/limen/io.py
```

Result: `24 passed`; compile passed.

### Claude gauge and branch-reap fail-open paths still trusted malformed local data

Severity: medium for usage-window control and branch-lifecycle reliability.

Evidence:

- Claude session `0305e50a-e5ba-48e6-8fb1-6fb61264470d` covers the Claude usage gauge, branch reaper, publication-policy, and budget-gauge truth window.
- The prompt/session intent was a durable "forever bridge" gauge, visible dark avenues instead of silent all-clear readings, and loss-free branch reaping.
- `scripts/claude-usage.py` parsed `LIMEN_CLAUDE_GAUGE_FRESH_S` with bare `float(...)` at import, parsed proxy percentages with bare `float(...)`, and allowed malformed freshness timestamps to abort an avenue.
- The on-disk Claude gauge summed raw transcript token fields without coercion, so a string or malformed usage field could darken the whole transcript avenue.
- `scripts/reap-branches.py` parsed `LIMEN_BRANCH_REAP_MAX` and `LIMEN_BRANCH_REAP_EVERY_MIN` with bare `int(...)` / `float(...)` before classification.
- `scripts/verify-budget-gauge.py` parsed live Codex `window_minutes` with bare `int(...)` and formatted malformed `used_percent` values directly.

Repair:

- Added finite numeric parsing and per-avenue exception guards to `claude-usage.py`.
- Made proxy, count, calibration, and transcript-token values degrade to dark/unknown readings instead of aborting the gauge.
- Added branch-reap env parsers with minimum bounds for max and throttle values.
- Made budget-gauge Codex rate-limit window/percentage parsing and human display tolerate malformed live payloads.
- Added focused regressions for malformed env, malformed proxy telemetry, string count values, branch-reap env knobs, and bad Codex rate-limit payloads.

Touched paths:

- `scripts/claude-usage.py`
- `scripts/reap-branches.py`
- `scripts/verify-budget-gauge.py`
- `cli/tests/test_claude_usage.py`
- `cli/tests/test_reap_branches.py`
- `cli/tests/test_verify_budget_gauge.py`

Verification:

```bash
python3 -m pytest cli/tests/test_claude_usage.py cli/tests/test_reap_branches.py cli/tests/test_verify_budget_gauge.py -q
python3 -m py_compile scripts/claude-usage.py scripts/reap-branches.py scripts/verify-budget-gauge.py
```

Result: `29 passed`; compile passed.

### Usage reserve inputs could poison census-derived pacing

Severity: medium for gauge truth and front-load pacing.

Evidence:

- Claude session `a39889c7-0aae-4348-84ed-19612cb0daa2` covers the census/vendor-registry, usage-telemetry derivation, and stale budget-reset healing window.
- The prompt/session intent was one vendor truth source, no fabricated meters, and no stale-counter deadlock.
- The landed census register, capacity projections, dispatch lane cascade, Agy meter-honesty guard, and budget reset heal tests passed on current `main`.
- The remaining gap was in the adjacent census-derived usage telemetry consumer: `load_reserve_pct()` and `load_reserve_floor_pct()` accepted bare `float(...)` values from env or `logs/usage-limits.json`.
- `float("nan")`, infinite values, negative values, or percentages above `100` could flow into `effective_reserve_pct`, lane health, and front-load `will_expire` math, contradicting the gauge-truth intent.

Repair:

- Added a bounded percent parser on top of the existing finite non-negative numeric helper.
- Applied it to `LIMEN_RESERVE_PCT`, `LIMEN_RESERVE_FLOOR_PCT`, and the matching `usage-limits.json` fields.
- Added a regression proving malformed/out-of-range reserve env values fall back to the default reserve and do not poison pacing health.

Touched paths:

- `scripts/usage-telemetry.py`
- `cli/tests/test_usage_telemetry_health.py`

Verification:

```bash
python3 -m pytest cli/tests/test_census.py cli/tests/test_budget_reset_heal.py cli/tests/test_usage_telemetry.py cli/tests/test_usage_telemetry_health.py -q
python3 -m py_compile cli/src/limen/census.py cli/src/limen/dispatch.py scripts/usage-telemetry.py
```

Result: `29 passed, 1 skipped`; compile passed.

### Dispatch blocked-lane signals still had type and reporting gaps

Severity: medium for dispatch steering clarity.

Evidence:

- While reconstructing the unresolved rank-7 control-plane row, the listed temp artifacts were already gone; the durable review surface available in the same pass was landed dispatch usage-gate code, including `9dd0b53` (`limen: stop dispatch on blocked lane signals`).
- The implementation intent was honest dispatch steering: do not assign work to lanes the live meter says cannot produce, and mark unavailable repos as terminal `failed_blocked` instead of cascading forever.
- `_usage_dead_lanes()` only treated numeric `0` as zero headroom/remaining. A JSON telemetry writer or hand-edited usage file with `"0"` would leave a throttle lane dispatchable even though it had no runway.
- `dispatch_parallel()` applied blocked results correctly to the task, but its summary bucket counted them as generic failures, obscuring the difference between retryable cascade failures and terminal routing blockers.

Repair:

- Added typed zero parsing for usage telemetry gate values.
- Counted blocked parallel results in a separate summary bucket.
- Added regressions for stringified zero headroom and parallel blocked-result persistence/reporting.

Touched paths:

- `cli/src/limen/dispatch.py`
- `cli/tests/test_usage_gate.py`
- `cli/tests/test_dispatch.py`

Verification:

```bash
python3 -m pytest cli/tests/test_usage_gate.py cli/tests/test_dispatch.py -q
python3 -m py_compile cli/src/limen/dispatch.py
```

Result: `43 passed`; compile passed.

### Claude workflow audits missed nested fanout transcripts

Severity: high for spend governance and post-run review accuracy.

Evidence:

- Rank 12 (`b7efae9c-af24-4c2c-9288-d2fa860ba974`) was an off-repo `/Volumes/Archive4T` PR-healing session with 4,098 prompt events and 23 changed-file entries. Most changed paths were deleted temp scratch files; the durable artifacts were the main Claude transcript and workflow scripts under `~/.claude/projects/-Volumes-Archive4T/...`.
- The persistent workflow prompts were mass PR-healing/triage launchers. They authorized one-head-per-repo fanout, rebases, merges, and limited admin merges for billing-blocked CI. That is exactly the kind of session shape the workflow guard is supposed to measure after the fact.
- Before this repair, `scripts/claude-workflow-guard.py audit-transcript` only scanned flat `session/subagents/*.jsonl`. Claude's workflow runner stores subagents at `session/subagents/workflows/<workflow-id>/*.jsonl`, so the guard audited only the main transcript file and reported zero expensive subagents.
- After recursive scanning, the same rank-12 transcript audit sees 216 transcript files, 5,396 usage-bearing messages, 9,891,611 billable-ish tokens, 237,812,500 cache-read tokens, and 134 Opus-class nested subagents. The prompt/session diff was therefore not just "large fanout happened"; the tracked proof surface undercounted the fanout by construction.

Repair:

- Made transcript audit recurse under the session `subagents/` tree.
- Added a regression for nested `subagents/workflows/<workflow>/agent-*.jsonl` layout.

Touched paths:

- `scripts/claude-workflow-guard.py`
- `cli/tests/test_claude_workflow_guard.py`

Verification:

```bash
python3 -m pytest cli/tests/test_claude_workflow_guard.py -q
python3 -m py_compile scripts/claude-workflow-guard.py
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Volumes-Archive4T/b7efae9c-af24-4c2c-9288-d2fa860ba974.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank12-audit.json
```

Result: `14 passed`; compile passed; patched audit reports 216 transcript files and 134 Opus-class nested subagents for rank 12.

### Claude transcript audits leaked raw unbounded prompt excerpts

Severity: high for the private/public boundary of prompt review artifacts.

Evidence:

- Refreshed rank 1 (`9750bef7-8829-4373-916a-f86338b2e20a`) was a broad Archive4T conductor/session-foundation run with 5,021 prompt events, 92 changed-file entries, 12 saved workflows, and 180 transcript files. The durable changed files are mostly Archive4T docs, Claude memory, launchd/container/dispatch surfaces, and workflow records; listed `~/.claude/jobs/9750bef7/tmp/*` scratch files were gone.
- Patched transcript audit reports 63,473,116 billable-ish tokens, 61,179,741 Opus-class billable-ish tokens, 1,621,582,877 cache-read tokens, 148 Opus-class subagents, 32 agent/workflow calls, and two unbounded-goal prompt hits for this session.
- `audit-session` already flags one completed workflow (`exposure-map-phase0`) as containing errored agents and failure/dead-agent evidence, so the existing guard can identify completion-shape lies in saved workflow JSON.
- The transcript guard's `unboundedGoalEvidence` field, however, carried a raw user prompt excerpt. `scripts/hooks/session-closeout.sh` can append the audit JSON into `logs/model-tier-audit.jsonl` when fanout fires, so the raw excerpt was an avoidable private-text leak in a durable audit surface.

Repair:

- Replaced raw `unboundedGoalEvidence.text` excerpts with `path`, `line`, `textSha256`, and `chars`.
- Added a regression that asserts the original prompt text is absent from audit stdout while the hash and length remain available for local correlation.

Touched paths:

- `scripts/claude-workflow-guard.py`
- `cli/tests/test_claude_workflow_guard.py`

Verification:

```bash
python3 -m pytest cli/tests/test_claude_workflow_guard.py -q
python3 -m py_compile scripts/claude-workflow-guard.py
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Volumes-Archive4T/9750bef7-8829-4373-916a-f86338b2e20a.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank1-audit.json
```

Result: `15 passed`; compile passed; patched rank-1 audit reports only line/hash/character metadata for the two unbounded prompt hits.

### Studium state loading was not actually fail-open

Severity: medium for daemon reliability.

Evidence:

- Refreshed rank 2 (`eb3b624c-206f-4c9e-91aa-f069967a3796`) was the broad Studium transmission-curriculum run: 3,593 prompt events, 229 changed-file entries, and substantial generated content plus the live `scripts/studium*.py` surfaces.
- The original worktree path was gone, but the Studium scripts and content are live on `main`.
- Patched transcript audit for the session reports 275 transcript files, 4,960 usage-bearing messages, 27,068,236 billable-ish tokens, 326,821,696 cache-read tokens, and 20 agent/workflow calls.
- The prompt/session intent repeatedly promised a fail-open daily face that would not crash the beat on missing or degraded data. `scripts/studium.py` handled malformed JSON, but not valid JSON with the wrong top-level shape. A `logs/studium-state.json` containing a list made `load_state()` call `.items()` on a list and crash before rendering the degraded face.
- Cursor fields from state were also trusted enough that non-string `work_id`, non-numeric `division`, or non-positive `day_in_division` could poison later rendering/advance logic.

Repair:

- Rejected wrong-shaped persisted state back to defaults.
- Normalized the cursor and streak fields on load.
- Added regressions for wrong top-level JSON shape and poisoned cursor fields.

Touched paths:

- `scripts/studium.py`
- `cli/tests/test_studium.py`

Verification:

```bash
python3 -m pytest cli/tests/test_studium.py -q
python3 -m py_compile scripts/studium.py
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-rippling-launching-trinket/eb3b624c-206f-4c9e-91aa-f069967a3796.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-eb3-audit.json
```

Result: `8 passed`; compile passed.

### Evocator canon loading trusted valid YAML shape too much

Severity: medium for autonomous beat reliability.

Evidence:

- Refreshed rank 3 (`343d6769-bdee-480f-88d9-981eec736b87`) was the Evocator/SVMMONER run. The original worktree and `~/.claude/jobs/343d6769/tmp/*` activation files were gone, but commits `078f90c` and `035ddae` landed the durable `scripts/evocator.py` and `spec/evocator` surfaces on `main`.
- Patched transcript audit reports 39 transcript files, 3,622 usage-bearing messages, 24,600,795 billable-ish tokens, 448,429,536 cache-read tokens, 22,631,162 Opus-class billable-ish tokens, 24 Opus-class subagents, 23 agent/workflow calls, and one unbounded-goal prompt hit.
- The organ promised "fail-open, never gate the beat." It caught unreadable or syntactically invalid YAML, but a valid YAML root with the wrong shape, such as a list, made `load_canon()` call `.get()` on a list. A truth whose `channels` field was present but not a mapping would later break render/channel logic.

Repair:

- Rejected wrong-shaped canon roots and non-list `truths` values as logged problems.
- Normalized non-mapping `channels` to an empty mapping while preserving the truth and reporting the problem.
- Added Evocator unit tests for both shape failures.

Touched paths:

- `scripts/evocator.py`
- `cli/tests/test_evocator.py`

Verification:

```bash
python3 -m pytest cli/tests/test_evocator.py -q
python3 -m py_compile scripts/evocator.py
python3 scripts/evocator.py
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-fluttering-wandering-wilkes/343d6769-bdee-480f-88d9-981eec736b87.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-343-audit.json
```

Result: `2 passed`; compile passed; live Evocator run reported `3 truths`, `FLAME unchanged`, corpus skipped because knowledge-corpus is absent on this host, and memory all present.

### Archive4T convergence row is transcript-only for code attribution

Severity: medium for audit completeness, not a current `main` code defect.

Evidence:

- Refreshed rank 4 (`7c761a22-5bdf-42e8-bfb6-e8988530303f`) was a broad Archive4T convergence/knowledge-corpus planning run: 1,719 prompt events, 41 changed-file entries, and mostly docs/memory/knowledge-corpus paths.
- Patched transcript audit reports 79 transcript files, 2,289 usage-bearing messages, 17,333,349 billable-ish tokens, 165,663,795 cache-read tokens, 12,719,125 Opus-class billable-ish tokens, 34 Opus-class subagents, 26 agent/workflow calls, and 23 unbounded-goal prompt hits.
- The only code/test paths in the row were under `~/Workspace/.limen-worktrees/converge-build`, but that worktree is no longer present. There were no matching in-window commits for `cli/src/limen/converge.py`, `cli/tests/test_converge.py`, or `docs/CONVERGE-ACTIVATION-RUNBOOK.md`.
- Current `cli/src/limen/converge.py` and `cli/tests/test_converge.py` exist on `main`, but they cannot be attributed to this session window from the surviving git evidence.

Outcome:

- No Limen code change was made for this row.
- The row remains useful as prompt/session evidence: high unbounded-goal pressure, high Opus usage, and off-repo knowledge-corpus/memory churn, but no durable code diff to review or patch.

Verification:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Volumes-Archive4T/7c761a22-5bdf-42e8-bfb6-e8988530303f.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-7c-audit.json
git log --all --since=2026-06-19T22:10:36Z --until=2026-06-20T11:09:22Z --oneline --stat -- cli/src/limen/converge.py cli/tests/test_converge.py docs/CONVERGE-ACTIVATION-RUNBOOK.md
```

Result: transcript audit succeeded; git-window search returned no matching commits.

### Obligations face did not fail open on wrong-shaped ledgers

Severity: medium for mail-beat reliability.

Evidence:

- Refreshed rank 5 (`a290329e-a778-478f-a7a7-9afa79709221`) was the UMA/mail obligations run: 30 changed-file entries spanning Limen mail-beat/obligations surfaces plus external Domus and universal-mail-automation roots.
- The original `glimmering-mapping-whistle` worktree and `/tmp/uma-*` atlas outputs were gone, but commits `7dd1789` and `310b83c` show the durable Limen-side mail/obligations surfaces on `main`.
- Patched transcript audit reports 40 transcript files, 3,019 usage-bearing messages, 17,224,078 billable-ish tokens, 269,663,204 cache-read tokens, 12,133,498 Opus-class billable-ish tokens, 6 Opus-class subagents, 15 agent/workflow calls, and three unbounded-goal prompt hits.
- `scripts/obligations-view.py` promised that a missing or torn ledger yields an empty state, never a crash. It handled parse errors, but if `obligations-ledger.json` was valid JSON of the wrong shape, such as a list, `build_view()` called `.get()` on a list. Mixed scalar entries inside `obligations`, `accounts`, `noise_killers`, or `levers` could still crash rendering.

Repair:

- Normalized non-mapping ledgers to `{}`.
- Filtered list fields down to mapping entries before rendering.
- Added regression tests for wrong-shaped ledgers and scalar list entries.

Touched paths:

- `scripts/obligations-view.py`
- `cli/tests/test_obligations_view.py`

Verification:

```bash
python3 -m pytest cli/tests/test_obligations_view.py -q
python3 -m py_compile scripts/obligations-view.py
python3 scripts/obligations-view.py
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-glimmering-mapping-whistle/a290329e-a778-478f-a7a7-9afa79709221.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-a290-audit.json
```

Result: `2 passed`; compile passed; live renderer reported 27 obligations and 3 verify-first items.

### Education-organism row has no surviving artifact root

Severity: medium for auditability, not a current Limen code defect.

Evidence:

- Refreshed rank 6 (`dc879846-e9bf-41c0-b25d-5cebab230983`) was a broad education-organism buildout: 97 changed-file entries, mostly external `~/Workspace/edu-organism/**` docs/config/code plus temporary PR files under `/tmp`.
- Patched transcript audit reports 57 transcript files, 3,434 usage-bearing messages, 21,420,595 billable-ish tokens, 315,757,786 cache-read tokens, 15,778,453 Opus-class billable-ish tokens, 10 Opus-class subagents, and 25 agent/workflow calls.
- The Limen worktree `.claude/worktrees/nested-humming-mochi` is gone.
- The temporary `/tmp/vh-*` commit/PR files are gone.
- The referenced external root `~/Workspace/edu-organism` is absent on this host, so none of the listed external code/docs/tests can be inspected directly.

Outcome:

- No Limen code change was made.
- This row is recorded as transcript-only/off-host artifact loss: the prompts/session are reviewable, but the actual produced files are not currently available for diff review.

Verification:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-nested-humming-mochi/dc879846-e9bf-41c0-b25d-5cebab230983.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-dc-audit.json
test -d /Users/4jp/Workspace/limen/.claude/worktrees/nested-humming-mochi
test -d /Users/4jp/Workspace/edu-organism
```

Result: transcript audit succeeded; both artifact roots were absent.

### Revenue backlog generator trusted local ladder and telemetry shape

Severity: medium for revenue-feed reliability.

Evidence:

- Refreshed rank 13 (`4693c425-3c29-4a48-9a0b-54fd9fd37753`) was the revenue-backlog / model-tier run. The original `piped-booping-kettle` worktree is gone, but the durable commits include `8d63423`, `91e5ff6`, `6973619`, and `304656b`.
- Patched transcript audit reports 31 transcript files, 2,361 usage-bearing messages, 13,691,070 billable-ish tokens, 266,381,347 cache-read tokens, 11,720,797 Opus-class billable-ish tokens, 15 expensive subagents, 18 agent/workflow calls, and three unbounded-goal prompt hits.
- The prompt/session intent was to feed idle win-class capacity with revenue work rather than generated busywork. `scripts/generate-revenue-backlog.py` was therefore a heartbeat-critical revenue supply path.
- The generator already failed open on unreadable or syntactically invalid `revenue-ladder.json`, but valid JSON with the wrong top-level shape made `_products()` call `.get()` on a non-mapping. A non-list `products` value could also break product extraction.
- `LIMEN_REVENUE_FLOOR` and `LIMEN_REVENUE_MAX` were parsed with bare `int(...)` while constructing argparse defaults, so one malformed launchd/shell env value could abort the feed before the script reached read-only planning.
- Headroom telemetry only accepted native numeric JSON types and treated booleans as integers. Numeric strings from JSON-safe telemetry were ignored, while boolean `true` could count as `1%` headroom.

Repair:

- Added positive integer fallback parsing for revenue floor and max-new defaults.
- Added finite numeric parsing for usage headroom that accepts numeric strings but rejects booleans, malformed strings, and non-finite values.
- Made revenue ladder loading fail open on wrong-shaped roots and wrong-shaped `products` collections.
- Added regressions for bad ladder shape, mixed headroom telemetry, and malformed revenue env defaults.

Touched paths:

- `scripts/generate-revenue-backlog.py`
- `cli/tests/test_generate_revenue_backlog.py`

Verification:

```bash
python3 -m pytest cli/tests/test_generate_revenue_backlog.py -q
python3 -m py_compile scripts/generate-revenue-backlog.py
git diff --check -- scripts/generate-revenue-backlog.py cli/tests/test_generate_revenue_backlog.py docs/agent-code-diff-review.md
LIMEN_REVENUE_FLOOR=bad LIMEN_REVENUE_MAX=bad python3 scripts/generate-revenue-backlog.py
```

Result: `5 passed`; compile passed; diff check passed; malformed-env dry run exited `0` and remained read-only.

### Moneta order persistence trusted saved row shape

Severity: medium for checkout reliability and restart durability.

Evidence:

- Refreshed rank 14 (`4a4c2aa8-d455-431e-b18c-3ac1d5824741`) maps to live Moneta checkout/order work. Durable commits include `eeb1d55` (`feat(moneta): serve MONETA's own buyer-facing checkout page`) and `a5d4a49` (`feat(moneta): persist the order book so the pooled valve survives a restart`).
- Patched transcript audit reports 19 transcript files, 2,793 usage-bearing messages, 18,447,762 billable-ish tokens, 388,544,259 cache-read tokens, 13,495,868 Opus-class billable-ish tokens, one expensive subagent, 11 agent/workflow calls, and two unbounded-goal prompt hits.
- The prompt/session intent was that Moneta's pooled buyer demand and paid licences survive process restarts on ephemeral hosts. `FileOrderPersistence.load()` caught syntax errors and wrong top-level JSON shapes, but trusted any valid JSON array as `Order[]`.
- A valid JSON array containing `null`, a scalar, or an object with malformed `id`, `status`, `sats`, or timestamp fields could make `OrderStore` crash during startup when it read `order.id`. That violates the "corrupt file must never crash the mint" contract and can drop the checkout surface until the file is manually repaired.

Repair:

- Added an explicit persisted-order shape guard for IDs, addresses, finite numeric fields, canonical statuses, and optional string fields.
- Changed file loading to filter valid saved orders from a mixed array instead of blindly casting the whole array.
- Added a regression proving malformed saved rows are dropped without losing valid pooled demand.

Touched paths:

- `moneta/src/orders-file.ts`
- `moneta/src/__tests__/orders-file.test.ts`

Verification:

```bash
npm test --prefix moneta
git diff --check -- moneta/src/orders-file.ts moneta/src/__tests__/orders-file.test.ts docs/agent-code-diff-review.md
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-linear-conjuring-bear/4a4c2aa8-d455-431e-b18c-3ac1d5824741.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-4a4c-audit.json
```

Result: Moneta tests/typecheck returned `43 passed`; diff check passed; transcript audit completed and reported the expected spend/unbounded-goal violations for this high-pressure session.

### Course-recapitulation row has no surviving code artifact root

Severity: medium for auditability, not a current Limen code defect.

Evidence:

- Refreshed rank 15 (`95f5e850-1274-40de-8a32-8ade3192b22a`) was a course-recapitulation / education-organism run with 50 changed-file refs, mostly under `~/Workspace/edu-organism/**`, plus Claude plan/memory files and a temp converter script.
- Patched transcript audit reports 16 transcript files, 1,556 usage-bearing messages, 12,477,844 billable-ish tokens, 158,961,756 cache-read tokens, 10,316,377 Opus-class billable-ish tokens, two expensive subagents, and 15 agent/workflow calls.
- The original Limen worktree `.claude/worktrees/peaceful-plotting-fern` is absent on this host.
- The external root `~/Workspace/edu-organism` is absent on this host.
- The temp script `~/.claude/jobs/95f5e850/tmp/conv_eng101.py` is absent. The Claude plan file and two memory files still exist, but they are evidence of intent/handoff, not the generated course-engine code itself.
- A git-window search over the listed course-engine and feedback-bank paths found no matching commits in the Limen repo.

Outcome:

- No Limen code change was made for this row.
- This row remains review-relevant because it shows a high-cost session where prompts and handoff memory survived, but the actual produced education-organism files are unavailable for code diff review on this host.

Verification:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-peaceful-plotting-fern/95f5e850-1274-40de-8a32-8ade3192b22a.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-95f5-audit.json
test -d /Users/4jp/Workspace/limen/.claude/worktrees/peaceful-plotting-fern
test -d /Users/4jp/Workspace/edu-organism
test -f /Users/4jp/.claude/jobs/95f5e850/tmp/conv_eng101.py
git log --all --since=2026-06-23T16:58:37Z --until=2026-06-24T15:45:34Z --oneline --stat -- courses/_engine/dates.py courses/_engine/ingest.py courses/_engine/pii.py courses/_engine/recapitulate.py academia/feedback-bank/universal-feedback-discussions.md academia/feedback-bank/universal-feedback-essays.md
```

Result: transcript audit completed and reported an Opus budget violation; both artifact roots and the temp converter were absent; git-window search returned no matching commits.

### Credential wall predicate could crash before checking homes

Severity: medium for secret-handling governance reliability.

Evidence:

- Refreshed rank 16 (`06d2559b-05e9-4ff3-b1bf-4473bd935228`) maps to landed wall/dialog commits including `cbeed10` (`feat(walls): machine-generate the secret Wall + add the his-hand aggregate Wall`), plus adjacent dialog-silencing and obligations-deadline commits.
- Patched transcript audit reports 25 transcript files, 1,603 usage-bearing messages, 12,143,079 billable-ish tokens, 149,801,452 cache-read tokens, 9,591,570 Opus-class billable-ish tokens, eight expensive subagents, and seven agent/workflow calls.
- The session/prompt intent was to move token/secret/API/login/env handling out of chat and into a durable Wall with an executable `--check` predicate. That predicate should be robust to local operator env drift.
- `scripts/credential-wall.py` parsed `LIMEN_CRED_WALL_ISSUE` with bare `int(...)` at import time. A malformed shell/launchd value crashed the script before `--check` could verify that every secret atom has a registered home.

Repair:

- Added a positive integer env parser for the wall issue number.
- Made malformed, zero, or negative values fall back to issue `320`.
- Added an import-time regression and verified the live predicate under a poisoned env value.

Touched paths:

- `scripts/credential-wall.py`
- `cli/tests/test_credential_wall.py`

Verification:

```bash
python3 -m pytest cli/tests/test_credential_wall.py -q
python3 -m py_compile scripts/credential-wall.py
LIMEN_CRED_WALL_ISSUE=bad python3 scripts/credential-wall.py --check
git diff --check -- scripts/credential-wall.py cli/tests/test_credential_wall.py docs/agent-code-diff-review.md
```

Result: `6 passed`; compile passed; malformed-env `--check` exited `0` and reported all 16 secret atoms registered.

### Scoped cell conductor could fall back to the full mixed board

Severity: high for the one-worker-one-workstream invariant.

Evidence:

- Refreshed rank 17 (`3be1f3a6-e00e-403d-a967-6d86c55deb56`) maps to landed workstream/channel commits: `0fcd5b3`, `b7ca033`, `2aa6011`, and `17a12d3`.
- Patched transcript audit reports eight transcript files, 2,328 usage-bearing messages, 17,064,364 billable-ish tokens, 377,658,818 cache-read tokens, six expensive subagents, six agent/workflow calls, and two unbounded-goal prompt hits.
- The prompt/session ideal was a purpose axis above vendor lanes: a worker session should draw open tasks from exactly one workstream so it cannot create another mixed-purpose PR pile.
- The pure `limen.workstream` grouping code was mostly sound, but `scripts/cells.sh` violated the operational invariant. If `limen channels --scope <workstream> --emit tasks.cell.yaml` failed, `cell conduct --workstream` copied the full `tasks.yaml` into the cell board as a fallback.
- That meant a transient CLI failure, bad scope, or invalid board could silently hand the scoped conductor all mixed tasks while still printing `workstream=<handle>`.

Repair:

- Added a helper that writes a minimal valid empty board.
- Changed the scoped-conductor failure path to write the empty board and log the isolation-preserving fallback instead of copying the full board.
- Added a shell regression with a fake failing `limen` binary proving `tasks.cell.yaml` contains no mixed task when scoped emit fails.
- This code fix was captured by the repo daemon in `3789b78` while the review was running; this section records the review evidence and acceptance.

Touched paths:

- `scripts/cells.sh`
- `cli/tests/test_cells.py`

Verification:

```bash
python3 -m pytest cli/tests/test_workstream.py cli/tests/test_cells.py -q
bash -n scripts/cells.sh
```

Result: `13 passed`; shell syntax check passed.

### Insights and multiprovider reanchor row is split across surviving private artifacts

Severity: medium for auditability, not a current Limen code defect.

Evidence:

- Refreshed rank 18 (`57fa1ead-aabf-4c2e-b62e-6843cf74a66a`) spans the Claude insights hook, temp rescue/snapshot scripts, Claude plan/settings/memory files, two `.limen-worktrees` side roots, and one `.session-meta-worktrees` side root.
- Patched transcript audit reports 15 transcript files, 2,030 usage-bearing messages, 9,991,973 billable-ish tokens, 205,630,944 cache-read tokens, 7,850,263 Opus-class billable-ish tokens, seven agent/workflow calls, and one unbounded-goal prompt hit.
- Surviving private artifacts: `~/.claude/hooks/insights-capture.sh`, `~/.claude/plans/indexed-baking-breeze.md`, `~/.claude/settings.proposed.json`, and the Claude memory files for censor/pillars context.
- Surviving side-worktree artifact: `/Users/4jp/Workspace/.session-meta-worktrees/reanchor-multiprovider-ingest`, with commit `048dd74` (`feat(ingest): re-anchor multi-provider atoms producer into session-meta`) touching `ingest/refresh-atoms.sh`.
- Missing artifacts: `~/.claude/jobs/57fa1ead/tmp/rescue_insights.py`, `~/.claude/jobs/57fa1ead/tmp/snapshot_0623.py`, `/Users/4jp/Workspace/.limen-worktrees/censor-institution`, `/Users/4jp/Workspace/.limen-worktrees/cutover-corpus-feed-multiprovider`, and `/Users/4jp/Workspace/.limen-worktrees/heal-192-regression`.
- A Limen git-window search over the listed hook/temp/worktree paths found no matching in-repo commits.

Outcome:

- No Limen code change was made for this row.
- The review finding is provenance/auditability: some work survived as private home-state and a separate session-meta worktree, while the claimed temp and side-worktree artifacts needed for full code diff review are gone.

Verification:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-indexed-baking-breeze/57fa1ead-aabf-4c2e-b62e-6843cf74a66a.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-57fa-audit.json
test -f /Users/4jp/.claude/hooks/insights-capture.sh
test -f /Users/4jp/.claude/jobs/57fa1ead/tmp/rescue_insights.py
test -d /Users/4jp/Workspace/.limen-worktrees/censor-institution
test -d /Users/4jp/Workspace/.session-meta-worktrees/reanchor-multiprovider-ingest
git -C /Users/4jp/Workspace/.session-meta-worktrees/reanchor-multiprovider-ingest log -5 --oneline --decorate --stat -- ingest/refresh-atoms.sh
```

Result: transcript audit completed with spend/unbounded-goal violations; hook/plan/settings/memory and the session-meta worktree were present; temp scripts and the two named `.limen-worktrees` roots were absent; session-meta log showed commit `048dd74`.

### Mail audit row has an external classifier fix and an unclosed ledger gap

Severity: medium for auditability and obligation truth.

Evidence:

- Refreshed rank 19 (`5e1004b3-b917-4a9d-a1ca-0f9b2b8dba45`) spans mail audit artifacts, Domus workflow probe drafts, verification scripts, Claude memory files, and an external `~/Workspace/universal-mail--automation` test path.
- Patched transcript audit reports 67 transcript files, 1,549 usage-bearing messages, 13,646,225 billable-ish tokens, 271,134,912 cache-read tokens, 10,748,941 Opus-class billable-ish tokens, 24 expensive subagents, and six agent/workflow calls.
- Surviving private artifacts include `MAIL-AUDIT.md`, `extract_prompts.py`, `ground-truth.md`, `verify_decide.py`, and `verify_star_disposition.py`.
- Missing private artifacts include the `domus-draft`, `domus-probe`, `domus-probe2`, and `um-inc2` temp worktrees.
- The external `universal-mail--automation` repo survived the relevant code diff at commit `39bf80d` (`fix(inbox_sweep): stop the flagged-newsletter storm at its root`), adding `tests/test_inbox_sweep_decide.py`.
- Focused external verification passes: `python3 -m pytest tests/test_inbox_sweep_decide.py -q` returned `7 passed`.
- The surviving mail audit itself records the main residual: sent/withheld replies are not reconciled back into the obligations ledger, so obligations such as replied or deliberately skipped mail can remain displayed as "Reply owed."

Outcome:

- No Limen code change was made for this row.
- The newsletter-storm classifier fix is verified in the external mail repo; the prompt-vs-done gap to carry forward is obligation-ledger reconciliation, not another classifier patch.

Verification:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen/5e1004b3-b917-4a9d-a1ca-0f9b2b8dba45.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-5e1004-audit.json
python3 -m pytest tests/test_inbox_sweep_decide.py -q  # run in /Users/4jp/Workspace/universal-mail--automation
git -C /Users/4jp/Workspace/universal-mail--automation log --since=2026-07-02T17:34:35Z --until=2026-07-03T18:34:03Z --oneline --decorate --stat -- tests/test_inbox_sweep_decide.py
```

Result: transcript audit completed with an Opus budget violation; external classifier tests returned `7 passed`; external git log showed commit `39bf80d`.

### Pre-build excavation gate matched keywords as regex

Severity: medium for duplicate-work prevention.

Evidence:

- Refreshed rank 20 (`ce278978-35f1-4b6c-a511-41f5d1de75cf`) maps to landed Limen commit `28cdcb3` (`feat(scripts): pre-build-excavate — enforceable 'did a parallel session already ship this?' predicate`).
- Patched transcript audit reports 37 transcript files, 1,465 usage-bearing messages, 13,810,471 billable-ish tokens, 89,690,141 cache-read tokens, 11,527,801 Opus-class billable-ish tokens, 21 expensive subagents, and 11 agent/workflow calls.
- The prompt/session ideal was an enforceable pre-build gate: before building in a shared fleet repo, enumerate PR/commit streams and stop if a user-supplied keyword literally matches shipped or in-flight work.
- `scripts/pre-build-excavate.sh` used `grep -i` for keyword matching. That treated user keywords as regular expressions, so `moneta.checkout` could match `moneta-checkout`, and regex metacharacters could create false duplicate hits or false clears.
- The temp research/audit files and private venture root listed in the session metadata are absent on this host; no private venture content was copied into the public review doc.

Repair:

- Changed keyword matching to `grep -Fi` so user keywords are fixed strings.
- Added fake-`gh` shell tests proving literal duplicate hits still return `LIKELY-DUP` and regex-like keywords do not match different strings.

Touched paths:

- `scripts/pre-build-excavate.sh`
- `cli/tests/test_pre_build_excavate.py`

Verification:

```bash
python3 -m pytest cli/tests/test_pre_build_excavate.py -q
bash -n scripts/pre-build-excavate.sh
git diff --check -- scripts/pre-build-excavate.sh cli/tests/test_pre_build_excavate.py docs/agent-code-diff-review.md
```

Result: `2 passed`; shell syntax check passed; diff check passed.

## Current File References

- `scripts/route.py:115` defines the tolerant numeric parser.
- `scripts/route.py:137` fails malformed `runway_h` open to infinite runway.
- `scripts/route.py:205` applies safe self-improve weight floor/ceiling parsing.
- `scripts/route.py:239` and `scripts/route.py:249` apply safe cadence/timeout parsing.
- `scripts/route.py:273` applies safe ledger-bias floor parsing.
- `cli/tests/test_route_bias.py:106` covers malformed route knob parsing.
- `cli/tests/test_route_bias.py:119` covers malformed usage runway parsing.
- `cli/src/limen/dispatch.py:38` defines the dispatch tolerant numeric parsers.
- `cli/src/limen/dispatch.py:145` applies safe OAuth preflight timeout parsing.
- `cli/src/limen/dispatch.py:477` applies safe agent command timeout parsing.
- `cli/src/limen/dispatch.py:1365` applies safe isolated lane timeout parsing.
- `cli/src/limen/dispatch.py:1744` applies safe accelerator floor/ceiling parsing.
- `scripts/dispatch-async.py:52` defines async-dispatch tolerant numeric parsing.
- `cli/tests/test_dispatch.py:493` covers malformed dispatch env knobs.
- `cli/tests/test_async_dispatch.py:107` covers malformed async-dispatch env knobs.
- `.github/workflows/auto-scale.yml:34` commits only when `tasks.yaml` changed.
- `.github/workflows/auto-scale.yml:40` stages only `tasks.yaml`.
- `scripts/auto-scale.py:30` imports the canonical `queue_lock`.
- `scripts/auto-scale.py:114` caps pagination and tracks repeated page URLs.
- `scripts/auto-scale.py:158` takes the queue lock before the final board mutation.
- `scripts/auto-scale.py:162` re-reads `tasks.yaml` under the lock.
- `scripts/auto-scale.py:197` skips the atomic write when no new tasks survive.
- `cli/tests/test_auto_scale.py:193` covers reloading under lock before write.
- `cli/tests/test_auto_scale.py:263` covers repeated duplicate pages.
- `cli/src/limen/dispatch.py:1873` defines fresh-board parallel reservation selection.
- `cli/src/limen/dispatch.py:1920` tracks selected budget across lanes before reserving.
- `cli/src/limen/dispatch.py:1975` takes the queue lock before live reservation.
- `cli/src/limen/dispatch.py:1982` re-reads `tasks.yaml` under the lock before selecting reservations.
- `cli/tests/test_dispatch.py:440` covers preserving concurrently added tasks during reservation.
- `cli/tests/test_dispatch.py:494` covers not dispatching stale-open tasks that became `done`.
- `scripts/dispatch-async.py:270` skips candidates that no longer fit current reserve-pass headroom.
- `scripts/dispatch-async.py:274` decrements lane remaining budget as tasks are picked.
- `scripts/dispatch-async.py:275` decrements shared daily budget as tasks are picked.
- `cli/tests/test_async_dispatch.py:290` covers per-agent picked-cost accumulation.
- `cli/tests/test_async_dispatch.py:301` covers daily picked-cost accumulation across lanes.
- `scripts/agent-session-full-stack-review.py:78` matches patch file headers.
- `scripts/agent-session-full-stack-review.py:293` extracts changed files from Codex patch text.
- `scripts/agent-session-full-stack-review.py:318` extracts changed files from structured tool payloads.
- `scripts/agent-session-full-stack-review.py:749` wires Codex assistant/tool records into changed-file extraction.
- `scripts/agent-session-full-stack-review.py:759` wires Codex function/custom tool records into changed-file extraction.
- `scripts/agent-session-full-stack-review.py:837` wires Claude assistant tool-use records into changed-file extraction.
- `scripts/agent-session-full-stack-review.py:81` defines mutating Agy action detection.
- `scripts/agent-session-full-stack-review.py:359` decodes bounded embedded JSON objects around Agy `TargetFile` fields.
- `scripts/agent-session-full-stack-review.py:394` extracts changed files from Agy CLI `TargetFile` spans.
- `scripts/agent-session-full-stack-review.py:1094` wires Agy CLI conversation steps into changed-file extraction.
- `cli/tests/test_agent_session_full_stack_review.py:18` covers patch header extraction.
- `cli/tests/test_agent_session_full_stack_review.py:42` covers Codex custom `apply_patch` extraction.
- `cli/tests/test_agent_session_full_stack_review.py:59` covers Claude mutating-tool extraction.
- `cli/tests/test_agent_session_full_stack_review.py:73` covers Agy mutating `TargetFile` extraction and read-only exclusion.
- `web/api/main.py:76` rejects boolean values before integer validation.
- `web/api/main.py:168` applies strict budget-cost validation to task creation.
- `web/api/main.py:257` applies strict budget-cost validation to assignment steering.
- `web/api/main.py:312` applies strict limit validation to dispatch requests.
- `web/worker/src/index.js:75` rejects boolean integer inputs in the worker adapter.
- `web/api/tests/test_main.py:559` covers assignment boolean budget rejection.
- `web/api/tests/test_main.py:903` covers task-create boolean budget rejection.
- `web/api/tests/test_main.py:921` covers dispatch boolean limit rejection.
- `scripts/verify-dispatch.py:38` defines tolerant verifier env integer parsing.
- `scripts/verify-dispatch.py:45` applies the verifier dispatch grace fallback.
- `scripts/prompt-lifecycle-ledger.py:46` defines tolerant lifecycle env integer parsing.
- `scripts/prompt-lifecycle-ledger.py:53` applies the lifecycle dispatch grace fallback.
- `scripts/prompt-lifecycle-ledger.py:54` applies the GitHub receipt retry fallback.
- `cli/tests/test_verify_dispatch.py:27` covers malformed verifier timeout import.
- `cli/tests/test_prompt_lifecycle_ledger.py:18` covers malformed lifecycle timeout and retry imports.
- `scripts/claim-task.py:15` defines the canonical claimable-agent allowlist.
- `scripts/claim-task.py:47` rejects boolean, malformed, and negative integer fields.
- `scripts/claim-task.py:59` defaults absent optional integer fields without accepting present malformed values.
- `scripts/claim-task.py:65` rejects unknown claim agents before board mutation.
- `scripts/claim-task.py:81` validates task budget cost before claim mutation.
- `scripts/claim-task.py:91` validates global spent before claim mutation.
- `scripts/claim-task.py:95` validates per-agent spent before claim mutation.
- `cli/tests/test_claim_task.py:37` covers valid reservation and budget accounting.
- `cli/tests/test_claim_task.py:50` covers invalid-agent rejection without mutation.
- `cli/tests/test_claim_task.py:61` covers malformed-budget rejection without mutation.
- `cli/tests/test_claim_task.py:72` covers boolean-budget rejection without mutation.
- `scripts/usage-telemetry.py:41` defines the finite non-negative numeric coercion helper.
- `scripts/usage-telemetry.py:56` applies fail-open cooldown parsing at import time.
- `scripts/usage-telemetry.py:232` tolerates non-string window labels.
- `scripts/usage-telemetry.py:490` coerces Opencode clock token counters.
- `scripts/usage-telemetry.py:493` coerces Opencode clock cap tokens.
- `scripts/usage-telemetry.py:499` coerces Opencode clock used percentage.
- `scripts/usage-telemetry.py:520` coerces possible budget before headroom math.
- `scripts/usage-telemetry.py:521` coerces consumed budget before headroom math.
- `cli/tests/test_usage_telemetry_health.py:87` covers string Opencode clock numerics.
- `cli/tests/test_usage_telemetry_health.py:106` covers malformed Opencode clock numerics.
- `cli/tests/test_usage_telemetry_health.py:125` covers malformed cooldown env parsing.
- `cli/src/limen/tabularius.py:247` handles board-meta tickets.
- `cli/src/limen/tabularius.py:253` rejects non-mapping board portal patches.
- `cli/src/limen/tabularius.py:256` validates candidate board metadata before mutation.
- `cli/src/limen/tabularius.py:267` handles board-order tickets.
- `cli/src/limen/tabularius.py:269` rejects malformed board-order id lists.
- `cli/src/limen/tabularius.py:349` folds the candidate board under validation.
- `cli/src/limen/tabularius.py:350` quarantines fold validation failures instead of crashing.
- `cli/tests/test_tabularius.py:176` covers bad board-meta quarantine with good-ticket survival.
- `cli/tests/test_tabularius.py:191` covers bad board-order quarantine with good-ticket survival.
- `scripts/watchdog.py:55` defines positive integer env fallback parsing.
- `scripts/watchdog.py:71` applies fallback parsing to the loop max threshold.
- `scripts/watchdog.py:72` applies fallback parsing to the lane timeout threshold.
- `scripts/watchdog.py:74` applies fallback parsing to the dispatch ceiling threshold.
- `scripts/watchdog.py:75` applies fallback parsing to watchdog overhead.
- `scripts/watchdog.py:76` applies fallback parsing to the stale threshold.
- `scripts/watchdog.py:80` applies fallback parsing to max-fails.
- `scripts/self-heal.py:197` defines positive integer env fallback parsing.
- `scripts/self-heal.py:207` applies fallback parsing to heal scan size.
- `scripts/self-heal.py:209` applies fallback parsing to heal scan max.
- `scripts/self-heal.py:211` applies fallback parsing to heal emit limit.
- `cli/tests/test_watchdog.py:77` covers malformed watchdog numeric env values.
- `cli/tests/test_self_heal.py:120` covers malformed self-heal numeric env values.
- `scripts/ledger.py:30` defines safe integer fallback parsing for ledger values.
- `scripts/ledger.py:40` defines finite float fallback parsing for ledger thresholds.
- `scripts/ledger.py:85` applies safe parsing to spent totals.
- `scripts/ledger.py:86` applies safe parsing to sunk totals.
- `scripts/ledger.py:116` applies safe parsing to the waste-rate threshold.
- `scripts/ledger.py:117` applies safe parsing to the win-rate threshold.
- `scripts/ledger.py:118` applies safe parsing to the minimum-volume threshold.
- `scripts/score-dispatch.py:41` defines positive integer fallback parsing for task costs.
- `scripts/score-dispatch.py:92` applies safe parsing to `budget_cost`.
- `scripts/ingest-coverage.py:29` defines non-negative integer fallback parsing for manifest counts.
- `scripts/ingest-coverage.py:55` applies safe parsing to `atom_count`.
- `scripts/ingest-coverage.py:56` normalizes manifest source keys.
- `scripts/media-atomize.py:53` defines positive integer env fallback parsing.
- `scripts/media-atomize.py:61` applies safe parsing to media chunk max.
- `scripts/media-atomize.py:62` applies safe parsing to media chunk min.
- `scripts/media-atomize.py:63` applies safe parsing to PDF timeout.
- `scripts/media-atomize.py:502` applies safe parsing to default media atomize limit.
- `cli/tests/test_ledger.py:93` covers malformed ledger numeric inputs and threshold env values.
- `cli/tests/test_score_dispatch.py:93` covers malformed task `budget_cost` values.
- `cli/tests/test_ingest_coverage.py:52` covers malformed manifest atom counts.
- `cli/tests/test_media_atomize.py:184` covers malformed media atomize env values.
- `cli/src/limen/models.py:7` defines the canonical task-id pattern.
- `cli/src/limen/models.py:33` applies the task-id pattern and length guard.
- `cli/src/limen/models.py:46` bounds `budget_cost` to a positive integer range.
- `cli/src/limen/models.py:71` rejects boolean task budget values before Pydantic integer coercion.
- `cli/tests/test_io_atomic.py:166` covers invalid task-id rejection.
- `cli/tests/test_io_atomic.py:173` covers invalid and boolean task-budget rejection.
- `cli/src/limen/io.py:26` defines integer fallback parsing for shared IO env knobs.
- `cli/src/limen/io.py:38` defines finite float fallback parsing for shared IO env knobs.
- `cli/src/limen/io.py:52` applies fallback parsing to queue-lock stale seconds.
- `cli/src/limen/io.py:283` applies fallback parsing to the board shrink floor.
- `cli/src/limen/io.py:284` applies fallback parsing to the board shrink fraction.
- `cli/tests/test_io_atomic.py:145` covers malformed, `nan`, and infinite shared IO env values.
- `cli/tests/test_io_atomic.py:157` covers non-positive shared IO env values.
- `scripts/claude-usage.py:43` defines finite numeric parsing for Claude gauge inputs.
- `scripts/claude-usage.py:62` finds numeric fields in usage dictionaries.
- `scripts/claude-usage.py:70` applies fallback parsing to the Claude gauge freshness env.
- `scripts/claude-usage.py:133` coerces transcript token fields before weighted-cost math.
- `scripts/claude-usage.py:168` treats malformed freshness timestamps as unknown freshness.
- `scripts/claude-usage.py:197` rejects malformed proxy used-percent fields.
- `scripts/claude-usage.py:225` validates calibration cost and percent fields.
- `scripts/claude-usage.py:293` accepts numeric usage-count fields without trusting malformed values.
- `scripts/claude-usage.py:305` validates the explicit Claude weekly cap env.
- `scripts/claude-usage.py:367` catches per-avenue exceptions so one bad source cannot abort the cascade.
- `scripts/reap-branches.py:85` defines integer env fallback parsing.
- `scripts/reap-branches.py:95` defines finite float env fallback parsing.
- `scripts/reap-branches.py:312` applies safe parsing to branch-reap max.
- `scripts/reap-branches.py:315` applies safe parsing to branch-reap throttle minutes.
- `scripts/verify-budget-gauge.py:56` defines finite numeric parsing for live gauge payloads.
- `scripts/verify-budget-gauge.py:70` converts rate-limit minutes to window labels without throwing.
- `scripts/verify-budget-gauge.py:177` coerces Codex primary used-percent and window fields.
- `scripts/verify-budget-gauge.py:182` coerces Codex weekly used-percent and window fields.
- `scripts/verify-budget-gauge.py:310` coerces display percentages before formatting.
- `cli/tests/test_claude_usage.py:43` covers malformed Claude freshness env fallback.
- `cli/tests/test_claude_usage.py:50` covers malformed proxy used-percent telemetry.
- `cli/tests/test_claude_usage.py:65` covers malformed proxy freshness timestamps.
- `cli/tests/test_claude_usage.py:102` covers string count/cap numerics.
- `cli/tests/test_reap_branches.py:84` covers malformed and non-positive branch-reap env knobs.
- `cli/tests/test_verify_budget_gauge.py:15` covers malformed live Codex rate-limit payloads.
- `cli/tests/test_verify_budget_gauge.py:37` covers human display of malformed used-percent fields.
- `scripts/usage-telemetry.py:53` bounds reserve percentage inputs.
- `scripts/usage-telemetry.py:160` applies bounded parsing to reserve floor env values.
- `scripts/usage-telemetry.py:166` applies bounded parsing to reserve floor config values.
- `scripts/usage-telemetry.py:222` applies bounded parsing to reserve env values.
- `scripts/usage-telemetry.py:228` applies bounded parsing to reserve config values.
- `cli/tests/test_usage_telemetry_health.py:135` covers malformed and out-of-range reserve env values.
- `cli/src/limen/dispatch.py:114` stops throttle lanes with zero remaining/headroom.
- `cli/src/limen/dispatch.py:119` parses usage zero values from JSON-safe numeric strings.
- `cli/src/limen/dispatch.py:2032` tracks blocked results separately in parallel dispatch summaries.
- `cli/src/limen/dispatch.py:2056` increments the blocked result bucket.
- `cli/tests/test_usage_gate.py:48` covers stringified zero headroom/remaining telemetry.
- `cli/tests/test_dispatch.py:726` covers parallel blocked-result persistence and reporting.
- `scripts/claude-workflow-guard.py:339` recursively includes nested workflow subagent transcripts.
- `scripts/claude-workflow-guard.py:371` stores unbounded prompt evidence as hash/length metadata instead of raw text.
- `cli/tests/test_claude_workflow_guard.py:189` covers redacted unbounded prompt evidence.
- `cli/tests/test_claude_workflow_guard.py:264` covers nested Claude workflow subagent layout.
- `scripts/studium.py:109` defines positive integer normalization for persisted Studium state.
- `scripts/studium.py:119` rejects wrong-shaped state before merging persisted values.
- `cli/tests/test_studium.py:132` covers wrong-shaped state JSON.
- `cli/tests/test_studium.py:143` covers poisoned cursor fields.
- `scripts/evocator.py:88` rejects wrong-shaped canon roots.
- `scripts/evocator.py:91` rejects non-list canon truth collections.
- `scripts/evocator.py:104` normalizes non-mapping channel data.
- `cli/tests/test_evocator.py:22` covers wrong-shaped canon YAML.
- `cli/tests/test_evocator.py:36` covers bad channel data without crashing rendering.
- `scripts/obligations-view.py:43` rejects non-mapping ledgers for lever union.
- `scripts/obligations-view.py:63` rejects non-mapping ledgers before view construction.
- `scripts/obligations-view.py:69` filters obligations to mapping entries.
- `cli/tests/test_obligations_view.py:20` covers wrong-shaped obligation ledgers.
- `cli/tests/test_obligations_view.py:33` covers scalar entries in ledger lists.
- `scripts/generate-revenue-backlog.py:105` defines positive integer fallback parsing for revenue defaults.
- `scripts/generate-revenue-backlog.py:115` defines finite telemetry numeric parsing.
- `scripts/generate-revenue-backlog.py:133` rejects wrong-shaped revenue-ladder roots.
- `scripts/generate-revenue-backlog.py:137` rejects non-list product collections.
- `scripts/generate-revenue-backlog.py:153` coerces usage headroom before averaging.
- `scripts/generate-revenue-backlog.py:258` applies safe revenue floor default parsing.
- `scripts/generate-revenue-backlog.py:260` applies safe revenue max-new default parsing.
- `cli/tests/test_generate_revenue_backlog.py:98` covers wrong-shaped revenue ladder JSON.
- `cli/tests/test_generate_revenue_backlog.py:112` covers mixed headroom telemetry parsing.
- `cli/tests/test_generate_revenue_backlog.py:134` covers malformed positive integer defaults.
- `moneta/src/orders-file.ts:21` defines canonical persisted order statuses.
- `moneta/src/orders-file.ts:23` rejects non-finite numeric persisted fields.
- `moneta/src/orders-file.ts:31` validates persisted order rows before replaying them.
- `moneta/src/orders-file.ts:52` filters malformed saved rows during load.
- `moneta/src/__tests__/orders-file.test.ts:67` covers dropping malformed saved rows while preserving valid pooled demand.
- `scripts/credential-wall.py:42` defines positive integer parsing for the wall issue env.
- `scripts/credential-wall.py:50` applies the wall issue fallback.
- `cli/tests/test_credential_wall.py:64` covers malformed wall issue env values.
- `scripts/cells.sh:40` writes a valid empty scoped board.
- `scripts/cells.sh:116` attempts scoped board emission for the requested workstream.
- `scripts/cells.sh:118` preserves isolation with an empty board when scoped emission fails.
- `cli/tests/test_cells.py:13` covers the no-full-board fallback for scoped conductors.
- `scripts/pre-build-excavate.sh:74` matches duplicate-check keywords as fixed strings.
- `cli/tests/test_pre_build_excavate.py:57` covers literal duplicate hits.
- `cli/tests/test_pre_build_excavate.py:65` covers regex-like keywords as fixed strings.
- `cli/src/limen/dispatch.py:1147` copies directory-shaped Agy scratch deltas.
- `cli/src/limen/dispatch.py:1150` mirrors deleted Agy paths that are symlinks or directories.
- `cli/tests/test_agy_bridge.py:69` covers untracked directory deltas from `git status --porcelain -z`.

### Agy scratch bridge skipped new directory deltas

Severity: high for Agy/Antigravity work recovery, medium for repo safety.

Evidence:

- Claude session `84a89bbb-ecd3-4e22-8148-f9b683bd2d92` asked the lane to make Agy scratch work bridgeable and Jules dispatch autonomous.
- The Jules half survived on `main`: `_call_jules()` uses `jules remote new --repo ... --session ...`, the prompt is directive-led, and `_run_cmd()` captures the durable `ID:` from stdout for harvest matching.
- The Agy half correctly stopped whole-tree scratch overlays, but it still only copied regular-file paths. `git status --porcelain -z` reports a fully untracked directory as one `?? dir/` record, so a session that created a new test/package/docs folder could print a successful bridge message while carrying none of that folder's contents.

Repair:

- Updated `_bridge_agy_scratch()` to copy directory deltas with `shutil.copytree(..., dirs_exist_ok=True)`.
- Made deletion mirroring handle symlinks and directories, not only regular files.
- Added a regression for the exact `?? new_suite/` shape.

Touched paths:

- `cli/src/limen/dispatch.py`
- `cli/tests/test_agy_bridge.py`

Verification:

```bash
python3 -m pytest cli/tests/test_agy_bridge.py cli/tests/test_flame_kernel.py -q
bash scripts/done-jules-lane.sh
```

Result: `14 passed in 0.21s`; `jules-lane verification passed`.

### Archive4T relay handoff artifacts aged out of truth

Severity: medium for relay reliability and auditability, not a current Limen code defect.

Evidence:

- Claude session `f38f4b2a-5c49-4d13-9b36-24bf31c941cc` was a broad `/Volumes/Archive4T` conductor/relay incident run with 23 changed-file refs and 1,383 prompt events in the private queue metadata.
- Transcript audit reports 28 transcript files, 2,013 usage-bearing messages, 19,944,431 billable-ish tokens, 576,806,109 cache-read tokens, 19,458,400 Opus-class billable-ish tokens, 18 expensive subagents, five agent/workflow calls, and one unbounded-goal phrase hit stored as hash/length metadata.
- Sixteen changed-file refs under `/tmp` and `/Volumes/Archive4T` are absent on this host, including the listed vendor-lane audit, container manifest, consolidation docs, and backlog/owner rewrite scripts.
- Seven home-state artifacts survive: one Claude plan, three Claude memory files, `~/Workspace/LEMONSQUEEZY-HANDOFF.md`, `~/Workspace/RELAY-HANDOFF.md`, and `~/Workspace/limen-status-report.html`.
- The surviving static handoffs are historical, not current source of truth. For example, the June 21 status report says the heartbeat is down and the conductor scripts are missing, while current `main` has `scripts/generate-backlog.py`, `scripts/verify-dispatch.py`, `scripts/heal-dispatch.py`, `scripts/consolidate-github.py`, `scripts/watchdog.py`, and `cli/src/limen/dispatch.py` imports `secrets`.

Outcome:

- No code change was made for this row.
- The ideal-form diff is that the prompts demanded relay-grade, durable, verifiable state, but the produced state mixed ephemeral off-volume files with static handoffs that became stale. Future relay prompts should point to live probes and tracked generated reports instead of treating the June 2026 handoff files as current truth.

Verification:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Volumes-Archive4T/f38f4b2a-5c49-4d13-9b36-24bf31c941cc.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-f38-audit.json
test -f /Volumes/Archive4T/scripts/generate-backlog.py
test -f /Volumes/Archive4T/docs/CONSOLIDATE-DRYRUN.md
test -f /Users/4jp/Workspace/RELAY-HANDOFF.md
rg -n "^import secrets|def atomic_write_text|generate-backlog|verify-dispatch|heal-dispatch|consolidate-github|watchdog" cli/src/limen scripts docs
```

Result: transcript audit completed with Opus budget and unbounded-goal violations; the `/Volumes/Archive4T` changed-file refs sampled above were absent; the surviving relay/status artifacts are stale against current `main`.

### Etceter4 revival manifest missed archive photos

Severity: medium for the external revival site, low for Limen control-plane safety.

Evidence:

- Claude session `685b48b0-94fa-4537-a327-453a6ba01238` produced an external `etceter4-revival` document/script set: nine revival docs and `scripts/gen-image-manifest.mjs` survived under `~/Workspace/organvm/etceter4-revival`; the two temp extractor scripts are absent.
- Transcript audit reports 28 transcript files, 1,140 usage-bearing messages, 10,896,690 billable-ish tokens, 71,620,782 cache-read tokens, 10,585,171 Opus-class billable-ish tokens, 25 expensive subagents, and 13 agent/workflow calls.
- The prompt/session intent was to derive real revival inventories from disk rather than hand-pin media. The generator did that for carousel folders whose filename stem matched the folder name.
- The archive folder `img/photos/glitchpr0n/` contains files named `glitch1.png` through `glitch41.png`, but the generator expected names like `glitchpr0n1.png`, so it emitted `glitchpr0n: []` while 41 real images existed.
- The natural-sort comparator also returned `NaN` for identifiers without a leading number, making future nonnumeric archive identifiers fragile.

Repair:

- External repo commit `e53ada4` (`fix(revival): derive archive image manifest stems`) on branch `etceter4-revival` in `organvm/a-mavs-olevm`.
- Added collection metadata that separates folder name from filename stem.
- Switched natural sorting to `Intl.Collator(..., { numeric: true })`.
- Added `scripts/verify-image-manifest.mjs` and `npm run verify:image-manifest`.
- Regenerated `js/imageManifest.js`, now reporting `glitchpr0n=41`.

Touched external paths:

- `/Users/4jp/Workspace/organvm/etceter4-revival/scripts/gen-image-manifest.mjs`
- `/Users/4jp/Workspace/organvm/etceter4-revival/scripts/verify-image-manifest.mjs`
- `/Users/4jp/Workspace/organvm/etceter4-revival/js/imageManifest.js`
- `/Users/4jp/Workspace/organvm/etceter4-revival/package.json`

Verification:

```bash
npm run verify:image-manifest --prefix /Users/4jp/Workspace/organvm/etceter4-revival
npm run validate:package-lock --prefix /Users/4jp/Workspace/organvm/etceter4-revival
node --check scripts/gen-image-manifest.mjs
node --check scripts/verify-image-manifest.mjs
python3 scripts/claude-workflow-guard.py audit-transcript /Users/4jp/.claude/projects/-Users-4jp-Workspace-limen--claude-worktrees-calm-questing-ember/685b48b0-94fa-4537-a327-453a6ba01238.jsonl --max-billable-tokens 100000000 --max-agent-calls 100000 --max-opus-agents 100000 --max-fable-agents 100000 --out /tmp/rank-685-audit.json
```

Result: image manifest verification passed with `glitchpr0n=41`; package-lock validation passed with existing duplicate-package warnings; Node syntax checks passed; transcript audit completed with an Opus budget violation.

## Remaining Review Queue

1. Continue other off-repo/no-git reconstructions before spending time on large Studium content churn; those windows need private artifact review rather than a straightforward Limen git diff.
2. Add stronger provider-clock and receipt extraction for Agy. Changed-file `TargetFile` evidence is now covered when present, but quota, verification, and no-op classification still depend on weaker outcome text.
3. Continue branch-artifact review for other unmerged OpenCode security/test-coverage branches before any stale branch is rebased or merged.
