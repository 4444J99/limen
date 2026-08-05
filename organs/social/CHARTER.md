# Social Organism — CHARTER (Koinonia)
## The relationship-stewardship desk

> **Boundary:** this organ builds social-institution infrastructure. It does not manipulate
> relationships, send messages autonomously, surveil people, or replace consent. Every outreach,
> invitation, apology, boundary statement, and community rule stays with the human who owns
> the relationship. See [KERNEL.md](KERNEL.md) for the full guardrails.
> The organ also does not practice therapy, counseling, or mediation. It is **relationship-stewardship
> infrastructure**, not a therapeutic or social-work platform.

## What it rivals — the community-institution + relationship-guru standard

A civic/community institution (a neighborhood association, a church, a mutual-aid network, an alumni
office) plus a dedicated relationship-support office ("relationship gurus") — the relational memory,
correspondence triage, care-cadence, boundary enforcement, and community governance that today only
the wealthy can afford through human staff (assistants, social secretaries, community operators,
alumni offices, mutual-aid networks).

The relationship guru is not a therapist. A relationship guru is someone who:

- **Remembers** who matters, what each tie needs, and where each relationship stands — so the human
  never walks into a conversation cold.
- **Triages** the social field so care, gratitude, repair, and distance go to the right people at
  the right time — not reactively to whoever shouted loudest.
- **Coaches** on relational patterns: "you haven't replied to X in three weeks," "Y's birthday is
  next week and the last contact was a strained conversation," "Z has reached out twice — this tie
  needs a decision."
- **Protects** boundaries by tracking who has asked for space, who is off-limits for certain topics,
  and whose data must never be shared.
- **Holds community memory** — the group norms, past conflicts, shared decisions, and unwritten rules
  that make a community function without everyone carrying the full weight of its history.

The point is not to automate friendship. The point is to give one person enough institutional weight
to hold a community's worth of ties without burning out — the same way a litigation firm gives one
attorney a bench, and a concierge recovery team gives one patient a coordination staff.

## Institutional weight — how idle fleet capacity becomes a community/relationship institution

VLTIMA's fleet produces 14K-16K idle AI workunits per month. This organ converts that spare
capacity into ongoing social-operations infrastructure. The mapping:

| Fleet idle capacity (supply) | → | Social organ demand |
|---|---|---|
| Unlimited cheap reads + writes | → | Continuous relationship-posture maintenance, re-briefing as ties change |
| Background processing beats | → | Daily triage updates, care-cadence checks, overdue-reply flags, boundary-conflict scans |
| Structured-data workflows | → | People registry, relationship posture records, community rulebooks |
| Drafting runs | → | Correspondence drafts, care-action templates, repair-approach drafts, introduction language |
| Cross-model verification | → | Consent/boundary sentinel checks on every output before it reaches the human |

The binding constraint is not capacity — it is **relationships to steward**. One active relationship
consumes approximately 1-3 workunits/month in steady-state operations (posture check, triage slot,
cadence reminder, occasional draft). A diverse personal network of 50-100 active+ warm ties
consumes 50-300 workunits/month. A fleet of 14K+ idle workunits can sustain many personal networks
simultaneously once the intake, consent, and review gates are wired. The first engagement (Derek)
proves the pipeline; scaling means adding relationships and community contexts, not inventing new
social authority.

## The org-chart (AI roles, human-supervised)

### Tier 1: The human owning the relationships

| Role | Institution equivalent | Does | Human check |
|---|---|---|---|
| **You** (the human) | Community leader / head of household | owns every relationship, decides every outbound act, sends or does not send, sets all boundaries | — (this is the human) |

### Tier 2: The relationship-guru bench (AI roles)

| Role | Institution equivalent | Does | Human check |
|---|---|---|---|
| **Memory Keeper** | Social secretary / community archivist | maintains the relationship-posture record: Member, Mandate, Standing, Standard, Governance for every tie in the social field. Never loses a name, a context, a promise, or a boundary | Confirms accuracy; corrects errors; revokes stale data |
| **Correspondence Steward** | Executive assistant / personal secretary | drafts replies tiered by tie-strength and urgency, flags overdue messages, stages correspondence for human review, surfaces threads that need a decision | Reviews before sending; never sends automatically |
| **Care Cadence Keeper** | Personal scheduler / alumni-relations officer | tracks the expected pattern: birthdays, check-ins, follow-ups, gratitude notes, repair windows, and boundary resets. Produces a living care calendar | Approves cadence changes; cancels reminders when timing is wrong |
| **Boundary Steward** | Ombudsperson / consent officer | enforces consent rules: who may be contacted, how, about what, at what frequency, and whose data is shared with whom. Every draft, reminder, and workflow is checked against active boundaries before reaching the human | Sets and revokes boundaries; confirms they are structural, not advisory |
| **Community Clerk** | Community manager / clerk of the assembly | tracks community rules, group norms, conflict history, shared governance decisions, and membership for groups the human belongs to or leads. Maintains the community rulebook | Ratifies rules; participates in conflict resolution; never acts as community authority autonomously |
| **Network Strategist** | Chief of staff / relationship coach | surfaces patterns: which ties are drifting, which are strengthening, where reciprocity is unbalanced, where introductions would serve both parties. Frames strategic choices about relational energy allocation | Decides whether to act on any pattern or recommendation |

### Tier 3: The guardian (cross-cutting)

| Role | Institution equivalent | Does | Human check |
|---|---|---|---|
| **Consent/Privacy Sentinel** | Ethics officer / privacy counsel | enforces the invariant: no autonomous outreach, no data sharing without consent, no manipulation, no scoring of human worth. Gates every deliverable before it reaches the human | Final arbiter of all ethics and consent questions |

The point of the chart: each role is a **workflow the conductor can run continuously**, so the
human's social field is always organized, always current, always respectful of boundaries — the
leverage a community institution buys with headcount.

The human remains the center of relational gravity. These roles do not own relationships; they
prepare the ground so the human's relational attention is better spent and never wasted on
administrative overhead.

## The workflows it runs

Each workflow maps to the 5-primitive kernel (Member/Mandate/Standing/Standard/Governance) and
produces a specific artifact. Workflows run on a **cadence** — continuous for registry, daily for
triage, weekly for posture, on-demand for correspondence and repair.

### 1. Intake → posture (Member + Mandate)

- **Trigger:** new person enters the social field, or a relationship changes materially.
- **Process:** capture the person's identity and context (Member), the relationship type and why it
  matters (Mandate), current tie strength (Standing), reciprocity norms (Standard), and consent rules
  (Governance). Write one complete five-primitive record.
- **Runs:** on intake + on any material relationship change.
- **Output:** a Relationship-Posture Brief — one complete five-primitive record per tie, machine-
  readable (YAML) and human-readable (generated Markdown).
- **Human gate:** human confirms accuracy, corrects errors, revokes stale data.
- **Build path:** first as `engagements/<identifier>.yaml` + generated brief. Already proven for
  Derek. Next: family tie, collaborative network member.

### 2. Registry to triage (Standing)

- **Trigger:** daily beat or posture change.
- **Process:** scan all engagement records, sort by standing priority (STRAINED → BROKEN → PROTECTED
  → ACTIVE → WARM → DORMANT), flag overdue care, unreplied messages, approaching dates, and
  boundary conflicts. Surface the top 3-5 ties needing human attention today.
- **Runs:** daily.
- **Output:** a Triage Dashboard — sorted fleet-wide view with attention flags per tie.
- **Human gate:** human reviews triage, decides which items to act on. The dashboard is advisory.
- **Build path:** already exists as `scripts/triage-dashboard.py`. Next: wire it to the daily
  cadence beat so it auto-generates.

### 3. Care cadence → calendar (Standard + Standing)

- **Trigger:** posture recorded or cadence updated.
- **Process:** for each tie, extract the expected cadence, reply window, care pattern, important
  dates (birthdays, anniversaries, obligations), and overdue items. Produce a living calendar of
  care actions sorted by date and tie priority.
- **Runs:** daily — calendar rebuilt every 24h with proximity alerts and overdue flags.
- **Output:** a Care Calendar — chronological list of expected care actions, flagged by urgency and
  tie-standing.
- **Human gate:** human approves cadence changes, cancels reminders when timing is wrong.
- **Build path:** first as a generated Markdown calendar from the engagement YAMLs. Later as a
  structured calendar artifact with configurable alert thresholds.

### 4. Triage to draft (Standard + Governance)

- **Trigger:** human requests a draft, or a tie crosses a care/repair threshold.
- **Process:** for a given tie and action type (reply, check-in, gratitude note, repair attempt,
  introduction, boundary statement), generate a context-aware draft that carries the relationship
  record (current standing, recent history, owed replies, relevant boundaries). Every draft is
  watermarked "DRAFT — REVIEW BEFORE SENDING" and routed through the Consent/Privacy Sentinel
  before human delivery.
- **Runs:** on demand or on trigger (e.g., overdue reply reaches N days, birthday approaches).
- **Output:** a staged correspondence draft — never an autonomous send, always review-only.
- **Human gate:** human reviews, rewrites, and sends. Nothing leaves the organ without human review.
- **Build path:** first as manual prompt patterns using the engagement YAML as context. Later as a
  structured draft generator that reads posture + relevant history and produces tiered drafts.

### 5. Boundary to enforcement (Governance — cross-cuts all)

- **Trigger:** every output before delivery to the human.
- **Process:** each deliverable (draft, reminder, triage item, calendar entry, community rule) is
  checked against: active boundaries (who may be contacted, about what, at what frequency), consent
  rules (whose data is shared with whom), privacy scope (no personal data outside authorized
  channels), and the overreach invariant (no manipulation, no scoring, no autonomous outreach).
- **Runs:** continuously, as a gate on every output workflow.
- **Output:** a consent certification — a stamp on every deliverable: "Boundary check passed:
  all active boundaries honored, consent rules satisfied, no overreach detected."
- **Human gate:** human sets and revokes boundaries; the sentinel enforces them structurally.
- **Build path:** first as a manual checklist step in each workflow. Later as an automated preflight
  that blocks any deliverable mentioning a boundary-restricted person, topic, or action.

### 6. Conflict to repair (Mandate + Standing)

- **Trigger:** a tie's standing changes to STRAINED or BROKEN, or the human flags a conflict.
- **Process:** surface the relevant relationship history, current standing, known friction points,
  and owed replies or apologies. Draft a repair approach or boundary reset: what the relationship
  needs, what the human might say, what boundaries should be set or reinforced. Stage for review.
- **Runs:** on standing change to STRAINED/BROKEN or on human request.
- **Output:** a Repair Brief — relationship history, conflict context, staged approach, and
  recommended next step. Always review-only.
- **Human gate:** human decides whether and how to engage. No repair action is autonomous.
- **Build path:** first as a manual workflow guided by the posture record. Later as a structured
  repair-brief generator using the relationship history and standing trajectory.

### 7. Community to governance (Governance + Standard)

- **Trigger:** community rule change, membership change, conflict within a group, or shared
  decision needed.
- **Process:** for each community the human belongs to or leads, maintain a community rulebook:
  membership roster, shared norms, conflict history, past decisions, active governance questions.
  Draft proposed rules or decision frameworks for human review. Never self-executes community
  governance.
- **Runs:** on any community event or on human request; posture review weekly for active groups.
- **Output:** a Community Rulebook — membership, norms, decisions, conflict log, open governance
  questions. One per community context.
- **Human gate:** human ratifies rules, participates in conflict resolution. The community owns
  its own governance; the organ is infrastructure, not authority.
- **Build path:** first as a structured YAML record per community (like engagements but for groups).
  Later as a community-memory generator that surfaces past decisions and norms when new questions
  arise.

### Workflow orchestration diagram

```
                    ┌──────────────┐
                    │  Intake →    │
                    │  Posture     │
                    │(Member +     │
                    │  Mandate)    │
                    └──────┬───────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
     ┌──────────┐  ┌──────────────┐  ┌──────────┐
     │ Registry │  │Care Cadence  │  │Community │
     │ → Triage │  │ → Calendar   │  │→ Rulebook│
     │(Standing)│  │(Standard +   │  │(Governanc│
     │          │  │  Standing)   │  │+Standard)│
     └─────┬────┘  └──────┬───────┘  └────┬─────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Triage →     │
                    │ Draft        │
                    │(Standard +   │
                    │  Governance) │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Conflict →   │
                    │ Repair       │
                    │(Mandate +    │
                    │  Standing)   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Boundary /  │
                    │  Consent     │
                    │  Sentinel    │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   The Human  │
                    │  (reviews,   │
                    │   decides,   │
                    │   sends)     │
                    └──────────────┘
```

Every workflow feeds the next. Posture feeds triage. Triage + cadence feed drafting. Conflict
feeds repair. Community feeds governance. Boundary sentinel gates everything. The human stands
at the end of every path — no relational act is autonomous.

## Inputs / outputs

### Inputs (what the human or community supplies)

| Input | Format | Source | Maps to kernel |
|---|---|---|---|
| Person identity and context | Structured or narrative | Human | Member |
| Relationship type and why it matters | Structured or narrative | Human | Mandate |
| Current tie standing + history | Standing label + narrative | Human assigns; organ tracks changes | Standing |
| Reciprocity norms and cadence | Expected cadence, reply window, care pattern | Human sets per tie | Standard |
| Boundaries and consent rules | Per-person and per-community rules | Human sets and revokes | Governance |
| Community rules and decisions | Norms, membership, conflict log, past decisions | Human ratifies; community owns | Governance + Standard |
| Relationship changes | Standing updates, new context, new mandates | Human reports or confirms | All primitives |
| Feedback and corrections | Corrections to any recorded entry | Human reviews | Governance |

### Outputs (what the organ delivers to the human)

| Output | Format | Cadence | Maps to kernel |
|---|---|---|---|
| Relationship-Posture Brief | Markdown (one page per tie) | On intake + on change | All five primitives |
| People Registry | YAML records, one per tie | Continuous as ties are added | Member + Mandate |
| Triage Dashboard | Markdown sorted by standing priority | Daily | Standing |
| Care Calendar | Chronological list with proximity alerts and overdue flags | Daily rebuild | Standard + Standing |
| Correspondence Drafts | Markdown with DRAFT watermark | On demand or on trigger | Standard + Governance |
| Repair Brief | Relationship history + conflict context + staged approach | On standing change to STRAINED/BROKEN | Mandate + Standing |
| Community Rulebook | Structured YAML + generated Markdown | Per community event + weekly for active groups | Governance + Standard |
| Consent Certification | Inline stamp on each deliverable | Every output | Governance |

All outputs are **advisory to the human**. None are self-acting, none are sent or shared
automatically, and none replace the human's relational judgment.

## How the institutional weight works (the leverage math)

A community institution or relationship support office's leverage comes from **ratio**: one person
with a social secretary, a correspondence assistant, a scheduler, a community manager, and a
boundary-consent officer. That is a 1:5 ratio. The person's relational attention is worth 5x
because the bench remembers, triages, drafts, schedules, and enforces boundaries while the human
does the actual relating.

This organ delivers that bench as **continuous processing**. The key multipliers:

| Factor | Solo person | This organ (steady state) | Source of leverage |
|---|---|---|---|
| Relationship memory | One person's memory (fallible, finite) | Persistent posture records for every tie — never loses a name, context, promise, or boundary | Continuous write-once, read-anytime storage |
| Correspondence triage | Inbox chaos + react-to-loudest | Daily sorted triage by tie strength and urgency | Background processing beat every 24h |
| Care cadence | Manual calendar + "I should really reach out" | Living care calendar with proximity alerts and overdue flags | Runs every 24h regardless of human attention |
| Boundary enforcement | Self-policing (exhausting, easy to violate under pressure) | Automated sentinel on every output — checks every draft, reminder, and workflow against active boundaries | Cross-model verification run |
| Community memory | Carried by the most committed members (burnout risk) | Persistent community rulebook — norms, decisions, conflicts, membership | Structured records updated per event |
| Drafting | From scratch each time | Context-aware drafts carrying the full relationship record | Structured data always ready |
| Relationship coaching | Reactive — only when a problem is already acute | Proactive pattern-spotting: drifting ties, unbalanced reciprocity, introduction opportunities | Network Strategist review of standing trends |
| Total effective bench | 1 person | 7 roles running continuously (Memory Keeper, Correspondence Steward, Care Cadence Keeper, Boundary Steward, Community Clerk, Network Strategist, Consent Sentinel) | Idle fleet capacity mapped to social-operations workflows |

The human still does what only the human can do: show up for the actual relationship, send the
message, make the call, have the hard conversation, set the boundary, offer the gratitude, and
decide who matters and why. The organ does what headcount would do: remember, triage, draft,
track, enforce boundaries, hold community memory, and surface patterns.

## The relationship guru difference

The relationship guru tier (the AI roles above) differs from a simple CRM or contact manager in
four structural ways:

1. **Posture, not pipeline.** The system tracks relationship health (active, warm, dormant,
   strained, broken, protected), not sales-funnel stages. A person is never a lead, a prospect,
   or a conversion target.
2. **Reciprocity, not extraction.** The standard for each tie is mutual care, not unilateral
   value capture. The organ surfaces where reciprocity is unbalanced and where care is owed in
   both directions.
3. **Boundaries, not reach.** The system enforces who may be contacted, how, about what, and at
   what frequency — and it does so structurally, before any reminder or draft reaches the human.
4. **Community, not contacts.** The organ holds group memory, shared norms, conflict history, and
   collective decisions — the infrastructure of a living community, not a flat address book.

That is the relationship guru standard in buildable form: not "AI friend," but a disciplined
relational back office that keeps memory, triage, cadence, boundaries, and community governance
in motion until the human has a community-institution's worth of relational infrastructure to
act from.

## First proof: the micro instance

The micro instance — Anthony's relationship network — is the first deployment. The first
engagement (`engagements/derek.yaml`) proves the posture record for a multi-dimensional tie
(collaborator, client, creative partner).

The rollout order, matching the workflows above:

1. **Workflow 1 (Intake → posture)** — already proven. Derek's Relationship-Posture Brief is
   complete and validated. Next: family tie, collaborative network member.

2. **Workflow 2 (Registry → triage)** — already proven. `scripts/triage-dashboard.py` generates
   a fleet-wide triage view sorted by standing. The fleet today is one engagement; the triage
   dashboard proves the structure for N.

3. **Workflow 3 (Care cadence → calendar)** — next build target. Extract cadence data from
   each engagement's Standard to produce a chronological care calendar. First as a generated
   Markdown artifact; later as a structured calendar.

4. **Workflow 4 (Triage → draft)** — builds on workflow 2+3 output. Generate context-aware
   correspondence drafts from the posture record. First as manual prompt patterns; later as a
   structured draft generator.

5. **Workflow 5 (Boundary → enforcement)** — gates all outputs from step 1 onward. First as a
   manual checklist; later as the automated Consent/Privacy Sentinel.

6. **Workflow 6 (Conflict → repair)** — activated when a tie reaches STRAINED or BROKEN standing.
   First engagement tests the structure before it is needed under emotional load.

7. **Workflow 7 (Community → governance)** — activated when a community context is added. First
   community context tests the community rulebook structure.

The SCRUM: run workflow 1 (intake → posture) for each new engagement and workflow 2 (triage)
daily from the start. Build workflows 3-7 as the required inputs become available.

## The six social organ rules (validated by `validate-social.py`)

Rules enforced automatically against every engagement record:

| # | Rule | What it checks | Enforced by |
|---|---|---|---|
| 1 | **Valid Posture** | standing must be a recognized tie-strength in the canonical sequence (ACTIVE → WARM → DORMANT → STRAINED → BROKEN → PROTECTED). Standing advances in sequence; `next_standing` must advance forward. PROTECTED is a boundary state, not a regression. | `validate-social.py` |
| 2 | **Manual Mode** | no engagement may claim autonomic operation. `manual_mode` must be `true`. At least one `human_gates` entry must be named. The `never_autonomous` list must enumerate what the organ must never do autonomously for this tie. | `validate-social.py` |
| 3 | **5-Primitive Completeness** | every engagement record must capture all five kernel primitives: Member, Mandate, Standing, Standard, and Governance. No floating contacts. | `validate-social.py` |
| 4 | **Evidence Integrity** | every `artifacts.evidence` entry must reference real artifacts or clear statuses. No TODO, TBD, FIXME, PLACEHOLDER, or "to be determined" patterns. | `validate-social.py` |
| 5 | **No Overreach** | the engagement record must not claim or imply autonomous sending, surveillance, manipulation, or scoring of human beings. Overreach patterns are explicitly checked across all text fields. | `validate-social.py` |
| 6 | **Reviewable Output** | every engagement must name a `next_reviewable_output` — the concrete artifact the human should review next. | `validate-social.py` |

These six rules are the executable floor of the social organ. No engagement enters the fleet
without passing all six.

## Maturity and next steps

The social organ is **15% mature** (scaffold stage, rank 8 on the organ ladder). The kernel
architecture is specified, the five-primitive map is complete, the triage dashboard is wired as
a generated report, the six validation rules are executable, and the first relationship-posture
brief proves the concept for one real tie (Derek). The remaining lift to 30% (entering building
stage):

1. **Complete the engagements fleet** with 3–5 diverse relationship types — family tie,
   collaborative network member, community context — each validated by Rules #1–6.
2. **Wire the cadence engine** as a recurring beat — Workflow 3 (Care Cadence → Calendar)
   running on a daily cadence, producing a structured calendar artifact from engagement posture records.
3. **Operationalize boundary enforcement** as a structural check — Workflow 5 (Boundary → Enforcement)
   running as an automated preflight on every deliverable before it reaches the human.

### Validation

```bash
# Validate the fleet against all six social organ rules
python organs/social/validate-social.py --fleet

# Generate a relationship-posture brief for any engagement
python organs/social/scripts/relationship-brief.py organs/social/engagements/derek.yaml

# Generate the fleet-wide triage dashboard
python organs/social/scripts/triage-dashboard.py
```

### Target build surface (scaffold-complete set)

```
organs/social/
  KERNEL.md               -- 5-primitive kernel, boundary, architecture
  CHARTER.md              -- this file: org-chart, workflows, I/O, leverage
  seed.yaml               -- organ declaration for the cursus honorum
  validate-social.py      -- Rules #1–6: every engagement must pass all six
  MACRO-FACE.md           -- the community + relationship infrastructure platform
  MICRO-FACE.md           -- Anthony's live instance
  engagements/            -- per-tie relationship-posture records
    <identifier>.yaml     -- five-primitive posture record (Member, Mandate, Standing, Standard, Governance)
    <identifier>-brief.md -- generated human-readable relationship-posture brief
  scripts/
    triage-dashboard.py    -- W2: generates fleet-wide triage view sorted by standing priority
    relationship-brief.py  -- W1: generates human-readable posture brief from engagement YAML
```

The micro instance (Anthony's network) proves the platform. The macro platform (this directory
tree minus the engagement contents) is the portable standard any operator can adopt.

## Future scaling (non-blocking, noted for later maturity bands)

When the organ reaches building stage (30%+):

- **Multi-network support**: the same workflow stack runs against N personal networks simultaneously
  (Anthony's network, a family network, a community network), each with its own registry, triage,
  care calendar, and boundary scope.
- **Relationship archive**: structured closeout records for ties that have ended or transitioned —
  what the tie was, what care was given, why it changed, any unresolved obligations. The record
  the next phase starts from.
- **Calendar integration**: export the care calendar to a personal calendar (iCal/ICS) so the human
  sees care reminders alongside other commitments — always review-only, never auto-scheduled.
- **Network graph**: a lightweight map of ties and introductions — who knows whom, who was introduced
  by whom, where introductions would strengthen the network — surfaced as an advisory pattern,
  never as a social score.
- **Community templates**: reusable community rulebook templates (neighborhood association, creative
  collective, mutual-aid network, family system) that accelerate setup for common community types.
- **Relationship health trends**: standing trajectory per tie over time — drifting, strengthening,
  stable — surfaced by the Network Strategist as a periodic review.
- **Multi-human**: support for shared community infrastructure where multiple humans hold the same
  community rulebook but each owns their own personal relationships within it.

All future builds preserve the invariant: no autonomous outreach, no manipulation, no scoring of
human worth, and the human remains the final authority for every relational act.

## Constraint registry

| Constraint | Why | How it's enforced |
|---|---|---|
| No autonomous outreach | Relationships require consent and human presence; automated contact damages trust | Consent Sentinel blocks every output path to external communication; no workflow produces an autonomous send |
| No manipulation | People are not funnels, pressure targets, parasocial assets, or status tokens | Overreach patterns are explicitly checked in validation (Rule #5); KERNEL.md is prepended to every workflow prompt |
| Consent is structural | Private relationship facts must never leak; sharing requires explicit permission | Boundary Steward enforces per-person and per-community consent rules before any output reaches the human |
| Boundaries outrank cadence | If a boundary says no contact, no reminder about that person may reach the human | Consent Sentinel checks every deliverable against active boundaries before delivery; boundary violations block the entire output |
| Posture is diagnostic, not a score | Tie strength guides attention; it is never a measure of a person's worth | Standing labels are descriptive states (active, warm, dormant, strained, broken, protected); no numeric scores, no ranking |
| Community governance belongs to the community | The organ can draft rules and surface conflicts; it does not appoint itself as authority | Community Clerk role explicitly prevents autonomous governance acts; all rules and decisions require human ratification |
| No therapy, counseling, or mediation | The organ is relationship-stewardship infrastructure, not a clinical or social-work platform | Boundary in the charter header; no workflow produces therapeutic or diagnostic claims |
| Human owns every output | The human is the final authority for every relational act | Every deliverable is explicitly advisory, marked as review-required, and stops at the human terminal |

All constraints are non-negotiable. They are the load-bearing walls of this organ.

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`MACRO-FACE.md`](MACRO-FACE.md) (platform thesis), [`MICRO-FACE.md`](MICRO-FACE.md)
(Anthony's live instance).*
