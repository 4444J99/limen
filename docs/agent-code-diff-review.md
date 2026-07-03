# Agent Code Diff Review

Generated: `2026-07-03T23:13:41Z`

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

## Finding Fixed

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

## Remaining Review Queue

1. Reconstruct changed-file evidence for queue rank 1; the exact OpenCode window has no commit on `main`, so the next pass should inspect private session outcome receipts and nearby branch/worktree state.
2. Continue rank 7-12 control-plane windows before spending time on large Studium content churn; those windows touch dispatch, capacity, CI, and lifecycle code with higher operational blast radius.
3. Add stronger changed-file extraction for Codex, Claude, and Agy. OpenCode is currently the only reviewed agent with native changed-file refs, which makes cross-agent diff review uneven.
