# Representation Substrate - KERNEL

> Boundary: this organ stages representation. It can gather evidence, model
> relationship posture, draft packets, and preview public surfaces. It does not
> publish, submit, contact, claim agency, or expose private material without an
> explicit approval gate.

## Why This Organ Exists

Creator representation is usually split across private history, public proof,
work provenance, relationship context, market fit, and web presence. The
substrate turns those fragments into one consent-gated record: every claim has
sources, every output names its mode, and every outward surface is locked until
the represented subject approves it.

The first mode is literary submission support, but that is only one mode. The
same source-backed record can render a canon dossier, public presence draft,
authority scorecard, private dossier, creator presence preview, public page
draft, submission packet, collaboration packet, market-fit packet, or
co-branded project page.

## Core Schema

Each representation record uses these shared primitives:

| Field | Meaning |
|---|---|
| `subject` | Person, creator, collaborator, project, venue, or opportunity being represented |
| `works` | Authored, creative, project, exhibition, publication, or distribution artifacts |
| `candidate_works` | Metadata-only work candidates for submission, packet, or venue-fit review |
| `relations` | Collaborations, shared history, consent constraints, and posture references |
| `claims` | Generated statements; each must be source-backed and visibility-scoped |
| `sources` | Local repo, remote repo, public web, messages, user assertion, or confirmed subject evidence |
| `approvals` | Public export, co-branded page, submission, outreach, or project-page gates |
| `outputs` | Renderable packets or pages produced from the same source-backed record |
| `authority_program` | Civilizational-gravitas program axes for canon, readership, and hybrid public presence |

## Source Contract

Report-grade records and outputs must include all three non-negotiable evidence
planes:

- `local_repo`: live local evidence, usually organ or project files
- `remote_repo`: canonical remote repository, issue, PR, or release evidence
- `web`: public web evidence

Message evidence is required only when a record makes private relational,
persona, or collaboration-posture claims. Message sources are private or
sensitive by default and may never store raw excerpts, contact data, or direct
quotes in tracked files.

## Mode Contract

Renderers are modes over one schema, not separate products:

- `canon_dossier`
- `public_presence_draft`
- `authority_scorecard`
- `private_dossier`
- `creator_presence_preview`
- `public_page_draft`
- `writer_submission`
- `market_fit`
- `collaboration_packet`
- `project_page`
- `co_branded_page`

Private renderers can include private source notes and private claim summaries.
Public-facing renderers only include claims supported by public sources or
claim-level approval. Private message-derived claims require claim-level
approval before any public renderer may show them.

## Authority Program Contract

Authority work remains inside `organs/representation/` as a canon and public
presence apparatus joined to the artist, media, positioning, and publication
policy organs. It is not a new `organs/literary` surface.

Records that declare authority modes must include `authority_program` with
`goal: civilizational_gravitas` and exactly three axes:

- `canonical_institution`
- `mass_readership`
- `hybrid_presence`

The archetype functions are institutional gravity and mass readership: they
name the apparatus to build over time, not a status equivalence to Stephen King,
T. S. Eliot, or any other figure. Axis copy can reference only declared
`claim_ids`. Public-facing axis copy must use public-source claims or
claim-approved private claims through `public_claim_ids`.

The authority scorecard reports each axis as `BLOCKED`, `STAGED`, or
`PUBLIC_READY` from source-backed claims, public-renderable proof, output gates,
and approval state. It must report blockers instead of claiming achieved
civilizational status.

The combined packet command is review-only:

```bash
python organs/representation/representation_substrate.py authority-packet \
  --record organs/representation/records/christopher-notarnicola.yaml
```

It renders the canon dossier, public presence draft, authority scorecard,
blockers, source appendix, and approvals required. It does not publish, submit,
upload, contact, mine private material, or act outward.

## Handoff Audit Contract

The old application pipeline's useful shape is preserved here as a literary and
public-presence loop:

- scan: source-backed venue routes, guideline fields, deadlines, fees, pay, and
  AI-policy posture;
- match: writer proof, candidate-work metadata, and route constraints rendered
  as a fit check;
- build: dossiers, public drafts, authority scorecards, and no-send literary
  packets;
- apply: approval-gated dry runs first, then `publication-send` only when an
  explicit `real_send` approval names the selected writer, opportunity,
  candidate, route, adapter, recipient ref, and payload ref;
- follow up: blockers and approvals required become the next work surface.

Before a record is handed to Chris or used as the basis for outward literary
work, run the handoff audit:

```bash
python organs/representation/representation_substrate.py handoff-audit \
  --writer organs/representation/records/christopher-notarnicola.yaml \
  --opportunity organs/representation/opportunities/literary-submission-landscape.yaml \
  --candidate chris-public-profile-readiness \
  --route yale-review-nonfiction-route
```

The audit distinguishes broken features from honest gates. A missing manuscript
source ref, unresolved approval, or venue-specific blocker is a gate. A schema
violation, renderer crash, public privacy leak, or unlocked export is broken and
blocks handoff. The audit does not submit, publish, upload, contact, mine
private messages, or represent AI-generated text as human work.

## Publication Readiness Contract

`publication-readiness` is the no-drudgery publication packet. It renders the
current state for one writer, one `candidate_works` id, and one route:

```bash
python organs/representation/representation_substrate.py publication-readiness \
  --writer organs/representation/records/christopher-notarnicola.yaml \
  --opportunity organs/representation/opportunities/literary-submission-landscape.yaml \
  --candidate chris-metadata-only-nonfiction-candidate \
  --route yale-review-nonfiction-route
```

The report is Chris-facing: it states what the packet is, what works now, what
is still gated, and how private refs, voice, approval, and real sends are
controlled. It may say a private content ref is recorded, but it must not print
the private ref, local paths, contact data, raw manuscript text, or private
message refs.

A candidate may use `status: READY_FOR_REVIEW` only when genre, form, length,
rights status, content ref, source IDs, and claim IDs are all present. Route
readiness requires public guideline source refs and sourced, resolved AI-policy
status. Dry-run export additionally requires writer public-export approval,
writer submission approval, and opportunity submission approval. Real submission
uses `publication-send`; it requires the same dry-run approvals plus an approved
`real_send` record. Local outbox execution writes a receipt. Direct email
execution sends through SMTP using runtime sender/recipient env vars, optional
private payload path, and SMTP settings supplied at execution time; receipts
redact those runtime values.

## Literary Intake Contract

Literary intake remains inside `organs/representation/`. The canonical no-send
CLI shape is:

```bash
python organs/representation/representation_substrate.py literary-packet \
  --writer organs/representation/records/christopher-notarnicola.yaml \
  --opportunity organs/representation/opportunities/literary-submission-landscape.yaml \
  --candidate chris-public-profile-readiness \
  --route submittable-discover-route
```

The packet combines writer public/profile evidence, a metadata-only
`candidate_works` entry, opportunity context, and selected route metadata.
Candidate metadata may name genre, form, length, status, rights status, and a
source/content ref, but it must not store manuscript text, raw excerpts,
private messages, contact data, or fabricated details.

Use `candidate-intake` to stage a real candidate only after a source/content ref
exists:

```bash
python organs/representation/representation_substrate.py candidate-intake \
  --id candidate-with-source-ref \
  --title "Sourced candidate manuscript" \
  --content-ref source://private-manuscripts/chris/candidate-001 \
  --source-id subject-confirmed-candidate-ref \
  --claim-id chris-public-writing
```

The command prints a YAML snippet for reviewer insertion. It does not read or
copy the manuscript. Chris remains blocked on `Content/source ref` until such a
metadata-only row is intentionally attached.

Submission routes keep `guidelines_url`, `deadline`, `word_limits`, `fee`,
`pay`, `ai_policy_disclosure_status`, `guidelines_source_ids`, and
`ai_policy_source_ids`. Venue-specific routes must cite public guideline
sources. Missing route fields remain review gaps. Unsourced or unresolved
AI-policy disclosure remains a blocker, even when the rest of the venue fit is
present.

## Organ Bridges

The representation substrate does not duplicate the surrounding organs:

- Koinonia supplies relationship and collaboration posture.
- The artist organ supplies work, provenance, and exhibition logic.
- The media organ supplies staged public distribution.
- Positioning and inbound systems supply opportunity and public-proof logic.
- Publication Policy supplies privacy and visibility gates.

Chris remains the first full literary proof. ET4L is the second proof: a
non-writer artist/project record proving the substrate is not secretly only a
submission desk.

The authority program applies to all first proofs:

- ET4L: body of work, provenance, exhibition argument, and public project proof.
- Chris: public writing record, editorial/theatre proof, submission blockers,
  and private collaboration context withheld from public copy.
- Generic authority template: reusable axes and output modes for future artists.

## Validation

```bash
python organs/representation/validate-representation.py --fleet
python organs/representation/representation_substrate.py handoff-audit --writer organs/representation/records/christopher-notarnicola.yaml --opportunity organs/representation/opportunities/literary-submission-landscape.yaml --candidate chris-public-profile-readiness --route yale-review-nonfiction-route
python organs/representation/representation_substrate.py authority-packet --record organs/representation/records/christopher-notarnicola.yaml
python organs/representation/representation_substrate.py publication-readiness --writer organs/representation/records/christopher-notarnicola.yaml --opportunity organs/representation/opportunities/literary-submission-landscape.yaml --candidate chris-metadata-only-nonfiction-candidate --route yale-review-nonfiction-route
python organs/representation/representation_substrate.py publication-send --writer organs/representation/records/christopher-notarnicola.yaml --opportunity organs/representation/opportunities/literary-submission-landscape.yaml --candidate chris-metadata-only-nonfiction-candidate --route yale-review-nonfiction-route --approval-record organs/representation/approvals/chris-yale-review-nonfiction-real-send.template.yaml
python organs/representation/representation_substrate.py packet organs/representation/records/christopher-notarnicola.yaml --mode writer_submission
python organs/representation/representation_substrate.py packet organs/representation/records/et4l.yaml --mode project_page
```
