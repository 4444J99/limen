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

On 2026-08-10, the public status endpoint reported **3,111 total tasks** and **1,357 completed
tasks**. These are an exact, dated snapshot—not a forecast, a reliability rate, or a measure of
customer use. Reproduce them with `python3 scripts/flagship-evidence.py --verify-live --json`.

## Authorship and limitations

The system is architected and directed through a governed multi-agent production process; machine
assistance is central and disclosed. Public task records demonstrate internal operation, not an
external adoption, revenue, or manual-authorship claim.

## Withdrawal route

If the endpoint, workflow, or metric no longer validates, withdraw the numeric sentence from
public use, preserve the dated record, and refresh the machine-readable index before republishing.
