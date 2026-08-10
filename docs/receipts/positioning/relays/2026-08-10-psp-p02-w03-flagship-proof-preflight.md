---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex desktop human-protected preflight task
to: next healthy human-protected Codex task
scope: organvm/limen@codex/psp-p02-w03-flagship-proof-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-P02-W03: flagship proof-set preflight

## Routing

- Program work ID: `PSP-P02-W03`
- GitHub issue: https://github.com/organvm/limen/issues/2175
- Formal dependency: https://github.com/organvm/limen/issues/2174
- Target repository: `organvm/limen`
- Branch: `codex/psp-p02-w03-flagship-proof-preflight`
- Stacked base: `codex/psp-p02-w02-estate-classification-preflight`
- Draft pull request: https://github.com/organvm/limen/pull/2308
- Authority receipt: human-authorized fresh Codex task under the merged C00 routing correction; this remains a reversible preflight, not a claimed W03 completion.

## Exact implementation checkpoint

| Item | Value |
| --- | --- |
| W02 base branch head | `ee26b101879ca65e05cfabd3e0cc5253b82c2e74` |
| Verified W03 implementation commit | `10104e541ef9ec227c3a92d18595f2490a89f6fd` |
| Integrated implementation checkpoint | `a897a8cc96a816a7da7f6283a8581e42d27613c3` — W03 plus the full-diff, exact-token W02 privacy guard |
| Published remote branch checkpoint before this relay refresh | `48bb826d875dfb905a0c5a15c64e370ab73492a7`; fetch the PR head before resuming |
| Selected preflight set | Limen; UCC Public-Records Intelligence Platform; AI Chat Exporter |
| Named alternates | Universal Mail; Styx; a-i--skills; MONETA |
| Public candidate denominator | 20 |
| Private names in the public matrix | 0 |
| External effects | Draft PR and branch push only; no merge, publication, visibility, account, or issue-state change |

This relay is the only authored diff after the integrated implementation checkpoint. Resolve the live
PR head before formal work rather than treating the relay commit as a new implementation batch.

## Verified preflight state

- `python3 scripts/tests/flagship-proof-set.test.py` — 7 tests passed.
- `python3 scripts/tests/estate-classification.test.py` — 5 tests passed, including full-diff and
  longer-public-slug prefix regressions.
- `python3 scripts/flagship-proof-set.py --verify-live --json` — passed; all 20 named repository
  candidates are public, and each selected exact-head workflow plus public endpoint is live.
- `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w02-estate-classification-preflight`
  — passed: 314 repositories, 235 public, 79 private, 15 front-door proof, no newly added private
  repository token.
- `scripts/verify-scoped.sh` — passed all 21 implicated cheap-wave gates. No heavy gate was selected,
  so the sanctioned verifier did not require a machine-wide heavy lease.
- `python3 scripts/positioning-program.py --verify-work PSP-P02-W03` — intentionally not run; no
  marked W03 receipt exists and #2174 remains open.

## Reviewer verdict

The public scored matrix is `docs/positioning/flagship-proof-set.yaml`. Hard evidence gates override
numeric rank. The preflight selects three unique roles:

1. Limen — governed agent delivery.
2. UCC Public-Records Intelligence Platform — public-record decision pipeline.
3. AI Chat Exporter — privacy-first data portability.

Every selected claim has current public exact-head evidence, a live public endpoint, a bounded claim,
and no private-only dependency. The four alternates retain explicit promotion conditions; the 13
remaining candidates retain explicit exclusion reasons. No live profile generator was changed.

## Dependency boundary

- #2174 was open when this relay was written; W03 is not exposed as formally ready.
- PR #2308 must remain draft and stacked. Do not merge it or close #2175 from this preflight.
- The W02 branch is a dependency input, not a mutation target. Never rewrite it, `tasks.yaml`, or a
  sibling worktree.
- Private repository names and sensitive metadata remain in sanctioned custody. Do not copy them into
  the matrix, PR, issue receipt, or public docs.

## Formal completion sequence

After GitHub records #2174 closed with its valid W02 receipt:

1. Run `gh issue view 2174 --repo organvm/limen --json state,closedAt,url` once to confirm the event.
2. Fetch the merged W02 exact classification and reconcile PR #2308 through the normal integration
   rail; do not assume the preflight denominator or heads remain current.
3. Refresh every matrix source and selected live anchor, then run
   `python3 scripts/flagship-proof-set.py --verify-live --json`.
4. Run the refreshed W02 classifier/private-name guard and `scripts/verify-scoped.sh` on one exact tree.
5. Generate the W03 receipt skeleton with
   `python3 scripts/positioning-program.py --receipt-template PSP-P02-W03`; record the flagship
   validator as the non-circular underlying predicate and post the marked receipt to #2175.
6. Run `python3 scripts/positioning-program.py --verify-work PSP-P02-W03` bare. Close #2175 only if it
   passes against the merged exact head and latest marked receipt.

## Rollback

Revert the W03 selection commit without deleting the matrix history. Alternates, exclusion reasons,
and source observations remain evidence. No public generator or external publication needs rollback
because none changed in this preflight.

The fresh-agent injection phrase is:

```text
Continue from docs/receipts/positioning/relays/2026-08-10-psp-p02-w03-flagship-proof-preflight.md on draft PR #2308. Dependency-gated: confirm #2174 is closed before formal W03 refresh or receipt work.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, or permission.
