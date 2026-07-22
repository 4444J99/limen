# Dispatch architecture — how the fleet turns tasks.yaml into PRs

Update verified 2026-06-28:

- Live launchd heartbeat is running and `python3 scripts/watchdog.py --dry-run` reports healthy.
- Live heartbeat is still using SYNC dispatch. The installed plist now records `LIMEN_DISPATCH_ASYNC=0`; the currently loaded launchd job has not been reloaded since that file repair.
- Async orchestration is implemented and tested. `pytest -q cli/tests/test_async_dispatch.py` passes after fixing stale-worker reaping so async-reserved tasks reopen when their detached worker dies.
- `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --dry-run` reports current async workers and launchable tasks using the live host-derived local ceiling.

The heartbeat (`scripts/heartbeat-loop.sh`, launchd `com.limen.heartbeat`) runs one polyrhythmic
beat repeatedly: drain → heal → feed (mine) → route/rebalance → **dispatch** → reconcile → web.
Dispatch is where open tasks become worktree→PR. There are two interchangeable dispatch engines.

Route and rebalance are read-only planners. `target_agent` is durable eligibility/ownership metadata,
not a heartbeat scratch field. A bounded failure records the next live lane in the latest open
`dispatch_log.route_to`; selection consumes that receipt at claim time, and the claim receipt records
the actual authenticated executor. Neither planning nor fallback rewrites `target_agent`.

## The two engines

### SYNC (default) — `scripts/dispatch-parallel.py` → `dispatch.dispatch_parallel()`
RESERVE (mark open→dispatched, save once) → RUN all picked tasks concurrently in a thread pool →
COMMIT (apply results, save once). **The beat blocks until the slowest agent finishes** — that is
the throughput ceiling ("900s gates every beat"). Safe + simple; one process owns the two writes.

### ASYNC (opt-in, `LIMEN_DISPATCH_ASYNC=1`) — `scripts/dispatch-async.py` + `scripts/async-run-one.py`
Decouples agent runtime from the beat. Each beat: **reap** dead workers → **harvest** finished
results → **reserve + launch** detached workers up to a local host slot cap, then **return
immediately**.
- `async-run-one.py` (detached worker): runs ONE task's `call_agent_dispatch` and writes
  `logs/async-runs/<id>.result.json`; never touches tasks.yaml.
- `dispatch-async.py` (orchestrator): harvest applies results under the queue-lock; reserve marks
  dispatched + writes a `<id>__<agent>.running` marker + `Popen(start_new_session)` the worker.
- Local concurrency = `LIMEN_ASYNC_MAX` (derived from live host CPU count); local fan-out per lane =
  `LIMEN_ASYNC_LOCAL_PER_LANE` / `--local-per-lane`. Remote lanes such as Jules are not local CPU
  workers: their burst size comes from `--per-lane` plus live provider runway in `logs/usage.json`,
  and they do not consume the local host slot cap. Per-agent in-flight is counted from
  `__<agent>.running` markers so reservations hold between reserve & harvest; `reap_stale`
  (LIMEN_ASYNC_MAX_AGE=1200s) reopens tasks whose worker died without a result (no leaked slots).
- Beats stay fast; a slow/stuck agent can't gate the beat. CI-tested in `cli/tests/test_async_dispatch.py`.
- TO ACTIVATE: set `LIMEN_DISPATCH_ASYNC=1` in the plist + restart **between beats** (no in-flight
  dispatch, else reserved tasks strand as phantoms). Left OFF until a focused, monitored switch.

## Cross-cutting keystones (apply to both engines)

- **Conductor-first packetization:** a broad human prompt is not itself a dispatchable task. The
  conductor first preserves the prompt/session in the private corpus, derives bounded work packets,
  and records each packet's owner, repo/worktree scope, receipt target, and verification command.
  Only then should a lane receive work. Jules is appropriate for independent remote GitHub tasks
  with branch/PR/check receipts; local lanes such as OpenCode and Agy are appropriate for a
  specific checkout plus predicate; Gemini is review/synthesis or narrow code work only when auth
  is configured. A near-exhausted lane such as Claude should be treated as a data source or last
  resort, not as the default absorber for macro cleanup.
- **Auth/secret gates are parked, never solved inline:** login failures, missing keys, expired
  tokens, password prompts, and credential hydration issues are recorded as redacted
  `failed_blocked` / `needs_human` work in the owning board or credential ledger, then excluded from
  the current convergence stream. No dispatch packet should ask a lane to print, paste, mint,
  recover, or infer secrets; the current stream continues on non-secret work.
- **Timeout group-kill** (`dispatch._run_capture`): agents run via `start_new_session=True`; on
  timeout the WHOLE process group is `SIGKILL`ed. Plain `subprocess.run(timeout=)` only kills the
  direct child — if an agent CLI spawns grandchildren holding the stdout pipe, `communicate()`
  hangs forever past the timeout (caused a real 23-min beat freeze). This makes timeouts actually fire.
- **Isolated root retention** (`dispatch._cleanup_isolated_worktree`): local lane worktrees and
  branch refs are classified after each run but not physically deleted by dispatch. Reclaim/removal
  happens later through `docs/worktree-reclaim-acceptance.jsonl` and
  `docs/branch-reap-acceptance.jsonl`, after archive and redaction proof.
- **Queue-lock (#11)** (`dispatch._queue_lock(tasks_path)`): cross-process mutex on tasks.yaml
  (`logs/.queue.lock.d`, sibling of tasks.yaml). The heartbeat releases it BEFORE the slow dispatch
  so supervisors (seed/heal/verify) aren't starved; dispatch self-locks its reserve and
  **reloads-fresh at commit** so a write made mid-run isn't clobbered.
- **Lane-down filter** (`dispatch._down_lanes` ← `logs/lanes-down.txt`, derive-not-pin): the planners
  and both dispatchers skip unproductive lanes. The plan may nominate a productive executor, but it
  leaves durable task ownership byte-identical; a runtime fallback is carried by `dispatch_log.route_to`.
- **Reconcile** (`scripts/verify-dispatch.py` → `scripts/heal-dispatch.py`): every C_HEAL beat,
  verify each `dispatched` task's real PR state on GitHub; PR_MERGED/PR_OPEN→done, PR_CLOSED/
  DISPATCHED_NO_PR→open (re-dispatch). Respects async `.running` markers (won't reopen a live run).
- **jules→PR** (`scripts/jules-land.py`, wired into `drain.sh`): lands completed jules sessions as
  PRs (the async-cloud equivalent of worktree→PR), dup-safe via PR-URL backfill in dispatch_log.
  It retains the isolated local worktree/branch after PR creation; physical cleanup belongs to the
  receipt-backed reclaim/reap organs once merged/archive/redaction proof exists.

## Shipping the output
`scripts/merge-ready.sh` (dry-run default, `--apply` gated) merges CLEAN non-junk PRs revenue-first.
Merge-readiness of all open PRs is mapped in `memory/merge-readiness-map.md`. Mass merge/close is
auto-mode-classifier-gated — grant `Bash(gh pr merge:*)` / `Bash(gh pr close:*)` to let the fleet ship.

## Operational gotchas
- dispatch.py changes take effect the NEXT beat (fresh subprocess) — NO restart needed.
- heartbeat-loop.sh changes need a restart — do it BETWEEN beats (mid-dispatch restart strands phantoms).
- A long-running `dispatch-parallel`/worker with live agent children is WORKING (slow), not hung —
  check `ps` descendants before killing; only no-children + no-progress past timeout is a real hang.
