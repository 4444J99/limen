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
