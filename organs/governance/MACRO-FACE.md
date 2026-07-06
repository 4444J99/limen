# Aerarium / Cvrsvs Honorvm — MACRO FACE
## The portable governance-as-code open standard

*One standard, two engines, five primitives. Adopt it in one directory. Your institution has
a governance floor — machine-checkable rules, no board required.*

This is the **macro face** — the reusable platform before any entity name is in it. Fill in
your entities, repos, and cursus registrations; run the validators; your organization has the
same institutional floor that a foundation board or constitutional governance office provides.
The **micro instance** — ORGANVM's own dual-entity operation (Cind & Sol Foundation + Sovereign
Systems LLC) — proves this platform against real entities, a real fleet, and real beats, every
day. See [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The problem

Most organizations — open-source foundations, dual-entity startups, solo operators building an
institution — run on **founder trust, not institutional systems**. Good intentions are real, but
they are not a governance floor. When the founder steps away, when priorities conflict, when a
project claims maturity without the receipts — accountability goes with them.

In a multi-repo ecosystem the problem compounds:
- **No clear posture.** Nobody has a single source of truth for what stage each project is at.
- **Entity blur.** A non-profit starts behaving like a commercial venture. An LLC claims
  public-benefit standing. Each began with a clear mandate; drift is a gradient, not a switch.
- **Aspirational promotions.** A repo calls itself STABLE with no record of passing through the
  prerequisite offices — because no record *exists*.
- **No standing register.** There is no durable answer to "what is this project's current office,
  and what must happen before it advances."

The institutions that solve this — constitutional offices, foundation boards, regulatory bodies —
are available only to organizations that can staff them. This platform gives **any** organization
the same institutional weight without hiring a governance team.

---

## The thesis

> **The cursus honorum — a sequential ladder of offices with machine-checkable prerequisites — is
> the missing institution. Every project passes through INCUBATOR → ALPHA → BETA → STABLE → MATURE
> in order, one office at a time, validated by executable rules. No skipped stages, no
> self-ratification, no silent entity drift. The sequence is public; the rules are executable;
> the audit trail is append-only.**

This is the same structural invariant that Roman public law enforced for 400 years: no one held
the consulship without first holding the quaestorship and praetorship. Applied to projects,
contributors, and legal entities — and checked by software on every beat.

---

## How it works: two engines, one register

The platform runs on two synchronized engines. Both must pass for governance to be satisfied:

| Engine | What it validates | The invariant |
|---|---|---|
| **Cursus Validator** `validate-seed.py` | Every project's standing declaration — `promotion_status` and `implementation_status` must agree and name a recognized office | Promotions are earned, not claimed. A project at ALPHA cannot claim BETA without satisfying all BETA prerequisites |
| **Entity Registrar** `validate-entities.py` | Every legal entity — type, jurisdiction, mandates, forbidden acts, and the cursus standing of every registered repo | Entity roles cannot blur. A non-profit cannot drift into commercial contracts; an LLC cannot claim charitable status |

Neither engine works without the other. Validation without registration is a claim with no witness.
Registration without validation is a phone book with no rules.

---

## The five-primitive kernel

Every organization governed by this platform is structured around five primitives. This is the
same kernel that drives every organ in the VLTIMA body — only the domain skin changes:

| Primitive | Governance meaning | Concretely |
|---|---|---|
| **Member** | the entity / contributor | A person or organization whose standing is tracked. Never floating; always registered in `entities.yaml` |
| **Mandate** | the office / authority | The specific power or duty conferred at the current cursus stage. What this office-holder may decide, and what must wait for the next office |
| **Standing** | cursus posture | Where in the sequence the member or project currently sits — which offices held, what prerequisites satisfied, what comes next |
| **Standard** | the governing rule | A constitutional rule, sequence invariant, or precedent that constrains advancement. Every rule is machine-checkable |
| **Governance** | the senate / board | Who ratifies promotions, how disputes are resolved, what stays irreducibly in the human fiduciary's hand. The organ audits; the board decides |

No entity enters governance without a Member record in `entities.yaml`. No repo advances without
satisfying its Standing prerequisites. No entity changes its Mandate without an explicit board
action recorded in the audit log.

---

## The cursus honorum

```
INCUBATOR → ALPHA → BETA → STABLE → MATURE
```

A project advances one office at a time. No skipping. Each promotion requires **all** prerequisites:

| Promotion | Prerequisites | Validated by |
|---|---|---|
| INCUBATOR → ALPHA | `seed.yaml` exists and validates; organ `KERNEL.md` and `CHARTER.md` exist | `validate-seed.py` |
| ALPHA → BETA | First vertical slice exists; organ registered in organ-ladder; `promotion_status` matches `implementation_status` | `validate-seed.py` — Rule 1e: no split declaration |
| BETA → STABLE | Organ beat wired into heartbeat loop; maturity >= 60% in organ-ladder.json | `validate-seed.py` + manual beat verification |
| STABLE → MATURE | Organ face (macro + micro) documented; governance rules operationalized as checks; maturity >= 90% | `validate-seed.py` + manual beat verification |

---

## The dual-entity boundary

The most common governance failure in a dual-entity structure is **role blurring**: a non-profit
selling services, or an LLC claiming charitable status. This platform prevents it with a
machine-checkable boundary defined in [`entities.yaml`](entities.yaml):

| Entity type | Allowed mandates | Always forbidden |
|---|---|---|
| **Non-profit** | open-project-commons, grant-receiving, public-benefit | private-profit-generation, commercial-contracts-for-revenue |
| **LLC** | service-delivery, revenue-generation, commercial-contracts | receive-charitable-grants, claim-public-benefit-status |

The `boundary_matrix` in `entities.yaml` is the single source of truth. `validate-entities.py`
checks every entity's mandates against it on every governance beat. Any crossing is flagged and
surfaced to the human fiduciaries — never self-resolved.

---

## Try it yourself (30 seconds, one entity, one repo)

You don't need a dual-entity structure. A solo operator with one GitHub org and one project gets
the same institutional floor:

```bash
# 1. Create a governance directory and copy the template
mkdir -p organs/governance
cp path/to/entities.yaml organs/governance/   # replace the entities + repos with yours

# 2. Create a seed declaration for your repo
cat > organs/governance/seed.yaml << 'EOF'
schema_version: "1.0"
organ: "my-organ"
repo: "my-org/my-repo"
org: "my-org"
metadata:
  implementation_status: "INCUBATOR"
  promotion_status: "INCUBATOR"
EOF

# 3. Run the validators
python3 organs/governance/validate-seed.py organs/governance/seed.yaml --strict-graph
python3 organs/governance/validate-entities.py organs/governance/entities.yaml --strict-graph
```

When both exit 0, your institution has a governance floor. Add entities and repos as you grow.
The structure scales because the rules are the same at every scale. See
[`entities.yaml`](entities.yaml) and [`seed.yaml`](seed.yaml) for the full template structure.

---

## What you receive

Adopting this platform gives you six concrete artifacts, all machine-checkable:

1. **Entity register** (`entities.yaml`) — every legal entity with its type, jurisdiction,
   fiduciary, mandates, and forbidden acts. Self-describing via `entity_taxonomy`.

2. **Dual-entity boundary matrix** (embedded in `entities.yaml`) — the rule table that prevents
   role blurring. `allowed_mandates` and `always_forbidden` per entity type. Enforced by
   `validate-entities.py` on every beat.

3. **Promotion rules** (embedded in `entities.yaml`) — every cursus promotion with structured
   prerequisites. `validate-seed.py` checks each attempt against these rules.

4. **Cursus status report** — every registered repo's current office, offices held, and
   prerequisites for the next promotion. Computed by `validate-seed.py`'s `_posture()` function.

5. **Promotion validation report** — each promotion attempt against the standing rules. Output:
   `PASS` (with next office) or `FAIL` (with the specific rule violated, line-level findings).

6. **Compliance sentinel alert** — any action that would blur entity roles, skip a step, or
   bypass a rule. Staged and surfaced for fiduciary review. The sentinel flags and waits; it
   never self-corrects.

---

## How to adopt

### 1. Create your entity register

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

Add your entities under `entities:` and repos under `repos:`. See the file for the full structure
with `promotion_rules` and `cursus_offices`.

### 2. Generate seed declarations

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

### 3. Run the validators

```bash
python3 validate-seed.py --fleet --strict-graph         # Rules #1-2
python3 validate-entities.py --fleet                     # Rules #3-4
```

Both exit 0 when governance is satisfied. Wire them into your CI/CD or heartbeat loop.

---

## What this platform is not

This platform does **not** issue binding resolutions, sign on behalf of entities, replace board
judgment, or practice law. Entity formation, governance votes, and formal resolutions stay with
the human fiduciaries — every time.

It does **not** self-ratify. The organ audits governance; it does not govern.

It does **not** provide legal, tax, or regulatory advice. It is **governance infrastructure**,
not a law firm or compliance consultancy.

It does **not** require a board or legal team to operate. The machine runs the checks; the human
runs the decisions. That is the entire division of labor.

The constraint is a feature. It enforces the boundary that keeps the platform trustworthy and the
fiduciaries' authority intact. A governance tool that could override its governors is not a tool
— it is a coup.

---

## Why this, not a legal agreement or a spreadsheet

| Alternative | What it gives you | What it misses |
|---|---|---|
| **Legal agreement** (bylaws, operating agreement) | Binding authority, enforceable rights | No machine enforcement. A violation is discovered only when someone sues — after the damage is done |
| **Spreadsheet / database** | A list of entities and cursus stages | No validation, no boundary enforcement, no sequence checking. The spreadsheet lies silently until an audit |
| **CI pipeline / automated governance** | Machine enforcement of rules | Brittle and organization-specific. Hard to adopt across multiple repos, entities, or jurisdictions. No portable standard |
| **This platform** | Machine-checkable rules + portable standard + append-only trail | Does not form entities, sign documents, or replace fiduciaries — by design |

Agreements define rights; this platform enforces the invariants that keep those rights from being
violated before anyone notices. It fills the gap between "we wrote it down" and "the machine
checks it."

---

## Governance layer (the authority contract)

| What the organ does | What the fiduciaries do |
|---|---|
| Maintains entity register and boundary matrix | Confirm entity state matches legal reality |
| Validates every promotion against cursus rules | Ratify each promotion before it takes effect |
| Runs compliance sentinel on every action | Review flagged violations; decide resolution |
| Maintains append-only audit log | Verify the log; order corrections if needed |
| Stages irreversible actions for review | Sign, file, and execute external acts |

No autonomous entity formation. No autonomous promotion ratification. No autonomous filing.

---

## Who holds this platform

The platform is intentionally generic:
- No hardcoded entity names
- No jurisdiction-specific legal assumptions
- No organization-specific governance idiom

A two-person foundation managing a growing repo fleet, a dual-entity startup running an open
commons alongside a commercial product, or a solo founder building the governance floor before
they need one — all three hold the same toolkit.

The proof that it works across different entity types, jurisdictions, and maturity levels is the
**micro instance** — ORGANVM's own dual-entity operation (Cind & Sol Foundation + Sovereign
Systems LLC), documented in [`MICRO-FACE.md`](MICRO-FACE.md). It passes every check, every beat.

---

## Validation

```bash
# Rules #1-2: cursus office integrity + structured edges
python3 organs/governance/validate-seed.py organs/governance/seed.yaml --strict-graph

# Rules #3-4: entity register integrity + repo registration
python3 organs/governance/validate-entities.py organs/governance/entities.yaml --strict-graph
```

Expected result — both exit 0:

```
PASS  organs/governance/seed.yaml    cursus: INCUBATOR → ALPHA → BETA  |  next: STABLE
PASS  organs/governance/entities.yaml
Cvrsvs Honorvm Rules #1 & #2: all checks passed. Concordia.
Cvrsvs Honorvm Rules #3 & #4 (strict-graph): all checks passed. Concordia.
```

---

## Stage and maturity

The macro platform is **75% mature** (maturing stage). The entity register with dual-entity
boundary matrix, cursus validator, and entity-integrity checker are all operational and running
on every governance beat. Remaining lift to 90% (mature):

1. Wire the governance beat into the heartbeat loop (`C_GOVERNANCE` cadence)
2. Operationalize the compliance sentinel as a continuous beat (not just on-demand validation)
3. Automate the append-only audit log (every action: timestamp, actor, rule, outcome)
4. Close one complete promotion cycle with full validation, ratification, and audit trail

---

## Files

| File | Purpose |
|---|---|
| `KERNEL.md` | Architecture, 5-primitive map, hard guardrails |
| `CHARTER.md` | AI roles, workflows, human-supervision contract |
| `MACRO-FACE.md` | **This file** — the portable open standard |
| `MICRO-FACE.md` | ORGANVM's live dual-entity instance (proof this works) |
| `entities.yaml` | Entity register + boundary matrix + cursus promotion rules |
| `seed.yaml` | This organ's own standing declaration |
| `validate-seed.py` | Cursus honorum Rules #1-2: office integrity + structured edges |
| `validate-entities.py` | Cursus honorum Rules #3-4: entity integrity + repo registration |

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`CHARTER.md`](CHARTER.md) (roles + workflows), [`MICRO-FACE.md`](MICRO-FACE.md)
(proof instance — Cind & Sol Foundation / Sovereign Systems LLC).*
