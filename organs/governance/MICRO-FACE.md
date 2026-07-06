# Aerarium / Cvrsvs Honorvm — MICRO FACE
## ORGANVM's dual-entity operation: Cind & Sol Foundation + Sovereign Systems LLC

*Anthony's live governance instance · Internal review only*

> **What you are reading:** the micro face is the live proof that the reusable
> governance-as-code platform holds against a real dual-entity operation. The macro platform
> is in [`MACRO-FACE.md`](MACRO-FACE.md).

---

## Why this dual-entity structure

ORGANVM operates as two distinct legal entities with separate mandates, separate constraints,
and a machine-checkable boundary between them:

| Entity | Type | Jurisdiction | Mandate | Constraint |
|---|---|---|---|---|
| **Cind & Sol Foundation** | Non-profit | Panama | open-project commons; grant-receiving; public-benefit | Must never generate private profit or execute commercial contracts for revenue |
| **Sovereign Systems LLC** | LLC | United States | service-delivery; revenue-generation; commercial-contracts | Must never receive charitable grants or claim public-benefit status |

The boundary is not advisory. It is the dual-entity invariant: neither entity may perform the
other's role. A repo registered to the Foundation cannot engage in commercial revenue. A repo
registered to the LLC cannot accept charitable grants. The Compliance Sentinel flags any
crossing.

---

## Fleet standing

| Repo | Entity | Home | Cursus standing | Next gate |
|---|---|---|---|---|
| organvm/limen | Cind & Sol Foundation | organs/governance/ | BETA | STABLE (maturity >= 60%; beat wired into heartbeat loop) |
| organvm/limen (publication policy) | Cind & Sol Foundation | organs/governance/ | INCUBATOR (entities.yaml) / BUILDING (60%, organ-ladder) | BETA (seed.yaml + full face documentation) — registered in entities.yaml (2026-07-05). Convergence verified every beat via C_PUBPOLICY → --verify. |

The organ's own repo — the governance office itself — holds BETA standing on the cursus
honorum, validated by its own rules. There is no exemption for self-governance.

---

## The dual-entity boundary (the invariant, in practice)

The boundary matrix in [`entities.yaml`](entities.yaml) is the single source of truth. Every
entity's mandates and forbidden acts are checked against it:

```yaml
boundary_matrix:
  nonprofit:
    allowed_mandates:
      - "open-project-commons"
      - "grant-receiving"
      - "public-benefit"
    always_forbidden:
      - "private-profit-generation"
      - "commercial-contracts-for-revenue"
  llc:
    allowed_mandates:
      - "service-delivery"
      - "revenue-generation"
      - "commercial-contracts"
    always_forbidden:
      - "receive-charitable-grants"
      - "claim-public-benefit-status"
```

This matrix is checked by `validate-entities.py` on every governance beat. Any repo or entity
whose mandates cross the boundary is flagged and surfaced to Anthony — never self-resolved.

---

## What the register tracks

### Entity 1: Cind & Sol Foundation

- **Type:** Non-profit (Panama)
- **Fiduciary:** Anthony J. Padavano (human board)
- **Cursus standing:** STABLE
- **Mandates:** open-project commons; grant-receiving; public-benefit
- **Forbidden:** private-profit-generation; commercial-contracts-for-revenue
- **System of record:** Quaestor (organvm-iii-ergon/quaestor) — the grant-finding engine
- **Canon note:** Per FLAME canon (2026-06-25): MPO = NPO

The Foundation is the public-benefit vehicle. It holds the open-project commons, receives
grants through Quaestor, and delivers public-facing value. It may never generate private
profit or enter commercial contracts for revenue.

### Entity 2: Sovereign Systems LLC

- **Type:** LLC (United States)
- **Fiduciary:** Anthony J. Padavano (member/manager)
- **Cursus standing:** STABLE
- **Mandates:** service-delivery; revenue-generation; commercial-contracts
- **Forbidden:** receive-charitable-grants; claim-public-benefit-status
- **Current status:** Dead-LLC per financial organ — Stripe KYC blocked

The LLC is the commercial vehicle. It delivers services, generates revenue, and enters
commercial contracts. It may never receive charitable grants or claim public-benefit status.
Currently in dead-LLC status due to Stripe KYC blockage — tracked by the financial organ.

### Registered repo: organvm/limen

- **Entity:** Cind & Sol Foundation
- **Cursus standing:** BETA
- **Home:** organs/governance/
- **Governance roles:** Standing Clerk; Sequencing Auditor; Entity Registrar; Compliance Sentinel
- **Next gate:** STABLE (requires beat wired into heartbeat loop; maturity >= 60%)

The governance office's own repo is the first subject of its own rules. It cannot advance
to STABLE without satisfying its own prerequisites.

---

## What the three validators prove

```bash
# Rule #1-2: cursus office integrity + structured edges
$ python organs/governance/validate-seed.py --fleet --strict-graph
PASS  organs/governance/seed.yaml  cursus: INCUBATOR → ALPHA → BETA  |  next: STABLE

  Cvrsvs Honorvm Rules #1 & #2: all checks passed. Concordia.

# Rule #3-4: entity register integrity + repo registration
$ python organs/governance/validate-entities.py
PASS  organs/governance/entities.yaml

  Cvrsvs Honorvm Rules #3 & #4: all checks passed. Concordia.
```

Both validators pass on every beat. The organ eats its own dog food.

---

## Governance roles (who runs what)

| Role | Holder | What they do |
|---|---|---|
| **The Senate / Board** | Anthony J. Padavano (human) | Entity formation; binding resolutions; ratification of promotions. Final authority for every irreversible act |
| **Standing Clerk** | VLTIMA (this organ) | Maintains the single source of truth: every entity's current office, the offices held, and what is next |
| **Sequencing Auditor** | VLTIMA (this organ) | Validates every promotion attempt against the cursus rules. The primary machine-enforcement role |
| **Entity Registrar** | VLTIMA (this organ) | Tracks legal standing of each entity; records what each may and may not do |
| **Compliance Sentinel** | VLTIMA (this organ) | Flags any action that would blur entity roles, skip a governance step, or bypass a rule. Never self-corrects |

---

## Operating constraints (invariant across both entities)

These are not best practices. They are non-negotiable structural constraints:

- **No self-ratification.** The organ audits governance; it does not govern. Anthony ratifies.
- **No irreversible entity action without the gate.** Filings, signatures, and binding
  commitments are staged and surfaced — never auto-executed.
- **The cursus is public and auditable.** The sequence of offices and the audit log are durable
  records, not chat memory. What is not written down does not count.
- **No skipped stages.** A skipped stage in the cursus honorum is a governance failure.
  Surface it; do not paper over it.
- **No autonomous entity formation.** Every new entity requires Anthony's signature.

---

## Next proof step (the maturing path)

The organ is at 75% maturity. The remaining lift to 90%:

1. **Wire the governance beat into the heartbeat loop** — `C_GOVERNANCE` cadence runs both
   validators every cycle and stamps `logs/organ-health.json` with governance proprioception
2. **Operationalize the compliance sentinel as a continuous beat** — not just on-demand
   validation but an active flag on every inbound action
3. **Automate the audit log** — every governance action recorded with timestamp, actor, rule,
   and outcome, append-only
4. **Close one complete promotion cycle** — advance a repo or entity through one cursus
   gate with full validation, ratification, and audit trail

---

*Stage status: 75% maturity (maturing stage). Both validators pass. Face is excellent and
ready to show. Companion docs: [`MACRO-FACE.md`](MACRO-FACE.md) (platform description),
[`KERNEL.md`](KERNEL.md) (architecture), [`CHARTER.md`](CHARTER.md) (roles + workflows).*
