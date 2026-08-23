# Project: Platform Security & Permissions Census (Horizon 2)

## Architecture
- **Governance & Policy Layer (`institutio/`)**:
  - `github/access.yaml`: Partner partitioning, `role_ceiling: push`, banned admin grants, engine repo protection.
  - `github/estate.yaml`: App permissions least privilege, audience classification (`world`, `collab`, `self`).
  - `collaboration-operations/platform.yaml`: Operation-private records hub, zero external collaborator grants, dedicated actor partition lanes.
  - `governance/direct-main-writers.yaml`: Remote enforcement ruleset, zero bypass actors.
  - `governance/mail-tiers.yaml`: Subtractive 3-tier email authorization (`no_reply`, `hold`, `safe`).
  - `governance/outbound-effectors.yaml`: Proof-of-observation receipts for external side-effects (`mail.send`, `github.comment`).
  - `governance/covenant.yaml`: Single-writer covenants for memory and board projections.

- **Conduct Protocol RBAC Layer (`cli/src/limen/conduct/` & `web/worker/src/conduct/`)**:
  - `ConductRole`: `observer`, `conductor`, `executor`, `compatibility`.
  - Constant-time HMAC bearer authentication (`hmac.compare_digest`).
  - Broker method RBAC: `register`, `submit`, `split`, `claim`, `heartbeat`, `report`, `harvest`, `adopt`, `cancel`, `request_stop`.
  - Authority envelope attenuation (`AuthorityEnvelopeV1`): actions, repositories, path prefixes, external effects, delegation.

- **Notification & Effector Layer (`scripts/_notify.py`, `scripts/check-notify-gate.py`)**:
  - Effector chokepoint: `_root_may_speak` liveness check.
  - RFC 8785 canonical digest deduplication (`logs/vigilia/event-notifications.json`).
  - AST flow-sensitive bypass scanner (`check-notify-gate.py`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Conduct RBAC & Authority Attenuation | Strict method-level RBAC, path normalization (no `..`), harvest role checks | M1 | Survey 1, Survey 2 |
| 2 | Role Literals & Fallback Mechanics | Non-recursive scans, sensor role defaulting, role alias parity in gitvs/constellation | M1 | Survey 2 |
| 3 | Notification Authorization & Gates | Effector chokepoints, `_root_may_speak`, event dedup, AST bypass scan | M2 | Survey 1, Survey 3 |
| 4 | Outbound Effector & Governance Policies | Observation proof receipts, mail tiers, partner access ceilings (`push`), zero direct-main bypass | M2 | Survey 1, Survey 3 |
| 5 | Full Security Test Grid & Closeout | 25+ hermetic test suites, verify-scoped.sh, no-tasks-on-me.sh, credential-wall.py | M3 | Survey 1, 2, 3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: RBAC Matrix & Role Hardening | `cli/src/limen/conduct/`, `scripts/check-sensors.py`, `gitvs.py`, `constellation_registry_enumerator.py` | none | IN_PROGRESS |
| 2 | M2: Notification Auth & Policy Audit | `scripts/_notify.py`, `scripts/check-notify-gate.py`, `institutio/governance/`, `scripts/hooks/` | M1 | PLANNED |
| 3 | M3: Security Test Grid & Closeout | Full security test execution, scoped verification, zero dangling state | M2 | PLANNED |

## Interface Contracts
### ConductPrincipal ↔ Broker RBAC
- `ConductRole`: Literal["observer", "conductor", "executor", "compatibility"]
- `_require_role(principal, *roles)`: Raises `ConductConflict` if `principal.roles.isdisjoint(roles)`
- `AuthorityEnvelopeV1.validate_paths`: Must reject `..` and non-normalized relative path prefixes

### Sensor Role Defaulting
- `VALID_OMEGA_ROLE = {"input", "owner_receipt"}`
- Empty role string `""` or `None` consistently defaults to `"input"`

## Code Layout
- `cli/src/limen/conduct/`: Auth, models, broker, canary implementation
- `cli/tests/`: Security and permissions unit tests
- `institutio/`: Declarative governance, access, and security policies
- `scripts/`: Policy checkers, notification gates, and hook guards
- `web/worker/src/conduct/`: Cloudflare Worker conduct keeper implementation
