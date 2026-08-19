# Project: VLTIMA 5-Primitive Kernel Mapping & Organ Execution

## Architecture
The system consists of two primary organ domains and ecosystem governance integration:
1. **Representation Organ (`organs/representation/`)**:
   - Implements the VLTIMA 5-primitive kernel (`Member · Mandate · Standing · Standard · Governance`).
   - Powers career and literary opportunity intake, candidate intake, multi-mode packet generation (11 render modes), authority packets, publication readiness audit, and delivery execution adapters (`direct_email`, `local_outbox`, `submission_form`).
   - Deterministic validation entrypoint: `organs/representation/validate-representation.py`.
2. **Observation Organ (`organs/observation/`)**:
   - Implements the VLTIMA 5-primitive kernel across 3 facets: OBSERVATORY (Rank 15: legibility & field analysis), BIFRONS (Rank 16: star ↔ contribution portal), and DECORVM (Rank 17: surface quality federator).
   - Unified telemetry aggregation engine (`cli/src/limen/observation/` + `scripts/observation-feed.py`) collecting system vitals (`limen.vigilia.vitals`), Bifrons portal status (`scripts/bifrons-organ.py`), and Observatory briefs (`cli/src/limen/observatory/brief.py`).
   - Emits schema-checked records (`limen.observation.feed.v1`) to `logs/observation/feed.jsonl` and `logs/observation/feed-latest.json`.
   - Deterministic validation entrypoint: `organs/observation/validate-observation.py`.
3. **Governance & Verification Infrastructure (`institutio/governance/`, `scripts/`)**:
   - `gates.yaml`: Declarative gate registry checked by `scripts/verify-scoped.sh` and `scripts/check-gates.py`.
   - `sensors.yaml`: Heartbeat sensors for scheduled telemetry.
   - `check-agent-docs.py`: Doc drift and canonical state rules.
   - `no-tasks-on-me.sh` & `credential-wall.py`: Lifecycle closure and credential security.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Representation Bare Validator | `validate-representation.py` defaults to `--fleet` and exits 0 deterministically | M1 | R1, Explorer 1 |
| 2 | Representation 5-Primitive Mapping | Complete 5-primitive schema (`representation.v3`), records, opportunities, approvals | M1 | R1, Explorer 1 |
| 3 | Career & Opportunity Pipeline | Opportunity ingestion, candidate intake, 11 packet modes, publication readiness, stack generation | M1 | R1, Explorer 1 |
| 4 | Observation Feed Schema | Canonical schema `limen.observation.feed.v1` for telemetry records | M2 | R2, Explorer 2 |
| 5 | Observation Telemetry Collector | Self-feeding collector aggregating Vitals, Bifrons, and Observatory into `logs/observation/` | M2 | R2, Explorer 2 |
| 6 | Observation Organ Validator | `validate-observation.py` enforcing Rules #1–6 (Standing, Human Gate, 5-Primitive, Evidence, No-Overreach, Feed Schema) | M2 | R2, Explorer 2 |
| 7 | Governance Gates & Sensors | Register representation and observation gates/sensors in `gates.yaml` and `sensors.yaml` | M2 | R1, R2, Explorer 1, 2, 3 |
| 8 | Whole Repository & Protocol Verification | All acceptance criteria verified (representation validation, observation feed, verify-scoped, check-agent-docs, no-tasks-on-me, credential-wall) | M3 | AC, Explorer 3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Representation Organ Vertical Slice & Validation | `organs/representation/validate-representation.py`, `organs/representation/representation_substrate.py`, validation & tests | none | DONE |
| M2 | Observation Organ Autonomous Self-Feed Loop | `cli/src/limen/observation/`, `scripts/observation-feed.py`, `organs/observation/validate-observation.py`, `sensors.yaml`, `gates.yaml`, tests | M1 | READY |
| M3 | E2E Testing & Acceptance Criteria Verification | E2E test suite, scoped verification, doc check, lifecycle closure, terminal verification | M1, M2 | PLANNED |

## Interface Contracts
### Representation Substrate ↔ Ecosystem
- Validator entrypoint: `python3 organs/representation/validate-representation.py [--fleet] [--quiet]`
- Schema: `representation.v3`
- Mode renderers: `packet`, `authority-packet`, `literary-packet`, `publication-readiness`, `publication-stack`, `handoff-audit`
- Gate in `gates.yaml`: `representation-records`, `representation-substrate-test`

### Observation Telemetry ↔ Ecosystem
- Feed schema: `limen.observation.feed.v1`
  - Fields: `schema`, `observed_at`, `source`, `vitals` (level, action, load_per_core, swap_used_gib, ram_gib), `bifrons` (stars, dossiers, resonance_edges, awaiting_gate), `observatory` (hero, external_gaps, internal_gaps, top_mechanism), `status` (ok, degraded, shed)
- Output destinations: `logs/observation/feed.jsonl` (append-only), `logs/observation/feed-latest.json`
- Collector entrypoint: `python3 scripts/observation-feed.py [--emit] [--check] [--json]`
- Validator entrypoint: `python3 organs/observation/validate-observation.py [--fleet] [--quiet]`
- Gate in `gates.yaml`: `observation-records`, `observation-feed-test`

## Code Layout
- Representation Organ: `organs/representation/`
- Observation Organ: `organs/observation/`
- Observation CLI/Package: `cli/src/limen/observation/`
- Observation Scripts: `scripts/observation-feed.py`
- Tests: `cli/tests/test_representation_substrate.py`, `cli/tests/test_observation_feed.py`
- Governance: `institutio/governance/gates.yaml`, `institutio/governance/sensors.yaml`
