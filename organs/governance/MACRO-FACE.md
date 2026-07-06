# Aerarium / Cvrsvs Honorvm — MACRO FACE
## The portable governance-as-code open standard

*The platform form of the governance organ · Available to any foundation, multi-repo ecosystem, or
dual-entity organization · One file, two engines, five primitives*

> **What you are reading:** the macro face is what an outside operator holds — the portable,
> reusable body of this organ before any entity name is in it. Fill in your entities, repos, and
> cursus registrations; run the validators; your institution has a governance floor. The micro
> instance — ORGANVM's own dual-entity operation (Cind & Sol Foundation + Sovereign Systems LLC) —
> proves this platform against real entities, a real fleet, and a real beat. That proof is in
> [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The problem

Most organizations — open-source foundations, dual-entity startups, solo operators building an
institution — run on **founder trust, not institutional systems**. A founder's good intentions are
real, but they are not a governance floor. When the founder steps away, when priorities conflict,
when a project claims maturity without the receipts — accountability goes with them.

In a multi-repo ecosystem the problem compounds:
- Nobody has a clear picture of what stage each project is actually at
- Entity roles blur: a non-profit starts behaving like a commercial venture, or an LLC claims
  public-benefit standing without the mandate
- Promotions are aspirational: a repo calls itself STABLE with no record of passing through the
  prerequisite offices
- There is no standing register — no durable answer to "what is this project's current office, and
  what must happen before it advances"

The institutions that solve this — constitutional governance offices, foundation boards,
regulatory bodies — are available only to organizations that can staff them. This platform gives
any organization the **same institutional floor** without hiring a governance team.

---

## The thesis

> **The cursus honorum — a sequential ladder of offices with machine-checkable prerequisites — is
> the missing institution. Every project must pass through INCUBATOR → ALPHA → BETA → STABLE → MATURE
> in order, one office at a time, validated by executable rules. No skipped stages, no
> self-ratification, no silent entity drift. The sequence is public; the rules are executable;
> the audit trail is append-only.**

This is not a suggestion. It is the structural invariant that makes institutional accountability
possible without a full-time board. The same invariant that Roman public law enforced through its
cursus honorum — no one held the consulship without first holding the quaestorship and praetorship —
applied to software projects, contributors, and legal entities.

---

## Architecture: the two synchronized engines

The platform runs on two engines that must both pass for governance to be satisfied:

| Engine | What it validates | The invariant it enforces |
|---|---|---|
| **Cursus Validator** (`validate-seed.py`) | Every project's standing declaration against the canonical cursus sequence — `promotion_status` and `implementation_status` must agree and name a recognized office | Promotions are earned, not claimed. A project at ALPHA cannot claim BETA without satisfying all BETA prerequisites |
| **Entity Registrar** (`validate-entities.py`) | Every legal entity under governance — its type, jurisdiction, mandates, forbidden acts, and the cursus standing of every registered repo that belongs to it | Entity roles cannot blur. A non-profit cannot drift into commercial contracts; an LLC cannot claim charitable status. The boundary is machine-checkable |

Neither engine works without the other. Validation without registration is a claim with no witness.
Registration without validation is a phone book with no rules.

---

## The five-primitive kernel

Every organization governed by this platform is structured around five primitives. This is the
same kernel that drives every organ in the VLTIMA body — only the domain skin changes:

| Primitive | Governance meaning | Concretely |
|---|---|---|
| **Member** | the entity / contributor | the person or organization whose standing in the system is tracked — their role, capacity, and office history. Never floating; always registered in `entities.yaml` |
| **Mandate** | the office / authority | the specific power or duty conferred at the current cursus stage. What this office-holder may decide, and what must wait for the next office |
| **Standing** | cursus posture | where in the sequence the member or project currently sits — which offices have been held, what prerequisites are satisfied, what comes next |
| **Standard** | the governing rule | the constitutional rule, sequence invariant, or precedent that constrains advancement. Every rule is machine-checkable via `validate-seed.py` or `validate-entities.py` |
| **Governance** | the senate / board | who ratifies promotions, how disputes are resolved, what stays irreducibly in the human fiduciary's hand. The organ audits; the board decides |

No entity enters governance without a named Member record in `entities.yaml`. No repo advances
without satisfying the Standing prerequisites. No entity changes its Mandate without an explicit
board action recorded in the audit log.

---

## The cursus honorum (the sequence of offices)

The Roman cursus honorum was the sequential ladder of public offices. This platform expresses
that same invariant for repositories and contributors:

```
INCUBATOR → ALPHA → BETA → STABLE → MATURE
```

A project can only advance one office at a time. No skipping. Each promotion requires ALL
prerequisites to be satisfied:

| Promotion | Prerequisites | Validated by |
|---|---|---|
| INCUBATOR → ALPHA | `seed.yaml` exists and validates; organ `KERNEL.md` and `CHARTER.md` exist | `validate-seed.py` |
| ALPHA → BETA | First vertical slice artifact exists; organ registered in organ-ladder; `promotion_status` matches `implementation_status` | `validate-seed.py` — `.metadata.promotion_status == .metadata.implementation_status` |
| BETA → STABLE | Organ beat wired into heartbeat loop; maturity >= 60% in organ-ladder.json | `validate-seed.py` + manual beat verification |
| STABLE → MATURE | Organ face (macro + micro) documented; governance rules operationalized as checks; maturity >= 90% | `validate-seed.py` + manual beat verification |

---

## The dual-entity boundary (the invariant)

The most common governance failure in a dual-entity structure is **role blurring**: a non-profit
starts selling services as if it were an LLC, or an LLC claims charitable status to avoid
taxation. This platform prevents role blurring with a machine-checkable boundary defined in
[`entities.yaml`](entities.yaml):

| Entity type | Allowed mandates | Always forbidden |
|---|---|---|
| **Non-profit** | open-project commons; grant-receiving; public-benefit | private-profit-generation; commercial-contracts-for-revenue |
| **LLC** | service-delivery; revenue-generation; commercial-contracts | receive-charitable-grants; claim-public-benefit-status |

The `boundary_matrix` in `entities.yaml` is the single source of truth. `validate-entities.py`
checks every entity's mandates against this matrix on every governance beat. Any action that
crosses the boundary is flagged and surfaced to the human fiduciaries — never self-resolved.

---

## Try it yourself in 30 seconds — one entity, one repo

You don't need a dual-entity structure to benefit from this platform. A solo operator with a single
GitHub org and one project gets the same institutional floor:

```bash
# Create a governance directory
mkdir -p organs/governance

# Copy the boilerplate (see Step 1 for the full template)
# Create your entity register with ONE entity and ONE repo:
cat > organs/governance/entities.yaml << 'YAML'
schema_version: "1.0"
organ: "governance"
repo: "your-org/your-repo"
entity_taxonomy:
  sole_proprietor:
    required_fields: [name, jurisdiction, mandates, forbidden_acts, fiduciary]
boundary_matrix:
  sole_proprietor:
    allowed_mandates: ["project-development", "open-source"]
    always_forbidden: ["fiduciary-delegation", "entity-blurring"]
cursus_offices: ["INCUBATOR", "ALPHA", "BETA", "STABLE", "MATURE"]
promotion_rules:
  INCUBATOR_to_ALPHA:
    prerequisites: ["seed.yaml exists and validates"]
    validated_by: "validate-seed.py"
  ALPHA_to_BETA:
    prerequisites: ["vertical slice exists", "promotion matches implementation"]
    validated_by: "validate-seed.py"
  BETA_to_STABLE:
    prerequisites: ["maturity >= 60%"]
    validated_by: "validate-seed.py + manual"
  STABLE_to_MATURE:
    prerequisites: ["governance operationalized", "maturity >= 90%"]
    validated_by: "validate-seed.py + manual"
entities:
  - id: "your-entity"
    name: "Your Entity"
    type: sole_proprietor
    jurisdiction: "your-jurisdiction"
    fiduciary: "you"
    mandates: ["project-development", "open-source"]
    forbidden_acts: ["fiduciary-delegation"]
    cursus: "STABLE"
repos:
  - repo: "your-org/your-repo"
    organ: "Your First Organ"
    home: "organs/your-organ/"
    entity: "your-entity"
    cursus: "INCUBATOR"
    implementation_status: "INCUBATOR"
YAML

# Create a seed declaration
cat > organs/governance/seed.yaml << 'YAML'
schema_version: "1.0"
organ: "governance"
repo: "your-org/your-repo"
org: "your-org"
metadata:
  implementation_status: "INCUBATOR"
  promotion_status: "INCUBATOR"
YAML

# Run the validators
python organs/governance/validate-seed.py organs/governance/seed.yaml --strict-graph
python organs/governance/validate-entities.py organs/governance/entities.yaml --strict-graph
```

That is the entire governance floor for a one-person institution. Add more entities and repos as
you grow. The structure scales to any size because the rules are the same at every scale.

---

## What the operator actually receives

Adopting this platform gives you six concrete artifacts, each machine-checkable:

1. **Entity register** (`entities.yaml`) — every legal entity under governance with its type,
   jurisdiction, fiduciary, mandates, and forbidden acts. One source of truth. The `entity_taxonomy`
   block defines required fields per entity type so the register is self-describing.

2. **Dual-entity boundary matrix** (embedded in `entities.yaml`) — the invariant rule table that
   prevents role blurring. `allowed_mandates` and `always_forbidden` per entity type.
   Machine-checkable; `validate-entities.py` enforces it on every beat.

3. **Promotion rules** (embedded in `entities.yaml`) — every cursus promotion with its
   prerequisites, specified as structured YAML. `validate-seed.py` checks each promotion attempt
   against these rules.

4. **Cursus status report** — every registered repo's current office (`cursus` field in
   `entities.yaml`), the offices it has held, and the prerequisites for its next promotion.
   The `_posture()` function in `validate-seed.py` computes this from the seed metadata.

5. **Promotion validation report** — each promotion attempt checked against the standing rules.
   Output: `PASS` (with next office named) or `FAIL` (with the specific rule violated, including
   line-level findings where applicable).

6. **Compliance sentinel alert** — any action that would blur entity roles, skip a governance
   step, or bypass a rule. Staged and surfaced for fiduciary review. The sentinel never
   self-corrects — it flags and waits.

---

## How to adopt (three-step quickstart)

### Step 1: Create your entity register

Copy [`entities.yaml`](entities.yaml) into your governance directory. Replace the ORGANVM entities
with your own:

```yaml
entity_taxonomy:
  nonprofit:
    required_fields: [name, jurisdiction, mandates, forbidden_acts, fiduciary]
  llc:
    required_fields: [name, jurisdiction, mandates, forbidden_acts, fiduciary]

boundary_matrix:
  nonprofit:
    allowed_mandates: ["open-project-commons", "grant-receiving", "public-benefit"]
    always_forbidden: ["private-profit-generation", "commercial-contracts-for-revenue"]
  llc:
    allowed_mandates: ["service-delivery", "revenue-generation", "commercial-contracts"]
    always_forbidden: ["receive-charitable-grants", "claim-public-benefit-status"]

cursus_offices: ["INCUBATOR", "ALPHA", "BETA", "STABLE", "MATURE"]
```

Add your entities under `entities:` and your repos under `repos:`.

### Step 2: Generate seed declarations

For each governed repo, create a `seed.yaml`:
```yaml
schema_version: "1.0"
organ: "<organ-name>"
repo: "<org>/<repo>"
org: "<org>"
metadata:
  implementation_status: "INCUBATOR"
  promotion_status: "INCUBATOR"
produces:
  - type: "<artifact-type>"
    consumers: ["<consumer-organ>"]
consumes:
  - type: "<artifact-type>"
    source: "<source-path>"
```

### Step 3: Run the validators

```bash
# Rules #1-2: cursus office integrity + structured edges
python validate-seed.py --fleet --strict-graph

# Rules #3-4: entity register integrity + repo registration
python validate-entities.py --fleet
```

Both exit 0 when governance is satisfied. Wire them into your CI/CD or heartbeat loop.

---

## What this platform is not (and why that is the point)

This platform does **not** issue binding resolutions, sign on behalf of entities, replace board
judgment, or practice law. Entity formation signatures, governance votes, and formal resolutions
stay with the human fiduciaries.

It does **not** self-ratify. The organ audits governance; it does not govern. Final decisions stay
with the human fiduciaries, every time.

It does **not** provide legal, tax, or regulatory advice. It is **governance infrastructure**, not a
law firm or compliance consultancy.

It does **not** require a board, a legal department, or a governance team to operate. The machine
runs the machine-checks; the human runs the human-decisions. That is the entire division of labor.

The constraint is a feature. It enforces the boundary that keeps the platform trustworthy and the
fiduciaries' authority intact. A governance tool that could override its governors is not a tool —
it is a coup.

---

## Why this, not a legal agreement or a spreadsheet

| Alternative | What it gives you | What it misses |
|---|---|---|
| **Legal agreement** (operating agreement, bylaws) | Binding authority, enforceable rights | No machine enforcement. A violation is only discovered when someone sues — after the damage is done. |
| **Spreadsheet / database** | A list of entities and cursus stages | No validation. No boundary enforcement. No sequence checking. The spreadsheet lies silently until an audit. |
| **CI pipeline / automated governance** | Machine enforcement of rules | Brittle, organization-specific. Hard to adopt across multiple repos, entities, or jurisdictions. No portable standard. |
| **This platform** | Machine-checkable rules + portable standard + append-only trail | Does not form entities, sign documents, or replace fiduciaries — by design |

The platform fills the gap between "we wrote it down" and "the machine enforces it." Agreements
define rights; this platform enforces the invariants that keep those rights from being violated
before anyone notices.

---

## Governance layer (the authority contract)

The organ runs the governance system. The human fiduciaries run the institution.

| What the organ does | What the fiduciaries do |
|---|---|
| Maintains entity register and boundary matrix | Confirm entity state matches legal reality |
| Validates every promotion against cursus rules | Ratify each promotion before it takes effect |
| Runs compliance sentinel on every action | Review flagged violations; decide resolution |
| Maintains append-only audit log | Verify the log; order corrections if needed |
| Stages irreversible actions for review | Sign, file, and execute external acts |

No autonomous entity formation. No autonomous promotion ratification. No autonomous filing.
The fiduciaries are the final authority for every institutional act.

---

## Who holds this platform

The macro form of Aerarium / Cvrsvs Honorvm is intentionally generic:

- No hardcoded entity names
- No jurisdiction-specific legal assumptions
- No organization-specific governance idiom

A two-person open-source foundation managing a growing repo fleet, a dual-entity startup running
a non-profit commons alongside a commercial product, or a solo founder who wants a governance
floor before they need one — all three hold the same toolkit and fill in their own entities,
repos, and cursus registrations.

The proof that it holds across different entity types, different jurisdictions, and different
maturity levels is the micro instance — ORGANVM's own dual-entity operation documented in
[`MICRO-FACE.md`](MICRO-FACE.md).

---

## Validation

```bash
# Rules #1-2: cursus office integrity + structured edges
python3 organs/governance/validate-seed.py organs/governance/seed.yaml --strict-graph

# Rules #3-4: entity register integrity + repo registration
python3 organs/governance/validate-entities.py organs/governance/entities.yaml --strict-graph
```

Expected result: `PASS` for the governance seed and entity register,
`Cvrsvs Honorvm Rules #1 & #2: all checks passed. Concordia.` for the seed validator, and
`Cvrsvs Honorvm Rules #3 & #4 (strict-graph): all checks passed. Concordia.` for the entity
validator. Both exit 0.

---

## Stage and maturity

The macro platform is **75% mature** (maturing stage). The entity register with dual-entity
boundary matrix, the cursus honorum seed validator, and the entity integrity validator are all
operational, machine-checkable, and running on every governance beat. The remaining lift to 90%:

1. Wire the governance beat into the heartbeat loop as `C_GOVERNANCE` cadence
2. Operationalize the compliance sentinel as a continuous beat (not just on-demand validation)
3. Automate the append-only audit log (every action: timestamp, actor, rule, outcome)
4. Close one complete promotion cycle with full validation, ratification, and audit trail

---

## Files

| File | Purpose |
|---|---|
| `KERNEL.md` | Architecture, the 5-primitive map, hard guardrails |
| `CHARTER.md` | AI roles (Standing Clerk, Sequencing Auditor, Entity Registrar, Compliance Sentinel), workflows, human-supervision contract |
| `MACRO-FACE.md` | **This file** — the portable open standard |
| `MICRO-FACE.md` | ORGANVM's live dual-entity instance (proof this works) |
| `entities.yaml` | Entity register + boundary matrix + cursus promotion rules |
| `seed.yaml` | This organ's own standing declaration |
| `validate-seed.py` | Cursus honorum Rules #1-2: office integrity + structured edges |
| `validate-entities.py` | Cursus honorum Rules #3-4: entity register integrity + repo registration |

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`CHARTER.md`](CHARTER.md) (roles + workflows), [`MICRO-FACE.md`](MICRO-FACE.md)
(proof instance — Cind & Sol Foundation / Sovereign Systems LLC).*
