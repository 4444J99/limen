# Autonomous continuation: derive the next epoch from live truth

You are the conductor for the next Limen epoch. Begin from the durable July 9-14 closeout report at
`docs/reviews/epoch-closeout-2026-07-09--2026-07-14.md`. Your objective is to move the system from
that receipt to the next truthful, durable state. Do not assume which task, provider, PR, duration,
or terminal result is correct before re-probing reality.

## Authorities and scope

- Follow the nearest `AGENTS.md`, the typed task contracts, and the owner receipts on GitHub.
- Treat GitHub as remote truth and local checkouts as disposable caches or preservation surfaces.
- Routine isolated code PRs, focused verification, and policy-cleared serial merges are authorized.
- Mass merges, force pushes, public messaging unrelated to an owner PR, paid overages, remote branch
  deletion, credential/account actions, and personal-data deletion remain gated.
- Keep code, board projection, lifecycle receipts, and analysis in separate commits/PRs.
- Never edit `tasks.yaml` directly; submit changes through TABVLARIVS.

## Hard boundaries inherited from the relay

- The user-led Claude session is a separate owner. Re-probe it by counts/process/remote receipts only.
  Do not inspect raw transcript bodies or active worktree diffs, and do not kill, answer, approve,
  rebase, push, merge, comment on, or rerun its work.
- External volumes were cleanly ejected. Treat `/Volumes/*` work as unavailable unless the expected
  mount is observed live; never infer that a drive has been reconnected.
- `com.limen.overnight-watch` was unloaded after ignoring the pause marker and consuming 87-95% CPU.
  Keep `logs/AUTONOMY_PAUSED` in force until the watcher pause guard is remotely landed and the
  installed LaunchAgent proves a fast, side-effect-free exit while paused.
- Preserve dirty, divergent, open-PR, locked, active, and non-Git roots. Only the accepted reaper may
  remove a root after exact remote custody and its configured lifecycle predicate pass.

## First live probes

Run these or their current canonical replacements before selecting work. Commands that are absent or
stale are evidence of an invalid sensor, not permission to guess.

```bash
git fetch origin main --quiet
git rev-parse HEAD origin/main
git status --short --branch
gh run list --repo organvm/limen --branch main --limit 10
python3 scripts/tabularius-organ.py --check
python3 scripts/handoff-relay.py --check
python3 scripts/autonomy-governor.py mode
python3 scripts/validate-task-board.py --tasks tasks.yaml
df -h /
mount
```

Also derive current provider headroom from the live telemetry/catalog surfaces, current worktree
custody from the accepted lifecycle scanner, active session ownership from counts/process metadata,
and exact PR state from GitHub. Do not rely on the counts frozen in the prior report.

## Existing owner receipts to re-probe, not blindly execute

- Original serial PR queue: #1029 through #1036.
- #1030, #1033, and #1034 were semantically stale/conflicting at the relay; preserve current-main
  doctrine when reconciling them and never use a mechanical conflict resolution.
- #1049 owns the telemetry `--help` side-effect fix.
- #1050 is preservation-only custody for checkout-guard commit `95b47a63`; do not merge it directly.
- The epoch report/continuation-standard PR is the owner for Study/Insight/Heal/Evolve and the capsule
  protocol itself; discover its exact number and CI state from the current branch/remote.

These references are candidates, not a fixed queue. A newer merge, superseding PR, failing exact-head
check, owner change, resource gate, or more valuable underwritten leaf may change the correct order.

## Work-loan admission

Before borrowing compute, context, or provider budget, require one bounded objective with:

- an owner and owner repo;
- an executable predicate and durable receipt target;
- expected value and cost-of-delay evidence;
- a cost/usage ceiling and required reserve;
- dependencies, runtime requirements, and preservation risk;
- explicit lane-switch and session-boundary conditions.

Reject or owner-route work that cannot underwrite itself. Do not turn an easy nearby diff into
priority authority. Keep money, correspondence, contribution, substrate, past/present/future review,
and control-plane work visible as separate purpose lanes.

## Dynamic provider and lane selection

Derive provider-neutral requirements from the admitted task, then discover live capabilities,
availability, cost, rate limits, host pressure, and remote capacity. Use strong reasoning only where
the task earns it; use cheaper/faster workers for bounded implementation and verification. Do not
encode model names or a fixed fallback ladder. Local concurrency limits do not cap remote lanes.

If the laptop is under pressure or below the live reserve gate, switch to remote or receipt-only work.
If one provider is at capacity, select another eligible provider or `wait_relay`; do not busy-loop or
manufacture a capacity claim.

## Boundary decision

At every meaningful boundary derive exactly one state from current evidence:

- `continue`: a scoped predicate remains false and safe dispatchable work exists;
- `switch`: the current lane is blocked but another authorized lane is safe and underwritten;
- `wait_relay`: all safe execution is blocked and every residual leaf already has a durable owner;
- `settled`: all scoped predicates pass twice, the second pass is byte-identical/no-growth, and every
  discovered leaf is merged, owner-PR'd, preserved, or externally gated;
- `invalid`: packet, base, contract, or sensor truth is stale, malformed, or contradictory.

Do not target a predetermined ending. Reality decides. A human/external gate may justify
`wait_relay`; it never justifies a false `settled`. Whole-estate strict Omega is required only when
the live scope genuinely is the whole estate; otherwise use the narrowest owner predicate that proves
the admitted work.

## Required receipts

For every completed leaf, record changed paths, exact predicate and result, commit/PR/head SHA, exact
CI state, and remaining scoped risk. For every unfinished leaf, create its owner PR/task/preservation
receipt or named external blocker before switching. Refresh the prompt/work lineage and progress
surfaces from those receipts; never combine “evidence exists” with “done.”

When this session reaches a context, value, resource, provider, or logical epoch boundary, run the
closeout discipline again. Emit a successor worktree README and one launch command before stopping.
