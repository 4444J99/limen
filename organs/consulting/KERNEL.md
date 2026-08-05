# Sovereign Systems — KERNEL
## The consulting organ's architecture

> **Boundary (load-bearing, repeated everywhere in this organ):** this is consulting-infrastructure
> that augments human founders, operators, and domain specialists. It does **not** replace commercial
> judgment, sales judgment, final scope decisions, legal advice, invoicing, contract execution, or
> signature authority. The human partner owns every external act, every commitment, and every
> outward-facing statement.

---

## Why this organ exists

Most teams with good intent lose to well-backed teams not because they lack ability, but because
they lack **institutional weight** — the fixed routines, structured memory, and disciplined
operating floors that convert effort into reliable outcomes.

The wealthy have firms: PM systems, dedicated staff, and process layers that keep intakes clean,
mandates explicit, and deliverables reviewable. A solo operator has context and will, but usually
not the same floor under the feet.

This organ gives one person the institutional floor of a boutique service studio: structured
intake, explicit goals and scope, disciplined delivery evidence, and a reusable operations layer.
The same scaffold proves itself in Anthony's three active deployments (Maddie, Rob, Derek) and
is intentionally generic enough to be held by any operator with different clients and different
domains.

---

## The 5-primitive kernel, mapped to consulting

| Primitive | Consulting meaning | Concretely |
|---|---|---|
| **Member** | the client | the person or organization requesting work; constraints, context, and consent |
| **Mandate** | the engagement | what outcome was hired for, in language both sides can sign |
| **Standing** | delivery posture | where the engagement sits right now: discovery, proposal, acceptance, execution, review, hold, or archived |
| **Standard** | the quality bar | minimum thresholds for clarity, evidence quality, scope integrity, and handoff completeness |
| **Governance** | authority and ethics | who decides what, what requires explicit approval, what cannot be sent or committed by the system |

The same five primitives map every other organ in the VLTIMA body. Consulting is not a
special case — it is the same structure with domain-appropriate labels.

---

## Fractal deployment

### MACRO face — ORGANVM-as-a-service

The reusable consulting toolkit any operator can hold:

- Structured intake that produces a named, version-controlled client posture record
- Proposal-grade scope assembly: inclusions, exclusions, assumptions, change log
- Milestone sequencing: staged, owned, gated — no one-step commits to full outcomes
- Per-deliverable quality audit against the agreed standard before handoff
- A closeout archive: what was promised, built, deferred, and unresolved

The macro form carries no hardcoded client names, no private pricing assumptions, and no
idiom specific to one personality. It is the generic institutional platform. The full
platform description is in [`MACRO-FACE.md`](MACRO-FACE.md).

### MICRO instance — five active engagements across four domains

Five live client deployments that prove the macro platform under different stress conditions:

- **Maddie** — scope capture under shifting priorities (tests mandate stability)
- **Rob** — recurring execution support with staged deadlines (tests cadence stability)
- **Derek** — cross-program, education-adjacent, narrative-facing work (tests portability)
- **Jessica** — greenfield niche entry, HR domain with Styx product tie (tests greenfield capture)
- **John F.** — minimal-signal finance thread captured from a principal directive (tests intake honesty)

Three at EXECUTION standing, two at DISCOVERY. All five pass the six-rule validator. The full
deployment record is in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The delivery posture sequence

```
DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION → REVIEW → ARCHIVED
                                                      ↓
                                                    HOLD
```

Posture rules:
- The sequence advances; it does not regress silently
- Scope changes are logged explicitly and require partner approval before taking effect
- HOLD is a declared state, not an implied one
- ARCHIVED is a complete closeout — what was promised, delivered, deferred, and outstanding

---

## The authority contract

| What the organ does | What the operator does |
|---|---|
| Captures intake, structures posture record | Strategic accept/reject, final scope |
| Assembles scope draft, logs changes | Approves boundaries before any external send |
| Sequences milestones, tracks standing | Approves reprioritization and commitments |
| Drafts deliverables, flags quality gaps | Signs off each handoff slice |
| Stages outbound artifacts for review | Sends, signs, commits externally |
| Flags irreversible actions, surfaces them | Makes the call; the system never does |

The pattern is: **draft and stage internally; deliver to the human for external execution**.
Nothing sends itself. Nothing commits itself. The operator is the release authority.

---

## Hard constraints (non-negotiable, every beat)

- **Manual prototype mode.** No autonomous client messaging, no autonomous contract send,
  no autonomous billing, no autonomous commitment of external obligations.
- **No irreversible outward actions without his hand.** Send, signature, acceptance, or public
  deliverable: staged, surfaced, held for human action.
- **No overreach.** Delivery infrastructure, not legal, tax, or medical advice.
- **Scope integrity.** Every engagement has a concrete current standing; scope changes are
  explicit and logged.
- **No invented proof.** Deliverables and status reflect what actually exists in the repo and
  on human-approved channels. Placeholders are labeled as placeholders.

---

## Executable validation

The engagement posture rules are checked by `validate-consulting.py`:

- **Rule 1: Valid Posture** — standing must be in the canonical sequence; no skips, no
  silent regression
- **Rule 2: Manual Mode** — no engagement may claim autonomic delivery; all milestones
  declare explicit human gates
- **Rule 3: 5-Primitive Completeness** — all five primitives named in every engagement record
- **Rule 4: Scope Integrity** — scope boundary is explicit; changes are tracked
- **Rule 5: No Overreach** — scope does not claim legal, tax, or medical advice
- **Rule 6: Evidence Integrity** — every `standard.evidence` field references real artifacts
  or clear statuses, not TODO / TBD / placeholder

Run the fleet check:

```bash
python organs/consulting/validate-consulting.py --fleet
python organs/consulting/validate-consulting.py --fleet --quiet
```

---

## What gets built next

From the `organ-backlog` for the maturing stage:

1. Close one complete intake-to-closeout cycle for all three micro deployments
2. Publish the closeout archive as the first repeatable handoff proof
3. Operationalize the governance layer: make the authority contract executable, not just stated

---

*Companion documents: [MACRO-FACE.md](MACRO-FACE.md) (platform pitch · institutional face),
[MICRO-FACE.md](MICRO-FACE.md) (live deployments · Maddie / Rob / Derek / Jessica / John F.),
[CHARTER.md](CHARTER.md) (org chart + role assignments + workflow steps).*
