# Limen — Public Evidence Packet

## Bounded claim

Limen is a governed multi-agent delivery system with public operating, failure, and verification
receipts. This packet establishes public operational evidence only; it does not claim customer
adoption, revenue, or zero-maintenance operation.

## Inspectable evidence

- Architecture and governance: [public source](https://github.com/organvm/limen).
- Exact-head verification: [successful workflow run](https://github.com/organvm/limen/actions/runs/31404705695)
  at `d169c7d8ad9fc8f75d7e9200658758b2715eae97`.
- Operating snapshot: [public status JSON](https://limen-dashboard.pages.dev/public-status.json).

## Dated metrics

- The public dashboard reported 3,111 total tasks on 2026-08-10.
- The public dashboard reported 1,357 completed tasks on 2026-08-10.

These are an exact, dated snapshot—not a forecast, a reliability rate, or a measure of customer
use. Reproduce them with `python3 scripts/flagship-evidence.py --verify-live --json`.

## Authorship and limitations

Architected and directed through a governed multi-agent system; machine assistance is disclosed,
not concealed.

- The public dashboard is an operational snapshot, not customer-adoption evidence.
- Counts may change after the observation timestamp and must be refreshed before reuse.

## Withdrawal route

If the endpoint, workflow, or metric no longer validates, withdraw the numeric sentence from
public use, preserve the dated record, and refresh the machine-readable index before republishing.

## Reader-mode claim ledger

This section connects the historical flagship packet above to the canonical
[`project-record.yml`](../../../project-record.yml) and its audience editions. Status terms here are
claim-level judgments: `verified`, `partial`, `proposed`, `unknown`, and `contradicted`.

| Claim | Status | Inspectable support | Boundary |
|---|---|---|---|
| The checked tree implements versioned work packets, leases, role-bound conduct, resource conflict rules, fencing, and terminal receipts. | `verified` | `cli/src/limen/conduct/`, `spec/contracts/conduct/`, and focused conduct tests | Source and deterministic tests do not substitute for a fresh authenticated production canary. |
| Owner, QA, client, and public surfaces enforce different persona and disclosure contracts. | `verified` | `web/api/main.py`, `web/worker/src/index.js`, and their test suites | No formal security certification is claimed. |
| A public dashboard and Worker health endpoint are deployed. | `verified` as of 2026-08-31 | `https://limen-dashboard.pages.dev/public-status.json` and `https://limen-runtime.ivixivi.workers.dev/health` returned `status: ok` | Reachability at one observation time is not an SLA or customer deployment. |
| Limen operates in the owner's environment. | `verified` within the project's owner-record and public-evidence policy | Historical exact-head workflow and public operating packet; current Worker health reports configured writable private keeper storage | Internal operation is not customer adoption and protected operations cannot be reproduced from the public projection. |
| Limen is deployed in external customer organizations. | `unknown` | No public customer or deployment receipt is present in this record | Do not claim adoption, revenue, retention, or ROI. |
| Multi-agent governance for engineering teams, consultancies, and research engineering groups is an applicable use. | `proposed` | Mechanism-to-workflow analysis in `docs/audiences/business.md` | These are application hypotheses, not industry deployments. |
| The repository is MIT-licensed and open source. | `contradicted` in the verified tree | The README previously displayed an MIT badge, but no `LICENSE` file is present and GitHub's repository record reports `license: null` | Source is publicly inspectable; reuse rights remain unresolved until a license is explicitly committed. |

Machine-readable assertion records live in
[`docs/positioning/evidence/assertions/`](assertions/). Each material route in the project record
references an `assertion-evidence.v1` object rather than restating a second machine claim.

## Freshness note

The two numeric sentences in **Dated metrics** are preserved as an historical 2026-08-10 snapshot
because the flagship verifier binds them to that packet. On 2026-08-31 the public endpoint returned
a different redacted projection: `total: 0`, `completed: 0`, generated
`2026-08-20T23:21:16.041Z`. The historical values must not be described as current. The changed
projection also cannot be interpreted as evidence that protected internal operation stopped.

## Reader routes

- [General explanation](../../audiences/general.md)
- [Technical architecture](../../audiences/technical.md)
- [Humanities interpretation](../../audiences/humanities.md)
- [Operational and business edition](../../audiences/business.md)
- [Evaluator guide](../../audiences/evaluator.md)
