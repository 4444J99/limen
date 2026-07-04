# Agent Code Diff Review

Generated: `2026-07-04T00:27:53Z`

## Scope

- Input queue: `docs/agent-code-review-queue.md` plus private queue metadata under `.limen-private/session-corpus/full-stack-review/`.
- Review method: start from high-risk prompt/session rows, reconstruct the matching git window, inspect the actual code diff, and record concrete implementation findings.
- Redaction boundary: no raw prompt bodies are included here; prompt bodies remain in the ignored private corpus.

## Reviewed Windows

| Queue rank | Agent | Session | Result |
|---:|---|---|---|
| 1 | `opencode` | `ses_11427e08affe3D8jAAl5W43viB` | Exact window had no matching commits on `main`, but the matching unmerged branch is `limen/gen-organvm-limen-security-0625-57ce` at `02f256e` (`Security hardening pass on organvm/limen`). Reviewed as a reject/do-not-merge artifact. |
| 2 | `opencode` | `ses_114c8f0c6ffeixS8gn4VxGqoHb` | Exact window matched `80d4e21f` (`feat(route): consume self-improve lane weights`). Widened window also showed related routing/meter/queue commits including `0146190` and `a6488c9`. |
| 3 | `opencode` | `ses_1095e9b19ffe4yg9h4la7tGU4d` | Exact window had no matching commits on `main`; widened window was mostly Studium content-generation churn, not the control-plane code path reviewed here. |
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

## Remaining Review Queue

1. Continue rank 7-12 control-plane windows before spending time on large Studium content churn; those windows touch dispatch, capacity, CI, and lifecycle code with higher operational blast radius.
2. Add stronger provider-clock and receipt extraction for Agy. Changed-file `TargetFile` evidence is now covered when present, but quota, verification, and no-op classification still depend on weaker outcome text.
3. Continue branch-artifact review for other unmerged OpenCode security/test-coverage branches before any stale branch is rebased or merged.
