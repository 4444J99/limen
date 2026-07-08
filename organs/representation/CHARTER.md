# Representation Substrate - CHARTER

## What It Rivals

A creator agency, studio CRM, publication desk, publicist, collaborator memory
office, and portfolio studio. The substrate gives a creator institutional
representation without taking over their voice or outward choices.

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
| Privacy Sentinel | Blocks raw excerpts, contact data, creative text, and unapproved public claims | Blocks by default |

## First Proofs

Christopher Author-One is the first full record and the first
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

## Output Modes

The same representation record can render:

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

Venue and route records keep the review fields beside the opportunity:
`guidelines_url`, `deadline`, `word_limits`, `fee`, `pay`, and
`ai_policy_disclosure_status` with `ai_policy_source_ids`. Unsourced or
unresolved AI-policy status is a blocker, especially for venue-specific routes.

## Executable Proof

```bash
python organs/representation/validate-representation.py --fleet
python organs/representation/representation_substrate.py packet organs/representation/records/christopher-author-one.yaml --mode writer_submission
python organs/representation/representation_substrate.py packet organs/representation/records/et4l.yaml --mode project_page
PYTHONPATH=cli/src python3 -m pytest cli/tests/test_representation_substrate.py -q
```
