# Autonomy Continuation

> Relocated verbatim from `AGENTS.md` (2026-08-06) under the instruction-surface byte budget
> (`institutio/governance/gates.yaml` → `instruction_surfaces`, check S). The binding stub in
> `AGENTS.md` points here; this file is the full doctrine.

When the human explicitly says to keep working until usage is spent or everything is done, that is an
operating order, not motivation text.

- Do not leave `logs/AUTONOMY_PAUSED` in place unless a higher-priority safety gate requires it. If
  the policy already permits dispatch, remove the stale pause marker, verify the heartbeat LaunchAgent
  is loaded, and record any remaining blocker in the owning receipt.
- Fan out all healthy remote lanes according to live usage telemetry. Jules is a remote lane; do not
  count Jules against local CPU or disk concurrency. If Jules is exhausted or rate-limited, record that
  from `logs/usage.json` and use the remaining healthy lanes.
- Keep local lanes bounded by host pressure and local concurrency (`LIMEN_LOCAL_LIMIT`,
  `--local-per-lane`, and `--max`), but do not convert a local cap into a global fleet cap.
- A future time gate or bounded waiter must not monopolize an autonomous runway. Once the wait is
  registered with its durable owner (the sanctioned PR waiter, heartbeat rung, or continuation
  receipt), calculate the unreserved runway and route immediately executable independent packets
  through their own owners and capsules, subject to live host admission and concurrency. Elapsed
  watch time is not value; each parallel packet still needs its own predicate and durable receipt.
- If disk pressure is part of the correction, dry-run proof is not enough. Run the accepted reclaim
  path until it reaches a fixed point, deleting only roots the reclaim script classifies as clean,
  inactive, and exact-HEAD remote-preserved (pushed, merged, or patch-equivalent). Anything left must
  be owner-routed by its concrete reason (`dirty`, `unpushed`, `active-process-cwd`, `locked`,
  `not-a-git-dir`), not explained away in chat.
- A zero-launch dispatch command is not progress. If a lane filter launches nothing, inspect the board
  and usage telemetry, then dispatch the actual eligible lanes or record the exact blocker.
