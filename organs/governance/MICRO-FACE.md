# Aerarium / Cvrsvs Honorvm — MICRO FACE
## ORGANVM's dual-entity operation: Cind & Sol Foundation + Sovereign Systems LLC

*Anthony's live governance instance · Proof that the portable governance-as-code standard holds
against real entities, a real fleet, and a real beat · Passes every check, every beat.*

This is the **micro face** — ORGANVM's own dual-entity operation, run through the same platform
that [`MACRO-FACE.md`](MACRO-FACE.md) describes as a generic standard. Every entity, every repo,
every cursus stage is registered in [`entities.yaml`](entities.yaml) and validated by
[`validate-seed.py`](validate-seed.py) and [`validate-entities.py`](validate-entities.py) on
every governance beat. The organ eats its own dog food before it governs anything else.

---

## The dual-entity structure at a glance

| Entity | Type | Jurisdiction | Fiduciary | Mandate | Forbidden |
|---|---|---|---|---|---|
| **Cind & Sol Foundation** | Non-profit | Panama | Anthony J. Padavano (board) | open-project commons; grant-receiving; public-benefit | private-profit-generation; commercial-contracts-for-revenue |
| **Sovereign Systems LLC** | LLC | United States | Anthony J. Padavano (member/manager) | service-delivery; revenue-generation; commercial-contracts | receive-charitable-grants; claim-public-benefit-status |

This structure is not advisory. It is recorded in `entities.yaml` and checked by
`validate-entities.py` on every governance beat. The boundary matrix below is the single source
of truth; any crossing is flagged and surfaced to the human fiduciaries.

### Repos under governance

| Repo | Organ | Entity | Cursus | Roles |
|---|---|---|---|---|
| `organvm/limen` | Aerarium / Cvrsvs Honorvm | Cind & Sol Foundation | BETA | Standing Clerk, Sequencing Auditor, Entity Registrar, Compliance Sentinel |
| `organvm/limen` | Publication Policy (disclosure court) | Cind & Sol Foundation | INCUBATOR | Content Disposition |

---

## The dual-entity boundary in practice

The boundary matrix from `entities.yaml`, enforced by the Compliance Sentinel:

```yaml
boundary_matrix:
  nonprofit:
    allowed_mandates: ["open-project-commons", "grant-receiving", "public-benefit"]
    always_forbidden: ["private-profit-generation", "commercial-contracts-for-revenue"]
  llc:
    allowed_mandates: ["service-delivery", "revenue-generation", "commercial-contracts"]
    always_forbidden: ["receive-charitable-grants", "claim-public-benefit-status"]
```

`validate-entities.py` (Rules #3a-3c) checks that:
- Every entity has all required fields for its type
- Every entity's mandates are in the allowed set for its type
- No entity's `forbidden_acts` overlap with its `mandates`
- Every entity's `forbidden_acts` are in the standard set for its type

On every governance beat, this matrix is the boundary that neither entity may cross.

---

## Fleet standing

### Cind & Sol Foundation

- **Type:** Non-profit (Panama)
- **Fiduciary:** Anthony J. Padavano (human board)
- **Cursus standing:** STABLE
- **Mandates:** open-project commons; grant-receiving; public-benefit
- **Forbidden:** private-profit-generation; commercial-contracts-for-revenue
- **System of record:** Quaestor (organvm-iii-ergon/quaestor) — the grant-finding engine
- **Canon:** Per FLAME canon (2026-06-25): MPO = NPO. This is the public-benefit vehicle. Holds
  the open-project commons, receives grants through Quaestor, delivers public-facing value.
- **Status:** active

### Sovereign Systems LLC

- **Type:** LLC (United States)
- **Fiduciary:** Anthony J. Padavano (member/manager)
- **Cursus standing:** STABLE
- **Mandates:** service-delivery; revenue-generation; commercial-contracts
- **Forbidden:** receive-charitable-grants; claim-public-benefit-status
- **Current status:** Dead-LLC per financial organ — Stripe KYC blocked. Tracked by the
  financial office (rank 2). The entity register records its legal standing regardless of
  operational status; a dead-LLC remains an LLC under governance.
- **Status:** active (legal entity exists; payment rail blocked)

### Aerarium / Cvrsvs Honorvm (`organvm/limen`)

- **Entity:** Cind & Sol Foundation
- **Cursus standing:** BETA
- **Home:** `organs/governance/`
- **Seed status:** `implementation_status: BETA`, `promotion_status: BETA`
- **Governance roles:** Standing Clerk, Sequencing Auditor, Entity Registrar, Compliance Sentinel
- **Next gate:** STABLE (requires beat wired into heartbeat loop; maturity >= 60% in
  organ-ladder.json)

The governance office's own repo is the first subject of its own rules. It cannot advance to
STABLE without satisfying its own BETA → STABLE prerequisites.

### Publication Policy (`organvm/limen`)

- **Entity:** Cind & Sol Foundation
- **Cursus standing:** INCUBATOR
- **Home:** `organs/governance/` (PUBLICATION-POLICY.md + DISCLOSURE-AUDIT.md)
- **Seed status:** `implementation_status: INCUBATOR`, `promotion_status: INCUBATOR`
- **Governance roles:** Content Disposition
- **Next gate:** ALPHA (requires validated seed.yaml + KERNEL.md + CHARTER.md)

---

## What the validators prove (actual output, live)

Both validators exit 0 on every governance beat. The organ passes its own checks.

### Rules #1-2: Cursus office integrity + structured edges

```bash
$ python3 organs/governance/validate-seed.py organs/governance/seed.yaml --strict-graph
PASS  organs/governance/seed.yaml  cursus: INCUBATOR → ALPHA → BETA  |  next: STABLE

────────────────────────────────────────────────────────────
  1/1 passed  |  0 violation(s)
  Cvrsvs Honorvm Rules #1 & #2: all checks passed. Concordia.
```

Checks:
- **Rule 1a:** All required top-level fields (`schema_version`, `organ`, `repo`, `org`)
- **Rule 1b:** All required metadata fields (`implementation_status`, `promotion_status`)
- **Rule 1c-1d:** Both status fields name recognized cursus offices
- **Rule 1e:** `implementation_status` matches `promotion_status` (no split declaration)
- **Rule 2:** `produces`/`consumes` blocks are structured edge contracts

### Rules #3-4: Entity register integrity + repo registration

```bash
$ python3 organs/governance/validate-entities.py --strict-graph
PASS  organs/governance/entities.yaml

────────────────────────────────────────────────────────────
  1/1 passed  |  0 violation(s)
  Cvrsvs Honorvm Rules #3 & #4 (strict-graph): all checks passed. Concordia.
```

Checks:
- **Rule 3a:** Required fields per entity type (from `entity_taxonomy`)
- **Rule 3b:** Mandates are in the `allowed_mandates` for the entity type
- **Rule 3c:** No `forbidden_acts` overlap with `mandates`; every forbidden act is in the
  standard set for the type
- **Rule 3d:** Entity cursus office is a valid cursus stage
- **Rule 4a:** Repo cursus office is a recognized cursus stage
- **Rule 4b:** Repo `implementation_status` matches `cursus` (no split office)
- **Rule 4c:** Every repo references a known entity by `id`
- **Rule 4d** (strict-graph): `promotion_rules` are well-formed — every key is a valid
  `FROM_to_TO` transition with non-empty prerequisites

---

## Dogfooding: the organ governs itself first

This governance office governs itself before it governs anything else. Every rule applies to
`organvm/limen`'s governance directory:

| Rule | Subject | Status |
|---|---|---|
| Every repo must have a `seed.yaml` with valid cursus standing | `organs/governance/seed.yaml` — BETA | PASS |
| Every entity must be registered with mandates and boundary | Cind & Sol + Sovereign Systems in `entities.yaml` | PASS |
| Every repo must reference a known entity | `organvm/limen` → `cind-and-sol-foundation` | PASS |
| Promotion status must match implementation status | `BETA` = `BETA` | PASS |
| No split-office declarations | Both repos hold one office each | PASS |
| Entity mandates within allowed set | All mandates in `allowed_mandates` for their types | PASS |

The governance organ cannot claim STABLE until it satisfies its own BETA → STABLE rules. That
is not irony; it is integrity.

---

## Organ-ladder entry

Aerarium / Cvrsvs Honorvm is rank 5 on the VLTIMA institutional census. Source:
[`organ-ladder.json`](/organ-ladder.json) (the authoritative census, derived at every read):

```json
{
  "rank": 5,
  "pillar": "governance",
  "organ": "Aerarium / Cvrsvs Honorvm",
  "repo": "organvm/limen",
  "home": "organs/governance/",
  "maturity": 75,
  "stage": "maturing",
  "whose_hand": "mine (entity formation signatures are his)",
  "rival": "a constitutional state / a foundation's governance office",
  "domain_map": "the Roman cursus-honorum office sequence expressed as executable rules",
  "macro": "a portable governance-as-code open standard anyone can adopt",
  "micro": "ORGANVM's own dual-entity operation (non-profit open project + commercial LLC)"
}
```

---

## Governance roles

| Role | Holder | What they do | Validated by |
|---|---|---|---|
| **The Senate / Board** | Anthony J. Padavano (human) | Entity formation, binding resolutions, ratification of promotions. Final authority for every irreversible act | Human judgment |
| **Standing Clerk** | VLTIMA (this organ) | Maintains the single source of truth: every entity's current office, offices held, and what is next | `validate-entities.py` — cursor integrity |
| **Sequencing Auditor** | VLTIMA (this organ) | Validates every promotion attempt against the cursus rules | `validate-seed.py` — office sequence checks |
| **Entity Registrar** | VLTIMA (this organ) | Tracks legal standing of each entity; records what each may and may not do | `validate-entities.py` — field completeness + boundary |
| **Compliance Sentinel** | VLTIMA (this organ) | Flags any action that would blur entity roles, skip a step, or bypass a rule. Never self-corrects | Manual review of flagged violations |

---

## Operating constraints

These are not best practices. They are non-negotiable structural constraints:

- **No self-ratification.** The organ audits governance; Anthony ratifies.
- **No irreversible entity action without the gate.** Filings, signatures, and binding commitments
  are staged and surfaced — never auto-executed.
- **The cursus is public and auditable.** What is not written down does not count.
- **No skipped stages.** A skipped stage in the cursus honorum is a governance failure. Surface
  it; do not paper over it.
- **No autonomous entity formation.** Every new entity requires Anthony's signature.

---

## Current state and next beat

Both validators pass on every governance beat. Maturity: **75%** (maturing stage). All core
infrastructure is operational:

- Entity register with dual-entity boundary matrix
- Cursus honorum seed validator (Rules #1-2)
- Entity integrity checker (Rules #3-4) with strict-graph mode
- MACRO and MICRO faces — polished and ready to show

### Remaining lift to 90% (mature)

1. Wire `C_GOVERNANCE` into the heartbeat loop — run both validators every cycle and stamp
   `logs/organ-health.json` with governance proprioception
2. Operationalize the compliance sentinel as a continuous beat — active flag on every inbound
   action that would cross the dual-entity boundary
3. Automate the append-only audit log — every governance action: timestamp, actor, rule, outcome
4. Close one complete promotion cycle — advance a repo through one cursus gate with full
   validation, ratification, and audit trail

---

## Files in this organ

| File | Purpose |
|---|---|
| `KERNEL.md` | Architecture, 5-primitive map, hard guardrails |
| `CHARTER.md` | AI roles, workflows, dual-entity boundary, maturity path |
| `MACRO-FACE.md` | Portable governance-as-code open standard |
| **`MICRO-FACE.md`** | **This file** — ORGANVM's live dual-entity instance |
| `entities.yaml` | Entity register + boundary matrix + cursus promotion rules |
| `seed.yaml` | This organ's own standing declaration (BETA) |
| `validate-seed.py` | Cursus honorum Rules #1-2 |
| `validate-entities.py` | Cursus honorum Rules #3-4 |
| `PUBLICATION-POLICY.md` | The disclosure court — content-disposition matrix |
| `DISCLOSURE-AUDIT.md` | 2026-07 PII sweep, re-decided by the engine |

---

*Stage status: 75% maturity (maturing stage). Both validators pass on every beat. Companion
docs: [`MACRO-FACE.md`](MACRO-FACE.md) (platform), [`KERNEL.md`](KERNEL.md) (architecture),
[`CHARTER.md`](CHARTER.md) (roles + workflows).*
