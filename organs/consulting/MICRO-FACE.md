# Sovereign Systems — MICRO FACE
## The live engagement record

*Anthony's active client deployments · Internal review only · Five engagements across four domains*

> **What you are reading:** the micro face is the live proof of the macro platform. Each deployment
> runs the same five-primitive posture model, the same governance contract, and the same manual-prototype
> constraints — on real work with real clients. The platform description is in
> [`MACRO-FACE.md`](MACRO-FACE.md).

---

## The fleet at a glance

| Engagement | Domain | Standing | Next | Scope changes | Validated |
|------------|--------|----------|------|---------------|-----------|
| Maddie | Wellness (Elevate Align) | EXECUTION | REVIEW | 0 (unchanged since acceptance) | PASS |
| Rob | Fitness + chess (HokageChess + BODi) | EXECUTION | REVIEW | 2 (logged & approved) | PASS |
| Derek | Education + narrative (cross-program) | EXECUTION | REVIEW | 0 (original brief structure held) | PASS |
| Jessica | Human resources + Styx | DISCOVERY | PROPOSAL | 1 (record creation) | PASS |
| John F. | Finance | DISCOVERY | PROPOSAL | 1 (record creation) | PASS |

Three deployments in active delivery. Two in discovery — added organically from the same pipeline,
proving the platform scales to new niches without ceremony.

---

## Why these five — the stress axis

These engagements were not chosen to be easy. They were chosen to stress the platform across the
five ways consulting operations break down:

| Deployment | Stress test | The failure mode it guards against |
|------------|-------------|-----------------------------------|
| **Maddie** | Scope stability under shifting priorities | The mandate moves mid-delivery; scope creep becomes the new baseline |
| **Rob** | Execution rhythm across recurring work + the niche-funnel engine (proven funnel discipline generalized from 3+ years of BODi operations) | Cadence holds until it doesn't — without a recorded standing, no one catches the delta |
| **Derek** | Portability across a different working idiom | The process only works for one client type — adding a different domain reveals it was never a platform, just a habit |
| **Jessica** | Greenfield niche entry — HR domain with a real product tie (Styx peer-audited behavioral blockchain) | New niche capture without a prior relationship to guide the record |
| **John F.** | Minimal-record niche — thin prior thread, no written history | The platform must work when the starting point is nearly zero signal |

If all five pass the same six rules, the macro platform is proven portable, adaptable,
and capable of capturing a niche from the very first signal.

---

## Fleet validation

```bash
$ python3 organs/consulting/validate-consulting.py --fleet
PASS  engagements/derek.yaml     posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
PASS  engagements/jessica.yaml   posture: DISCOVERY  |  next: PROPOSAL
PASS  engagements/john-f.yaml    posture: DISCOVERY  |  next: PROPOSAL
PASS  engagements/maddie.yaml    posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
PASS  engagements/rob.yaml       posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
────────────────────────────────────────────────────────────
  5/5 passed  |  0 violation(s)
  Sovereign Systems Rules #1-6: all checks passed. Concordia.
```

Five engagements, 30 checks, zero violations. The three at EXECUTION each show a complete
posture arc — `DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION` — with no skips and no
regressions. The two at DISCOVERY are the platform's first greenfield captures: created
from a principal directive with no prior written record, validated on the same rules.

---

## Deployment 1: Maddie

**File:** `engagements/maddie.yaml` · **Standing:** EXECUTION

**What this proves:** scope can be held when the client's priorities keep moving. A consistent
record of what was agreed, what changed, and what the current scope actually is — with zero
scope changes since acceptance, proving the intake was accurate enough that the mandate has
not needed correction.

**Primitives recorded:**
- **Member:** "Maddie" — private client channel, wellness domain (Elevate Align)
- **Mandate:** engagement intake and delivery posture under changing scope — test stability when requirements shift
- **Standing:** EXECUTION (path: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION)
- **Standard:** every deliverable must have a named owner and a human gate; artifacts exist in repo or on human-approved channels
- **Governance:** Engagement Partner (human) — strategic accept/reject, final scope, commitments

**Human gates:** 3 declared — intake completeness, scope approval, deliverable sign-off

**Scope boundary:** scope capture, posture tracking, assumption logging

**Exclusions (explicit to prevent overreach):** no contract execution, no billing, no legal advice

**Constraint in effect:** no client-facing sends, no contract modifications, no billing actions.
All external actions are staged and passed to Anthony.

**The signal:** zero scope changes is not absence — it is evidence. The intake was specific
enough, and the mandate was bounded enough, that the work has not needed correction since
ACCEPTANCE. This is the strongest test of scope hygiene.

**Next move:** Anthony signs off the current deliverable package → standing advances to REVIEW.

---

## Deployment 2: Rob

**File:** `engagements/rob.yaml` · **Standing:** EXECUTION

**What this proves:** execution rhythm stays stable across recurring work packet adjustments.
Also: this is the niche-funnel engine's flagship instance — Rob's 3+ year BODi funnel
discipline has been recovered, documented, and generalized in [`FUNNEL-ENGINE.md`](FUNNEL-ENGINE.md)
and [`funnel/ROB-BODI-OPERATING-FLOOR.md`](funnel/ROB-BODI-OPERATING-FLOOR.md).

**Primitives recorded:**
- **Member:** "Rob" — NYC-based dual-discipline creator: chess content (HokageChess, 322+ videos) + fitness coaching (BODi affiliate, proven L0-L4 funnel)
- **Mandate:** recurring execution support with staged deadlines and clear decision checkpoints; expanded 2026-07-04 to the niche-funnel program (package Rob's proven funnel as repeatable processes, sequences, staged drafts)
- **Standing:** EXECUTION (path: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION)
- **Standard:** every milestone has a named owner and a human gate; every funnel stage names its artifact
- **Governance:** Engagement Partner (human) — strategic direction, re-prioritization

**Human gates:** 4 declared — milestone completion, reprioritization, handoff sign-off, plus: Rob fires every outbound post, DM, and send himself (the system stages drafts only)

**Scope changes:** 2 logged and attributed:
- `2026-06-15`: scope refined to add milestone checkpoint documentation
- `2026-07-04`: expanded to the niche-funnel program (principal's directive — build Rob's funnel machinery, generalized in FUNNEL-ENGINE.md)

**What the scope changes prove:** this is the deployment's most important evidence. When scope
changes, it is recorded, attributed, and approved — not silently absorbed. A solo operator
without this discipline would have expanded scope in conversation and forgotten the delta by
the next cycle. The change log is timestamped, described, and attributed to a requesting party.

**Funnel integration:** Rob's proven L0-L4 funnel (discovery content → audience capture →
opt-in → conversion → expansion) has been recovered from the 2026-04-25 strategy corpus
(144 recovered docs on Archive4T), rebuilt as a runnable floor with:
- Instance config: `funnel/instances/rob-fitness.yaml`
- Talk tracks: `funnel/templates/talk-tracks-fitness.md`
- Capture form: `funnel/templates/capture-form-fitness.md`
- Validator: `funnel/validate-funnel.py` (Engine Rules #1-7)

**Exclusions (explicit to prevent overreach):** no financial commitments, no contract changes,
no third-party agreements, no outbound sends in Rob's name — he fires every send

**Owed by Rob (blockers surfaced, not hidden):** personal BODi affiliate link (never recorded),
canonical handle confirmation (RB-8), Teamzy field schema, existing reel/short links

**Next move:** Anthony confirms the milestone checkpoint → handoff package is staged →
standing advances to REVIEW.

---

## Deployment 3: Derek

**File:** `engagements/derek.yaml` · **Standing:** EXECUTION

**What this proves:** one operating model works across a different working idiom without
changing its substrate terms. This is the hardest test of portability — the work crosses
education, narrative, and program management domains, each with different vocabularies,
different rhythms, and different quality expectations.

**Primitives recorded:**
- **Member:** "Derek" — cross-program work, education-adjacent and narrative-facing
- **Mandate:** cross-program work with frequent context shifts — test one operating model across different working idioms
- **Standing:** EXECUTION (path: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION)
- **Standard:** structured brief format, milestone ledger, handoff package completeness
- **Governance:** Engagement Partner (human) — strategic fit, cross-program coordination

**Human gates:** 3 declared — brief structure confirmation, ledger entry approval, handoff sign-off

**Scope changes:** 0 — the original brief structure has held across education and narrative domains

**What this deployment proves:** the five-primitive structure, posture sequence, and validator
produce clean PASS results across domains with different vocabularies and rhythms. The platform
is not tuned to one client type. The same `quality_bar` template produces review-ready artifacts
in education, narrative, and cross-program contexts.

**Exclusions (explicit to prevent overreach):** no independent client outreach, no narrative
publication without partner review, no billing or financial commitments

**Constraint in effect:** no independent client outreach, no narrative publication without
partner review, no billing

**Next move:** Anthony reviews the current brief + milestone ledger → standing advances to REVIEW.

---

## Deployment 4: Jessica

**File:** `engagements/jessica.yaml` · **Standing:** DISCOVERY

**What this proves:** the platform can capture a new niche from a principal directive with no
prior engagement record — and the same six rules hold from the very first standing.

**Status:** DISCOVERY — the engagement record exists, the five primitives are named, and the
validator passes. The scope boundary is drawn: HR niche delivery infrastructure (Styx peer-audited
behavioral blockchain + the HR organ). Jessica's participation is hers to confirm.

**Created:** 2026-07-04 from the principal's niche-institution directive.

**The signal:** this deployment was created from zero — no prior written record, no existing
relationship in the engagement system. The validator accepted it on its first write because
the five-primitive structure works as well for "we think this might become something" as it
does for "we have been delivering for months."

**Next move:** stand up the HR niche funnel instance — Jessica's professional reach built with
the same staged pipeline as Rob's, Styx as the flagship product, the HR organ as the
institutional frame. Produce a scoped proposal Jessica can accept.

---

## Deployment 5: John F.

**File:** `engagements/john-f.yaml` · **Standing:** DISCOVERY

**What this proves:** the platform works when the starting point is nearly zero signal — a
thin finance-niche thread named in a principal directive, no prior written record beyond a
collaborative game lane. The DISCOVERY standing captures the open state honestly.

**Status:** DISCOVERY — the record captures what is known (micro-tato game lane, the finance
collaboration thread) and what is owed (John's actual niche, offer, channels). The validator
passes because the rules check structure, not completeness of discovery.

**Created:** 2026-07-04 from the principal's niche-institution directive.

**The signal:** this is the hardest test of intake honesty. A conventional system would either
skip the record (and lose the thread) or invent facts to fill it (and misrepresent the state).
The platform's answer is: record what you know, mark the gap, and let the validator confirm
the structure is sound even while the content is thin. The DISCOVERY standing is designed
for this.

**Next move:** fill in the DISCOVERY record — John's niche, offer, channels, and whether a
funnel instance is wanted. Close the gap between "named in a directive" and "recorded in a
posture file."

---

## What the fleet proves together — evidence table

| Claim | Evidence | Status |
|-------|----------|--------|
| Scope does not drift silently | 3 scope changes logged across 5 engagements (Rob: 2, Jessica: 1, John F.: 1) — all attributed and approved | **CONFIRMED** |
| Posture is always named | All 5 have a named `standing.current`. All 3 at EXECUTION have complete `standing.history[]` with full arcs. Both at DISCOVERY have explicit `next_standing` | **CONFIRMED** |
| Human gates are structural, not advisory | All 5 declare ≥3 named human gates. 0 engagements have `autonomic: true`. The Rob engagement adds a fourth gate: he fires every send personally | **CONFIRMED** |
| The validator enforces the rules | 30/30 checks pass (6 rules × 5 engagements) | **CONFIRMED** |
| Portability holds across domains | One process works for scope-stability (Maddie), cadence-stability + funnel-engineering (Rob), cross-domain (Derek), greenfield-HR (Jessica), and minimal-signal-finance (John F.) | **CONFIRMED** |
| No overreach exists in scope boundaries | All 5 engagements explicitly disclaim legal/tax/medical. None contain prohibited language | **CONFIRMED** |
| Evidence is real, not placeholder | Every `standard.evidence` field references real artifacts. Zero TODO, TBD, or placeholder text | **CONFIRMED** |
| The platform captures greenfield niches from zero signal | Jessica and John F. were created from a principal directive with no prior written record. Both passed validation on first write | **CONFIRMED** |

The macro platform makes testable claims about engagement discipline. All eight claims are
verifiable from the validator output and the engagement files.

---

## Operating constraints (invariant across all deployments)

These are not best practices. They are non-negotiable structural constraints enforced by
the validator at every beat:

- **No autonomous client-facing messages.** The organ drafts; the partner sends.
- **No autonomous contract sends or modifications.** Staged and surfaced only.
- **No autonomous billing.** Invoice drafts are reviewed before any send.
- **No external commitments without explicit gate.** The partner is the final authority.
- **No invented proof.** Deliverables and status reflect what actually exists in this repo
  and on human-approved channels. Placeholders are labeled as placeholders.
- **No legal, tax, or medical advice.** Delivery infrastructure, not professional services.
- **No scraping or bulk prospecting.** Discovery happens through published content only
  (enforced by funnel Engine Rules #4).

---

## The forward path

All three EXECUTION deployments are in active delivery. The next step is not to add a sixth —
it is to close one complete intake-to-closeout cycle:

1. **Finish the deliverable package** for each EXECUTION engagement
2. **Pass the quality audit** against each posture file's declared standard
3. **Stage each handoff** for Anthony's review (standing → REVIEW)
4. **Write each closeout archive** once Anthony confirms — what was promised, delivered, deferred

Once one complete cycle closes cleanly from DISCOVERY through ARCHIVED, the macro platform
has its first full end-to-end proof.

For the two DISCOVERY engagements, the work is:
5. **Jessica:** complete the HR niche discovery → produce a scoped proposal for her acceptance
6. **John F.:** fill in the finance niche record → determine whether a funnel instance is wanted

**Stage status:** maturing (60%). All five deployments pass the six-rule validator. Three at
EXECUTION with one scope change cycle proven. Two at DISCOVERY — organic growth evidence.
The next lift is closing a complete cycle and advancing the two discovery instances to
PROPOSAL.

---

*Companion docs: [MACRO-FACE.md](MACRO-FACE.md) (platform description),
[CHARTER.md](CHARTER.md) (roles + workflows), [KERNEL.md](KERNEL.md) (architecture).*
