# Education Organism - MICRO FACE
## ENC1101, Derek's narrative workshop, and the homeschool engine

*Anthony's live education deployments. Internal review only.*

> **What you are reading:** the micro face is the proof that the macro
> alt-education platform holds in three different learning contexts. The
> platform description is in [`MACRO-FACE.md`](MACRO-FACE.md).

---

## Why these three

The platform has to work in more than one kind of school-shaped problem.

| Deployment | Stress test | Why it matters |
|---|---|---|
| ENC1101 | Legacy-adjacent college course | Proves the organ can operate inside D2L and institutional constraints without being owned by them |
| Derek narrative workshop | Private mentorship and output coaching | Proves the posture model holds in a one-to-one creative apprenticeship |
| Homeschool engine | Family-owned curriculum | Proves the same structure can protect a learner outside the legacy system entirely |

Together, they test the platform across institution, mentor, and family.

---

## Fleet standing

| Deployment | Current standing | Next gate | Owner of gate |
|---|---|---|---|
| ENC1101 | ACTIVE | Module package to REVIEW | Anthony |
| Derek narrative workshop | ACTIVE | Brief and artifact ledger to REVIEW | Anthony |
| Homeschool engine | ACTIVE | Quest arc and rubric packet to REVIEW | Anthony |

No deployment has autonomous outbound action open. No grades, credentials,
enrollment changes, or published curriculum move without human review.

---

## Deployment 1: ENC1101

**What this proves:** the platform can run inside a legacy institution without
absorbing that institution's assumptions.

**Mandate:** keep the writing course legible, staged, and reviewable. The organ
tracks posture, rubric, feedback bank, and learner-facing artifacts while the
instructor keeps D2L, grading, and institutional submission authority.

**What exists now:**

- Learner/instructor posture record in `engagements/enc1101.yaml`
- ACTIVE standing with next gate set to REVIEW
- Rubric evidence tied to `KERNEL.md`, `MACRO-FACE.md`, and this micro proof
- Manual gates for D2L go-live, feedback release, and grade submission

**Next proof step:**

Package one course module into a reviewable bundle: objective, prompt, rubric,
feedback bank, learner artifact path, and closeout note.

---

## Deployment 2: Derek narrative workshop

**What this proves:** the platform can hold an output-oriented apprenticeship
where the work is narrative, personal, and frequently shifting.

**Mandate:** turn narrative coaching into a named quest arc. The learner's
standing, standards, and artifact path must remain explicit even when the work
itself is exploratory.

**What exists now:**

- Posture record in `engagements/derek.yaml`
- ACTIVE standing with next gate set to REVIEW
- Artifact ledger path named before review
- Manual gates for brief confirmation, feedback delivery, and publication

**Next proof step:**

Produce the current narrative brief plus artifact ledger: what is being made,
what standard applies, what is deferred, and what Anthony must approve before it
leaves the system.

---

## Deployment 3: Homeschool engine

**What this proves:** the platform can support a family-owned curriculum without
depending on school bureaucracy for coherence.

**Mandate:** convert a homeschool learning goal into a staged quest with rubric,
feedback, Wings artifacts, and a closeout archive.

**What exists now:**

- Posture record in `engagements/homeschool.yaml`
- ACTIVE standing with next gate set to REVIEW
- Family consent and curriculum approval held as explicit human gates
- Wings artifact path declared for the first module

**Next proof step:**

Write the first Quest packet: learner context, module objective, rubric, cadence,
parent review gate, and the eight Wings outputs that will prove completion.

---

## What the three deployments prove together

1. **The posture model is portable.** Institution, mentor, and family all use
   Member, Mandate, Standing, Standard, and Governance.
2. **The human gate is structural.** D2L, publication, credentialing, and family
   curriculum choices remain human acts.
3. **The alternative is not soft.** Every deployment must produce artifacts that
   can be reviewed against named criteria.
4. **The quarantine thesis is operational.** The platform can keep the learner
   protected from the worst legacy mechanisms without abandoning rigor.

---

## Validation

Run:

```bash
python organs/education/validate-education.py --fleet
```

Expected result: all three deployments pass the first six education rules.

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture),
[`MACRO-FACE.md`](MACRO-FACE.md) (platform thesis), [`CHARTER.md`](CHARTER.md)
(roles and workflows).*

