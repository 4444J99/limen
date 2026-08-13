---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-12
from: codex direct-session preflight
to: next healthy session in PSP-C08 scope
scope: /Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees/8407/limen
phase: PROVE
compression_level: medium
---

# Relay — PSP-C08: private proof-led content preflight

## Routing

- Program work ID: `PSP-C08` / `PSP-P09-W01` through `PSP-P09-W08`
- GitHub issue: [#2230](https://github.com/organvm/limen/issues/2230)
- Target repository: `organvm/limen`
- Branch/worktree: `codex/psp-c08-proof-led-content-preflight` / this worktree
- Conduct root/run/lease receipt, if any: none — this was an authorized direct-session preflight and does not claim or close a program leaf.

## Reconciled current state

| Item | Live state |
|---|---|
| Original package commit | `fb77c679b84064162675f6851e816e46e5ee07be` |
| Reconciliation base head | `36bf386c22e64785db8e7843899bf9aabf85bf89` |
| Pull request | [#2316](https://github.com/organvm/limen/pull/2316), integration package, base `main` |
| Current package state | `PREPARED`; private staging only; no P09 leaf or phase is closed |
| Acceptance condition | private staging package is met; every PSP-P09 leaf and the phase exit remain deliberately unmet |
| Package predicate | `python3 scripts/check-psp-c08-preflight.py` must pass on the current exact tree |
| Scoped predicate | `scripts/verify-scoped.sh` must pass on the current exact tree |
| Receipt verifier | no PSP leaf receipt exists or is claimed |
| Phase exit proof | unmet: `python3 scripts/positioning-program.py --phase-proof PSP-P09` requires content-pinned receipts and approved external effects |
| External effects | none; no publishing, distribution, capture activation, analytics modification, deployment, or send occurred |

## Dependency pins

| Dependency | Current evidence and boundary |
|---|---|
| P02 | accepted main `8faa5fb9899231ebf5f87e78bb171544c11b79d7`; phase receipt [#2172](https://github.com/organvm/limen/issues/2172#issuecomment-5270095170) |
| C03 / P03 | offer #2312 source `b6af8086c9050634313f519c29a6dfcb922c3721`, integrated `8f89ad16ca1df84b00cb8227c88f368d0d64631a`; W01-W06 accepted at `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; [#2188/W07](https://github.com/organvm/limen/issues/2188) remains genuinely reader-blocked |
| C04 | merged prepared proof: Limen #2313 source `1bb0ceca162129f6c90ae47958712bb19cd99cbb`, integrated `3f2269dd38865244f826aaff4818912a636167be`; portfolio #220 source `8974543ba9675ed0504141895812476efef5dd80`, integrated `a01b6d85f78d2d744c0c994f7220081bb54a85c5` |
| C06 | merged prepared public-surface relay: Limen #2317 source `854b6385de6b340485baaf59b1be55bd4d243a4d`, integrated `690617fc2aeea79acfe5604799e6413d70b6e4dd`; portfolio #221 source `7c150fc81184df1715824be28b32472baadbb3b6`, integrated `797cda3fb903b07d4152e5bbde9f468beeeab3e0`; all three directions remain `UNSELECTED` |
| C07 | merged prepared private inbound: Limen #2318 source `9d81552a65cab1a8785e74251853881ac1957925`, integrated `799c4bbe80634bb870e379061d03d08a74ea5405`; no inbound evidence is admitted |
| P09 formal frontier | P05, P07, and P08 remain open/prepared; this C08 package cannot promote them |

Execution records retain only capability, reasoning, effect, and effort requirements. The provider
is selected from the live runtime catalog at dispatch; an unavailable assignment fails blocked
rather than silently substituting a stale model name.

`dependency-bindings.json` is the machine-validated exact binding record. It remains `PREPARED` and
`counts_as_closure=false`; it records no reader evidence, approval, or external distribution effect.

## Completed work

- [x] Added a claim-source register with admitted wording and explicit withheld categories.
- [x] Staged the 90-day calendar, flagship report draft, derivative deck, synthetic visual, measurement contract, and correction/withdrawal contract under the chunk-owned content path.
- [x] Bound the package to a no-effect check that preserves synthetic/observed separation and both human gates.
- [x] Added deterministic evidence-to-draft controls for all W01–W08, with source-ID/citation equality, four bounded channel transformations, synthetic architecture and correction fixtures, redaction checks, review gates, freshness classification, analytics schemas, and a held dry-run publication package.
- [x] Opened draft PR #2316 with the package validation evidence.

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| Use the current dependency frontier | P02 is accepted; P03 is blocked only on genuine W07 reader evidence; C04, C06, and C07 are merged prepared packages and cannot be promoted by this private staging package. |
| Keep the report as a private draft | The claims ledger admits internal operational evidence and authorship disclosure, while commercial, adoption, ranking, and unsanitized-incident claims remain withheld. |
| Keep the measurement fixture synthetic | The capture policy permits attributable door tags, but a fixture cannot become observed demand or a distribution receipt. |

## Next actions

1. Re-verify the exact PR head and run `python3 scripts/check-psp-c08-preflight.py` before review or integration.
2. Run `python3 scripts/psp_c08_content.py --check` for source/citation, redaction, freshness, review-gate, analytics, and dry-run validation; `--dry-run` may render the held package but must never be treated as a publication command.
3. For any leaf execution, obtain current broker authority and use the relevant `--verify-work` predicate only after the leaf's actual acceptance condition has evidence.
4. Do not advance W02 without `HG-PUBLIC-IDENTITY`; do not advance W08 without `HG-PUBLICATION-SEND` and real per-channel receipts.

## Risks and prohibitions

- Human gates still unpulled: `HG-PUBLIC-IDENTITY` (W02) and `HG-PUBLICATION-SEND` (W08).
- PR metadata boundary: PR #2316 tracks the pushed branch; its body is public-safe and must retain the exact prepared-binding boundary through integration.
- Sensitive/private material boundary: no private evidence, personal contact data, or real incident record belongs in this package.
- Files or sibling work that must not be touched: `tasks.yaml`, generated program indexes, external target repositories, and active sibling preflight paths.
- Rollback route: remove or quarantine a staged asset under this directory; for a later real release, use the correction/withdrawal contract and preserve its external receipt.

## References

- Program manifest: `institutio/positioning/program.yaml`
- Claim policy: `docs/positioning/claims-ledger.md`
- Pull request / receipt: [#2316](https://github.com/organvm/limen/pull/2316) / original package commit `fb77c679b84064162675f6851e816e46e5ee07be`

The fresh-agent injection phrase is:

```text
Continue from relay at /Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees/8407/limen/docs/positioning/content/RELAY.md. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not identity, lease, approval, or permission.
