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
same source-backed record can render a private dossier, a creator presence
preview, a public page draft, a submission packet, a collaboration packet, a
market-fit packet, or a co-branded project page.

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

## Literary Intake Contract

Literary intake remains inside `organs/representation/`. The canonical no-send
CLI shape is:

```bash
python organs/representation/representation_substrate.py literary-packet \
  --writer organs/representation/records/christopher-author-one.yaml \
  --opportunity organs/representation/opportunities/literary-submission-landscape.yaml \
  --candidate chris-public-profile-readiness \
  --route submittable-discover-route
```

The packet combines writer public/profile evidence, a metadata-only
`candidate_works` entry, opportunity context, and selected route metadata.
Candidate metadata may name genre, form, length, status, rights status, and a
source/content ref, but it must not store manuscript text, raw excerpts,
private messages, contact data, or fabricated details.

Submission routes keep `guidelines_url`, `deadline`, `word_limits`, `fee`,
`pay`, `ai_policy_disclosure_status`, and `ai_policy_source_ids`. Missing route
fields remain review gaps. Unsourced or unresolved AI-policy disclosure remains
a blocker, even when the rest of the venue fit is present.

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

## Validation

```bash
python organs/representation/validate-representation.py --fleet
python organs/representation/representation_substrate.py packet organs/representation/records/christopher-author-one.yaml --mode writer_submission
python organs/representation/representation_substrate.py packet organs/representation/records/et4l.yaml --mode project_page
```
