# Sovereign Systems
## The institutional consulting toolkit — ready to show

*ORGANVM-as-a-service · Micro instance: Maddie · Rob · Derek*

---

## One-line position

Sovereign Systems gives a solo operator, a founding team, or an independent contractor the
same structured delivery floor that a well-resourced agency has — without the overhead.

---

## The pitch, plainly

Most consulting engagements fail at the same four points:

1. **The intake is soft.** Nobody wrote down what the client actually needs before the work started.
2. **The mandate drifts.** Scope expands, changes go unlogged, and the original agreement is lost.
3. **Handoffs are rushed.** Deliverables are handed over before anyone checked them against the agreed standard.
4. **Nothing closes cleanly.** The end of an engagement is "the work stopped," not a documented package.

A boutique agency solves this with staff and process. Sovereign Systems solves it with a structured
posture record and an explicit governance contract — held by one person, applied to any number of
clients.

---

## What the system delivers

For every engagement, the operator receives five concrete outputs:

| Output | What it is |
|---|---|
| **Client posture record** | One file. Member, mandate, standing, standards, human gates, scope boundary, change log. The single source of truth for the engagement. |
| **Scope draft** | A proposal-grade document: what is included, what is excluded, what assumptions are in play. Ready for partner review before any client send. |
| **Milestone map** | Staged, owned, gated. No single-step commits to a full outcome. No implicit "we'll figure it out." |
| **Quality review** | A per-deliverable audit against the agreed standard before handoff. Flags gaps before they reach the client. |
| **Closeout archive** | What was promised. What was delivered. What was deferred. What is still open. The record the next engagement starts from. |

---

## The engagement lifecycle

```
DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION → REVIEW → ARCHIVED
```

Every engagement has a named standing. Posture advances; it does not regress without a
logged change. A hold is declared, not implied. An archive is written, not assumed.

---

## The authority contract

| Sovereign Systems does | The operator does |
|---|---|
| Captures intake, builds posture record | Strategic accept/reject — the human call |
| Assembles scope draft, logs changes | Approves scope before any external send |
| Sequences milestones, tracks standing | Approves reprioritization |
| Drafts deliverables, flags gaps | Signs off each handoff |
| Stages outbound artifacts for review | Sends, signs, commits externally |

**The rule:** the system drafts and stages. The operator decides and acts. Nothing external
happens without explicit human authorization.

---

## The live proof: three active deployments

### Maddie — scope stability under shifting priorities

- **What it tests:** can the posture model hold when requirements keep moving?
- **Current standing:** EXECUTION — delivery artifacts in progress
- **Scope boundary:** intake capture, posture tracking, assumption logging
- **Scope change log:** no changes since acceptance — the mandate has held
- **Next gate:** Anthony signs off deliverable package → REVIEW

### Rob — cadence stability across recurring work

- **What it tests:** can the execution rhythm stay stable when work packets are adjusted?
- **Current standing:** EXECUTION — milestone checkpoint in progress
- **Scope boundary:** recurring execution support, milestone tracking, quality notes
- **Scope change:** one logged, attributed, and approved change (2026-06-15)
- **Next gate:** Anthony confirms milestone checkpoint → handoff package staged

### Derek — portability across a different working idiom

- **What it tests:** does one operating model hold across education-adjacent,
  narrative-facing, frequently-shifting work?
- **Current standing:** EXECUTION — brief format and milestone ledger active
- **Scope boundary:** structured brief format, milestone ledger, handoff packages
- **Scope change log:** no changes since acceptance — the brief structure has held
- **Next gate:** Anthony reviews brief + ledger → REVIEW

---

## What the three deployments prove together

The platform assumption is: **one posture model holds across different clients, different
rhythms, and different domain idioms.**

The proof:
- All three pass the six-rule engagement validator
- All three have explicitly named mandates (no soft intakes)
- All three have explicit scope boundaries (no silent drift)
- All three have declared human gates (no autonomous outbound)
- The one scope change that happened (Rob, 2026-06-15) was logged and approved

The platform holds.

---

## The validator

Run the six rules against all live deployments:

```bash
python organs/consulting/validate-consulting.py --fleet
```

Expected output: all three engagements green. Any failure names the specific rule and the
specific field — no guessing about what broke.

---

## Operating constraints (non-negotiable · repeated for every reader)

- No autonomous client-facing messages
- No autonomous contract sends or modifications
- No autonomous billing or invoice sends
- No external commitments without explicit partner gate
- No legal, tax, or medical advice — delivery infrastructure only
- No invented proof — all status reflects what actually exists

---

## What comes next

The three deployments are at EXECUTION. The next beat closes the loop:

1. Complete the deliverable package for each deployment
2. Pass the quality audit per deployment
3. Stage the handoff for Anthony's review
4. Write the closeout archive once confirmed

One clean close per deployment is the proof that the macro platform delivers its five outputs
end to end — not just intake and tracking, but the full cycle through archive.

---

*Sovereign Systems · stage: maturing (60%) · validator: green · constraint: manual prototype mode*  
*Full architecture: [KERNEL.md](KERNEL.md) · Platform face: [MACRO-FACE.md](MACRO-FACE.md) · Live deployments: [MICRO-FACE.md](MICRO-FACE.md)*
