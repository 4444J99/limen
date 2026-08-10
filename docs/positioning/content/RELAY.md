---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
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

## Verified current state

| Item | Live state |
|---|---|
| Exact package commit | `fb77c679b84064162675f6851e816e46e5ee07be` |
| Exact remote branch head at preflight receipt | `fb77c679b84064162675f6851e816e46e5ee07be` |
| Exact target base head | `b9c6872cbe352b64e37c69a7133f43f7d61018b5` (`origin/main`) |
| Pull request | [#2316](https://github.com/organvm/limen/pull/2316), draft, base `main` |
| Working tree at package receipt | clean |
| Acceptance condition | private staging package is met; every PSP-P09 leaf and the phase exit remain deliberately unmet |
| Package predicate | `python3 scripts/check-psp-c08-preflight.py` passed at `fb77c679b84064162675f6851e816e46e5ee07be` |
| Scoped predicate | `scripts/verify-scoped.sh` passed at `fb77c679b84064162675f6851e816e46e5ee07be` |
| Receipt verifier | no PSP leaf receipt exists or is claimed |
| Phase exit proof | unmet: `python3 scripts/positioning-program.py --phase-proof PSP-P09` requires content-pinned receipts and approved external effects |
| External effects | none; no publishing, distribution, capture activation, analytics modification, deployment, or send occurred |

## Completed work

- [x] Added a claim-source register with admitted wording and explicit withheld categories.
- [x] Staged the 90-day calendar, flagship report draft, derivative deck, synthetic visual, measurement contract, and correction/withdrawal contract under the chunk-owned content path.
- [x] Bound the package to a no-effect check that preserves synthetic/observed separation and both human gates.
- [x] Opened draft PR #2316 with the package validation evidence.

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| Do not use the historical C00/P00 identity gate | C00/P00 was closed by merged PR #2300; live registry and remote parity were rechecked. |
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
- Pull request / receipt: [#2316](https://github.com/organvm/limen/pull/2316) / package commit `fb77c679b84064162675f6851e816e46e5ee07be`

The fresh-agent injection phrase is:

```text
Continue from relay at /Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees/8407/limen/docs/positioning/content/RELAY.md. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not identity, lease, approval, or permission.
