# TABVLARIVS Writer Audit

<!-- tabularius-writer-audit:zero-unauthorized -->

Unauthorized lifecycle writers: `0`

## Authorized Projection Writers

| Path | Role |
|---|---|
| `cli/src/limen/io.py` | noncanonical local cache/export serializer; no lifecycle authority |
| `web/worker/src/conduct/projection.js` | sole lifecycle writer; authenticated remote GitHub SHA-CAS |

## Unauthorized Findings

| Path | Line | Kind | Call | Function |
|---|---:|---|---|---|
| (none) |  |  |  |  |

## Predicate

```bash
python3 scripts/task-writer-audit.py --enforce-zero
```

The predicate is a zero gate, not a baseline ratchet. It scans production Python, shell, Cloudflare
Worker JavaScript, and canonical agent instructions. TABVLARIVS itself is scanned and has no local
projection exemption. Derived inspection/exports may use the noncanonical serializer or an exact-line
sandbox marker, but lifecycle mutation must submit immutable tickets or conduct packets and wait for
the remote keeper receipt.

Projection authority is not default-branch bypass authority. The keeper publishes only through the
stable `tabularius/board-projection` branch and its exact-head PR; the repository merge queue
serializes the synthetic `merge_group`, and no agent, automation, or admin path may push `main`
directly.
