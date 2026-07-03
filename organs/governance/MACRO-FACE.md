# Aerarium / Cvrsvs Honorvm — MACRO FACE
## The portable governance-as-code open standard

*The platform form of the governance organ · Available to any foundation, multi-repo ecosystem, or dual-entity organization*

> **What you are reading:** the macro face is what an outside operator holds — the portable,
> reusable body of this organ before any entity name is in it. The micro instance (ORGANVM's
> own dual-entity operation: Cind & Sol Foundation + Sovereign Systems LLC) proves it in
> practice across two distinct entity types and a registered repo fleet. That proof is in
> [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The problem this platform solves

Most organizations run on **founder trust, not institutional systems**. A founder's good
intentions are real — but they are not a governance floor. When the founder steps away, when
priorities conflict, when a project claims maturity without the receipts — accountability
goes with them.

In a multi-repo ecosystem the problem compounds:
- Nobody has a clear picture of what stage each project is actually at
- Entity roles blur: a non-profit starts behaving like a commercial venture, or an LLC claims
  public-benefit standing without the mandate
- Promotions are aspirational: a repo calls itself STABLE with no record of passing through
  ALPHA or BETA
- There is no standing register — no one fact that answers "what is this project's current
  office and what must happen before it advances"

The institutions that solve this — constitutional governance offices, foundation boards,
regulatory bodies — are available only to organizations that can staff them. This platform
gives any organization the **same institutional floor** without hiring a governance team.

---

## The thesis

> **The cursus honorum — a sequential ladder of offices with machine-checkable
> prerequisites — is the missing institution. No skipped stages, no self-ratification,
> no silent entity drift. The sequence is public; the rules are executable; the audit
> trail is append-only.**

The platform runs on two synchronized engines:

| Engine | What it does | Why it works |
|---|---|---|
| **The Seed Validator** | Checks every project's standing declaration against the canonical cursus sequence: a repo cannot claim STABLE without passing INCUBATOR → ALPHA → BETA. `implementation_status` and `promotion_status` must agree — no split declaration | Promotions are earned, not claimed. A project that has not satisfied the prerequisites cannot advance, regardless of its owner's confidence |
| **The Entity Registrar** | Tracks every legal entity under governance: its type (non-profit, LLC), its permitted mandates, its always-forbidden acts, and the cursus standing of every registered repo that belongs to it | Entity roles cannot blur. A non-profit cannot drift into commercial revenue; an LLC cannot claim public-benefit status. The boundary is machine-checkable |

Neither engine works without the other. Validation without registration is a claim with no
witness. Registration without validation is a phone book with no rules.

---

## What this platform is

A **structured governance-operations toolkit** that runs the six functions a constitutional
governance office performs — stripped to their mechanical core, adaptable to any entity
structure and any project scale:

| Function | What it produces |
|---|---|
| **Entity Registry** | A single source of truth: every legal entity under governance, its type, jurisdiction, fiduciary, mandates, and forbidden acts |
| **Dual-Entity Boundary Matrix** | The invariant rule table: what each entity type may and must never do. Non-profits may receive grants and generate open-commons value; they may not generate private profit or execute commercial contracts for revenue |
| **Cursus Validator** | Machine-checkable promotion rules: a repo or entity may only advance one office at a time, no skipping, every prerequisite satisfied before advancement |
| **Repo Registration** | Every governed project registered with its cursus standing — the canonical answer to "where is this project right now and what must happen for it to advance" |
| **Compliance Sentinel** | Flags any action that would blur entity roles, skip a governance step, or bypass a rule. The sentinel never self-corrects — it surfaces the violation to the human fiduciaries |
| **Audit Log** | Every governance action — entity update, promotion, registration change — is appended with timestamp, actor, rule applied, and outcome. Append-only; entries are never amended |

Each function feeds the next. Entity registration feeds the boundary matrix. The boundary
matrix feeds the compliance sentinel. The cursus validator feeds the promotion audit. The
audit log feeds every governance review.

---

## The five-primitive kernel

Every organization governed by this platform is structured around five primitives. The same
map holds for any entity type and any project stage:

| Primitive | In governance | Concretely |
|---|---|---|
| **Member** | the entity / contributor | the person or organization whose standing in the system is tracked — their role, capacity, and office history. Never floating; always registered |
| **Mandate** | the office / authority | the specific power or duty conferred at the current stage of the cursus. What this office-holder may decide, and what must wait for the next office |
| **Standing** | cursus posture | where in the sequence the member or project currently sits — which offices have been held, what prerequisites are satisfied, what comes next |
| **Standard** | the governing rule | the constitutional rule, sequence invariant, or precedent that constrains advancement. Every rule is machine-checkable or explicitly deferred to human judgment |
| **Governance** | the senate / board | who ratifies promotions, how disputes are resolved, what stays irreducibly in the human fiduciary's hand. The organ audits; the board decides |

No entity enters governance without a named Member record. No repo advances without satisfying
the Standing prerequisites. No entity changes its Mandate without an explicit board action.

---

## The cursus honorum (the sequence of offices)

The Roman cursus honorum was the sequential ladder of public offices — no one could hold the
consulship without first holding the quaestorship and praetorship. This platform expresses that
same invariant for repositories and contributors:

```
INCUBATOR → ALPHA → BETA → STABLE → MATURE
```

A project can only advance one office at a time. No skipping. Each promotion requires ALL
prerequisites to be satisfied:

| Promotion | Prerequisites |
|---|---|
| INCUBATOR → ALPHA | `seed.yaml` exists and validates; organ `KERNEL.md` and `CHARTER.md` exist |
| ALPHA → BETA | First vertical slice artifact exists; organ registered in organ-ladder; `promotion_status` matches `implementation_status` |
| BETA → STABLE | Organ beat wired into heartbeat loop; maturity >= 60% |
| STABLE → MATURE | Organ face (macro + micro) documented; governance rules operationalized as checks; maturity >= 90% |

This is the discipline a foundation board enforces through constitutional process. Here it is
enforced through the cursus validator itself.

---

## The dual-entity boundary (the invariant)

The most common governance failure in a dual-entity structure is **role blurring**: a
non-profit starts selling services as if it were an LLC, or an LLC claims charitable status
to avoid taxation. This platform prevents role blurring with a machine-checkable boundary:

| Entity type | Permitted mandates | Always forbidden |
|---|---|---|
| **Non-profit** | open-project commons; grant-receiving; public-benefit | private-profit-generation; commercial-contracts-for-revenue |
| **LLC** | service-delivery; revenue-generation; commercial-contracts | receive-charitable-grants; claim-public-benefit-status |

The Compliance Sentinel checks every entity action against this matrix. Any action that
overlaps with `always_forbidden` is flagged and surfaced to the human fiduciaries — never
self-resolved.

---

## What the operator actually receives

1. **An entity register** — every legal entity under governance with its type, jurisdiction,
   fiduciary, mandates, and forbidden acts. One source of truth.
2. **A dual-entity boundary matrix** — the invariant rule table that prevents role blurring.
   Machine-checkable; flagged violations are surfaced to fiduciaries.
3. **A cursus status report** — every registered repo's current office, the offices it has
   held, and the prerequisites for its next promotion.
4. **A promotion validation report** — each promotion attempt is checked against the standing
   rules. PASS (with next office) or FAIL (with the rule violated).
5. **A compliance audit log** — every governance action recorded with timestamp, actor, rule
   applied, and outcome. Append-only; never amended.
6. **A compliance sentinel alert** — any action that would blur entity roles or bypass a
   governance step, staged and surfaced for fiduciary review.

---

## What this is not

This platform does not issue binding resolutions, sign on behalf of entities, replace board
judgment, or practice law. Entity formation signatures, governance votes, and formal
resolutions stay with the human fiduciaries.

It also does not self-ratify. The organ audits governance; it does not govern. Final decisions
stay with the human fiduciaries, every time.

It also does not provide legal, tax, or regulatory advice. It is **governance infrastructure**,
not a law firm or compliance consultancy.

The constraint is a feature. It enforces the boundary that keeps the platform trustworthy
and the fiduciaries' authority intact.

---

## Who holds this platform

The macro form of Aerarium / Cvrsvs Honorvm is intentionally generic:

- No hardcoded entity names
- No jurisdiction-specific legal assumptions
- No organization-specific governance idiom

A two-person open-source foundation managing a growing repo fleet, a dual-entity startup
running a non-profit commons alongside a commercial product, or a solo founder who wants a
governance floor before they need one — all three hold the same toolkit and fill in their own
entities, repos, and cursus registrations.

The proof that it holds across different entity types, different jurisdictions, and different
maturity levels is the micro instance.

---

## Governance layer (the authority contract, plainly stated)

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

## Current stage and validation

The macro platform is **75% mature** (maturing stage). The entity register with dual-entity
boundary matrix, the cursus honorum seed validator, and the entity integrity validator are
all operational and machine-checkable. The cursus promotion rules are fully specified and
validated against the organ's own fleet. The remaining lift to 90% is to close the audit-log
automation gap and operationalize the compliance sentinel as a continuous beat.

Validation:

```bash
# Rule #1-2: cursus office integrity + structured edges
python organs/governance/validate-seed.py --fleet --strict-graph

# Rule #3-4: entity register integrity + repo registration
python organs/governance/validate-entities.py --fleet
```

Expected result: all validators pass with "Concordia."

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`CHARTER.md`](CHARTER.md) (roles + workflows), [`MICRO-FACE.md`](MICRO-FACE.md)
(live entities: Cind & Sol Foundation / Sovereign Systems LLC).*
