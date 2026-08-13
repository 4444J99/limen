# PSP-C07 private-inbound preflight

Status: `PREPARED/PREFLIGHT`

`counts_as_closure: false` — this package is a reversible preflight, never a P08 or leaf receipt.

Chunk predecessor: `PSP-C06`. Formal P08 phase dependencies: `PSP-P04` and `PSP-P07`; both remain
open, and no capture surface is selected.

Scope: `PSP-P08-W01` through `PSP-P08-W07` contract preparation only

The current upstream C06 preflight packages are merged: portfolio
[PR #221](https://github.com/organvm-vii-kerygma/portfolio/pull/221) source
`7c150fc81184df1715824be28b32472baadbb3b6` is integrated at
`797cda3fb903b07d4152e5bbde9f468beeeab3e0`, and Limen relay
[PR #2317](https://github.com/organvm/limen/pull/2317) source
`854b6385de6b340485baaf59b1be55bd4d243a4d` is integrated at
`690617fc2aeea79acfe5604799e6413d70b6e4dd`. The portfolio package durably tracks the
manifest and exactly three source-grounded mockup PNGs; all three remain explicitly
unselected. Both merged packages remain `PREPARED/PREFLIGHT`, not C06 closure: operator selection
is still required, no visual implementation or deployment is authorized, 11 legacy
`organvm.github.io/portfolio` links remain dead, and the canonical
`organvm-vii-kerygma/portfolio` paths resolve.

P02 is closed. C03 W01-W06 are accepted at
`c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; C03 source
`b6af8086c9050634313f519c29a6dfcb922c3721` is integrated at
`8f89ad16ca1df84b00cb8227c88f368d0d64631a`, while W07 remains genuinely five-reader
blocked. W06 is
bound to [its marked receipt](https://github.com/organvm/limen/issues/2187#issuecomment-5271254820)
and SHA-256 `260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617`.
W07/#2188 remains open for five genuine independent target-like reader records; synthetic and model
responses cannot satisfy it. P04 therefore remains dependency-gated on P03.

This package prepares the reversible, privacy-sensitive interior of the inbound funnel without
choosing, wiring, or publishing a public capture surface. It consumes two capture-neutral envelope
shapes—tagged mail and form submission—so the later C06 decision can bind either path without
rewriting CTA provenance, minimum-data validation, normalization, scoring, routing, draft, custody,
ledger, view, or retention semantics.

## Prepared flow

```text
selected C06 capture surface (not yet selected)
  -> contract-only client | recruiter CTA mapping
  -> tagged_mail | form_submission adapter + bounded provenance tags
  -> minimal normalized lead record
  -> deterministic fit score + uncertainty margin
  -> client | recruiter | operator | spam | manual-review route
  -> declarative, non-authoritative response draft
  -> externally sealed private-custody adapter boundary
  -> owner-partitioned private opportunity ledger + retention/deletion contract
  -> partition-scoped operator view + aggregate-only dashboard/receipt
```

The tracked fixture set is wholly synthetic. Reserved `.invalid` addresses, synthetic owner
partitions, placeholder surfaces, and synthetic proof tags prevent fixture data from becoming
real-world lead evidence. The traversal receipt exposes synthetic-only opaque record IDs,
classifications, routes, stages, counts, and the zero-send counter only; names, addresses, requests,
draft bodies, and ledger rows never enter its public projection.

## Leaf preparation map

| Leaf | Prepared artifact | Formal boundary retained |
|---|---|---|
| `PSP-P08-W01` · routine/external/high | client/recruiter CTA-to-intake map, source/proof/audience tag contract, and tagged-mail fallback | contract only: no alias, CTA, deliverability, or public address activation |
| `PSP-P08-W02` · deep/write/xhigh | exact minimum contact/request/consent schema, bounded fields, privacy copy, and overcollection denylist | no public form or selected C06 surface |
| `PSP-P08-W03` · deep/write/xhigh | idempotent normalizer, dedupe index, synthetic fixtures, and seal/open/delete custody boundary | no cryptographic implementation, key material, provider mail, or real lead payload |
| `PSP-P08-W04` · deep/write/high | declared signals, thresholds, margin rule, and manual-review fallback | scores remain suggestions, never authority |
| `PSP-P08-W05` · routine/write/medium | seven declarative response-template families and authority-absent, hard-closed send valve | no transport or send capability; `HG-PUBLICATION-SEND` remains unpulled |
| `PSP-P08-W06` · deep/write/xhigh | owner-partitioned ledger, non-contact operator view, aggregate dashboard, and category retention/deletion contracts | in-memory synthetic harness only; retention defaults require private-owner ratification |
| `PSP-P08-W07` · deep/read/xhigh | five-route synthetic traversal, abuse/privacy negatives, zero-send assertion, and dependency-ordered live gate | synthetic proof is not a leaf or phase receipt |

These capability, reasoning, effect, and effort requirements are derived from the live registry.
The actual provider is selected from the runtime catalog at dispatch; an unavailable assignment
fails blocked rather than silently substituting a stale model name. This conductor preflight does
not impersonate those separately leased executions.

## Integration contract

After the operator selects one of the three grounded directions, C06 performs its separately
authorized implementation, fixes or redirects the 11 legacy links, and P07 closes with its
predicate-backed receipt, a separately leased C07 leaf may update the
contract with the selected capture surface and implement one repository-owned adapter. That adapter
must emit the exact common envelope represented here. The private owners must supply authenticated
partition access, real encryption via an external key manager, and delete semantics behind the
seal/open/delete boundary; this public preflight deliberately supplies neither a cipher nor keys.
Integration must keep the following invariant:

```text
capture may be live only when dependency receipt + selected surface + leaf authority are all present;
send remains a separate human-gated capability and is not granted by capture activation.
```

The later repository owners remain those in `program.yaml`: Limen for tags and scoring,
`organvm/universal-mail--automation` for mail normalization and drafts, and
`organvm-iii-ergon/collaboration-operations-platform` for the private opportunity ledger. The live
registry now correctly names `organvm-vii-kerygma/portfolio` for W02. This preflight deliberately
creates no shared generated index and writes no
cross-repository state.

## Verification

```bash
python3 scripts/positioning-private-inbound-preflight.py --mode validate --json
python3 scripts/positioning-private-inbound-preflight.py --mode traverse --json
python3 -m unittest discover -s scripts/tests -p 'test_positioning_private_inbound_preflight.py'
```

`--mode live-gate` is expected to exit `2` first on W07's five-reader receipt, then on P04, P07,
the selected capture surface, and separate leaf authority in that order.
That result is the intended fail-closed preflight behavior, not a verification failure.

All seven leaves now have reversible implementation coverage in this package while every formal leaf
status remains open and dependency-gated. No PSP leaf or phase may close from this package. Its
purpose is to make the later dependency-bound integration smaller, testable, and privacy-preserving.
