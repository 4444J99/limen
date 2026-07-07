# Mail Story Ledger

Redacted control-plane view over the local mail story corpus. Raw/private atoms stay in the ignored
`.limen-private/mail-story/` cartridge; this tracked report keeps only counts, domains, hashes,
cluster ids, and synthesized pain-point theses.

## Snapshot

- Generated: `2026-07-07T20:04:40Z`
- Source: Apple Mail Envelope Index, opened read-only.
- Processed scope: `all`
- Body/thread reads: `false`
- Mailbox mutations: `false`
- Private atom store: `.limen-private/mail-story/inventory/mail-story-atoms.jsonl`

## Corpus Counts

- Total indexed messages: `82042`
- Non-deleted messages: `82042`
- Flagged non-deleted messages: `127`
- First received: `2008-09-22 02:30:28`
- Last received: `2026-07-07 19:42:59`
- Atoms emitted in this run: `500`

## Pain Point Clusters

| cluster | type | atoms | priority | next actions | software thesis |
| --- | --- | --- | --- | --- | --- |
| Billing continuity | billing | 463 | 4690 | human_review:463 | A custody layer should turn billing and renewal mail into one verified account-continuity queue. |
| Uncategorized pressure | other | 16 | 175 | read_thread:16 | A story-mining workflow should park ambiguous mail with evidence and a next read action. |
| Infrastructure and domain custody | infra | 8 | 140 | human_review:8 | An operator custody ledger should unify infra notices, owners, renewals, and blast-radius state. |
| Debt and default navigation | debt | 3 | 105 | human_review:3 | A debt-navigation copilot should map notices into verified options, deadlines, and escalation paths. |
| Identity and compliance gates | identity | 1 | 85 | human_review:1 | A compliance dossier should collect requests, evidence, deadline state, and safe verification routes. |
| Security and fraud risk | security | 1 | 85 | human_review:1 | A verify-first security queue should route alerts through safe channels and preserve audit receipts. |
| Platform and developer ecosystem intelligence | platform | 4 | 70 | product_research:4 | A platform-intelligence digest should cluster vendor signals into product and risk theses. |
| Career routing | career | 2 | 50 | product_research:2 | A career router should score fit, extract next steps, and preserve opportunity history. |
| Relationship and personal administration | relationship | 1 | 40 | product_research:1 | A relationship memory layer should separate human context from institutional noise. |
| Life and creative logistics | creative_life | 1 | 25 | product_research:1 | A life-logistics layer should connect tickets, commitments, receipts, and story context. |

## Top Sender Domains In Processed Scope

| domain | messages |
| --- | --- |
| github.com | 461 |
| linkedin.com | 5 |
| doordash.com | 3 |
| notify.cloudflare.com | 3 |
| account.chime.com | 2 |
| update.one.app | 1 |
| awesomenyc.org | 1 |
| customers.instacartemail.com | 1 |
| thefloweryny.com | 1 |
| insideapple.apple.com | 1 |
| e.atlassian.com | 1 |
| email.apple.com | 1 |
| telehealth.netsmartcloud.com | 1 |
| alerts.santander.us | 1 |
| onedrive.com | 1 |
| s.usa.experian.com | 1 |
| email.informeddelivery.usps.com | 1 |
| app.collabwriting.com | 1 |
| ollama.com | 1 |
| socket.dev | 1 |

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
