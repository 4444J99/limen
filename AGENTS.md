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
  that request first. Do not claim unrelated queue work, reserve budget, or mutate `tasks.yaml`
  unless the request is to work from the Limen queue or the requested work itself requires a task
  state update.
- **Dispatch mode:** if launched by the scheduler, `limen dispatch`, MCP task tooling, or an
  explicit "take the next task" request, follow the startup checklist and session rituals below.

Do not let the dispatch startup ritual override a direct human request or a higher-priority
system / developer / runtime constraint.

## Startup Checklist (fast path)

For dispatch-mode sessions:

1. **Identify** yourself — set `LIMEN_AGENT` (`agy | claude | codex | copilot | gemini | github_actions | jules | opencode | oz | warp`).
2. **Read** `$LIMEN_ROOT/tasks.yaml` (fallback `./tasks.yaml`) — parse the budget and the full task list.
3. **Claim** the highest-priority `open` task targeted at you (or `any`) that fits the remaining budget.
4. **Update status** before (`dispatched` → `in_progress`) and after (`done` / `failed`) execution.
5. **Verify** before reporting `done` — run the task predicate, or the repo predicate
   (`scripts/verify-whole.sh`) when no narrower predicate is defined.
6. **Close out** — release stale claims back to `open`, restore budget, commit `tasks.yaml`.

Each step is detailed below.

## Precedence

When instructions conflict, the higher rule wins:

1. System / developer / runtime constraints (the harness)
2. The human's explicit instructions for this session
3. `tasks.yaml` — the single source of truth for task **state**
4. `AGENTS.md` — the cross-agent dispatch **protocol**
5. Tool-specific charters (`CLAUDE.md`, `GEMINI.md`) — per-agent behavior
6. General repository docs (`README.md`, `docs/**`)

`tasks.yaml` is authoritative for *state*; `AGENTS.md` is authoritative for *protocol*. Where a
tool charter restates a rule from this file, this file is the source of truth.

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

Cross-agent disciplines enforced by `scripts/check-agent-docs.py` (checks M and N). Each is
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
[`docs/concurrent-integration.md`](docs/concurrent-integration.md).

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

Lifecycle debt is first-class portfolio work. A preserved branch, merged PR, exact owner blocker,
or safely reclaimed cache is real value when it closes ambiguity or preservation risk; do not dismiss
that work as overhead. It still counts as progress only when the owning predicate and durable receipt
exist. Scans, classifications, token spend, commits, and agent motion are supporting evidence, not
terminal outcomes by themselves.

Keep four sources of work distinct even when they point to the same leaf:

- external obligations and work that is actually due;
- human prompts, asks, corrections, and acceptance criteria;
- agent or system recommendations about what should happen next;
- detected lifecycle, quality, custody, and control-plane debt.

Also preserve the purpose lane and time horizon (`past`, `present`, or `future`). Every normalized leaf
should converge on source lineage, lane, horizon, owner, priority rationale, executable predicate,
durable receipt target, and canonical state. Unknown classification or an unscanned source is visible
coverage debt; never render it as zero work. Macro progress is terminal closure over an explicit
denominator. Micro progress is predicate/receipt evidence or canonical lifecycle stage, never a
made-up estimate of effort.

Treat execution capacity as a work loan. Before dispatch, the task should underwrite the requested
capacity with an explicit value case, cost, origin, horizon, owner surface, predicate, and receipt
target. Urgency, cost of delay, confidence, reversibility, dependencies, and resource pressure inform
ranking when available. Record requested capacity as a debit, expected value as forecast credit, and
predicate plus receipt target as collateral. After execution, reconcile forecast to actual durable
credit and actual spend. A terminal board state is only a credit claim until the owning receipt passes;
do not let a high-cost attempt inherit the value it merely intended to create.

`limen progress` is only the partial task-board projection and source-readiness lens for this
doctrine. It does not ingest the source-owned leaves behind prompt, GitHub-estate, lifecycle, mail,
financial, or contribution receipts. Its `scope: partial` output, source contract hashes, and
separate board / coverage / verified-receipt debt counts must not be represented as whole-estate
proof. Dynamic source enumeration, actual spend/value reconciliation, historical comparison, and an
interactive TUI require their own owner receipts.

## Dynamic Provider Selection

Provider catalogs are live external state, not repository constants. Do not encode model IDs,
catalog snapshots, name-based capability guesses, or fixed fallback tables in dispatch logic,
instructions, tasks, or receipts.

- Derive provider-neutral requirements from the current task and discover reachable capabilities at
  execution time. Treat `tier:*` text as opaque context. Express numeric constraints only through the
  owning execution-profile schema, such as `profile:<field>:<value>`.
- When the provider exposes sufficient live metadata, filter and rank that catalog by capability,
  availability, cost, and task pressure. When it does not, leave model selection to provider Auto.
- A human-configured model override is an escape hatch, not a default. Validate it against the live
  catalog when possible; otherwise fail blocked instead of inventing or silently substituting a name.
- Tests use arbitrary and renamed fixture IDs and must prove that catalog add/remove/reorder changes
  are handled without a code change. Receipts may record the actual selected model when exposed, but
  never promise a future model name, price class, subscription outcome, or fixed tier mapping.

## Source of Truth and Local Cache

For GitHub, profile, repo inventory, credential, and public proof surfaces, the remote owner is the
source of truth. A local checkout is a disposable cache or staging area; it is not the golden state.

- Read remote state first through the GitHub API, live deployed endpoint, pinned issue, or owner repo
  receipt before trusting a local clone.
- If local work is required, create it in an isolated worktree or scratch lane, push/open the remote
  receipt, then reap the local cache once lifecycle custody is proven.
- Reaping local caches requires merged or patch-equivalent remote custody. A pushed branch or open PR
  is not enough to delete the local checkout; merge it first, or solve the reason it cannot merge.
- Do not fall back to local files when the canonical object is remote and queryable.
- Do not let local clone presence, local profile copies, or stale generated artifacts define public
  truth. If a remote cannot be updated, record the owner repo, missing gate, and next command.
- Do not generalize one failed GitHub surface into "GitHub is blocked." A zero-step hosted Actions
  job, including a runner-allocation or billing annotation, describes that exact execution surface;
  it does not make repository/API/PR custody unavailable and is not by itself an external stop
  condition. Verify live permissions and current receipts, continue every available local or remote
  predicate, and name the narrow failing surface without stalling unrelated closeout work.

## Run-and-Gun Substrate

The laptop must be able to operate alone as a thin control plane. External SSDs are the durable
library and processing substrate, not random leftovers from a recovery event.

- Keep the laptop as hot cache: active worktrees, small receipts, local tools, and enough context to
  continue from the remote owner without needing a drive at a coffee shop.
- Keep external drives as durable custody: complete private/raw data, processed/redacted corpora,
  archived repo/org mirrors, photos/media packages, and restore-tested recovery copies.
- At the desk, assume externals are plugged in and use them for hydration, archive, media processing,
  and bulk scans; when unplugged, continue from remote receipts and cached indexes.
- Do not move, delete, dedupe, or purge personal data without the relevant two-copy/restore gate and
  an owner receipt.

## Autonomy Continuation

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
  merged or patch-equivalent, idle, and remote-preserved. Anything left must be owner-routed by its
  concrete reason (`dirty`, `unpushed`, `not-merged-to-default`, `active`, `not-a-git-dir`), not
  explained away in chat.
- A zero-launch dispatch command is not progress. If a lane filter launches nothing, inspect the board
  and usage telemetry, then dispatch the actual eligible lanes or record the exact blocker.

## Pain Point Ownership

Every repeated pain point needs an owner. Missing scopes, stale profile metadata, disk pressure,
credential/token hygiene, contribution imbalance, voice/temp failure, and queue/lane drift are not
chat-only blockers.

- Put each pain point in the repo that owns the fix: issue, task packet, PR, pinned wall, or receipt.
- Credential, token, secret, API-key, login, and env-var problems belong to the credential wall owner;
  never paste values into chat, tasks, commits, or PRs.
- A blocker is incomplete unless it names the owning repo/surface, the failed predicate, and the next
  command that would clear it.
- If the same pain point appears twice, update the owner receipt instead of explaining it again.
- Default toward productizing the fix: split private adapters from reusable public shells, publish a
  redacted demo or method when safe, and route the outward-facing value surface through the owner repo.

## Full Lifecycle Closure

Every prompt, idea, viewpoint, branch, worktree, scratch root, and generated lane is work until it
has a durable terminal receipt. "Nothing came of it" is not a closeout state.

Valid closure forms are:

- shipped/merged with predicate evidence;
- open PR with owner, predicate, and merge condition;
- owner task or plan committed and pushed for later work;
- preservation receipt proving custody plus a concrete next owner/action;
- explicit blocker naming the external gate and next command.

Do not delete, reap, archive-away, or mark closed merely because a lane timed out, produced no diff,
lost context, looked stale, or was merely pushed to a remote branch. If a worktree produced no usable
code, emit the plan/owner task that captures the prompt's intent, then close the worktree only after
the work is merged or proven patch-equivalent to the remote default branch.

## Continuation Capsules

Every closeout and every new autonomous initiative must leave or begin from one continuation capsule.
For repository-backed work, use the existing worktree launcher (`limen workstream` /
`scripts/start-worktree-session.sh`) instead of inventing a parallel session framework. If no Git
repository is a logical owner, use an isolated owner-native workspace or remote receipt and explain
that choice in the capsule; never manufacture a fake worktree merely to satisfy the form.

A continuation capsule contains:

- one isolated worktree and single-purpose branch when repository-backed, otherwise one isolated
  owner-native workspace or durable remote surface;
- one validated, machine-readable workstream contract with an explicit finite configurable runway;
  the first launch admits it, successor sessions inherit its deadline, and malformed, unbounded, or
  expired contracts fail closed without preempting an already-running provider process;
- a README with the objective, current evidence links, authorities, prohibitions, first probes,
  executable predicates, ownership rules, and session-switch conditions;
- one copy/paste command that enters the worktree and starts the next agent with that README as its
  initial prompt;
- a durable remote receipt for the capsule itself before the producing session closes.

The capsule is a conducted workstream, not an implicit one-packet handoff. Its conductor re-checks
remaining runway at packet boundaries, derives healthy lanes from live capabilities, and routes
independently bounded packets across agents without pinning a provider or model. Full approval is
carried as a no-modal contract: in-scope reversible work proceeds without confirmation under the
scoped sandbox; destructive, credential, paid-spend, public-send, and runtime/host mutations remain
gated.

The capsule defines how reality decides what happens next; it never predeclares the ending. At launch,
derive the exact remote head and CI state, board/task contracts, handoff age, provider headroom, mounted
substrates, host pressure, active sessions, and lifecycle custody from live probes. Do not hard-code a
future model, provider table, task count, completion percentage, or claim that Omega is reachable.
Environment figures may select a lane, deny unsafe work, or trigger a session switch; they must never
be edited to manufacture green.

The next session finishes only when its live predicates pass and every discovered leaf has one of the
closure receipts above. If context, value, resource, provider, or human gates require a boundary, emit
the successor capsule and its launch command before ending. A closeout without that command is
incomplete; a new autonomous session without a capsule must create one before broad execution.

## Bounded Composition

A long-running campaign or whole-repo gate may exist only as a thin orchestrator over independently
owned, bounded units. Every unit declares its inputs, owner, predicate, execution profile, finite
retry policy, bounded-output policy, and durable receipt. The aggregate preserves completed receipts,
resumes from them, and reports counts plus links; it never reruns successful children or emits their
full logs.

Apply the same rule to artifacts: README files are indexes over cohesive modules, not concatenated
prompts, reports, transcripts, or append-only scrawl. Split on semantic ownership and independently
testable interfaces, not an arbitrary line count. A file repeatedly changed for unrelated reasons has
already exposed a missing module boundary.

CI must shard module predicates and run eligible shards in parallel. The final integration gate checks
the shard receipts plus only genuine cross-module seams. Each shard has an execution-profile timeout,
finite transient retry policy, output cap, and stable receipt; no unbounded wait, retry, or log stream
is a valid verification strategy.

## Machine-Wide Host Admission

Every heavy local Codex, Claude, OpenCode, Agy, or Limen surface must enter through the shared host
admission boundary documented in [`docs/host-work-admission.md`](docs/host-work-admission.md).
Admission is machine-wide across worktrees: at most one non-plan Codex root turn and at most one
heavy local surface. New heavy work is denied under declared Backblaze, swap, disk, or VITALS
pressure; existing work is never killed, restarted, or retuned and may perform bounded closeout.

Hooks are an early control layer, not sole enforcement. Codex `PreToolUse` cannot reliably block a
tool and `SubagentStart` cannot prevent creation, so heavy entrypoints must acquire the same atomic
lease internally. Leases bind PID plus process-start identity, refresh finitely, and clean up only
dead, reused, or stale owners. Never delete the lease store or signal a peer to seize capacity.

Project Codex families are capped at three threads and depth one. Global hook deployment and the
verified non-backed scratch root belong to the Domus cartridge; Limen must not patch home-directory
hooks or backup configuration directly.

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

- Append a `dispatch_log` entry for every state transition; do not rewrite prior entries except to
  correct your own unpushed typo.
- `open` may move to `dispatched` when budget is reserved for a specific agent/session.
- `dispatched` may move to `in_progress` when execution starts.
- `dispatched` may move back to `open` only if no execution occurred; restore the reserved budget.
- `in_progress` may move to `done`, `failed`, `failed_blocked`, or `needs_human`.
- `done` may move to `archived`. Reopening completed work requires a new task or explicit human instruction.

## Where to Find Tasks

```bash
# Path is always:
$LIMEN_ROOT/tasks.yaml

# Fallback if env var is unset:
./tasks.yaml
```

## Session Start Ritual

For dispatch-mode sessions, execute in order:

### 1. Identify Yourself

```bash
# Limen needs to know which agent you are. Set if not already:
export LIMEN_AGENT="${LIMEN_AGENT:-$(basename $0)}"
# Expected values: agy | claude | codex | copilot | gemini | github_actions | jules | opencode | oz | warp
```

### 2. Read the Task File

Read `$LIMEN_ROOT/tasks.yaml` (or `./tasks.yaml` if unset). Parse the full file. Pay
attention to:
- `portal.budget.track` — how much budget has been spent today
- `portal.budget.per_agent.<your_name>` — your per-agent cap
- The `tasks` list — all pending and in-progress work

### 3. Find Available Tasks

Filter for tasks matching ALL of:
```
target_agent == "<your_name>" OR target_agent == "any"
AND status == "open"
AND budget_cost <= remaining_daily_budget
```

Sort by priority: `critical > high > medium > low > backlog`.

### 4. If No Tasks Found

Report: "No pending tasks in limen for `<your_name>`."
Then run: `limen status` to show the full board (if CLI installed), or just exit.

### 5. Claim a Task

Pick the highest-priority task. Prefer the Limen CLI/MCP claim path when available (for example,
`limen dispatch --agent <your_name> --live` or the MCP task tools). If editing `tasks.yaml`
directly, re-read it immediately before writing and abort if the task status, budget, or
`dispatch_log` changed.

Update `tasks.yaml` and append to `dispatch_log`:

```yaml
# Change this:
  - id: "LIMEN-001"
    status: open

# To this:
  - id: "LIMEN-001"
    status: dispatched
    updated: "<now>"  # ISO-8601 UTC from: date -u +"%Y-%m-%dT%H:%M:%SZ"
    dispatch_log:
      - timestamp: "<now>"  # same timestamp format
        agent: "<your_name>"
        session_id: "<current_session_id>"
        status: dispatched
```

Also reserve budget by incrementing `spent` counters:
```yaml
portal:
  budget:
    track:
      spent: <previous + budget_cost>
      per_agent:
        <your_name>: <previous + budget_cost>
```

### 6. Execute

Begin work on the task. When you start actual execution (not just planning), update
status to `in_progress` and append a `dispatch_log` entry.

### 7. Report Results

On completion:
```yaml
  - id: "LIMEN-001"
    status: done
    updated: "<now>"
    dispatch_log:
      - timestamp: "<now>"
        agent: "<your_name>"
        session_id: "<current_session_id>"
        status: done
        output: "<summary of what was done, files changed, outcomes>"
```

On failure:
```yaml
  - id: "LIMEN-001"
    status: failed
    updated: "<now>"
    dispatch_log:
      - timestamp: "<now>"
        agent: "<your_name>"
        session_id: "<current_session_id>"
        status: failed
        output: "<what went wrong, why it failed>"
```

Choose the terminal state precisely:

- `failed` — the attempt ran and did not succeed, but another attempt may fix it.
- `failed_blocked` — an external system blocked progress (billing, auth, unavailable service,
  broken dependency outside the repo), or the healer parked chronic fleet-debt there
  (reopened ≥3×, never a PR — keep `needs_human` for genuinely human-gated atoms).
- `needs_human` — the next required action is a real human decision or manual step.

For `done`, include the evidence: predicate command, result, changed paths, PR/commit if any, and
any scoped caveats. If a higher-priority runtime constraint prevents verification, do not claim a
verified `done`; record the blocker instead.

---

## Session End Ritual

### 1. Release Stale Claims

For any tasks you have in `dispatched` status where no execution occurred:
```yaml
  - id: "LIMEN-001"
    status: open
    updated: "<now>"
```

Also restore budget for claims released before execution. Do not refund budget for work that
actually ran unless the task owner explicitly records that policy in `tasks.yaml`.

For tasks already in `in_progress`, do not silently reopen after partial work. Move them to
`failed`, `failed_blocked`, or `needs_human` with evidence, unless an explicit scheduler policy says
to release stale partial work.

### 2. Commit and Push

If `$LIMEN_ROOT` is a git repo, commit and push `tasks.yaml`:
```bash
git -C "$LIMEN_ROOT" add tasks.yaml
git -C "$LIMEN_ROOT" commit -m "limen: update task states"
git -C "$LIMEN_ROOT" push
```

Stage only `tasks.yaml` for board updates. Do not force-push, rewrite unrelated history, or include
unrelated work in the task-state commit. If the runtime or human instruction forbids git writes,
report the exact uncommitted board change instead.

## Safety & Evidence

- Never place plaintext secrets, tokens, credentials, personal contact data, or private customer
  data in `tasks.yaml`, `dispatch_log`, commits, PR bodies, or chat transcripts.
- Prefer durable links and paths over pasted logs. Summarize long outputs.
- Every `done` report should be reproducible from the repo: predicate command, result, changed
  files, and commit/PR reference where applicable.
- If a tool charter asks for behavior that conflicts with this protocol, follow the precedence
  ladder above and update the lower-priority doc later.

## Deployment Pointer

Production deployment is operational guidance, not dispatch protocol. Use
[`docs/deployment.md`](docs/deployment.md) for SaaS deployment variables, commands, and safety
checks.

---

## Agent-Specific Notes

### Claude
- You are Claude. Read this file as part of your startup instructions.
- You have access to the full filesystem — `$LIMEN_ROOT/tasks.yaml` is a regular file.
- Support `limen` as a subagent: when asked, run the limen CLI or read/write tasks.yaml directly.
- **Fleet launches never wait on permissions.** Limen-owned non-interactive Claude dispatch uses
  `--permission-mode dontAsk` with an explicit file-mutation allowlist. Bash/network policy remains
  owned by effective user/project/managed rules; Limen does not inject a blanket shell grant. A tool
  outside that surface, or one matched by an ask or deny rule, must fail closed and let the
  dispatcher cascade or owner-route it; it must never become an approval modal. Do not replace this with
  `acceptEdits` or `auto` (both can prompt), or `bypassPermissions` (unsafe on the host). This fleet
  contract does not change the operator's settings or any interactive/user-started Claude session.
- **Tier subagent fan-out by job.** Task/Workflow subagents inherit the session model; pick each agent's tier by its job (`.claude/agents/` types, or an explicit `model`/`effort`) so trivial workers never ride Opus. Authority: `cli/src/limen/model_selection.py`; details in CLAUDE.md → Parallel Exploration & Fan-Out.
- **Fable plans, cheaper tiers build.** Fable's role is PLAN-ONLY: it does the deep analysis, emits a build packet into a worktree, and hands off to a cheaper tier (Opus/Sonnet/Haiku) that builds; building on Fable is prohibited. It is acceptance-gated (`scripts/fable-allotment.py accept ...`, `LIMEN_FABLE_ACCEPTANCE=<receipt>`) AND live runtime-capped against actual weekly tokens burned (40% deliberate / 50% hard, `scripts/fable-allotment.py balance` → `logs/fable-allotment.json`, enforced in `cli/src/limen/model_selection.py`). Full doctrine + caps: `docs/fable-allotment.md`.

### Gemini
- You are Gemini CLI (v0.44.1+). Read `$LIMEN_ROOT/tasks.yaml` at session start.
- Use `--sandbox $LIMEN_ROOT` if you need repo context.
- You do not have background async dispatch — you claim and execute in the same session.
- Your per-agent budget is tracked separately from Jules.

### Jules
- You are Jules (Google async coding agent). You do not have interactive sessions.
- Your dispatch is managed by `limen dispatch --agent jules` or the scheduler.
- Read `tasks.yaml` to understand the task queue; your harvest cycle checks results.
- You are the workhorse: 100 runs/day budget is primarily allocated to you.

### OpenCode
- You are OpenCode. Read `$LIMEN_ROOT/tasks.yaml` at session start.
- Support `--task <id>` flag for targeted dispatch to a single task.
- Write results back to tasks.yaml on completion.

### Agy
- You are Agy / Antigravity CLI. Read `$LIMEN_ROOT/tasks.yaml` at session start.
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
- If you cannot update `tasks.yaml` directly, report task state and evidence in the PR or commit
  output so a writable agent can sync the board.

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
- You are a Warp-backed paid-service lane. Accept only work packets with a named repo/issue/PR
  receipt target and a verification command.
- If service credentials or workflow dispatch are unavailable, report `failed_blocked` with the
  missing external gate.

### Goose
- Goose is not currently in Limen's canonical `target_agent` set. Do not assign tasks to Goose
  until `VALID_AGENTS`, capacity detection, dispatch routing, and this protocol are updated
  together.

---

## Quick Reference

| Action | Command |
|---|---|
| Read tasks | `cat $LIMEN_ROOT/tasks.yaml` |
| Claim a task | Use CLI/MCP, or final re-read then edit `status: open` → `status: dispatched` |
| Start execution | Edit `status: dispatched` → `status: in_progress` |
| Report done | Edit `status: in_progress` → `status: done` + add output |
| Show board | `limen status` (if CLI installed) |
| Show macro/micro progress | `limen progress` (`--view`, `--scope`, `--all`, or `--json-output`) |
| Dispatch | `limen dispatch --agent <name> --live` |
| Harvest | `limen harvest --agent <name>` |
| Init new | `limen init --root <path>` |
| Sync with SaaS | `limen sync` |
