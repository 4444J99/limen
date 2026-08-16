# Project: PSP Omega Recovery Expert-Positioning Program

## Architecture
The PSP Omega Recovery program orchestrates autonomous execution of expert-positioning outcomes across isolated topic worktrees while enforcing a review-loop circuit breaker to prevent unbounded PR review ping-pong.

### Topology & Isolation
- **Root Directory**: `/Users/4jp/Workspace/limen`
- **Worktree Base**: `/Users/4jp/Workspace/.worktrees/`
- **Autonomous Lanes**:
  1. `limen-psp-omega-lane-circuit-breaker`: Resolution of quarantined C04 (#2414) and C05 (#139) PR review loops via exact-tree verification.
  2. `limen-psp-omega-lane-identity-offer`: Ratification and durable receipt generation for Canonical Identity & 4-tier Offer ladder (PSP-C03 / PSP-P03 & PSP-P04).
  3. `limen-psp-omega-lane-proof-architecture`: Production of Flagship Proof set, Case-Study architecture, and proof preflight contracts (PSP-C04 / PSP-P05 & PSP-P06).
  4. `limen-psp-omega-lane-portfolio-front-door`: Implementation and verification of public front doors, portfolio information architecture, and capture routing (PSP-C06 / PSP-P07).

### Protocol & Gate Enforcement
- **Conduct Broker**: Distributed leases and work packets managed via `conduct_*` tools and TABVLARIVS.
- **Predicates Single Source of Truth**: `institutio/governance/gates.yaml`.
- **Exact-Tree Scoped Verification**: `scripts/verify-scoped.sh` and `scripts/verify.py`.
- **Durable Receipts**: `limen.positioning_work_receipt.v1` and `limen.positioning_phase_receipt.v1` recorded under `docs/receipts/positioning/` and marked comments.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Worktree Isolation | Transactional setup of dedicated topic worktrees under `/Users/4jp/Workspace/.worktrees/` | M2 | ORIGINAL_REQUEST §R1 |
| 2 | Review-Loop Circuit Breaker | Quarantine C04 (#2414) and C05 (#139) review loops and enforce single-push exact-tree resolution | M1 | ORIGINAL_REQUEST §R2 |
| 3 | C04 Defensive Guard | Fix P2 dictionary lookup guard in `scripts/positioning-proof-preflight.py:973` | M1 | Survey 1 (PR #2414) |
| 4 | C05 Schema Alignment | Align 5 template & finding schema fields in `collaboration-operations-platform` validator | M1 | Survey 1 (PR #139) |
| 5 | Synthetic Receipt Sync | Update stale receipt hash in `docs/receipts/positioning/preflights/` restoring 100% test pass | M1 | Survey 2 (`test_positioning_c10_readiness.py`) |
| 6 | Canonical Identity Contracts | Ratify Production-Systems Architect narrative and Level-1/2/3 progressive disclosure | M3 | ORIGINAL_REQUEST §R1, PSP-C03 |
| 7 | 4-Tier Offer Ladder | Validate Audit ($5k–$15k), Install ($25k–$60k), Retainer ($10k–$25k/mo), and Partnership offers | M3 | ORIGINAL_REQUEST §R1, PSP-P04 |
| 8 | Identity Durable Receipts | Emit and verify `limen.positioning_work_receipt.v1` for P03/P04 leaves | M3 | ORIGINAL_REQUEST §Acceptance |
| 9 | Flagship Proof Architecture | Select and validate 3 flagship proof candidates (Limen, Public-Records, AI Chat Exporter) | M4 | ORIGINAL_REQUEST §R1, PSP-C04 |
| 10 | Case-Study Template & Contract | Formalize Level-2 case-study template and validate `psp-c04-proof-contract.json` | M4 | ORIGINAL_REQUEST §R1, PSP-P05/P06 |
| 11 | Proof Durable Receipts | Emit and verify `limen.positioning_work_receipt.v1` for proof classes | M4 | ORIGINAL_REQUEST §Acceptance |
| 12 | Public Front Door & IA | Materialize `_frontdoor.md`, `_capture.md`, and estate map in `organvm/.github` | M5 | ORIGINAL_REQUEST §R1, PSP-C06 |
| 13 | Visual Direction Framing | Document and freeze 3 digest-pinned visual mockup options awaiting human selection gate | M5 | Survey 2, PSP-P07 |
| 14 | Front Door Durable Receipts | Emit and verify `limen.positioning_work_receipt.v1` for public surface leaves | M5 | ORIGINAL_REQUEST §Acceptance |
| 15 | E2E Testing Suite | Multi-tier opaque-box test runner validating all R1/R2 requirements (Tiers 1–4) | E2E Track | Project Pattern |
| 16 | Adversarial Hardening | White-box Tier 5 challenger verification and edge-case stress testing | Final M | Project Pattern |
| 17 | Terminal Omega Proof | Two-pass convergence verification via `positioning-program.py --omega --require-two-pass` | Final M | Survey 1/3 (PSP-C12) |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Test harness & test suite (Tiers 1–4) for R1, R2, and positioning criteria | None | IN_PROGRESS |
| 1 | Review-Loop Circuit Breaker & Quarantine | Quarantine C04 (#2414) & C05 (#139), apply single-push exact-tree fixes, sync synthetic receipt | None | PLANNED |
| 2 | Worktree Isolation & Topic Branch Setup | Initialize topic worktrees under `/Users/4jp/Workspace/.worktrees/` | None | PLANNED |
| 3 | Canonical Identity & Offer Delivery | Validate identity narrative, 4-tier offers, and record durable receipts | M2 | PLANNED |
| 4 | Proof & Case-Study Architecture | Validate flagship proof set, case-study template, preflight contracts, and record durable receipts | M2 | PLANNED |
| 5 | Public Portfolio & Front Door Delivery | Materialize public front doors, capture funnel, link surfaces, and record durable receipts | M2 | PLANNED |
| Final | 100% E2E Verification & Omega Proof | Pass 100% E2E tests, execute Tier 5 adversarial hardening, and verify terminal Omega proof | M1, M3, M4, M5, E2E | PLANNED |

---

## Interface Contracts
### `limen_mcp` ↔ `conduct_broker`
- `trip_circuit_breaker()`: Sets system offline state in `.mcp_state.json`, blocking runaway loops.
- `reset_circuit_breaker()`: Restores online state for healthy operations.
- `conduct_submit(packet)`: Submits `WorkPacketV1` reserving budget and lane lease.
- `conduct_split(parent, children)`: Reserves child capacity before native subagent fanout.

### `positioning-program` ↔ `receipt_verifier`
- Leaf receipt format: `limen.positioning_work_receipt.v1`
- Phase receipt format: `limen.positioning_phase_receipt.v1`
- Command: `python3 scripts/positioning-program.py --verify-work <WORK-ID>` (bare, non-circular)
- Terminal check: `python3 scripts/positioning-program.py --omega --require-two-pass`

---

## Code Layout
- `institutio/positioning/`: Program manifest (`program.yaml`), commercial contract (`commercial-contract.yaml`), GitHub issue mapping (`github-map.json`).
- `docs/positioning/`: Architecture docs, identity narratives, claims ledger, estate classification, front door specs.
- `docs/positioning/offers/`: Offer specifications, decision records, pricing anchors, and validators.
- `docs/positioning/proof/`: Proof preflight contracts, flagship proof definitions, case-study templates.
- `docs/positioning/visual-directions/`: Digest-pinned visual mockups.
- `docs/receipts/positioning/`: Relays, preflights, and durable receipt storage.
- `scripts/`: Program runner (`positioning-program.py`), gate verifiers (`verify.py`, `verify-scoped.sh`, `verify-whole.sh`), preflight scripts.
- `/Users/4jp/Workspace/.worktrees/`: Isolated worktrees for autonomous topic branches.
