# Representation Substrate - CHARTER

## What It Rivals

A creator agency, studio CRM, publication desk, publicist, collaborator memory
office, portfolio studio, canon dossier desk, and public-presence authority
apparatus. The substrate gives a creator institutional representation without
taking over their voice or outward choices.

## Roles

| Role | Does | Gate |
|---|---|---|
| Subject | Owns voice, work, approvals, and public representation | Final authority |
| Evidence Librarian | Builds source appendices across local, remote, web, and authorized messages | Human reviews evidence scope |
| Relationship Steward | Imports collaboration posture from Koinonia without leaking private context | Consent and privacy gate |
| Provenance Clerk | Imports work, exhibition, and artifact state from the artist organ | Subject confirms provenance |
| Opportunity Analyst | Tracks markets, venues, collaborators, and public-proof fit | Subject chooses where to act |
| Packet Clerk | Stages dossier, submission, collaboration, and project packets | No send without approval |
| Presence Editor | Renders private previews and approved public copy | Public export approval required |
| Authority Clerk | Scores canon, readership, and hybrid public presence axes | Reports blockers instead of achieved status |
| Privacy Sentinel | Blocks raw excerpts, contact data, creative text, and unapproved public claims | Blocks by default |

## First Proofs

Christopher Notarnicola is the first full record and the first
`writer_submission` mode proof. One Chris record must support:

- local repo evidence from Studio, Speech Score, Limen, or relationship-pipeline surfaces;
- remote repo evidence from Object Lessons, Speech Score, Sign Signal, and planning issues;
- public web evidence from Christopher's site, publication pages, editorial roles, and theatre pages;
- metadata-only `candidate_works`, starting with a public/profile readiness candidate until a real manuscript source ref exists;
- optional authorized message evidence, stored only as source refs and non-sensitive notes;
- approval-gated public copy.

ET4L is the second proof and the first non-writer project record. It uses the
artist organ's chamber record to prove the substrate can represent creative
series, exhibition logic, provenance, and project pages without becoming a
literary-only system.

The authority-program proof is all-of-the-above: canonical institution, mass
readership, and hybrid public presence are required together. ET4L proves the
artist-organ bridge; Christopher proves the writer/public-record bridge while
keeping collaboration context private; `generic-authority-template` proves the
reusable shape for future artists. This is a representation and media apparatus,
not a new `organs/literary` surface.

## Output Modes

The same representation record can render:

- canon dossier
- public presence draft
- authority scorecard
- private dossier
- creator presence preview
- public page draft
- submission or market-fit packet
- collaboration or project packet
- co-branded Object Lessons or studio page

Every output is a draft packet. The system does not send submissions, publish
pages, contact collaborators, or act outward automatically.

Packet renderers include subject summary, works, relations, source appendix
summary, approval gates, and a no-outward-action notice. Each packet is scoped to
the `claim_ids` declared by its output mode.

The `literary-packet` renderer is the literary intake bridge. It combines a
writer record, an opportunity record, one `candidate_works` id, and one selected
submission route id. Candidate work metadata and route metadata are the
canonical inputs; raw manuscript text, private messages, contact data, and
invented work details are outside the tracked substrate.

The `candidate-intake` command emits a metadata-only `candidate_works` row from
a source/content ref. It is a staging aid, not a manuscript store: it rejects
contact data and private-text markers, prints a YAML snippet, and leaves the
record blocked until a reviewer deliberately attaches the source-backed
candidate row.

Venue and route records keep the review fields beside the opportunity:
`guidelines_url`, `deadline`, `word_limits`, `fee`, `pay`, and
`ai_policy_disclosure_status` with `guidelines_source_ids` and
`ai_policy_source_ids`. Venue-specific route examples must cite public guideline
sources. Unsourced or unresolved AI-policy status is a blocker, especially for
venue-specific routes.

The `authority-packet` renderer is the canon/authority bridge. It combines a
record's `canon_dossier`, `public_presence_draft`, and `authority_scorecard`
modes with blockers, source appendix, and approvals required. It is always
review-only: no send, upload, publication, outreach, private-material mining,
or achieved civilizational-status claim occurs.

The `handoff-audit` renderer is the Chris gate and the application-pipeline
merge point. It proves the source-backed record validates, every declared output
renders, public modes do not leak private refs, the authority packet renders,
the literary desk packet renders, candidate intake remains metadata-only, mention
indexing works, and exports stay approval-locked. Gates are allowed only when
they name the missing source, metadata, approval, or route evidence. Broken
features block handoff.

The `publication-readiness` renderer is the Chris-facing publication packet. It
combines one writer, one metadata-only candidate, and one sourced route into a
fit report, cover-letter readiness row, disclosure note status, rights
checklist, and submission checklist. It withholds private content refs and local
paths, treats missing approvals as blockers, allows only approved dry-run
exports, and reports whether an explicit `real_send` approval exists.

The `publication-send` command is the execution surface. It refuses implicit
send authority, requires the writer public-export, writer submission,
opportunity-route submission, and real-send approvals for the selected candidate
and route, then attempts the selected delivery adapter. `local_outbox` writes a
local execution receipt. `direct_email` builds and sends an SMTP message from
runtime sender/recipient env vars, optional private payload path, and SMTP
settings supplied at execution time; receipts redact those runtime values.

## Executable Proof

```bash
python organs/representation/validate-representation.py --fleet
python organs/representation/representation_substrate.py handoff-audit --writer organs/representation/records/christopher-notarnicola.yaml --opportunity organs/representation/opportunities/literary-submission-landscape.yaml --candidate chris-public-profile-readiness --route yale-review-nonfiction-route
python organs/representation/representation_substrate.py authority-packet --record organs/representation/records/christopher-notarnicola.yaml
python organs/representation/representation_substrate.py publication-readiness --writer organs/representation/records/christopher-notarnicola.yaml --opportunity organs/representation/opportunities/literary-submission-landscape.yaml --candidate chris-metadata-only-nonfiction-candidate --route yale-review-nonfiction-route
python organs/representation/representation_substrate.py publication-send --writer organs/representation/records/christopher-notarnicola.yaml --opportunity organs/representation/opportunities/literary-submission-landscape.yaml --candidate chris-metadata-only-nonfiction-candidate --route yale-review-nonfiction-route --approval-record organs/representation/approvals/chris-yale-review-nonfiction-real-send.template.yaml
python organs/representation/representation_substrate.py packet organs/representation/records/christopher-notarnicola.yaml --mode writer_submission
python organs/representation/representation_substrate.py packet organs/representation/records/et4l.yaml --mode project_page
python organs/representation/representation_substrate.py candidate-intake --id candidate-with-source-ref --title "Sourced candidate manuscript" --content-ref source://private-manuscripts/chris/candidate-001 --source-id subject-confirmed-candidate-ref --claim-id chris-public-writing
PYTHONPATH=cli/src python3 -m pytest cli/tests/test_representation_substrate.py -q
```
