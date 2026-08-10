# PSP-C07 private-inbound preflight

Status: `PREPARED/PREFLIGHT`

Formal predecessor: `PSP-C06` / `PSP-P07` (open; no capture surface selected)

Scope: `PSP-P08-W01` through `PSP-P08-W07` contract preparation only

The current upstream C06 preflight receipts are portfolio draft
[PR #221](https://github.com/organvm-vii-kerygma/portfolio/pull/221) at
`7283219f98053aabfede5c41467c7cc1010165c3` and Limen relay
[PR #2317](https://github.com/organvm/limen/pull/2317) at
`f5c5a03749a3ec44cf7eab278735b07f841bf60a`. The portfolio head durably tracks the
manifest and exactly three source-grounded mockup PNGs; all three remain explicitly
unselected. Both receipts are `PREPARED/PREFLIGHT`, not C06 closure: operator selection
is still required, no visual implementation or deployment is authorized, 11 legacy
`organvm.github.io/portfolio` links remain dead, and the canonical
`organvm-vii-kerygma/portfolio` paths resolve.

This package prepares the reversible, privacy-sensitive interior of the inbound funnel without
choosing, wiring, or publishing a public capture surface. It consumes two capture-neutral envelope
shapes—tagged mail and form submission—so the later C06 decision can bind either path without
rewriting normalization, scoring, routing, draft, or ledger semantics.

## Prepared flow

```text
selected C06 capture surface (not yet selected)
  -> tagged_mail | form_submission adapter
  -> minimal normalized lead record
  -> deterministic fit score + uncertainty margin
  -> client | recruiter | operator | spam | manual-review route
  -> non-authoritative draft
  -> owner-partitioned private opportunity ledger adapter
  -> aggregate-only public receipt + labeled synthetic routing evaluation
```

The tracked fixture set is wholly synthetic. Reserved `.invalid` addresses, synthetic owner
partitions, placeholder surfaces, and synthetic proof tags prevent fixture data from becoming
real-world lead evidence. The traversal receipt exposes synthetic-only opaque record IDs,
classifications, routes, stages, counts, and the zero-send counter only; names, addresses, requests,
draft bodies, and ledger rows never enter its public projection.

## Leaf preparation map

| Leaf | Prepared artifact | Formal boundary retained |
|---|---|---|
| `PSP-P08-W01` · `gpt-5.6-terra/high` | source/proof/audience tag contract and tagged-mail adapter | no alias, CTA, deliverability, or public address activation |
| `PSP-P08-W02` · `gpt-5.6-sol/xhigh` | minimal contact/request/consent field contract and overcollection denylist | no public form or selected C06 surface |
| `PSP-P08-W03` · `gpt-5.6-sol/xhigh` | idempotent normalizer, dedupe key, synthetic fixtures, private-storage adapter boundary | no provider mail or real lead payload |
| `PSP-P08-W04` · `gpt-5.6-terra/high` | declared signals, thresholds, margin rule, and manual-review fallback | scores remain suggestions, never authority |
| `PSP-P08-W05` · `gpt-5.6-luna/medium` | draft-family selection and hard-closed send valve | no send capability; `HG-PUBLICATION-SEND` remains unpulled |
| `PSP-P08-W06` · `gpt-5.6-sol/xhigh` | owner-partitioned in-memory ledger contract and aggregate projection | no real ledger owner or private record is committed here |
| `PSP-P08-W07` · `gpt-5.6-sol/xhigh` | client/recruiter plus operator/spam/ambiguous synthetic traversal | synthetic proof is not a leaf or phase receipt |

These are the exact live-registry assignments observed on 2026-08-10. They are recorded for later
leaf dispatch; this conductor preflight does not impersonate those separately leased executions.

## Integration contract

After the operator selects one of the three grounded directions, C06 performs its separately
authorized implementation, fixes or redirects the 11 legacy links, and P07 closes with its
predicate-backed receipt, a separately leased C07 leaf may update the
contract with the selected capture surface and implement one repository-owned adapter. That adapter
must emit the exact common envelope represented here. Integration must keep the following invariant:

```text
capture may be live only when dependency receipt + selected surface + leaf authority are all present;
send remains a separate human-gated capability and is not granted by capture activation.
```

The later repository owners remain those in `program.yaml`: Limen for tags and scoring,
`organvm/universal-mail--automation` for mail normalization and drafts, and
`organvm-iii-ergon/collaboration-operations-platform` for the private opportunity ledger. W02's
manifest target still says `organvm/portfolio`, while the verified C06 receipt names
`organvm-vii-kerygma/portfolio` as canonical; the later W02 lease must reconcile that registry owner
before mutation. This preflight deliberately creates no shared generated index and writes no
cross-repository state.

## Verification

```bash
python3 scripts/positioning-private-inbound-preflight.py --mode validate --json
python3 scripts/positioning-private-inbound-preflight.py --mode traverse --json
python3 -m unittest discover -s scripts/tests -p 'test_positioning_private_inbound_preflight.py'
```

`--mode live-gate` is expected to exit `2` while C06/P07 is open and no capture surface is selected.
That result is the intended fail-closed preflight behavior, not a verification failure.

No PSP leaf or phase may close from this package. Its purpose is to make the later dependency-bound
integration smaller, testable, and privacy-preserving.
