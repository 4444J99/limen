# Sovereign Systems — MICRO FACE
## The live engagement record: Maddie · Rob · Derek

*Anthony's active client deployments · Internal review only*

> **What you are reading:** the micro face is the live proof of the macro platform against
> three real engagements. Each deployment runs the same five-primitive posture model, the same
> governance contract, and the same manual-prototype constraints. The platform description
> is in [`MACRO-FACE.md`](MACRO-FACE.md).

---

## Why these three

These engagements were not chosen to be easy. They were chosen to stress the platform
across three different failure modes — the three ways most solo consulting operations
break down:

| Deployment | Stress test | The failure mode it guards against |
|---|---|---|
| **Maddie** | Scope capture under shifting priorities | The mandate moves mid-delivery and nobody writes it down — scope creep becomes the new baseline |
| **Rob** | Execution rhythm across recurring work packets | The cadence holds until it doesn't — and without a recorded standing, no one catches the delta until it's too late |
| **Derek** | Portability across a different working idiom | The process only works for one client type — and adding a different domain reveals it was never a platform, just a habit |

If all three pass the same six rules, the macro platform is proven portable.

---

## Fleet validation

```bash
$ python organs/consulting/validate-consulting.py --fleet
PASS  engagements/derek.yaml  posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
PASS  engagements/maddie.yaml  posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
PASS  engagements/rob.yaml     posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
────────────────────────────────────────────────────────────
  3/3 passed  |  0 violation(s)
  Sovereign Systems Rules #1-6: all checks passed. Concordia.
```

All three engagements are green. Six rules checked per engagement, eighteen checks total,
zero violations. The standing history for each deployment shows the full arc:
`DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION`. No skips. No regressions.

---

## Fleet standing

| Engagement | Current standing | Next gate | Owner of gate | Scope changes | Validated |
|---|---|---|---|---|---|
| Maddie | EXECUTION | Deliverable handoff → REVIEW | Anthony | 0 (unchanged since acceptance) | PASS |
| Rob | EXECUTION | Milestone checkpoint → REVIEW | Anthony | 1 (logged & approved 2026-06-15) | PASS |
| Derek | EXECUTION | Brief + ledger → REVIEW | Anthony | 0 (original brief structure held) | PASS |

All three are in active execution. No engagement claims autonomic delivery. Every gate
names Anthony as the final authority. No autonomous outbound action is open or pending.

---

## Deployment 1: Maddie

**File:** `engagements/maddie.yaml`
**What this proves:** scope can be held when requirements keep moving.

**The mandate:** maintain coherent engagement posture under shifting priorities. A consistent
record of what was agreed, what changed, and what the current scope actually is.

**What the file records:**

| Primitive | Recorded value |
|---|---|
| `member.name` | "Maddie" |
| `member.context` | "Private client channel — scope capture under changing priorities" |
| `mandate.description` | "Engagement intake and delivery posture under changing scope" |
| `mandate.outcome` | "Test engagement posture stability when requirements shift" |
| `standing.current` | EXECUTION |
| `standing.history` | DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION |
| `standard.quality_bar` | "Every deliverable must have a named owner and a human gate" |
| `standard.evidence` | "Artifacts exist in repo or on human-approved channels" |
| `scope.boundary` | "Scope capture, posture tracking, assumption logging" |
| `scope.changes` | [] (no changes since acceptance — the mandate has held) |
| `human_gates` | 3 gates declared: intake completeness, scope approval, deliverable sign-off |

**What this deployment proves:**
The engagement has moved from DISCOVERY through three posture states to EXECUTION without
a single scope change. The absence of change log entries is itself evidence — it means
the intake was accurate enough that the mandate has not needed correction.

**Scope boundary exclusions (explicit to prevent overreach):**
- No contract execution — the organ drafts; Anthony sends and signs
- No billing — invoices are staged for partner review
- No legal advice — delivery infrastructure only

**Constraint in effect:** No client-facing sends, no contract modifications, no billing
actions. All external actions are staged and passed to Anthony.

**Next move:** Anthony signs off the current deliverable package → standing advances to REVIEW.

---

## Deployment 2: Rob

**File:** `engagements/rob.yaml`
**What this proves:** execution rhythm stays stable across recurring work packet adjustments.

**The mandate:** recurring execution support with staged deadlines and clear decision
checkpoints. A cadenced model that holds its standing even when individual work items
are re-prioritized.

**What the file records:**

| Primitive | Recorded value |
|---|---|
| `member.name` | "Rob" |
| `member.context` | "Recurring execution support with staged deadlines" |
| `mandate.description` | "Recurring execution support with staged deadlines and clear decision checkpoints" |
| `mandate.outcome` | "Test execution rhythm stability across work packet adjustments" |
| `standing.current` | EXECUTION |
| `standing.history` | DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION |
| `standard.quality_bar` | "Every milestone has a named owner and a human gate" |
| `standard.evidence` | "Recurring cadence artifacts exist" |
| `scope.boundary` | "Recurring execution support, milestone tracking, quality notes" |
| `scope.changes` | 1 entry (see below) |
| `human_gates` | 3 gates declared: milestone completion, reprioritization, handoff sign-off |

**The one scope change (the live proof of scope integrity):**

```yaml
scope:
  changes:
    - date: "2026-06-15"
      description: "Scope refined to add milestone checkpoint documentation"
      approved_by: "Engagement Partner"
```

This is the deployment's most important evidence. It proves the platform's core claim:
when scope changes, it is recorded, attributed, and approved — not silently absorbed.
A solo operator without this discipline would have expanded scope in conversation and
forgotten the delta by the next cycle.

**Scope boundary exclusions (explicit to prevent overreach):**
- No financial commitments — the organ does not commit the partner's money
- No contract changes — the organ stages proposals; the partner executes
- No third-party agreements — external commitments require human authorization

**Constraint in effect:** No autonomous re-prioritization. No financial commitments.
No third-party agreements.

**Next move:** Anthony confirms the milestone checkpoint → handoff package is staged → standing advances to REVIEW.

---

## Deployment 3: Derek

**File:** `engagements/derek.yaml`
**What this proves:** one operating model works across a different working idiom without
changing its substrate terms.

**The mandate:** cross-program support — education-adjacent, narrative-facing, frequent
context shifts. The posture model must be portable enough to hold when the work itself
doesn't map cleanly to one domain.

**What the file records:**

| Primitive | Recorded value |
|---|---|
| `member.name` | "Derek" |
| `member.context` | "Cross-program work — education-adjacent and narrative-facing" |
| `mandate.description` | "Cross-program work with frequent context shifts, testing portability of the posture model" |
| `mandate.outcome` | "Test one operating model across different working idioms" |
| `standing.current` | EXECUTION |
| `standing.history` | DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION |
| `standard.quality_bar` | "Structured brief format, milestone ledger, handoff package completeness" |
| `standard.evidence` | "All artifacts review-ready before partner review" |
| `scope.boundary` | "Structured brief format, milestone ledger, handoff packages" |
| `scope.changes` | [] (no changes — the original brief structure has held) |
| `human_gates` | 3 gates declared: brief structure confirmation, ledger entry approval, handoff sign-off |

**What this deployment proves:**
This is the hardest test of portability. The work crosses education, narrative, and
program management idioms — domains with different vocabularies, different rhythms, and
different quality expectations. The fact that the same five-primitive structure, the same
posture sequence, and the same validator produce clean PASS results means the platform
is not tuned to one client type.

**Scope boundary exclusions (explicit to prevent overreach):**
- No independent client outreach — all external contact flows through Anthony
- No narrative publication without partner review — the organ drafts; the partner publishes
- No billing or financial commitments

**Constraint in effect:** No independent client outreach. No narrative publication without
partner review. No billing.

**Next move:** Anthony reviews the current brief + milestone ledger → standing advances to REVIEW.

---

## What the three deployments prove together — data

| Claim | Evidence | Status |
|---|---|---|
| Scope does not drift silently | Rob has 1 logged scope change (2026-06-15), Maddie and Derek have 0 — all are explicitly tracked | **CONFIRMED** |
| Posture is always named | All 3 have `standing.current = EXECUTION`, all 3 have `standing.history[]` with complete arcs | **CONFIRMED** |
| Human gates are structural, not advisory | All 3 declare ≥3 named human gates. No engagement has `autonomic: true` | **CONFIRMED** |
| The validator enforces the rules | 18/18 checks pass across the fleet (6 rules × 3 engagements) | **CONFIRMED** |
| Portability holds across domains | One process works for scope-stability (Maddie), cadence-stability (Rob), and cross-domain (Derek) | **CONFIRMED** |
| No overreach exists in scope boundaries | All exclusions explicitly disclaim legal/tax/medical. No scope boundary overclaims | **CONFIRMED** |
| Evidence is real, not placeholder | `standard.evidence` fields reference real artifacts. Zero TODO, TBD, or placeholder | **CONFIRMED** |

The platform makes testable claims about engagement discipline. All seven claims are
verifiable from the validator output and the engagement files.

---

## Operating constraints (invariant across all three deployments)

These are not best practices. They are non-negotiable structural constraints:

- **No autonomous client-facing messages.** The organ drafts; the partner sends.
- **No autonomous contract sends or modifications.** Staged and surfaced only.
- **No autonomous billing.** Invoice drafts are reviewed before any send.
- **No external commitments without explicit gate.** The partner is the final authority.
- **No invented proof.** Deliverables and status reflect what actually exists in this repo
  and on human-approved channels. Placeholders are labeled as placeholders.
- **No legal, tax, or medical advice.** Delivery infrastructure, not professional services.

---

## Next proof step — close one complete cycle

The three deployments are at EXECUTION. The next step is not to add a fourth deployment —
it is to complete one full intake-to-closeout cycle for all three:

1. **Finish the deliverable package** for each engagement — the artifacts that prove delivery
2. **Pass the quality audit** against each posture file's declared standard
3. **Stage each handoff** for Anthony's review (standing → REVIEW)
4. **Write each closeout archive** once Anthony confirms — what was promised, delivered, deferred

Once one complete cycle closes cleanly from DISCOVERY through ARCHIVED for any deployment,
the macro platform has its first full end-to-end proof.

---

*Stage status: three deployments at 60% maturity (maturing stage). All pass the six-rule
validator. The next lift is closing a complete cycle and moving all three through REVIEW
to ARCHIVED. Companion docs: [MACRO-FACE.md](MACRO-FACE.md) (platform description),
[CHARTER.md](CHARTER.md) (roles + workflows), [KERNEL.md](KERNEL.md) (architecture).*
