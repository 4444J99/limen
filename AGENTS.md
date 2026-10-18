# Limen Agent Protocol

**Read this file on every session start.** It says where to find work, how to claim it, and how to
report results. How it relates to `CLAUDE.md`, `GEMINI.md`, and the ecosystem `ORGANVM:AUTO` layer:
[`docs/agent-instruction-standard.md`](docs/agent-instruction-standard.md).

---

## Operating Modes

- **Direct-session mode:** if the human gives an explicit request in the current session, satisfy it
  first. Do not claim unrelated queue work or reserve budget. Submit any required task transition
  through the conduct broker; never edit the `tasks.yaml` projection. A correction or safety lane is
  additive unless the human cancels or replaces the active request: keep driving the original
  deliverable while resolving the added lane within its own safety and ownership boundary.
- **Dispatch mode:** if launched by the scheduler, `limen dispatch`, MCP task tooling, or an explicit
  "take the next task" request, follow the startup checklist and session rituals below.

## Working in This Repo

No root `pyproject.toml`, no root `package.json`, and **no pytest config anywhere**. Each package
carries its own manifest; the gate registry owns the commands.

| Path | What it is |
|------|------------|
| `cli/src/limen/` | The `limen` CLI (215 modules); Click tree in `cli.py`, entry `entrypoint.py`. **The core.** |
| `mcp/src/limen_mcp/server.py` | FastMCP conduct/task server holding canonical `VALID_STATUSES` / `VALID_AGENTS`, which this file is verified against. |
| `ianva/` | MCP doorway/orchestrator. Stdlib-only, `dependencies = []`. |
| `web/app/` | Next.js static dashboard (`output: "export"` → `out/`); `npm run build` runs a `prebuild` data pipeline. |
| `web/worker/` | Cloudflare Worker — **the live runtime**. DO `ConductKeeperDurableObject`; `npm run check` = `node --check` + `node --test`. |
| `web/api/` | FastAPI. Deploy rail **dormant** (no `GCP_SA_KEY`); `web/api/**` and `cli/**` are non-deploy. |
| `scripts/` | ~670 operational scripts **and the whole gate rail**; `scripts/verify-scoped.sh` is the push gate. |
| `institutio/governance/gates.yaml` | **The GATES registry is the command list** (175 gates). Consumers derive from it; never hardcode a gate into one. |
| `organs/` | 17 institutional pillars — records, mostly **data, not code**; only 8 ship a `validate-<organ>.py`. |
| `spec/contracts/` | Portable JSON Schemas (conduct receipts, leases, prima-materia). |
| `moneta/`, `apps/` | `moneta` is a standalone TS package (`vitest`); `apps/danse` a retired pointer. |

### Environment traps

- **Bare `python3` on this host is Homebrew's newest — it has neither PyYAML nor `click`**, so every
  gate script and the whole CLI need a resolved interpreter. `scripts/lib/gate-python.sh` resolves
  one, preferring yaml+pytest+ruff (`pip install -e 'cli[test]'`); override `LIMEN_GATE_PYTHON`.
  `bash scripts/verify-scoped.sh` calls it for you. Never hardcode a `.venv` path — `.venv/` is
  gitignored, so a fresh clone has none.
- **`limen` on PATH is not your checkout** — it is a Domus shim execing a SHA-pinned runtime. Run
  yours as `PYTHONPATH=cli/src "$LIMEN_GATE_PYTHON" -m limen …`; that interpreter needs
  `pip install -e 'cli[test]'` (the resolver's PyYAML-only fallback cannot run the CLI).
- Standard env: `LIMEN_ROOT=$PWD LIMEN_TASKS=$PWD/tasks.yaml PYTHONPATH=$PWD/cli/src`.
- `tasks.yaml` is a **public aggregate projection** (`tasks: []`); the real board is remote.

### Commands

```bash
# THE push gate — runs exactly the gates your diff implicates. Bare command, no && chains.
bash scripts/verify-scoped.sh

# Selection only; never combine with --changed (verify-scoped.sh hard-wires it). verify.py's
# shebang is a bare python3, so call it through a PyYAML interpreter:
"$LIMEN_GATE_PYTHON" scripts/verify.py --explain <path>...   # or --list
bash scripts/verify-whole.sh                            # whole-system; there is no --fast flag

# Lint / typecheck (as ci.yml, which also runs mypy as two steps)
python3 -m ruff check cli/src cli/tests web/api mcp ianva
python3 -m ruff format --diff cli/src cli/tests web/api mcp ianva
python3 -m mypy --config-file cli/pyproject.toml cli/src/limen/
python3 -m mypy --ignore-missing-imports mcp/src/limen_mcp/ ianva/src/ianva/
# web/app: CI runs `npx --yes -p typescript tsc --noEmit -p tsconfig.json` in web/app; registry gate `web-build`.

# Tests — the hermetic wrapper is mandatory
bash scripts/run-pytest-hermetic.sh cli/tests/test_<file>.py -q
npm --prefix web/worker run check     # node --check + node --test
npm --prefix moneta test              # vitest + tsc --noEmit
```

`scripts/run-pytest-hermetic.sh` scrubs every `LIMEN_*` var, neutralizes git/XDG config, pins
`PYTHONPATH` to this checkout, then re-arms `LIMEN_NOTIFY=0` — do not bypass it.

### Hooks that mechanically deny shell commands

A **denial** is one JSON object on stdout, `exit 0` — the exit code is never the channel. An
allow (or unclassifiable input) is silent: `exit 0`, no output.

| Guard | Denies | Escape hatch |
|-------|--------|--------------|
| `scripts/hooks/pytest-scope-guard.sh` | Full-suite pytest (`cli/tests`, `web/api/tests`, `tests/`, or bare pytest inside a suite parent) — *a directory plus `-k` is still a full collection* | `LIMEN_ALLOW_FULL_PYTEST=1` |
| `scripts/hooks/no-hand-poll-guard.sh` | loop + `gh` probe + `sleep` in one command; any `await-pr.sh` invocation (retired, exits 64) | `LIMEN_ALLOW_PR_POLL=1` — never revives `await-pr.sh` |
| `scripts/hooks/worktree-commit-guard.sh` | `git commit` in the **live** checkout while it sits on `main` | `LIMEN_ALLOW_LIVE_COMMIT=1` |
| `scripts/hooks/outbound-preflight-guard.py` | **Unarmed** — a filed human lever (`his-hand-levers.json`); no lane wires it, so nothing denies you. Sends still need a fresh, target-bound preflight receipt | `LIMEN_ALLOW_UNVERIFIED_OUTBOUND=1` |

All four are declared in `institutio/governance/parameters.yaml` (leave the value `0`), but wiring
is uneven: `.claude/settings.json` binds the first three, `.codex/hooks.json` binds only
`no-hand-poll`. Codex also denies compound bash via `cli/src/limen/action_admission.py`. An unwired
guard does not bind you.

### Isolating a mutation lane

One checkout and branch per session — never two. `limen workstream REPO SLUG` creates or reuses an
isolated worktree plus a kickoff capsule; `limen host-admission status` shows the writer/heavy
lease. Check it first; never nest a clone inside a worktree.

## Startup Checklist (fast path)

For dispatch-mode sessions: **1.** identify yourself · **2.** inspect broker capabilities plus the
`tasks.yaml` projection · **3.** register the native session · **4.** claim through the CLI/MCP
tools or accept a broker-assigned `WorkPacketV1` (both reserve the same lease and budget debit) ·
**5.** verify before reporting `done` · **6.** close out — report the receipt, harvest children, and
release any reservation that never started.

## Precedence

When instructions conflict, the higher rule wins:

1. System / developer / runtime constraints (the harness)
2. The human's explicit instructions for this session
3. TABVLARIVS broker events and their `tasks.yaml` projection — the source of truth for task **state**
4. `AGENTS.md` — the cross-agent dispatch **protocol**
5. Tool-specific charters (`CLAUDE.md`, `GEMINI.md`) — per-agent behavior
6. General repository docs (`README.md`, `docs/**`)

Where a tool charter restates a rule from this file, this file is the source of truth.

**Directory-scoped `AGENTS.md`.** A component may carry its own. It sits at rung 4 beside this file
and is *more specific*, not higher: it adds what only that component knows and may never contradict
this file or a tool charter. **Read the closest one to the files you are editing.** Keep it to what
is not derivable from the code — a component's verification belongs in a `gates.yaml` entry, where
every agent and CI get it without reading anything.

Harnesses that cannot read `AGENTS.md` natively get a thin pointer
([`.github/copilot-instructions.md`](.github/copilot-instructions.md)), never a second rulebook.

## Peer Conductor Contract

Conductor is a temporary capability, never a rank. There is no master agent or model hierarchy:
any registered peer may conduct, execute, review, or combine those roles while TABVLARIVS remains
the deterministic record keeper and lease authority.

- Agents do not control one another. They submit bounded `WorkPacketV1` children through the shared conduct broker
  and observe receipts; the broker atomically assigns work to a healthy native lane.
- A child may only reduce its parent's authority, path scope, spend, deadline, retry runway, depth,
  and fanout. Cycles and repeated ancestry work keys are rejected.
- Preserve native identity end to end: Codex executes as Codex, Claude as Claude, OpenCode as
  OpenCode, and every other lane as itself. A preferred target is a routing hint, not authority to
  substitute one provider identity for another.
- Register direct human sessions with `human_protected: true`. Autonomous peers may observe them
  but must not steal, adopt, retune, cancel, signal, stash, reset, or reap them.
- Reserve a child run before invoking native subagents, teams, or other fanout that consumes
  separate capacity or mutates state. Hidden native fanout is rejected.
- Only the broker may accept lifecycle transitions, budget debits, leases, or projection writes.
  Never edit `tasks.yaml` directly; CLI/MCP task compatibility tools submit the same broker events.
- Conductor loss does not cancel live children: after absence is proven another registered peer may
  adopt the graph. Cancellation before start is broker-owned; after start, stop requests are
  cooperative. If the broker is unavailable, inspection and already-leased work may continue, but new
  claims, children, and lifecycle transitions fail closed.

## Correction Propagation

Human corrections are system input, not local chat residue. Propagate a correction about workflow,
priority, ownership, evidence, cadence, or acceptance criteria before closing, using the narrowest
durable surface future siblings actually read:

- Cross-agent behavior → update `AGENTS.md` or the owning instruction standard, then run
  `bash scripts/verify-scoped.sh` (selects the `agent-docs` drift predicate).
- Creates or changes work → submit a TABVLARIVS ticket/task packet, never an ad-hoc board edit.
- Changes acceptance criteria → update the task, packet, PR body, or receipt target.
- Cannot be applied now → record a blocker with owner, missing gate, and next command.

A response-only apology does not propagate: a session that leaves no durable protocol, ticket,
receipt, or blocker has not closed the loop for the swarm.

## Engineering Ownership

The human supplies ideal forms, pain points, priorities, taste, and acceptance pressure; agents own
the engineering translation. Do not ask the human to choose routine coding mechanics, branch shape,
test scope, cleanup strategy, or best-practice tradeoffs when the repo and evidence make a
defensible path available.

Choose the smallest sound implementation, verify it, and record the result. Escalate only for real
human gates: irreversible deletion of personal data, credential or account actions, paid overages,
public identity claims, legal/medical/financial commitments, or product/values decisions not
derivable from existing doctrine.

Internal work follows [authorized scope and demonstrated capability](docs/architecture/internal-project-authority.md);
unfinished engineering is not a blocker.

## Session Discipline

Cross-agent disciplines enforced by `scripts/check-agent-docs.py` (checks M, N, Q, R), each stated
once here as the canonical shared layer. Tool-specific charters (`CLAUDE.md`, `GEMINI.md`) extend or
cite these; they must not contradict them.

**1. Derive answers — never present option menus when a registry already owns the answer.** Query
the registry and proceed. Options are forced by a genuine human-gated lever, not a default posture.

**2. No synchronous CI waits; scoped verification.**
`scripts/verify-scoped.sh` is the implicated pre-push gate; there is no synchronous waiter. A
registry-declared **single-owner fast lane** merges its verified head immediately with
`gh pr merge NUMBER --repo OWNER/NAME --squash --match-head-commit SHA` — remote checks and automated reviews are advisory, so
include any implicated local build/deploy predicate in that batch.
Other repositories submit at most once with
`scripts/merge-drain.py --repo OWNER/NAME --pr NUMBER --expected-head SHA` and return control;
untyped submissions become delivery, holds are preserved.
`QUEUED` is GitHub ownership, never a `MERGED` receipt. Never retry, re-arm, poll non-required
checks, or rerun a green exact-head predicate without a changed head or observed failure.

Treat one exact tree as one verification batch, not a per-finding waterfall: batch independent
corrections, then let the scoped resolver run eligible gates concurrently within each resource tier —
cheap wave first, then the admission-gated heavy wave, with only `serialize: true` gates forming the
heavy tail's local chain. Every gate has a finite deadline, bounded output, and a visible
start/finish receipt, and a new review observation invalidates only the implicated shard.

**3. Durable homing — all state in git-tracked homes; no local orphan files.**
Every work product, task, blocker, and human-gated atom must land in a git-tracked durable home
before the session ends: a merged PR, an open PR with a named owner, a pushed plan/task, or an
explicit blocker in its registry owner. Local-only state is not done, and human-gated atoms file in
`his-hand-levers.json` or the credential organ rather than being recited back in a closeout.

**4. No-stall — proceed on reversible actions; BLOCKED-once protocol for genuine gates.**
Reversible work proceeds without a confirmation gate. When a genuine external blocker is hit,
state it exactly once (`BLOCKED: <atom>`), file the atom in its registry owner, and keep driving
every other reversible lane to its verified end. Never loop on, poll, or re-surface a filed gate.
The litmus: am I destroying, sending, spending, or irreversibly leaking? If no, proceed.

**5. Concurrent integration — moving `main` is normal; rewriting every PR head is not.**
Interactive and autonomous sessions are co-equal supported work, provided each mutation lane is
isolated in its own worktree and topic branch. A newer `main` must never trigger an unbounded
merge/rebase → full-CI → newer-`main` loop. A single-owner fast lane merges its verified SHA through
the PR rail with `--match-head-commit`, without waiting for `pr-gate`, review, or a synthetic
`merge_group`; a shared-writer queue may verify that synthetic `merge_group` with one
`scripts/merge-drain.py --repo OWNER/NAME --pr NUMBER --expected-head SHA` submission. In either
lane, never use `scripts/await-pr.sh`, never `--admin`, force-push, repeated branch rewrites, or a
session-held merge watch. Direct `main` writes are forbidden, board snapshots included: Tabularius
coalesces the local projection onto its stable, fast-forward-only PR branch, and the no-bypass
`pull_request` rule makes that boundary remote-enforced. Full contract:
[`docs/architecture/concurrent-integration.md`](docs/architecture/concurrent-integration.md).

**6. Read the predicate's own exit code — never a pipeline's.**
`predicate | tail` reports the filter's exit status, not the predicate's, so a gate that printed
FAIL reads as green (observed 2026-08-05: a closeout reported `EXIT=0` from a run that had truly
exited 1). Run each gate bare and read its own exit code; when output must be filtered, capture to a
file and filter the copy, or read `PIPESTATUS`. The defect enters through improvised verification
shell, where a false green has no second reader.

**7. One command per judged invocation on hook-judged rails.**
Where a policy hook judges shell commands, compose nothing on the judged rail: one bare command per
invocation. A `&&`/`;`/pipe chain forces the judge to guess about the whole composition and also
short-circuits, hiding which member failed. Shell **scripts** chain freely inside their own bodies;
the rule binds the top-level judged invocation only.

**8. Landing proof is positive and repository-qualified.**
A closed-unmerged PR, the absence of an open PR, branch age, a lower branch count, or walkthrough
metadata is never proof that work landed or may be deleted. Landing requires the exact repository,
ref tip, and default generation plus ancestry/merge proof or reviewed tree/patch-equivalence to a
named successor. Every historical review finding stays lifecycle debt until its correction or
evidence-backed disposition is bound to the relevant head and default result. Destructive cleanup
needs separate custody and review-closure proof; census or prose may observe but never set
completion.

### Standing Corrections (from insights reports 2026-06-23 → 2026-07-17)

Six recurring failures distilled into lane-neutral rules, enforced by check N
(`scripts/check-agent-docs.py`). These bind every agent lane equally.

**N-a. Done is an executable predicate, never prose.** No agent claims completion until the owning predicate or tests pass on live state.
Motion, related PRs, and prose are not completion proof.

**N-b. Closeouts are terminal — reach the idempotent fixed point, state it once, stop.** File residual work with its durable owner (registry,
board, lever) before closing; never hand it back as a list. A closeout that recites open items has
failed the fixed-point test.

**N-c. Derive before asking.** A decision already answered by charter, registry, or precedent is queried and applied, never re-raised for
operator confirmation.

**N-d. Durable homing applies to all produced state.** Config, data, docs, and receipts produced in a session land in their git-tracked owner before
the session ends — never in local-only files, scratch, or orphan branches.

**N-e. Active unblocking.** When a bridge, auth, or gate is blocked, attempt its documented bootstrap path once; a passive re-report of a
known-blocked status is not acceptable, and reversible work in other lanes proceeds regardless.

**N-f. Triage windows anchor at the last human review point.** Triage windows start at the last human review, not the last automated run.
Sanity-check item counts against the live board first; a count mismatch stops the triage until
resolved.

## Doctrine Pointers

Each binds autonomy or integration and is stated once, in doctrine — read it when the question is
live; do not recite it.

| Question | Doctrine |
|---|---|
| Is this work authorized? | [Internal project authority](docs/architecture/internal-project-authority.md) |
| What counts as progress? | [Board progress and source-coverage truth](docs/architecture/board-progress-and-source-coverage-truth.md) |
| Which model should run this? | [Dynamic provider selection](docs/architecture/dynamic-provider-selection.md) |
| Local state or remote? | [Source of truth and local cache](docs/architecture/source-of-truth-and-local-cache.md) |
| Where does data live? | [Run-and-gun substrate](docs/architecture/run-and-gun-substrate.md) |
| When must autonomy stop? | [Finite-workspace recovery](docs/architecture/finite-workspace-recovery.md) |
| How long may a session run? | [Autonomy continuation](docs/architecture/autonomy-continuation.md) |
| Who owns a recurring pain point? | [Pain-point ownership](docs/architecture/pain-point-ownership.md) |
| May this session spawn a successor? | [Continuation capsules](docs/architecture/continuation-capsules.md) |
| How do campaigns fan out? | [Bounded composition](docs/architecture/bounded-composition.md) |
| Who runs the one heavy surface? | [Machine-wide host admission](docs/architecture/machine-wide-host-admission.md) |
| How is a tier reserved? | [Fable allotment](docs/fable-allotment.md) |
| How is anything deployed? | [Deployment](docs/deployment.md) — operational, not dispatch protocol |

## Prompt Corpus as the Control Plane

The human's prompt history is durable operating input, not disposable conversation context. Before
inventing priorities or asking the human to repeat an instruction, consult the corpus ledgers and
current receipts. Treat the individual ask or correction as the unit of intent; a session, plan, task,
branch, or PR is only one container for it.

- Preserve every prompt event privately with source lineage, atomized into asks, corrections,
  constraints, acceptance criteria, and human gates without erasing the original or its lineage.
- Derive intent through lineage: corrections and newer formulations can supersede an older
  implementation shape while the older prompt stays evidence. Age alone is never priority authority.
- Rank unresolved atoms on operator emphasis, systemic leverage, magnitude, recurrence,
  dependency/blocking impact, preservation risk, recency, and cost of delay. Easy or visible code
  must not outrank a larger control-plane concern merely because its receipt is nearby.
- Classify each atom with an evidence-backed corpus disposition — unassessed, not-done, partial,
  done, blocked, superseded. These are analytic dispositions, **not** Limen task states.
  `done` requires a durable owner receipt and a satisfied predicate; prose resemblance, motion, or a
  related PR is not completion proof.
- Corpus governance and execution run concurrently — the corpus ranks and feeds work while
  authorized lanes continue within their resource bounds; never force a false choice between
  auditing the whole and finishing sound in-flight work. Feed receipts back so ranking and
  completion truth evolve continuously.
- Do not make the human restate settled intent. Escalate only when the corpus and doctrine leave a
  genuine human gate or an irreducible product/values conflict.

Tracked ledgers stay redacted; raw prompt bodies, private paths, full hashes, and sensitive material
stay in `.limen-private/session-corpus`. Board mutations derived from corpus review still go through
TABVLARIVS, and task statuses use only the canonical state vocabulary below.

## Full Lifecycle Closure

Every prompt, idea, viewpoint, branch, worktree, scratch root, and generated lane is work until it
has a durable terminal receipt — "nothing came of it" is not a closeout state. Valid closure forms:

- shipped/merged with predicate evidence;
- open PR with owner, predicate, and merge condition;
- owner task or plan committed and pushed for later work;
- preservation receipt proving custody plus a concrete next owner/action;
- explicit blocker naming the external gate and next command.

Never close a lane merely because it timed out, produced no diff, lost context, looked stale, or was
pushed to a remote branch. Once a clean, inactive exact HEAD is pushed, reap the disposable checkout —
the branch, PR, plan, task, or blocker remains the durable owner. If a worktree produced no usable
code, push the plan/owner task capturing the prompt's intent before reaping it.

Closure is a covenant across every lane. Use
`scripts/no-tasks-on-me.sh --session-id ID --worktree PATH --receipt RECEIPT --json`.
The committed owner receipt binds custody, publication, scoped verification (including
`scripts/credential-wall.py --check` for secrets used), and retained broker obligations. Session
release, task completion, estate health and deletion eligibility are distinct, and unknown ownership
fails closed — estate diagnostics do not substitute for session proof. See
[session evidence](docs/session-closeout.md). Option menus, caveat tails, and items parked only in
the transcript are not closure forms. A handoff leaves unfinished tasks open.
After a passing session predicate at an idempotent fixed point, end with:
"CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items". Nothing follows it.

## Task States

The canonical state set lives in code — `VALID_STATUSES` in `mcp/src/limen_mcp/server.py` — and
this table is verified against it by `scripts/check-agent-docs.py`. Do not invent states.

| State | Meaning |
|-------|---------|
| `open` | Available to claim |
| `dispatched` | Claimed by an agent, not yet executing |
| `in_progress` | Actively being worked |
| `done` | Completed successfully |
| `failed` | Attempted, did not succeed — retryable |
| `failed_blocked` | Stopped by an external blocker (billing / auth / infra), or parked chronic fleet-debt (reopened ≥3×, never a PR — `scripts/heal-dispatch.py` parks it here, never `needs_human`) |
| `needs_human` | Cannot proceed without a human action |
| `archived` | Closed and suppressed from active steering |

Normal flow: `open → dispatched → in_progress → done → archived`; from `in_progress` a task may
instead move to `failed`, `failed_blocked`, or `needs_human`. A stale `dispatched`/`in_progress`
claim is released back to `open` (see Session End Ritual). There is **no** `completed` state — use `done`.

### Transition Rules

- Submit every transition to the broker. TABVLARIVS appends the `dispatch_log` projection entry;
  agents do not rewrite prior events or the projection.
- `open` → `dispatched` when budget is reserved for a specific agent/session.
- `dispatched` → `in_progress` when execution starts.
- `dispatched` → `open` only if no execution occurred; restore the reserved budget.
- `in_progress` → `done`, `failed`, `failed_blocked`, or `needs_human`.
- `done` → `archived`. Reopening completed work requires a new task or explicit human instruction.

## Where to Find Tasks

`limen status` · `$LIMEN_ROOT/tasks.yaml` (fallback `./tasks.yaml`) · `limen conduct capabilities`

## Session Start Ritual

For dispatch-mode sessions, execute the checklist above in order. The details that are easy to get
wrong:

### 1. Identify Yourself

`export LIMEN_AGENT="${LIMEN_AGENT:-$(basename $0)}"`. Expected values: agy | claude | codex | copilot | gemini | github_actions | jules | opencode | oz | warp.

### 2. Inspect the Projection and Register

Read the projection in full, noting `portal.budget.track` (spent today),
`portal.budget.per_agent.<your_name>` (your cap), and the `tasks` list. Register the real native
session — direct human sessions add `--human-protected`, and never register under the initiator's
identity when the executor is a different lane.

### 3. Find Available Tasks

Keep only tasks matching ALL of `target_agent == "<your_name>" OR target_agent == "any"`, `status == "open"`, and
`budget_cost <= remaining_daily_budget`; sort `critical > high > medium > low > backlog`. If nothing
matches, report "No pending tasks in limen for `<your_name>`" and exit.

### 4. Claim a Task

Claiming returns the canonical run/lease identity and reserves the task/resource claims plus one
budget debit atomically. If the broker is unavailable or busy, do not mutate the projection or begin
unleased work.

### 5. Execute

Begin work only after receiving the lease; heartbeat it while executing, and reserve any bounded
child with `limen conduct split` before any fanout.

### 6. Report Results

Submit a schema-valid `RunReceiptV1`, then harvest the root graph. The receipt records
executor/provider identity, exact old/new heads, changed paths, provider run URL,
predicate/check/review evidence, spend, child runs, and terminal outcome. For `done`, include
predicate command, result, changed paths, PR/commit, and scoped caveats. If a higher-priority runtime
constraint prevents verification, do not claim a verified `done`; record the blocker instead.

### 7. Choose the Terminal State Precisely

- `failed` — the attempt ran and did not succeed, but another attempt may fix it.
- `failed_blocked` — an external system blocked progress (billing, auth, unavailable service,
  dependency broken outside the repo), or the healer parked chronic fleet-debt there (reopened ≥3×,
  never a PR — keep `needs_human` for genuinely human-gated atoms).
- `needs_human` — the next action is a real human decision or manual step.

---

## Session End Ritual

### 1. Release Stale Claims

For a reserved run where execution never started, `limen conduct cancel <run>` (or
`conduct_cancel` over MCP); the broker releases its claims and applies the budget policy.

For tasks already in `in_progress`, do not silently reopen after partial work: move them to `failed`,
`failed_blocked`, or `needs_human` through a receipt with evidence, unless an explicit scheduler
policy says to release stale partial work.

### 2. Commit and Push Work

Commit and push only the leased work paths and durable receipts. Do not stage the local
`tasks.yaml` projection, force-push, rewrite unrelated history, or include unrelated work — the
keeper commits accepted projections remotely with SHA compare-and-swap.

## Safety & Evidence

- Never place plaintext secrets, tokens, credentials, or private customer data in `tasks.yaml`, `dispatch_log`, commits, PR bodies, or transcripts.
- Prefer durable links and paths over pasted logs; summarize long output.
- Every `done` report must be reproducible: predicate command, result, changed files, commit/PR.
- If a tool charter conflicts with this protocol, follow the precedence ladder above.

---

## Agent-Specific Notes

**Reserved tiers bind every lane, not just Claude** (`LIMEN_RESERVED_TIERS`): a written
`fable-allotment.py accept …` receipt before the run starts, audited by `scripts/check-reserved-tier.py`.

### Claude
- Use the conduct CLI/MCP surface and preserve Claude identity in every session, packet, receipt.
- Memory is keeper-owned — never Write MEMORY.md or memory atoms; submit a `memory-ticket.py`.
  Non-interactive dispatch never waits on permissions (`--permission-mode dontAsk`, never
  `acceptEdits`/`auto`/`bypassPermissions`; validated by `dispatch.py`). Full lane mechanics:
  `CLAUDE.md`; tier authority: `cli/src/limen/model_selection.py`.

### Gemini
- Live-verify the version; pins decay. Inspect the projection and register your native session at
  start, and use `--sandbox $LIMEN_ROOT` if you need repo context.
- Submit or accept broker-leased packets; never create hidden fanout.

### Jules
- Google async coding agent, no interactive sessions; dispatch is managed by
  `limen dispatch --agent jules` or the scheduler, and the provider relay returns schema-valid
  receipts. Read the projection for the queue.
- The workhorse: the 100 runs/day budget is primarily yours.

### OpenCode
- Register through ianva and preserve OpenCode identity in every child receipt. Support
  `--task <id>` only as a broker-backed targeted packet; do not mutate the projection.

### Agy
- Use the `agy-conductor` skill as a thin conduct adapter, and run only bounded, lane-safe packets
  with a repo/worktree scope and verification command.
- If work lands in Antigravity scratch space, preserve the per-run delta and return a receipt so
  Limen can bridge it into the task worktree.

### Codex
- Interactive coding harness: in direct-session mode follow the human's request first and do not
  claim unrelated queue work. System / developer / runtime constraints outrank this protocol.

### Copilot
- Treat this file as repository guidance and use the authenticated conductor profile published from
  `integrations/copilot/limen-conductor.agent.md` when available. Return native Copilot identity and
  exact-head evidence; do not merge or close PRs independently.

### GitHub Actions
- Work from the exact workflow input/task payload supplied by Limen, and report durable evidence
  through the workflow run, issue, PR, branch, or artifact named by the task — never chat-only state.

### Oz
- Accept only work packets with a named repo/issue/PR receipt target and a verification command. If
  service credentials or workflow dispatch are unavailable, report `failed_blocked` with the missing
  external gate.

### Warp
- Warp-backed paid-service lane. Same contract as Oz: packet-named repo/issue/PR receipt target plus a
  verification command; report `failed_blocked` on a missing external gate.

### Goose
- Not in the `target_agent` set. Do not assign Goose tasks until `VALID_AGENTS` and capacity
  detection are updated.

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
| Merge predicate | `bash scripts/merge-policy.sh <PR#>` → `CLEARED` (0) · `HOLD` (2) · `BLOCKED` (3) |
| Submit one exact head, return control | `python3 scripts/merge-drain.py --repo OWNER/NAME --pr N --expected-head SHA` |
| Show board / progress | `limen status` · `limen progress` (`--view`, `--scope`, `--all`, `--json-output`) |
| Dispatch / harvest dispatches | `limen dispatch --agent <name> --live` · `limen harvest --agent <name>` |
| Isolate a work lane | `limen workstream REPO SLUG` · `limen host-admission status` |
| Close out | `scripts/no-tasks-on-me.sh --session-id ID --worktree PATH --receipt RECEIPT --json` |
| Secrets homed? | `python3 scripts/credential-wall.py --check` |
| Adopt / cancel / stop | `limen conduct adopt` · `conduct cancel` · `conduct request-stop` |
