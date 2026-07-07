# Mail Story Ledger

Redacted control-plane view over the local mail story corpus. Raw/private atoms stay in the ignored
`.limen-private/mail-story/` cartridge; this tracked report keeps only counts, domains, hashes,
cluster ids, and synthesized pain-point theses.

## Snapshot

- Generated: `2026-07-07T19:59:25Z`
- Source: Apple Mail Envelope Index, opened read-only.
- Processed scope: `flagged`
- Body/thread reads: `false`
- Mailbox mutations: `false`
- Private atom store: `.limen-private/mail-story/inventory/mail-story-atoms.jsonl`

## Corpus Counts

- Total indexed messages: `82042`
- Non-deleted messages: `82042`
- Flagged non-deleted messages: `127`
- First received: `2008-09-22 02:30:28`
- Last received: `2026-07-07 19:42:59`
- Atoms emitted in this run: `127`

## Pain Point Clusters

| cluster | type | atoms | priority | next actions | software thesis |
| --- | --- | --- | --- | --- | --- |
| Billing continuity | billing | 32 | 380 | human_review:32 | A custody layer should turn billing and renewal mail into one verified account-continuity queue. |
| Identity and compliance gates | identity | 20 | 275 | human_review:20 | A compliance dossier should collect requests, evidence, deadline state, and safe verification routes. |
| Debt and default navigation | debt | 15 | 225 | human_review:15 | A debt-navigation copilot should map notices into verified options, deadlines, and escalation paths. |
| Relationship and personal administration | relationship | 17 | 200 | product_research:17 | A relationship memory layer should separate human context from institutional noise. |
| Legal and government accountability | legal | 9 | 150 | human_review:9 | A civic/legal organizer should translate notices into timelines, obligations, and evidence packets. |
| Uncategorized pressure | other | 13 | 145 | read_thread:13 | A story-mining workflow should park ambiguous mail with evidence and a next read action. |
| Infrastructure and domain custody | infra | 8 | 140 | human_review:8 | An operator custody ledger should unify infra notices, owners, renewals, and blast-radius state. |
| Security and fraud risk | security | 5 | 125 | human_review:5 | A verify-first security queue should route alerts through safe channels and preserve audit receipts. |
| Career routing | career | 5 | 80 | product_research:5 | A career router should score fit, extract next steps, and preserve opportunity history. |
| Platform and developer ecosystem intelligence | platform | 1 | 40 | product_research:1 | A platform-intelligence digest should cluster vendor signals into product and risk theses. |
| Life and creative logistics | creative_life | 2 | 35 | product_research:2 | A life-logistics layer should connect tickets, commitments, receipts, and story context. |

## Top Sender Domains In Processed Scope

| domain | messages |
| --- | --- |
| gmail.com | 17 |
| google.com | 13 |
| email.apple.com | 8 |
| stripe.com | 6 |
| nelnet.studentaid.gov | 6 |
| taxrise.com | 6 |
| notify.cloudflare.com | 5 |
| socket.dev | 4 |
| studentaid.gov | 4 |
| mail.anthropic.com | 4 |
| account.chime.com | 4 |
| insideapple.apple.com | 3 |
| longofirm.com | 3 |
| buytickets.at | 2 |
| stage4solutions.com | 2 |
| ceiamerica.com | 2 |
| email.legalzoom.com | 2 |
| docusign.net | 2 |
| nav.com | 2 |
| ssa.gov | 2 |

## Flagged By Mailbox

| mailbox scope | messages |
| --- | --- |
| gmail/all-mail | 115 |
| inbox | 12 |

## Flagged By Year

| year | messages |
| --- | --- |
| 2026 | 116 |
| 2025 | 10 |
| 2024 | 1 |

## Privacy Boundary

- No message body text is read by this pass.
- Full sender addresses, sender display names, subjects, summaries, and Apple row ids stay in ignored private JSON.
- The tracked report intentionally exposes only domains, counts, cluster names, and synthesized theses.
- Gmail thread enrichment is a later gated action for atoms whose `next_action` requires it.

## Commands

- Preview the hot flagged pass: `python3 scripts/mail-story-ledger.py`
- Refresh the redacted report and ignored private atoms: `python3 scripts/mail-story-ledger.py --write`
- Process all non-deleted indexed mail privately: `python3 scripts/mail-story-ledger.py --scope all --write`
