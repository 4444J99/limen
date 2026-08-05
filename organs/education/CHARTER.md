# Education Organism - CHARTER
## The alternative academy desk

> **Boundary:** this organ builds education infrastructure. It does not replace
> teacher judgment, learner agency, accreditation authority, grade submission, or
> institutional consent. Every external act stays with the human.

## What it rivals

A serious private academy's operating floor: learner records, staged quests,
rubrics, feedback loops, credential evidence, and closeout archives. The point is
not to imitate the legacy system. The point is to give a family, instructor, or
self-directed learner enough institutional weight to leave the legacy system
without losing rigor.

## Roles

| Role | Does | Human check |
|---|---|---|
| Learning Partner | final judgment, consent, institutional acts | This is the human |
| Intake Steward | captures learner context and constraints | Confirms fairness and consent |
| Quest Architect | turns a vague goal into a staged arc | Approves the standard before start |
| Rubric Keeper | names what good looks like at each gate | Reviews criteria for fit |
| Feedback Steward | drafts feedback and quality notes | Human delivers or approves feedback |
| Credential Clerk | stages completion evidence | Human signs, submits, or publishes |

## Workflows

1. **Intake to posture.** Create one Learner Posture Record with Member,
   Mandate, Standing, Standard, and Governance.
2. **Mandate to quest.** Convert the learning goal into a staged arc with named
   gates and rubric criteria.
3. **Delivery to feedback.** Track learner output, draft feedback, and flag
   gaps against the declared standard.
4. **Module to Wings.** Convert completed work into parallel artifacts:
   academic, SOP, business case, social, community, wiki, web/blog, and grant.
5. **Closeout to credential evidence.** Archive what was pursued, achieved,
   deferred, and unresolved.

## First proof

The three micro deployments are:

- **ENC1101** - a legacy-adjacent college class running inside D2L.
- **Derek narrative workshop** - a private mentor/apprenticeship arc.
- **Homeschool engine** - a family-owned curriculum arc.

They are checked by:

```bash
python organs/education/validate-education.py --fleet
```

The validator enforces the first six education rules:

1. Valid posture in the education sequence.
2. Manual mode with explicit human gates.
3. Five-primitive completeness.
4. Rubric and evidence integrity.
5. No overreach into accreditation, therapy, diagnosis, or autonomous grading.
6. Artifact path: every deployment must name the next reviewable output.

