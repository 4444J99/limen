# PSP-P02 Flagship Evidence Packets

This directory contains the public-safe evidence packets for the three flagships selected by
[`../flagship-proof-set.yaml`](../flagship-proof-set.yaml). Each packet is independently readable:
it gives the bounded claim, public source and deployment anchors, a dated metric where one is
material, implementation evidence, limitations, authorship treatment, and withdrawal route.

`flagship-evidence.yaml` is the machine-readable index. Run:

```bash
python3 scripts/flagship-evidence.py --verify-live --json
```

The command verifies public sources only. A changed live value intentionally fails the exact
snapshot comparison until a reviewer refreshes the dated packet and its ledger row. That prevents
old numbers from silently acquiring a new observation date.

No packet needs a private repository, private path, customer data, or private-only source to make
its claim understandable. The encrypted-addendum field is deliberately `not_created`; any future
diligence material must use the existing custody interface and remain out of this public-safe
directory.

## Dependency boundary

These are implementation preflight artifacts. They do not close W04 or W05: W04 remains gated on
the receipt-verified W03, and W05 remains gated on the receipt-verified W04. See the dependency
gate in the index and the continuation relay for the formal sequence.
