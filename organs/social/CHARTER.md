# Social Organism — CHARTER (Koinonia)
## The relationship-stewardship desk

> **Boundary:** this organ builds social-institution infrastructure. It does not manipulate
> relationships, send messages autonomously, surveil people, or replace consent. Every outreach,
> invitation, apology, boundary statement, and community rule stays with the human who owns
> the relationship. See [KERNEL.md](KERNEL.md) for the full guardrails.

## What it rivals

A civic/community institution plus a dedicated relationship-support office — the relational
memory, correspondence triage, care-cadence, boundary enforcement, and community governance that
today only the wealthy can afford through human staff (assistants, social secretaries, community
operators, alumni offices, mutual-aid networks). The point is not to automate friendship. The
point is to give one person enough institutional weight to hold a community's worth of ties
without burning out.

## Roles

| Role | Does | Human check |
|---|---|---|
| **You** (the human) | owns every relationship, decides every outbound act, sends or does not send | — (this is the human) |
| **Memory Keeper** | maintains the relationship-posture record: who matters, what the tie is, where it stands, what is owed, and what is sacred | Confirms accuracy; corrects errors; revokes stale data |
| **Correspondence Steward** | drafts replies, triages inbox by tie strength and urgency, flags overdue care, stages messages for review | Reviews before sending; never sends automatically |
| **Care Cadence Keeper** | tracks the expected pattern: birthdays, check-ins, follow-ups, gratitude, repair attempts, and boundary resets | Approves cadence changes; cancels reminders when timing is wrong |
| **Boundary Steward** | enforces consent rules: who may be contacted, how, about what, and at what frequency. Never overrides a boundary | Sets and revokes boundaries; confirms they are structural, not advisory |
| **Community Clerk** | tracks community rules, group norms, conflict history, and shared governance decisions for groups the human belongs to | Ratifies rules; participates in conflict resolution |

## Workflows

1. **Intake to posture.** Create one Relationship-Posture Brief with Member, Mandate, Standing,
   Standard, and Governance.
2. **Posture to triage.** Sort active relationships by standing: which need care, reply, repair,
   distance, or gratitude — and who is current, warm, or dormant.
3. **Triage to draft.** Generate a drafted correspondence or care action for the highest-priority
   ties. Every draft is staged; nothing leaves without the human's review.
4. **Boundary to enforcement.** Register relationship-level and community-level boundaries. The
   organ flags any reminder, draft, or workflow that would cross a boundary before it reaches
   the human.
5. **Conflict to repair.** Surface a relationship that is strained or broken, draft a repair
   approach or boundary reset, and stage it. The human decides whether and how to engage.
6. **Community to governance.** Draft community rules, surface conflicts, track decisions, and
   maintain the group's shared memory — but the community owns its own governance.

## First proof

The first vertical slice is a **Relationship-Posture Brief** for one real tie:

- A Member record (person/contact: identity and context, private by default)
- A Mandate (the relationship: what tie is held and why it matters)
- A Standing (tie strength and urgency: active · warm · dormant · strained · broken · protected)
- A Standard (reciprocity norm: expected cadence, boundaries, owed replies, and care)
- A Governance note (who may act, what requires the human's hand, what must never be shared)

The first engagement (`engagements/derek.yaml`) proves the brief works for Derek — a
collaborator, client, and creative partner whose relationship spans professional and personal
dimensions. The brief captures the tie, its current standing (active, warm, with clear care
obligations and human gates), and generates a relationship-posture report.

Checked by:

```bash
python organs/social/validate-social.py --fleet
python organs/social/scripts/relationship-brief.py organs/social/engagements/derek.yaml
```

The validator enforces the first six social organ rules:

1. Valid posture in the relationship sequence (active · warm · dormant · strained · broken · protected).
2. Manual mode with explicit human gates (no autonomous outreach).
3. Five-primitive completeness (member, mandate, standing, standard, governance).
4. Real evidence (no placeholder patterns in standard.evidence).
5. No overreach (no manipulation, no surveillance, no autonomous sending).
6. Artifact path: every engagement must name the next reviewable output.

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`MACRO-FACE.md`](MACRO-FACE.md) (platform thesis), [`MICRO-FACE.md`](MICRO-FACE.md)
(Anthony's live instance).*
