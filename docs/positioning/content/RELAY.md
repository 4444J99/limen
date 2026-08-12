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
| Pull request | [#2316](https://github.com/organvm/limen/pull/2316), draft, base `main` |
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
| P02 | closed |
| C03 / P03 | current preflight `c7c932205faa405e291f8030235a73cedeaa219e`; W01-W06 accepted at `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; #2188/W07 remains the sole five-reader gate |
| C04 | Limen #2313 `23712398c6586e005c303eff632604985cd0a25c`; portfolio #220 `9bcc4606b68da83dc0878b060989d35c3b649d7f` |
| C05 | Limen #2315 `a72a05d917bf14d53221c7d02ec52d3786b4f88e`; private #135 `6ff7d4e6bd9003213e2675f4e8d59c41a3726b3b` |
| C06 | portfolio #221 `6cb7f291ef758d26d136620398c6e9c09f74d0ea`; Limen #2317 `b3c8dcb8ee461fad7be971efc0fc60ca27726668`; exactly three directions remain unselected |
| C07 | Limen #2318 `6ee6bd7d546a56474cf3bd38e06fad794ab7bc45`; private inbound remains synthetic-only and P08 remains open |
| P09 formal frontier | P05, P07, and P08 remain open/prepared; this C08 package cannot promote them |

Conductor assignment remains `gpt-5.6-terra / high`. The manifest retains the registered leaf
assignments, including W02 `gpt-5.6-sol/max`, W07 `gpt-5.6-luna/medium`, and the remaining declared
leaves at `gpt-5.6-terra/high`.

## Completed work

- [x] Added a claim-source register with admitted wording and explicit withheld categories.
- [x] Staged the 90-day calendar, flagship report draft, derivative deck, synthetic visual, measurement contract, and correction/withdrawal contract under the chunk-owned content path.
- [x] Bound the package to a no-effect check that preserves synthetic/observed separation and both human gates.
- [x] Opened draft PR #2316 with the package validation evidence.

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| Use the current dependency frontier | P02 is closed; P03 is blocked only on genuine W07 reader evidence; C04-C07 remain prepared and cannot be promoted by this private staging package. |
| Keep the report as a private draft | The claims ledger admits internal operational evidence and authorship disclosure, while commercial, adoption, ranking, and unsanitized-incident claims remain withheld. |
| Keep the measurement fixture synthetic | The capture policy permits attributable door tags, but a fixture cannot become observed demand or a distribution receipt. |

## Next actions

1. Re-verify the exact PR head and run `python3 scripts/check-psp-c08-preflight.py` before review or integration.
2. For any leaf execution, obtain current broker authority and use the relevant `--verify-work` predicate only after the leaf's actual acceptance condition has evidence.
3. Do not advance W02 without `HG-PUBLIC-IDENTITY`; do not advance W08 without `HG-PUBLICATION-SEND` and real per-channel receipts.

## Risks and prohibitions

- Human gates still unpulled: `HG-PUBLIC-IDENTITY` (W02) and `HG-PUBLICATION-SEND` (W08).
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
