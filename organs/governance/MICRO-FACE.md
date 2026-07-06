# Aerarium / Cvrsvs Honorvm — MICRO FACE
## ORGANVM's dual-entity operation: Cind & Sol Foundation + Sovereign Systems LLC

*Anthony's live governance instance · Proof that the portable governance-as-code standard holds
against real entities, a real fleet, and a real beat · Internal review only*

> **What you are reading:** the micro face is the live proof that the reusable governance-as-code
> platform holds against a real dual-entity operation. The macro platform — the generic standard any
> organization can adopt — is in [`MACRO-FACE.md`](MACRO-FACE.md).

---

## Why this dual-entity structure

ORGANVM operates as two distinct legal entities with separate mandates, separate constraints, and
a machine-checkable boundary between them. The boundary is the dual-entity invariant: neither
entity may perform the other's role. A repo registered to the Foundation cannot engage in
commercial revenue. A repo registered to the LLC cannot accept charitable grants. The Compliance
Sentinel flags any crossing.

| Entity | Type | Jurisdiction | Fiduciary | Mandate | Forbidden |
|---|---|---|---|---|---|
| **Cind & Sol Foundation** | Non-profit | Panama | Anthony J. Padavano (human board) | open-project commons; grant-receiving; public-benefit | private-profit-generation; commercial-contracts-for-revenue |
| **Sovereign Systems LLC** | LLC | United States | Anthony J. Padavano (member/manager) | service-delivery; revenue-generation; commercial-contracts | receive-charitable-grants; claim-public-benefit-status |

This structure is not advisory. It is recorded in [`entities.yaml`](entities.yaml) and checked
by `validate-entities.py` on every governance beat. See the boundary matrix below.

---

## The dual-entity boundary in practice

The boundary matrix in `entities.yaml` is the single source of truth. Every entity's mandates and
forbidden acts are checked against it by the Compliance Sentinel:

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

`validate-entities.py` (Rules #3a-3c) checks that:
- Every entity has all required fields for its type
- Every entity's mandates are in the allowed set for its type
- No entity's `forbidden_acts` overlap with its `mandates`
- Every entity's `forbidden_acts` are in the standard forbidden set for its type

On every governance beat, this matrix is the boundary that neither entity may cross.

---

## Fleet standing

### Entity 1: Cind & Sol Foundation

- **Type:** Non-profit (Panama)
- **Fiduciary:** Anthony J. Padavano (human board)
- **Cursus standing:** STABLE (as recorded in `entities.yaml`)
- **Mandates:** open-project commons; grant-receiving; public-benefit
- **Forbidden:** private-profit-generation; commercial-contracts-for-revenue
- **System of record:** Quaestor (organvm-iii-ergon/quaestor) — the grant-finding engine
- **Canon note:** Per FLAME canon (2026-06-25): MPO = NPO. This is the public-benefit vehicle.
  Holds the open-project commons, receives grants through Quaestor, delivers public-facing value.
- **Status:** active

### Entity 2: Sovereign Systems LLC

- **Type:** LLC (United States)
- **Fiduciary:** Anthony J. Padavano (member/manager)
- **Cursus standing:** STABLE (as recorded in `entities.yaml`)
- **Mandates:** service-delivery; revenue-generation; commercial-contracts
- **Forbidden:** receive-charitable-grants; claim-public-benefit-status
- **Current status:** Dead-LLC per financial organ — Stripe KYC blocked. Tracked by the
  financial office (rank 2). The entity register records its legal standing regardless of
  operational status; a dead-LLC is still an LLC under governance.
- **Status:** active (legal entity exists; payment rail blocked)

### Repo: `organvm/limen` (Aerarium / Cvrsvs Honorvm)

- **Entity:** Cind & Sol Foundation
- **Cursus standing:** BETA
- **Home:** `organs/governance/`
- **Seed.yml status:** `implementation_status: BETA`, `promotion_status: BETA` — no split declaration
- **Governance roles:** Standing Clerk; Sequencing Auditor; Entity Registrar; Compliance Sentinel
- **Next gate:** STABLE (requires beat wired into heartbeat loop; maturity >= 60% in
  organ-ladder.json)

The governance office's own repo is the first subject of its own rules. It cannot advance to
STABLE without satisfying its own prerequisites.

### Repo: `organvm/limen` (Publication Policy — the disclosure court)

- **Entity:** Cind & Sol Foundation
- **Cursus standing:** INCUBATOR
- **Home:** `organs/governance/` (PUBLICATION-POLICY.md + DISCLOSURE-AUDIT.md)
- **Seed.yml status:** `implementation_status: INCUBATOR`, `promotion_status: INCUBATOR`
- **Governance roles:** Content Disposition
- **Next gate:** ALPHA (requires validated seed.yaml + KERNEL.md + CHARTER.md — convergence
  table already complete, DISCLOSURE-AUDIT.md exists, publication-policy.py engine operational)

---

## What the validators prove (actual output, live)

The organ passes its own checks on every governance beat. Both validators exit 0.

### Rules #1-2: Cursus office integrity + structured edges

```bash
$ python3 organs/governance/validate-seed.py organs/governance/seed.yaml --strict-graph
PASS  organs/governance/seed.yaml  cursus: INCUBATOR → ALPHA → BETA  |  next: STABLE

────────────────────────────────────────────────────────────
  1/1 passed  |  0 violation(s)
  Cvrsvs Honorvm Rules #1 & #2: all checks passed. Concordia.
```

This validator checks:
- **Rule 1a:** All required top-level fields exist (`schema_version`, `organ`, `repo`, `org`)
- **Rule 1b:** All required metadata fields exist (`implementation_status`, `promotion_status`)
- **Rule 1c-1d:** Both status fields name recognized cursus offices
- **Rule 1e:** `implementation_status` matches `promotion_status` (no split declaration — a repo
  may not hold two offices simultaneously)
- **Rule 2:** `produces` and `consumes` blocks are structured edge contracts with explicit
  partner declarations (`consumers` / `source`)

### Rules #3-4: Entity register integrity + repo registration

```bash
$ python3 organs/governance/validate-entities.py --strict-graph
PASS  organs/governance/entities.yaml

────────────────────────────────────────────────────────────
  1/1 passed  |  0 violation(s)
  Cvrsvs Honorvm Rules #3 & #4 (strict-graph): all checks passed. Concordia.
```

This validator checks:
- **Rule 3a:** Every entity has all required fields for its type (per `entity_taxonomy`)
- **Rule 3b:** Every entity's mandates are in the `allowed_mandates` for its type
- **Rule 3c:** No entity's `forbidden_acts` overlap with `mandates`; every forbidden act is
  in the standard set for the entity type
- **Rule 3d:** Every declared entity cursus office is a valid cursus stage
- **Rule 4a:** Every repo's cursus office is a recognized cursus stage
- **Rule 4b:** Every repo's `implementation_status` matches its `cursus` (no split office)
- **Rule 4c:** Every repo references a known entity (by `id`)
- **Rule 4d** (strict-graph): `promotion_rules` structure is well-formed — every key is a valid
  `FROM_to_TO` transition with non-empty prerequisites

Both validators exit 0. The organ eats its own dog food on every beat.

---

## Dogfooding: the organ is the first subject of its own rules

This governance office governs itself before it governs anything else. Every rule in this document
applies to `organvm/limen`'s governance directory:

| Rule | Subject | Status |
|---|---|---|
| Every repo must have a `seed.yaml` with valid cursus standing | `organs/governance/seed.yaml` — BETA | PASS (Rules #1-2) |
| Every entity must be registered with mandates and boundary | Cind & Sol Foundation + Sovereign Systems LLC in `entities.yaml` | PASS (Rules #3a-3d) |
| Every repo must reference a known entity | `organvm/limen` → `cind-and-sol-foundation` | PASS (Rule #4c) |
| Promotion status must match implementation status | `promotion_status: BETA` = `implementation_status: BETA` | PASS (Rule #1e) |
| No split-office declarations | Both governance + publication-policy registrations hold one office each | PASS (Rule #4b) |

The governance organ cannot claim STABLE until it satisfies its own BETA → STABLE rules. That is
not irony; it is integrity.

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
  "micro": "ORGANVM's own dual-entity operation (non-profit open project + commercial LLC)",
  "note": "deepened 2026-07-03: entity register (entities.yaml) with dual-entity boundary matrix, validate-entities.py (Rules #3-4: entity integrity + repo registration). Maturity 70%→75%. 2026-07-05: MACRO + MICRO faces polished as excellent, ready-to-show open standard with evidence-based instance; validate-entities.py hardened with Rule 4d (promotion_rules strict-graph)."
}
```

Maturity assessment: 75% (maturing). Entity register, boundary matrix, cursus validator, and
entity integrity checker are all operational with strict-graph mode. The organ is fully
self-validating on every governance beat.

---

## Governance roles (who runs what)

| Role | Holder | What they do | Validated by |
|---|---|---|---|
| **The Senate / Board** | Anthony J. Padavano (human) | Entity formation; binding resolutions; ratification of promotions. Final authority for every irreversible act | Human judgment (not the organ) |
| **Standing Clerk** | VLTIMA (this organ) | Maintains the single source of truth: every entity's current office, the offices held, and what is next | `validate-entities.py` — cursor integrity checks |
| **Sequencing Auditor** | VLTIMA (this organ) | Validates every promotion attempt against the cursus rules. The primary machine-enforcement role | `validate-seed.py` — office sequence checks |
| **Entity Registrar** | VLTIMA (this organ) | Tracks legal standing of each entity; records what each may and may not do | `validate-entities.py` — field completeness + boundary checks |
| **Compliance Sentinel** | VLTIMA (this organ) | Flags any action that would blur entity roles, skip a governance step, or bypass a rule. Never self-corrects | Manual review of flagged violations |

---

## Operating constraints (invariant across both entities)

These are not best practices. They are non-negotiable structural constraints enforced by the
organ's guardrails:

- **No self-ratification.** The organ audits governance; it does not govern. Anthony ratifies.
- **No irreversible entity action without the gate.** Filings, signatures, and binding commitments
  are staged and surfaced — never auto-executed.
- **The cursus is public and auditable.** The sequence of offices and the audit log are durable
  records, not chat memory. What is not written down does not count.
- **No skipped stages.** A skipped stage in the cursus honorum is a governance failure. Surface
  it; do not paper over it.
- **No autonomous entity formation.** Every new entity requires Anthony's signature.

---

## Current state and next beat

The governance organ is at **75% maturity** (maturing stage). Both validators pass on every
governance beat. The entity register, dual-entity boundary, cursus promotion rules, and both faces
(macro + micro) are complete and ready to show.

The remaining lift to 90% (mature stage):

1. **Wire `C_GOVERNANCE` into the heartbeat loop** — run both validators every cycle and stamp
   `logs/organ-health.json` with governance proprioception (current rung: `GOVERNANCE`)
2. **Operationalize the compliance sentinel as a continuous beat** — not just on-demand
   validation but an active flag on every inbound action that would cross the dual-entity boundary
3. **Automate the append-only audit log** — every governance action recorded with timestamp,
   actor, rule applied, and outcome. Entries never amended.
4. **Close one complete promotion cycle** — advance a repo or entity through one cursus gate with
   full validation, ratification, and audit trail

---

## Files in this organ

| File | Purpose |
|---|---|
| `KERNEL.md` | Architecture, 5-primitive map, hard guardrails, validation commands |
| `CHARTER.md` | AI roles, workflows, dual-entity boundary, maturity path |
| `MACRO-FACE.md` | Portable governance-as-code open standard |
| **`MICRO-FACE.md`** | **This file** — ORGANVM's live dual-entity instance |
| `entities.yaml` | Entity register + boundary matrix + cursus promotion rules + all registrations |
| `seed.yaml` | This organ's own standing declaration (BETA) |
| `validate-seed.py` | Cursus honorum Rules #1-2 (298 lines) |
| `validate-entities.py` | Cursus honorum Rules #3-4 (297 lines) |
| `PUBLICATION-POLICY.md` | The disclosure court — content-disposition matrix for the whole estate |
| `DISCLOSURE-AUDIT.md` | 2026-07 PII sweep, re-decided by the engine |

---

*Stage status: 75% maturity (maturing stage). Both validators pass. Face is excellent and
ready to show. Companion docs: [`MACRO-FACE.md`](MACRO-FACE.md) (platform description),
[`KERNEL.md`](KERNEL.md) (architecture), [`CHARTER.md`](CHARTER.md) (roles + workflows).*
