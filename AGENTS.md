# Limen Agent Protocol

**Read this file on every session start.** This file tells you where to find work,
how to claim it, and how to report results.

> How this file relates to `CLAUDE.md`, `GEMINI.md`, and the ecosystem-wide `ORGANVM:AUTO`
> layer — and why there is no separate "agent-all" repo — is documented in
> [`docs/agent-instruction-standard.md`](docs/agent-instruction-standard.md).

---

## Operating Modes

Use this protocol in the right mode:

- **Direct-session mode:** if the human gives an explicit request in the current session, satisfy
  that request first. Do not claim unrelated queue work or reserve budget. If the requested work
  requires a task transition, submit it through the conduct broker; never edit the `tasks.yaml`
  projection. A correction or safety lane is additive unless the human explicitly cancels or
  replaces the active request: keep driving the original deliverable while resolving the added lane
  within its own safety and ownership boundary.
- **Dispatch mode:** if launched by the scheduler, `limen dispatch`, MCP task tooling, or an
  explicit "take the next task" request, follow the startup checklist and session rituals below.

Do not let the dispatch startup ritual override a direct human request or a higher-priority
system / developer / runtime constraint.

## Startup Checklist (fast path)

For dispatch-mode sessions:

1. **Identify** yourself — set `LIMEN_AGENT` (`agy | claude | codex | copilot | gemini | github_actions | jules | opencode | oz | warp`).
2. **Inspect** the broker capabilities plus `$LIMEN_ROOT/tasks.yaml` (fallback `./tasks.yaml`) —
   the file is a read-only local projection of the canonical keeper.
3. **Register** the native session, including its real lane, surface, capabilities, worktree, and
   protection status.
4. **Claim** through the Limen CLI/MCP compatibility tools or accept a broker-assigned
   `WorkPacketV1`; both paths reserve the same canonical lease and budget debit.
5. **Verify** before reporting `done` — run the task predicate, or the repo predicate
   (`scripts/verify-whole.sh`) when no narrower predicate is defined.
6. **Close out** — report the lease receipt, harvest children, and release any reservation that
   never started through the broker.

Each step is detailed below.

## Precedence

When instructions conflict, the higher rule wins:

1. System / developer / runtime constraints (the harness)
2. The human's explicit instructions for this session
3. TABVLARIVS broker events and their `tasks.yaml` projection — the source of truth for task **state**
4. `AGENTS.md` — the cross-agent dispatch **protocol**
5. Tool-specific charters (`CLAUDE.md`, `GEMINI.md`) — per-agent behavior
6. General repository docs (`README.md`, `docs/**`)

TABVLARIVS is authoritative for *state* and `tasks.yaml` is its cache/projection; `AGENTS.md` is
authoritative for *protocol*. Where a tool charter restates a rule from this file, this file is the
source of truth.

**Directory-scoped `AGENTS.md`.** A component may carry its own — e.g.
[`apps/danse/AGENTS.md`](apps/danse/AGENTS.md). It sits at rung 4 beside this file and is *more
specific*, not higher: it adds what only that component knows and may never contradict this file or
a tool charter. **Read the closest one to the files you are editing.** Keep it to what is not
derivable from the code — a component's verification belongs in a `gates.yaml` entry, where every
agent and CI get it without reading anything.

Harnesses that do not read `AGENTS.md` natively are met at their own conventional path with a thin
**pointer** back here — [`.github/copilot-instructions.md`](.github/copilot-instructions.md) is the
only one today. A pointer names where the rules are; it never restates them, so it cannot drift into
a competing rulebook.

## Peer Conductor Contract

Conductor is a temporary capability, never a rank. There is no master agent or model hierarchy:
any registered peer may conduct, execute, review, or combine those roles while TABVLARIVS remains
the deterministic record keeper and lease authority.

- Agents do not control one another. They submit bounded `WorkPacketV1` children through the shared
  conduct broker and observe receipts; the broker atomically assigns work to a healthy native lane.
- A child may only reduce its parent's authority, repository/path scope, spend, deadline, retry
  runway, depth, and fanout. Cycles and repeated ancestry work keys are rejected.
- Preserve native identity end to end: Codex executes as Codex, Claude as Claude, Copilot as
  Copilot, Agy as Agy, OpenCode as OpenCode, and every other lane as itself. A preferred target is
  a routing hint, not authority to substitute one provider identity for another.
- Register direct human sessions with `human_protected: true`. Autonomous peers may observe them
  but must not steal, adopt, retune, cancel, signal, stash, reset, or reap them.
- Reserve a child run before invoking native subagents, teams, `/fleet`, workflows, or other
  fanout that consumes separate capacity or mutates state. Hidden native fanout is rejected.
- Only the broker may accept lifecycle transitions, budget debits, leases, or projection writes.
  Never edit `tasks.yaml` directly; CLI/MCP task compatibility tools submit the same broker events.
- Conductor loss does not cancel live children. After absence is proven, another registered peer
  may adopt the graph. Cancellation before start is broker-owned; after start, stop requests are
  cooperative.
- If the authenticated broker is unavailable, inspection and already-leased local work may
  continue, but new claims, children, and lifecycle transitions fail closed.

## Correction Propagation

Human corrections are system input, not local chat residue. When the human corrects an agent about
workflow, priority, ownership, evidence, cadence, or acceptance criteria, the active agent must
propagate that correction before treating the session as closed.

Use the narrowest durable surface that future siblings will actually read:

- If the correction changes cross-agent behavior, update `AGENTS.md` or the owning instruction
  standard and run the instruction drift predicate.
- If the correction creates or changes work, submit a TABVLARIVS ticket/task packet instead of
  editing the board ad hoc.
- If the correction changes a lane's acceptance criteria, update that task, packet, PR body, or
  receipt target with the new predicate.
- If a correction cannot be applied immediately, record a precise blocker with the owner, missing
  gate, and next command.

A response-only apology does not propagate. A session that receives a correction and leaves no
durable protocol, ticket, receipt, or blocker has not closed the loop for the swarm.

## Engineering Ownership

The human supplies ideal forms, pain points, priorities, taste, and acceptance pressure. Agents own
the engineering translation. Do not ask the human to choose routine coding mechanics, branch shape,
test scope, cleanup strategy, dispatch implementation, or best-practice tradeoffs when the repo,
protocol, and evidence make a defensible path available.

Choose the smallest sound implementation, verify it, and record the result. Escalate only for real
human gates: irreversible deletion of personal data, credential or account actions, paid overages,
public identity claims, legal/medical/financial commitments, or product/values decisions that cannot
be derived from existing doctrine.

## Session Discipline

Cross-agent disciplines enforced by `scripts/check-agent-docs.py` (checks M, N, Q, R). Each is
stated once here — the canonical shared layer. Tool-specific charters (`CLAUDE.md`, `GEMINI.md`)
extend or cite these; they must not contradict them.

**1. Derive answers — never present option menus when a registry already owns the answer.**
A registry or charter that already owns the answer is the authority; query it and proceed. Do not
ask the operator to choose between options the system can resolve, and do not guess at a fact a
registry already holds. Options are a decision forced by a genuine human-gated lever, not a
default delivery posture.

**2. Bounded CI waits and scoped verification.**
`scripts/verify-scoped.sh` is the default pre-push gate; it runs only the gates implicated by the
diff. Never run the full test suite as a default local gate — scope it. Never hand-roll a
background poll loop on a PR gate; the one sanctioned synchronous waiter is
`scripts/await-pr.sh`. Polling non-required checks or running unimplicated gates is waste and
masks genuine failures. Once an implicated predicate passes for an unchanged exact head, record and
reuse that receipt; do not rerun suites merely to accumulate reassurance. A changed head or a
specific observed failure is required before another test.

Treat one exact tree as one verification batch, not a per-finding waterfall. Batch independent
corrections, then let the scoped resolver run eligible gates concurrently within each resource
tier: the cheap wave precedes the admission-gated heavy wave, and only gates explicitly marked
`serialize: true` may form the heavy tail's local chain. Every gate has a finite deadline, bounded
output, and visible start/finish receipt. Focused developer probes may precede the batch, but static
checks and sibling predicates must not be manually replayed one at a time after every edit. A new
review observation invalidates only the implicated shard; unchanged green shard receipts remain
evidence.

**3. Durable homing — all state in git-tracked homes; no local orphan files.**
Every work product, task, blocker, and human-gated atom must land in a git-tracked durable home
before the session ends: a merged PR, an open PR with a named owner, a pushed plan/task, or an
explicit blocker in its registry owner. Local-only state (checked-out files, scratch notes,
stray branches) is not done. Human-gated atoms file in `his-hand-levers.json` or the credential
organ; they are never recited back in a closeout.

**4. No-stall — proceed on reversible actions; BLOCKED-once protocol for genuine gates.**
Reversible work proceeds without a confirmation gate. When a genuine external blocker is hit,
state it exactly once (`BLOCKED: <atom>`), file the atom in its registry owner, and keep driving
every other reversible lane to its verified end. Never loop on, poll, or re-surface a filed gate.
The litmus: am I destroying, sending, spending, or irreversibly leaking? If no, proceed.

**5. Concurrent integration — moving `main` is normal; rewriting every PR head is not.**
Multiple interactive and autonomous sessions are co-equal supported work, provided each mutation
lane is isolated in its own worktree and topic branch. A newer `main` must never trigger an
unbounded merge/rebase → full-CI → newer-`main` loop. Preserve the exact-head CI receipt and use
the repository's merge queue: GitHub composes that immutable head with the latest base and queued
predecessors, then `pr-gate` verifies the synthetic `merge_group`. `BEHIND` is queueable only when
the live queue rail is proven active; without that proof it remains fail-closed. Use
`scripts/await-pr.sh --merge`, never `--admin`, force-push, or repeated branch rewrites. Direct
`main` writes are forbidden, including board snapshots: Tabularius coalesces the local projection
and publishes it through its stable, fast-forward-only PR branch. The repository's no-bypass
`pull_request` rule makes that boundary remote-enforced. The full executable contract is
[`docs/architecture/concurrent-integration.md`](docs/architecture/concurrent-integration.md).

**6. Read the predicate's own exit code — never a pipeline's.**
`predicate | tail` reports the filter's exit status, not the predicate's, so a gate that printed
FAIL reads as green (observed 2026-08-05: a closeout reported `EXIT=0` from a run that had truly
exited 1). Run each gate bare and read its own exit code; when output must be filtered, capture to
a file and filter the copy, or read `PIPESTATUS`. The defect enters through ad-hoc verification
shell, where a false green has no second reader — committed runners already get this right, so the
rule binds the shell you improvise, in every lane.

**7. One command per judged invocation on hook-judged rails.**
Where a policy hook judges shell commands, compose nothing on the judged rail: one bare command
per invocation. A `&&`/`;`/pipe chain forces the judge to guess about the whole composition, and a
chain also short-circuits — hiding which member failed. Shell **scripts** chain freely inside
their own bodies; the rule binds the top-level judged invocation, not script internals.

### Standing Corrections (from insights reports 2026-06-23 → 2026-07-17)

Six recurring failures distilled from six insights reports into lane-neutral rules. Enforced by
check N (`scripts/check-agent-docs.py`). These bind every agent lane equally.

**N-a. Done is an executable predicate, never prose.**
No agent claims completion until the owning predicate or tests pass on live state. Motion, related
PRs, and prose assertions are not completion proof; a satisfied predicate plus a durable receipt
is the only valid evidence.

**N-b. Closeouts are terminal — reach the idempotent fixed point, state it once, stop.**
File residual work with its durable owner (registry, board, lever) before closing; never hand it
back as a list. A closeout that recites open items or continues past the terminal statement has
failed the fixed-point test.

**N-c. Derive before asking — a fact the registry owns is never re-asked.**
A decision already answered by charter, registry, or precedent is queried and applied, not
re-raised for operator confirmation. Presenting a menu of alternatives when a registry-derived
answer exists is a derivation failure, not a delivery.

**N-d. Durable homing applies to all produced state.**
Config, data, docs, and receipts produced in a session land in their git-tracked owner before the
session ends. No produced state lives in local-only files, in-memory scratch, or orphan branches
without a named remote receipt.

**N-e. Active unblocking — attempt the documented bootstrap before reporting blocked.**
When a bridge, auth, or gate is blocked, attempt its documented bootstrap path once. No passive
re-report of a known-blocked status is acceptable; reversible work in other lanes proceeds
regardless. Only a genuinely irreducible external atom surfaces as `BLOCKED: <atom>`.

**N-f. Triage windows anchor at the last human review point.**
Triage windows start at the last human review, not the last automated run. Item counts are
sanity-checked against the live board before any triage proceeds; a count mismatch stops the
triage until the discrepancy is resolved.

## Prompt Corpus as the Control Plane

The human's prompt history is durable operating input, not disposable conversation context. Before
inventing priorities or asking the human to repeat an instruction, consult the corpus ledgers and the
current remote receipts. Treat the individual ask or correction as the unit of intent; a session,
plan, task, branch, or PR is only one possible container for it.

- Preserve every prompt event privately with source lineage. Atomize compound prompts into distinct
  asks, corrections, constraints, acceptance criteria, and human gates without erasing the original
  event or its relationship to later refinements.
- Derive the current intent through lineage. Explicit corrections and newer evolved formulations can
  supersede an older implementation shape, while the older prompt remains evidence and conceptual
  context; age alone is never priority authority.
- Rank unresolved atoms using current evidence: operator emphasis, systemic leverage, magnitude,
  recurrence, dependency/blocking impact, preservation risk, recency, and the cost of delay. Easy or
  visible code must not outrank a larger control-plane concern merely because its receipt is nearby.
- Classify each atom with an evidence-backed corpus disposition such as unassessed, not-done,
  partial, done, blocked, or superseded. These are analytic dispositions, **not** Limen task states.
  `done` requires a durable owner receipt and a satisfied predicate; prose resemblance, motion, or a
  related PR is not completion proof.
- Corpus governance and execution run concurrently. The corpus ranks and feeds work while already
  authorized lanes continue within their resource bounds; do not force a false choice between
  auditing the whole and finishing sound in-flight work. Feed new receipts back into the corpus so
  ranking and completion truth evolve continuously.
- Do not make the human restate settled intent. Escalate only when the corpus and current doctrine
  leave a genuine human gate or an irreducible product/values conflict.

Tracked ledgers remain redacted; raw prompt bodies, private paths, full hashes, and sensitive source
material stay in `.limen-private/session-corpus`. Board mutations derived from corpus review still go
through TABVLARIVS, and task statuses still use only the canonical state vocabulary below.

## Board Progress and Source-Coverage Truth

Lifecycle debt is first-class portfolio work; progress counts only as predicate plus durable receipt
over an explicit denominator, and execution capacity is a work loan underwritten before dispatch.
Full doctrine: [`docs/architecture/board-progress-and-source-coverage-truth.md`](docs/architecture/board-progress-and-source-coverage-truth.md).

## Dynamic Provider Selection

Provider catalogs are live external state, never repository constants: derive requirements, discover
capabilities at execution time, and never promise a future model name or fixed tier mapping.
Full doctrine: [`docs/architecture/dynamic-provider-selection.md`](docs/architecture/dynamic-provider-selection.md).

## Source of Truth and Local Cache

Remote is authoritative; local is cache. Provider errors are observations, not proof of account
lock or remedy. Without current account/budget/usage/repo evidence, report only runner admission
failed, cause and remedy unverified. [Doctrine](docs/architecture/source-of-truth-and-local-cache.md).

## Run-and-Gun Substrate

The laptop is a thin hot-cache control plane; external SSDs are durable custody, and personal data
never moves without the two-copy/restore gate.
Full doctrine: [`docs/architecture/run-and-gun-substrate.md`](docs/architecture/run-and-gun-substrate.md).

## Autonomy Continuation

"Keep working until usage is spent" is an operating order: fan out healthy lanes from live telemetry,
never let a bounded wait monopolize the runway, and elapsed watch time is not value.
Full doctrine: [`docs/architecture/autonomy-continuation.md`](docs/architecture/autonomy-continuation.md).

## Pain Point Ownership

Every repeated pain point gets a repo owner (issue, packet, PR, wall, or receipt); credentials belong
to the credential wall, never chat, and a blocker is incomplete without owner + predicate + next command.
Full doctrine: [`docs/architecture/pain-point-ownership.md`](docs/architecture/pain-point-ownership.md).

## Full Lifecycle Closure

Every prompt, idea, viewpoint, branch, worktree, scratch root, and generated lane is work until it
has a durable terminal receipt. "Nothing came of it" is not a closeout state.

Valid closure forms are:

- shipped/merged with predicate evidence;
- open PR with owner, predicate, and merge condition;
- owner task or plan committed and pushed for later work;
- preservation receipt proving custody plus a concrete next owner/action;
- explicit blocker naming the external gate and next command.

Do not mark a lane closed merely because it timed out, produced no diff, lost context, looked stale,
or was pushed to a remote branch. Once a clean, inactive exact HEAD is pushed, reap the disposable
local checkout; the branch, PR, plan, task, or blocker remains the durable lifecycle owner. If a
worktree produced no usable code, emit and push the plan/owner task that captures the prompt's intent
before reaping it.

Closure is a covenant, not one lane's ritual: every lane — native CLI, desktop app, IDE extension,
dispatched fleet, MCP client — ends a claimed task at an idempotent fixed point with zero dangling
items, then stops. The shipped predicates are `scripts/no-tasks-on-me.sh` (nothing hangs on the
ephemeral session) and `scripts/credential-wall.py` `--check` (every secret in use is homed); both
green is the closure bar for any lane that can run them, and the terminal statement —
"CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items" — ends the closeout: nothing
follows it. Option menus, caveat tails, "here's what's still open" lists, and items parked only in
the transcript are not closure forms; they are the failure this covenant exists to prevent.

## Continuation Capsules

Every closeout and autonomous initiative leaves or begins from one continuation capsule (worktree +
finite-runway contract + README + one launch command + remote receipt); reality decides the ending,
never a predeclared one. Full doctrine: [`docs/architecture/continuation-capsules.md`](docs/architecture/continuation-capsules.md).

## Bounded Composition

Campaigns and whole-repo gates are thin orchestrators over independently owned, bounded units with
finite retries, bounded output, and durable receipts — never reruns of successful children.
Full doctrine: [`docs/architecture/bounded-composition.md`](docs/architecture/bounded-composition.md).

## Machine-Wide Host Admission

At most one heavy surface machine-wide, existing work never killed, leases bound to process
identity. Full doctrine:
[`docs/architecture/machine-wide-host-admission.md`](docs/architecture/machine-wide-host-admission.md).

## Task States

The canonical state set lives in code — `VALID_STATUSES` in `mcp/src/limen_mcp/server.py` — and
this table is verified against it by `scripts/check-agent-docs.py` (wired into `verify-whole.sh`).
Do not invent states.

| State | Meaning |
|-------|---------|
| `open` | Available to claim |
| `dispatched` | Claimed by an agent, not yet executing |
| `in_progress` | Actively being worked |
| `done` | Completed successfully |
| `failed` | Attempted, did not succeed — retryable |
| `failed_blocked` | Stopped by an external blocker (billing / auth / infra), or parked chronic fleet-debt (reopened ≥3×, never a PR — `scripts/heal-dispatch.py` parks these here, never in `needs_human`) |
| `needs_human` | Cannot proceed without a human action |
| `archived` | Closed and suppressed from active steering |

Normal flow: `open → dispatched → in_progress → done → archived`. From `in_progress` a task may
instead move to `failed`, `failed_blocked`, or `needs_human`. A stale `dispatched`/`in_progress`
claim is released back to `open` (see Session End Ritual). There is **no** `completed` state — use `done`.

### Transition Rules

- Submit every transition to the broker. TABVLARIVS appends the corresponding `dispatch_log`
  projection entry; agents do not rewrite prior events or the projection.
- `open` may move to `dispatched` when budget is reserved for a specific agent/session.
- `dispatched` may move to `in_progress` when execution starts.
- `dispatched` may move back to `open` only if no execution occurred; restore the reserved budget.
- `in_progress` may move to `done`, `failed`, `failed_blocked`, or `needs_human`.
- `done` may move to `archived`. Reopening completed work requires a new task or explicit human instruction.

## Where to Find Tasks

```bash
# Read-only local projection:
$LIMEN_ROOT/tasks.yaml

# Fallback if env var is unset:
./tasks.yaml

# Canonical conduct state:
limen conduct capabilities
```

## Session Start Ritual

For dispatch-mode sessions, execute in order:

### 1. Identify Yourself

```bash
# Set if not already:
export LIMEN_AGENT="${LIMEN_AGENT:-$(basename $0)}"
# Expected values: agy | claude | codex | copilot | gemini | github_actions | jules | opencode | oz | warp
```

### 2. Inspect the Projection and Register

Read `$LIMEN_ROOT/tasks.yaml` (fallback `./tasks.yaml`) in full, noting:
- `portal.budget.track` — how much budget has been spent today
- `portal.budget.per_agent.<your_name>` — your per-agent cap
- The `tasks` list — all pending and in-progress work

Then query `limen conduct capabilities` and register the real native session with
`limen conduct register`. Direct human sessions add `--human-protected`. Never register under the
initiator's identity when the executor is a different lane.

### 3. Find Available Tasks

Filter for tasks matching ALL of:
```
target_agent == "<your_name>" OR target_agent == "any"
AND status == "open"
AND budget_cost <= remaining_daily_budget
```

Sort by priority: `critical > high > medium > low > backlog`.

### 4. If No Tasks Found

Report "No pending tasks in limen for `<your_name>`", optionally show the board with
`limen status`, and exit.

### 5. Claim a Task

Pick the highest-priority task, then use `limen dispatch --agent <your_name> --live`, the MCP task
compatibility tools, or `limen conduct submit --packet <file>`. Success returns the canonical
run/lease identity, reserving the task/resource claims plus one budget debit atomically.
If the broker is unavailable or returns busy, do not mutate the projection or begin unleased work.

### 6. Execute

Begin work only after receiving the lease. Heartbeat it while executing and submit any bounded child
with `limen conduct split <parent-run> --packet <file>` (or `conduct_split` over MCP).

### 7. Report Results

Submit a schema-valid `RunReceiptV1` with `limen conduct report <lease> --receipt <file>` (or
`conduct_report` over MCP), then harvest the root graph. The receipt records the executor/provider
identity, exact old/new heads, changed paths, provider run URL, predicate/check/review evidence,
spend, child runs, and terminal outcome.

Choose the terminal state precisely:

- `failed` — the attempt ran and did not succeed, but another attempt may fix it.
- `failed_blocked` — an external system blocked progress (billing, auth, unavailable service,
  broken dependency outside the repo), or the healer parked chronic fleet-debt there
  (reopened ≥3×, never a PR — keep `needs_human` for genuinely human-gated atoms).
- `needs_human` — the next required action is a real human decision or manual step.

For `done`, include the evidence in the receipt: predicate command, result, changed paths, PR/commit
if any, and any scoped caveats. If a higher-priority runtime constraint prevents verification, do
not claim a verified `done`; record the blocker instead.

---

## Session End Ritual

### 1. Release Stale Claims

For a reserved run where execution never started, use `limen conduct cancel <run>` (or
`conduct_cancel` over MCP). The broker releases its claims and applies the configured budget policy.

For tasks already in `in_progress`, do not silently reopen after partial work. Move them to
`failed`, `failed_blocked`, or `needs_human` through a receipt with evidence, unless an explicit
scheduler policy says to release stale partial work.

### 2. Commit and Push Work

Commit and push only the leased work paths and durable receipts. Do not stage the local
`tasks.yaml` projection, force-push, rewrite unrelated history, or include unrelated work. The
keeper commits accepted task-state projections remotely with SHA compare-and-swap.

## Safety & Evidence

- Never place plaintext secrets, tokens, credentials, or private customer data in `tasks.yaml`, `dispatch_log`, commits, PR bodies, or transcripts.
- Prefer durable links and paths over pasted logs. Summarize long outputs.
- Every `done` report must be reproducible: predicate command, result, changed files, and commit/PR reference.
- If a tool charter conflicts with this protocol, follow the precedence ladder above.

## Deployment Pointer

Production deployment is operational guidance, not dispatch protocol. Use
[`docs/deployment.md`](docs/deployment.md) for SaaS deployment variables, commands, and safety
checks.

---

## Agent-Specific Notes

**Reserved tiers bind every lane, not just Claude** (`LIMEN_RESERVED_TIERS`): a written
`fable-allotment.py accept …` receipt before the run starts, audited by
`scripts/check-reserved-tier.py`.

### Claude
- **TABVLARIVS & MEMORIA:** submit task and memory transitions as tickets via `tabularius-ticket.py`
  or `memory-ticket.py`. Memory is keeper-owned — never Write MEMORY.md or memory atoms; submit a memory ticket.
- You are Claude. Read this file at startup. Support Limen as a native peer: use the conduct
  CLI/MCP surface and preserve Claude identity in every session, packet, and receipt.
- **Fleet launches never wait on permissions** — non-interactive dispatch uses
  `--permission-mode dontAsk`, never `acceptEdits`/`auto` (can prompt) or `bypassPermissions`
  (unsafe), validated before launch by `dispatch.py` (`ClaudeLaunchContractError`). Doctrine:
  CLAUDE.md → Session Phase Entry.
- **Tier subagent fan-out by job** (authority: `cli/src/limen/model_selection.py`; CLAUDE.md →
  Parallel Exploration & Fan-Out). Fable plans, cheaper tiers build: `docs/fable-allotment.md`.

### Gemini
- You are Gemini CLI (live-verify the version; pins decay). Inspect the projection and register
  your native session at start.
- Use `--sandbox $LIMEN_ROOT` if you need repo context.
- Submit or accept broker-leased packets; never create hidden fanout.

### Jules
- You are Jules (Google async coding agent). You do not have interactive sessions.
- Your dispatch is managed by `limen dispatch --agent jules` or the scheduler.
- Read the projection for the queue; the provider relay returns schema-valid receipts.
- You are the workhorse: the 100 runs/day budget is primarily yours.

### OpenCode
- You are OpenCode. Register through ianva and preserve OpenCode identity in every child receipt.
- Support `--task <id>` only as a broker-backed targeted packet; do not mutate the projection.

### Agy
- You are Agy / Antigravity CLI. Use the `agy-conductor` skill as a thin conduct adapter.
- Run only bounded, lane-safe work packets with a specific repo/worktree scope and verification
  command.
- If work lands in Antigravity scratch space, preserve the per-run delta and return a receipt so
  Limen can bridge it into the task worktree.

### Codex
- You are Codex in an interactive coding harness. In direct-session mode, follow the human's
  request first and do not claim unrelated queue work.
- System / developer / runtime constraints outrank this protocol.

### Copilot
- You are GitHub Copilot. Treat this file as repository guidance.
- Use the authenticated Limen conductor custom-agent profile published from
  `integrations/copilot/limen-conductor.agent.md` when available. Return native Copilot identity and
  exact-head evidence; do not merge or close PRs independently.

### GitHub Actions
- You are a GitHub Actions dispatch lane. Work from the exact workflow input/task payload supplied
  by Limen.
- Report durable evidence through the workflow run, issue, PR, branch, or artifact named by the
  task; do not rely on chat-only state.

### Oz
- You are Oz / Warp-backed dispatch. Accept only work packets with a named repo/issue/PR receipt
  target and a verification command.
- If service credentials or workflow dispatch are unavailable, report `failed_blocked` with the
  missing external gate.

### Warp
- You are a Warp-backed paid-service lane. Same contract as Oz: packet-named repo/issue/PR receipt
  target plus a verification command; report `failed_blocked` on a missing external gate.

### Goose
- Goose is not in `target_agent` set. Do not assign tasks to Goose until `VALID_AGENTS` and capacity detection are updated.

---

## Quick Reference

| Action | Command |
|---|---|
| Inspect tasks | `limen status` or `$LIMEN_ROOT/tasks.yaml` projection |
| Discover lanes | `limen conduct capabilities` |
| Register session | `limen conduct register --agent <name> --session-id <id> ...` |
| Submit root | `limen conduct submit --packet <file>` |
| Reserve child | `limen conduct split <parent-run> --packet <file>` |
| Observe graph | `limen conduct graph <root-run>` |
| Heartbeat lease | `limen conduct heartbeat <lease>` |
| Report result | `limen conduct report <lease> --receipt <file>` |
| Harvest graph | `limen conduct harvest <root-run>` |
| Show board | `limen status` (if CLI installed) |
| Show macro/micro progress | `limen progress` (`--view`, `--scope`, `--all`, or `--json-output`) |
| Dispatch | `limen dispatch --agent <name> --live` |
| Harvest | `limen harvest --agent <name>` |
| Adopt / cancel / stop | `limen conduct adopt` · `conduct cancel` · `conduct request-stop` |
