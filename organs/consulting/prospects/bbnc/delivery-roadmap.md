# Alpha-to-Omega delivery roadmap

Each phase is a separately accepted work package. Passing one phase authorizes only the next named
package; it never grants blanket authority for later work.

| Phase | Delivery slice | Exit predicate |
|---|---|---|
| 0 | Commission, ownership, authority | BBNC-owned executed charter, RACI, data boundary, authority statement, acceptance process, and delivery-account receipt |
| 1 | Current-state discovery and baseline | BBNC-approved authority map, service blueprint, data map, content/URL inventory, top journeys, baselines, risk register, and v1 requirements |
| 2 | Product, UX, architecture contract | Signed requirements, one selected visual system from exactly three accessible directions, tested prototypes, authorization matrix, ADRs, threat model, applicability matrix, and release plan |
| 3 | BBNC-owned foundation | Clean-checkout setup, green CI, staging deployment, denial tests, signed artifacts, and successful backup/restore |
| 4 | Stewardship Alpha in shadow mode | Decisions match BBNC owners, every transition is attributable and authorized, zero restricted data ingested, and evidence export verifies independently |
| 5 | Stewardship Beta and production | BBNC operators can run the platform, zero unresolved critical/high findings, SLO and recovery tests pass, and release authority signs v1 |
| 6 | BBNC.net Alpha | One critical shareholder-deadline journey and one Stewardship-originated public release work in production-equivalent staging with accessibility, security, telemetry, and rollback evidence |
| 7 | BBNC.net Beta and migration | Feature-complete staging, owner-signed content inventory, terminal redirect ledger, representative user testing, trained editors, and production-like operations |
| 8 | Release candidate and cutover | Exact release, signed package, redirects, accessibility, SEO, performance, receipts, restore, rollback, and BBNC approvals all pass |
| 9 | Production, hypercare, Omega | Ninety days within SLO, no unresolved P1/P2 or expired exception, successful restore and access review, measured outcomes, and no undocumented Padavano dependency |

## First live vertical slices

Stewardship Alpha proves this complete chain in shadow mode:

```text
content proposal -> value/risk screen -> generated gates -> review -> revision
  -> approval -> evidence -> staged publication package -> release -> outcome owner
```

Representative public content includes a news article, event, service or deadline, leadership
update, and company profile. The exercise covers rejection, changes requested, delegation expiry,
recusal, approval invalidation, inaccessible evidence, media-rights review, rollback, withdrawal,
and audit export.

BBNC.net Alpha proves one current shareholder deadline journey from plain-language preparation to a
monitored myBBNC handoff, plus one public initiative/story release originating in Stewardship. It
must retain last-known-good content during internal-platform or feed outages and remain usable under
low bandwidth.

## Migration and cutover controls

- Start discovery from a BBNC-authorized WordPress database/uploads export; do not infer inventory
  completeness from the public API.
- Every legacy URL receives one terminal disposition: `migrate`, `merge`, `archive`, `externalize`,
  `redirect`, or `approved gone`.
- Preserve originals while hashing and deduplicating media; require alt text, captions/transcripts,
  rights/consent state, and culturally appropriate publication approval.
- Standardize monitored handoffs to myBBNC, ATS products, BBNCVote, forms, foundation, business
  directory, and subsidiary sites.
- Do not cut over from ten business days before through two business days after a distribution,
  enrollment, annual-meeting, or proxy deadline without BBNC emergency approval.
- Preserve the WordPress origin read-only for 30 days.
- Promote blue/green at 5% for 30 minutes, 25% for 60 minutes, then 100%.
- Roll back on repeated critical synthetic failure, content-integrity failure, deployment-health
  failure, or five minutes of 5xx above 1%.

## Omega transfer

Padavano supplies 24/7 P1 coverage for the first 72 hours, daily review for seven days, and a 30-day
launch report only if those terms are accepted in the relevant work package. BBNC receives runbooks,
ADRs, inventories, dashboards, recovery instructions, training, and credentials. Two BBNC operators
must independently publish, deploy, restore, and roll back. At the 90-day review, routine Padavano
privileged access is removed.

Expansion requires a new BBNC-approved initiative. The proposed order is non-sensitive outcome
reporting, then corporate giving. Authenticated shareholder-portal modernization requires its own
data, legal, vendor, and threat-model program.
