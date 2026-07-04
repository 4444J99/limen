# Agent Code Diff Review

Generated: `2026-07-04T00:04:21Z`

## Scope

- Input queue: `docs/agent-code-review-queue.md` plus private queue metadata under `.limen-private/session-corpus/full-stack-review/`.
- Review method: start from high-risk prompt/session rows, reconstruct the matching git window, inspect the actual code diff, and record concrete implementation findings.
- Redaction boundary: no raw prompt bodies are included here; prompt bodies remain in the ignored private corpus.

## Reviewed Windows

| Queue rank | Agent | Session | Result |
|---:|---|---|---|
| 1 | `opencode` | `ses_11427e08affe3D8jAAl5W43viB` | Exact window had no matching commits on `main`; treated as a reconstruction gap for follow-up. |
| 2 | `opencode` | `ses_114c8f0c6ffeixS8gn4VxGqoHb` | Exact window matched `80d4e21f` (`feat(route): consume self-improve lane weights`). Widened window also showed related routing/meter/queue commits including `0146190` and `a6488c9`. |
| 3 | `opencode` | `ses_1095e9b19ffe4yg9h4la7tGU4d` | Exact window had no matching commits on `main`; widened window was mostly Studium content-generation churn, not the control-plane code path reviewed here. |

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

## Remaining Review Queue

1. Reconstruct changed-file evidence for queue rank 1; the exact OpenCode window has no commit on `main`, so the next pass should inspect private session outcome receipts and nearby branch/worktree state.
2. Continue rank 7-12 control-plane windows before spending time on large Studium content churn; those windows touch dispatch, capacity, CI, and lifecycle code with higher operational blast radius.
3. Add stronger provider-clock and receipt extraction for Agy. Changed-file `TargetFile` evidence is now covered when present, but quota, verification, and no-op classification still depend on weaker outcome text.
