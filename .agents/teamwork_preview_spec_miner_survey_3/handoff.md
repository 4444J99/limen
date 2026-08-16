# Handoff Report — Spec Mining Survey 3: Protocols, Requirements, and Predicate Verification

## Observation

Authoritative specification sources investigated:
1. `AGENTS.md` (Limen Agent Protocol, lines 1–731) — Canonical cross-agent dispatch protocol, peer conductor contract, session disciplines (Checks M, N, Q, R, S), task state vocabulary (`VALID_STATUSES`), worktree isolation, and full lifecycle closure covenant.
2. `GEMINI.md` (Limen Gemini Adapter) — Native transport, conductor swarm MCP interface (`conduct_*` tools), work packet leasing, subagent fanout reservation, and exact-tree evidence.
3. `docs/positioning/program/EXECUTION-CHUNKS.md` (lines 1–509) — Complete dependency DAG and prompt contracts for PSP-C00 through PSP-C12.
4. `docs/positioning/program/AGENT-RUNBOOK.md` (lines 1–236) — Leaf claiming, worktree isolation, bare predicate execution, durable receipt markers (`<!-- positioning-receipt:<WORK-ID> -->` and `<!-- positioning-phase-receipt:<PHASE-ID> -->`), phase verification (`--verify-phase`), and terminal Omega proof (`--omega --require-two-pass`).
5. `institutio/governance/gates.yaml` (lines 1–954) — Canonical verification gate registry defining command, paths, tier (cheap/heavy), serialization (`serialize: true`), and CI mirrors.
6. `mcp/src/limen_mcp/server.py` (lines 1–864) — Canonical MCP server implementation with circuit breaker tools (`trip_circuit_breaker`, `reset_circuit_breaker`), conduct broker methods (`conduct_*`), hard loop tracker (`TASK_LOOP_TRACKER > 3`), dynamic costing, and `VALID_STATUSES`.
7. `docs/architecture/*.md` — Key doctrines including `peer-conductor-protocol.md`, `worktree-initialization.md`, `worktree-abandonment.md`, `concurrent-integration.md`, `gates-registry.md`, `source-of-truth-and-local-cache.md`, `machine-wide-host-admission.md`, `continuation-capsules.md`, `bounded-composition.md`, `pain-point-ownership.md`.
8. `scripts/start-worktree-session.sh` & `scripts/verify.py` & `scripts/verify-scoped.sh` & `scripts/verify-whole.sh` — Concrete tooling for worktree setup, scoped verification, batch gate resolution, and whole-system checks.

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | R1: Worktree Isolation | Linked Worktree Lifecycle | Transactional creation and verified tear-down of isolated topic worktrees under `.worktrees/` | Repository alias/path, topic slug, branch prefix (`work`, `feat`, `fix`, etc.) | `.worktrees/<slug>` worktree on `<prefix>/<slug>` branch, `.limen-workstream/` capsule, `workstream.json` receipt | Refuses invalid branch prefix; fails closed on unverified staging roots (`docs/architecture/worktree-initialization.md`) | `scripts/start-worktree-session.sh`, `docs/architecture/worktree-initialization.md` |
| 2 | R1: Positioning Deliverables | Canonical Identity & Offers (PSP-C03) | Ratify production-systems identity, audience narratives, offer ladder, qualification rules, and commercial templates (PSP-P03, PSP-P04) | `institutio/positioning/program.yaml`, `institutio/positioning/commercial-contract.yaml`, reader feedback | Verified offer docs, decision records, narrative ladder in `docs/positioning/offers/` & `docs/positioning/` | Leaf/phase failure if offer economics or reader comprehension fail validation | `docs/positioning/program/EXECUTION-CHUNKS.md:170`, `docs/positioning/offers/` |
| 3 | R1: Positioning Deliverables | Proof & Case-Study Architecture (PSP-C04) | Produce flagship proof classes and design accessible progressive-disclosure case studies (PSP-P05, PSP-P06) | Flagship proof set, claims ledger, evidence packets in `docs/positioning/evidence/` | Validated proof artifacts, visual/accessibility/performance audit receipts | Fails closed on unadjudicated claims, private data leaks, or failing experience audits | `docs/positioning/program/EXECUTION-CHUNKS.md:204`, `docs/positioning/flagship-proof-set.yaml` |
| 4 | R1: Positioning Deliverables | Public Portfolio & Front Door (PSP-C06) | Implement profile, org map, portfolio, resume, identity package, domains, and analytics (PSP-P07) | Architecture specs in `docs/positioning/portfolio-information-architecture.md`, `org-profile-README.md` | Coherent public portfolio, front door, linked repos, analytics integration | Unlinked surfaces, broken navigation, or missing rollback safety fails exit gate | `docs/positioning/program/EXECUTION-CHUNKS.md:272`, `docs/positioning/portfolio.md` |
| 5 | R2: Circuit Breaker | MCP Circuit Breaker | System-wide pause mechanism to protect against API rate limits, bans, or runaway loops | `trip_circuit_breaker()` / `reset_circuit_breaker()` MCP calls | System status string ("Circuit breaker TRIPPED/RESET"), persisted in `.mcp_state.json` | Any MCP tool call while tripped raises `RuntimeError("SYSTEM OFFLINE - GO TO SLEEP...")` | `mcp/src/limen_mcp/server.py:368-384` |
| 6 | R2: Circuit Breaker | Hard Task Loop Tracker | Guard against endless task re-request cycles in the MCP server | Task ID requested via `get_task` | Increments `TASK_LOOP_TRACKER[task_id]` | If count > 3, raises `ValueError("HARD LOOP LIMIT REACHED...")` forcing task to `needs_human` or `failed_blocked` | `mcp/src/limen_mcp/server.py:518-524` |
| 7 | R2: Circuit Breaker | PR Quarantine & Dynamic Costing | Evict failing/looping PRs and double budget cost on failure to prevent starvation | Task transition to `failed`, `failed_blocked`, or `needs_human` | Status update in TABVLARIVS, doubled `budget_cost` (capped at 8) | Chronic fleet-debt (reopened >=3x without PR) parked in `failed_blocked` | `mcp/src/limen_mcp/server.py:645-648`, `scripts/heal-dispatch.py:30` |
| 8 | Verification | Scoped Push Gate | Resolves and executes only verification gates implicated by the changed diff paths | Changed file paths (`git diff` against base ref) | Parallel execution of cheap tier wave, then heavy tier under host admission lease, then serialized tail | Exit 0 if all implicated gates pass; non-zero if any gate fails | `scripts/verify.py`, `scripts/verify-scoped.sh`, `institutio/governance/gates.yaml` |
| 9 | Verification | Non-Circular Leaf Predicate Verification | Executes leaf check bare, generates durable receipt, and verifies via `--verify-work` | Work ID, leaf acceptance condition command bare | Marked comment `<!-- positioning-receipt:<WORK-ID> -->` with JSON payload | `--verify-work` fails closed if predicate wasn't run bare or receipt hashes mismatch | `docs/positioning/program/AGENT-RUNBOOK.md:65-102`, `scripts/positioning-program.py` |
| 10 | Verification | Phase Exit Predicate Verification | Validates aggregate child receipts, executes manifest `exit_predicate` bare, and generates phase receipt | Phase ID (`PSP-P00`..`PSP-P14`), child work receipts | Marked comment `<!-- positioning-phase-receipt:<PHASE-ID> -->` with JSON payload | `--verify-phase` fails closed on missing child receipts, drift, or non-zero predicate exit | `docs/positioning/program/AGENT-RUNBOOK.md:109-151`, `scripts/positioning-program.py` |
| 11 | Verification | Terminal Omega Two-Pass Proof | Proves whole-program terminal convergence over two atomic, distinct remote state snapshots | Pass number (1 and 2), program remote issues and receipts | Two pass files with `limen.positioning_omega_pass.v1` schema, verified by `--omega --require-two-pass` | Fails if state digests differ, timestamps identical, or non-terminal leaves remain open | `docs/positioning/program/AGENT-RUNBOOK.md:152-180`, `scripts/positioning-program.py` |
| 12 | Protocol | Peer Conductor Contract | Symmetric coordination protocol across native agent lanes without a master hierarchy | `conduct_*` MCP tools / `limen conduct` CLI, `WorkPacketV1`, `RunReceiptV1` | Distributed atomic leases, execution DAG, attenuated child reservations | Fails closed if authenticated broker is unavailable; prevents hidden fanout | `AGENTS.md:60-85`, `docs/architecture/peer-conductor-protocol.md` |
| 13 | Protocol | Full Lifecycle Closure Covenant | Mandate that every session terminates at an idempotent fixed point with zero dangling items | `scripts/no-tasks-on-me.sh`, `scripts/credential-wall.py --check` | Terminal closure statement: "CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items" | Fails if tasks remain unclaimed/in-progress on ephemeral session or secret unhomed | `AGENTS.md:213-238`, `docs/architecture/continuation-capsules.md` |

---

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Worktree Initialization | Sibling staging root fails validation (e.g. untracked files present) | Aborts before rename into final location; records `crashed` state in private journal without deleting content (`docs/architecture/worktree-initialization.md`). |
| 2 | Worktree Abandonment | Clean clone with exact HEAD reachable remotely | Reclaimed via `purge-proven-path` with zero-byte stable-lock revalidation, never following symlinks (`docs/architecture/worktree-abandonment.md`). |
| 3 | Concurrent Integration | PR is `BEHIND` latest `main` | Merge queue composes synthetic `merge_group` from latest `main` + PR HEAD; author branch is NOT rewritten or repeatedly rebased (`docs/architecture/concurrent-integration.md`). |
| 4 | Predicate Output Piping | Shell pipeline `predicate \| tail` | Prohibited by Rule 6 in `AGENTS.md`. Piping masks non-zero exit codes (reads filter exit instead of predicate). Must run bare or check `$PIPESTATUS`. |
| 5 | Scoped Gate Selection | Edit touching `firebase.json` or `scripts/assemble-dashboard-data.py` | Classified as deploy-sensitive via `deploy_triggers` in `gates.yaml`; requires full CI matrix pass before self-merge (`institutio/governance/gates.yaml:85`). |
| 6 | Leaf Verification | Invoking `--verify-work <ID>` as the predicate inside the receipt | Circular validation error: `--verify-work` strictly verifies the receipt of an underlying bare command and fails closed if called recursively (`docs/positioning/program/AGENT-RUNBOOK.md:69-72`). |
| 7 | Task Status Update | Updating task marked `workstream:successor-required` to `in_progress` | Refused: expired workstream task requires a separately admitted successor task; only transitions to `failed`, `done`, or `archived` are allowed (`mcp/src/limen_mcp/server.py:640-644`). |
| 8 | MCP Task Claim | Task loan readiness or execution requirement (mount path) missing | Refused: `task_work_loan_readiness` and `evaluate_execution_requirements` fail closed before reservation packet submission (`mcp/src/limen_mcp/server.py:739-746`). |
| 9 | Agent Documentation Budget | `AGENTS.md` exceeding consumer byte cap | Check S in `scripts/check-agent-docs.py` fails if file exceeds `budget_bytes: 32768` (measured 32,740 B) preventing silent Codex truncation (`institutio/governance/gates.yaml:41-56`). |
| 10 | Terminal Omega Proof | Copying Pass 1 output file to Pass 2 path | Rejected by `--require-two-pass`: both files must attest the same passing `state_digest` but have different integer `pass` numbers and different `observed_at` timestamps (`docs/positioning/program/AGENT-RUNBOOK.md:175-176`). |

---

## Detailed Specifications

### 1. Requirements & Interface Specifications for R1 & R2

#### R1: Worktree Isolation & Independent Positioning Outcomes
- **Root Directory Contract**: Dedicated worktrees created under `/Users/4jp/Workspace/.worktrees/` (or repository `.worktrees/<slug>`) on isolated topic branches (`<prefix>/<slug>`).
- **Branch Prefix Validation**: Validated against `VALID_BRANCH_PREFIXES="work feat fix heal chore docs refactor"`.
- **Initialization Protocol**: `limen.worktree_initialization.v1` enforces staging -> validation -> atomic rename -> backlink repair -> published state.
- **Positioning Track Delivery**:
  1. **Canonical Identity & Offer (PSP-C03 / PSP-P03, PSP-P04)**: Bound by `institutio/positioning/commercial-contract.yaml` and `docs/positioning/offers/agentic-delivery-audit.md`. Predicate: `python3 docs/positioning/offers/verify_agentic_delivery_audit_decision.py && bash scripts/run-pytest-hermetic.sh scripts/tests/test_agentic_delivery_audit_decision.py -q`.
  2. **Proof & Case-Study Architecture (PSP-C04 / PSP-P05, PSP-P06)**: Bound by `docs/positioning/flagship-proof-set.yaml` and `docs/positioning/claims-ledger.md`. Predicate: `python3 scripts/tests/flagship-proof-set.test.py && python3 scripts/tests/flagship-evidence.test.py`.
  3. **Public Portfolio & Front Door (PSP-C06 / PSP-P07)**: Bound by `docs/positioning/portfolio-information-architecture.md` and `docs/positioning/org-profile-README.md`. Predicate: `python3 scripts/positioning-program.py --chunk PSP-C06` exit gate verification.
- **Durable Receipts**: Each leaf records its receipt as a markdown code block after `<!-- positioning-receipt:<WORK-ID> -->` with exact head, duration, spend, and non-circular bare command output.

#### R2: Review-Loop Circuit Breaker
- **Loop Detection & Hard Limits**:
  - `TASK_LOOP_TRACKER` in `server.py` caps repeated `get_task` invocations at 3 per day.
  - Chronic fleet debt (reopened >= 3 times without PR) parked in `failed_blocked` via `scripts/heal-dispatch.py`.
- **MCP Circuit Breaker**:
  - `trip_circuit_breaker()` and `reset_circuit_breaker()` persist state in `.mcp_state.json`.
  - All conduct and task operations fail closed with `RuntimeError("SYSTEM OFFLINE - GO TO SLEEP...")` when tripped.
- **Quarantining C04/C05 Loops**:
  - Failing review loops are quarantined to isolated topic branches/worktrees without blocking sibling ready leaves.
  - Leaves with explicit dependencies run independently; phase/chunk dependencies block only aggregate phase closeout.
- **Single-Push Exact-Tree Verification**:
  - Run the narrow implicated gate batch bare once.
  - If green on live state, attach receipt and push once. Never hand-roll poll loops on PR gates.

---

### 2. Acceptance Criteria & Predicate Verification Rules

1. **Predicate Execution Standards**:
   - Every gate/predicate is executed **bare** without shell pipelines (`&&`/`;`/`|` at judged level prohibited).
   - Read the predicate's own exit status (exit 0 = PASS, non-zero = FAIL).
2. **Verification Resolution Architecture**:
   - `institutio/governance/gates.yaml` is the single source of truth for all gates.
   - `scripts/verify.py --changed` computes changed paths against merge-base and runs implicated gates in tiered waves:
     - **Cheap Wave**: Runs all non-heavy, non-serialized gates in parallel.
     - **Heavy Wave**: Runs heavy gates under machine-wide host admission lease (`hold_lease("heavy")`).
     - **Serialized Tail**: Runs gates marked `serialize: true` sequentially under flock (`limen-verify-whole.lock`).
3. **Completion Predicates**:
   - Scoped push: `bash scripts/verify-scoped.sh`
   - Whole system: `bash scripts/verify-whole.sh`
   - Leaf validation: `python3 scripts/positioning-program.py --verify-work <WORK-ID>`
   - Phase proof: `python3 scripts/positioning-program.py --phase-proof <PHASE-ID>`
   - Phase validation: `python3 scripts/positioning-program.py --verify-phase <PHASE-ID>`
   - Terminal Omega: `python3 scripts/positioning-program.py --omega --require-two-pass`
   - Session closure: `scripts/no-tasks-on-me.sh` and `python3 scripts/credential-wall.py --check`

---

### 3. Protocol Requirements (AGENTS.md & GEMINI.md)

1. **Peer Conductor Contract**:
   - Conductor is temporary capability, not rank.
   - Symmetric interface across all lanes: `conduct_capabilities`, `conduct_register`, `conduct_submit`, `conduct_split`, `conduct_graph`, `conduct_heartbeat`, `conduct_report`, `conduct_harvest`, `conduct_adopt`, `conduct_cancel`, `conduct_request_stop`.
   - Native identity preserved end-to-end (`agent: gemini`, `agent: agy`, etc.).
   - Child reservation before subagent spawning (`conduct_split`); hidden fanout is rejected.
   - Direct human sessions registered as `human_protected: true` (never stolen, cancelled, or reaped).
2. **Task State Discipline (`VALID_STATUSES`)**:
   - `open` -> `dispatched` -> `in_progress` -> `done` -> `archived`.
   - Side paths: `failed`, `failed_blocked`, `needs_human`.
   - No direct `tasks.yaml` file edits; all mutations submitted via conduct broker events.
3. **Lifecycle Closure Covenant**:
   - Every work product homes in git-tracked repositories.
   - Ephemeral session must pass `scripts/no-tasks-on-me.sh` and `scripts/credential-wall.py --check`.
   - Terminal closeout phrase: `CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items`.

---

## Logic Chain

1. **Requirement R1 Mapping (Observed in `ORIGINAL_REQUEST.md:12-14` & `docs/positioning/program/EXECUTION-CHUNKS.md:44-58`)**:
   - Worktree isolation requires separate linked checkouts under `/Users/4jp/Workspace/.worktrees/` on single-purpose branches.
   - Positioning deliverables map directly to `PSP-C03` (Identity & Offers / `PSP-P03, P04`), `PSP-C04` (Proof & Experience / `PSP-P05, P06`), and `PSP-C06` (Public Surfaces / `PSP-P07`).
   - Each leaf is admitted based on its explicit dependencies in `positioning-program.py --ready --json` rather than upstream aggregate chunk blocking, allowing parallel progression across isolated worktrees.

2. **Requirement R2 Mapping (Observed in `ORIGINAL_REQUEST.md:15-17`, `mcp/src/limen_mcp/server.py:210-247, 518-524`, & `scripts/heal-dispatch.py:30`)**:
   - Review-hardening loops (C04/C05) must not stall independent ready leaves.
   - Quarantining is enforced at the broker/MCP level: `TASK_LOOP_TRACKER` trips after 3 iterations, and chronic looping PRs move to `failed_blocked`.
   - Exact-tree verification uses scoped gate selection (`verify.py --changed`) to run single-push narrow checks without running unbounded full-suite rerun loops.

3. **Predicate Verification Rules (Observed in `institutio/governance/gates.yaml`, `scripts/verify.py`, `docs/positioning/program/AGENT-RUNBOOK.md`)**:
   - All gates derive from `gates.yaml`.
   - Leaves require bare command execution -> durable marked receipt -> `--verify-work` validation.
   - Phase closure requires manifest-defined `--phase-proof` -> marked phase receipt -> `--verify-phase` validation.
   - Terminal completion requires two-pass Omega verification.

4. **Protocol Rules (Observed in `AGENTS.md`, `GEMINI.md`, `docs/architecture/peer-conductor-protocol.md`)**:
   - Peer conductor contract guarantees symmetric execution and attenuating child bounds.
   - No direct `main` writes or unbrokered `tasks.yaml` edits.
   - Terminal closeout requires green closure predicates and fixed-point termination.

---

## Caveats

- Live GitHub API / remote network probes were not executed in this survey to remain purely read-only and hermetic.
- The Cloudflare Worker / Durable Object remote keeper endpoint requires live credentials (`LIMEN_CONDUCT_TOKEN`) when operating against production; local fallback uses SQLite adapter via `LIMEN_CONDUCT_STATE`.
- No caveats regarding specification discovery — all required files, tools, and doctrines were probed and documented.

---

## Conclusion

The authoritative specifications for R1 (Worktree Isolation & Positioning Outcomes) and R2 (Review-Loop Circuit Breaker), acceptance criteria, predicate verification rules, and Limen agent protocol requirements have been extracted and mapped. The orchestrator can proceed with milestone construction using isolated worktrees under `/Users/4jp/Workspace/.worktrees/`, strict non-circular predicate receipts, and the MCP circuit breaker / loop quarantine architecture.

---

## Verification Method

1. **Verify Agent Docs & Task Status Vocabulary**:
   ```bash
   python3 scripts/check-agent-docs.py
   ```
2. **Verify Gate Registry & Resolver Selection**:
   ```bash
   python3 scripts/check-gates.py
   bash scripts/tests/verify-resolver.test.sh
   ```
3. **Verify Scoped Verification Logic**:
   ```bash
   python3 scripts/verify.py --list
   python3 scripts/verify.py --explain docs/positioning/offers/agentic-delivery-audit.md
   ```
4. **Verify Positioning Program Tooling Contracts**:
   ```bash
   bash scripts/run-pytest-hermetic.sh cli/tests/test_positioning_program.py cli/tests/test_positioning_p14_control_plane.py -q
   ```
5. **Verify MCP Server Contracts**:
   ```bash
   bash scripts/run-pytest-hermetic.sh cli/tests/test_mcp_server.py -q
   ```
