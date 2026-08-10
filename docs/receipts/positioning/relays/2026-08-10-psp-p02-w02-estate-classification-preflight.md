---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex desktop human-protected preflight task
to: next healthy human-protected Codex task
scope: organvm/limen@codex/psp-p02-w02-estate-classification-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-P02-W02: estate-classification preflight

## Routing

- Program work ID: `PSP-P02-W02`
- GitHub issue: https://github.com/organvm/limen/issues/2174
- Target repository: `organvm/limen`
- Branch: `codex/psp-p02-w02-estate-classification-preflight`
- Authority receipt: human-authorized fresh Codex task under the merged C00 routing correction; this remains a reversible preflight, not a claimed work completion.

## Verified current state

| Item | Live state |
|---|---|
| Exact verified implementation/evidence source | `2451d7a409168f70bb9ba6fc83674ddd74aede44` (tree `946d68d6950bb9262d3fe7ae915e3b3063f9e447`) — current classifier, policy, scoped-gate registration, and all 20 focused regressions |
| Exact remote branch checkpoint | PR #2307 carries this relay as one receipt-only descendant of `2451d7a409168f70bb9ba6fc83674ddd74aede44`; fetch the PR head and require that immutable source commit as its parent before reusing these receipts |
| Exact target repository heads | `organvm/limen` only; the focused live classifier ran against the W01 denominator on 2026-08-10 |
| Working tree | Clean at the exact evidence source; this relay refresh is receipt-only and changes no executable or policy blob |
| Acceptance condition | Partial: the policy and live classifier satisfy coverage; dependency and formal receipt state must be queried live, and this lane did not close #2174 |
| Task-specific predicate | Not run as a completion claim; it must remain deferred until #2173 formally closes and a receipt is attached |
| Focused tests | `python3 scripts/tests/estate-classification.test.py` passed all 20 cases on exact source `2451d7a409168f70bb9ba6fc83674ddd74aede44` |
| Focused underlying predicate | `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w01-estate-census-preflight` passed on exact source `2451d7a409168f70bb9ba6fc83674ddd74aede44`: 314 total, 235 public, 79 private, exactly one primary role each; the guard scans the complete reviewed diff, treats GitHub identifiers case-insensitively, and retains added content beginning with `++` |
| Scoped verification | Bare `bash scripts/verify-scoped.sh` passed all 22 implicated cheap-wave gates for the tree committed as exact source `2451d7a409168f70bb9ba6fc83674ddd74aede44`, including the newly registered `estate-classification-test` |
| Receipt verifier | No W02 receipt and no issue comment posted |
| Phase exit proof | Not applicable; P02 remains open |
| Omega observation | Not applicable |
| External effects | None: no visibility change, merge, publication, or issue closure |

## Completed work

- Added the public-safe taxonomy and ordered policy to `institutio/github/estate.yaml`.
- Added `docs/positioning/estate-classification.md` with aggregate coverage, public/private rule, and finite uncertainty queue.
- Added a live classifier plus a registered 20-case scoped suite. It does not persist private repository names; it rejects case-insensitive private tokens in added content and paths, distinguishes real diff headers from added `++` lines, validates maturity cutoffs, and converts schema, timeout, and unexpected failures into sanitized output.

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| First-match primary role | Existing doctrine already owns the discriminators: access grants, GitHub archived fact, governance class, and product ledger. Ordered precedence makes partner/product and proof/product overlaps deterministic. |
| Public output is aggregate only | `organvm/limen` is public; the W01 receipt confirms the private denominator but does not disclose names. The classifier keeps private metadata in process and checks the diff for new private-name leakage. |
| Uncertainty remains explicit | 118 fallback experiments require role evidence; one public partner surface requires an explicit collaboration disposition. Neither ambiguity authorizes a visibility change. |

## Next actions

1. Query https://github.com/organvm/limen/issues/2173 and its receipt live; if it is closed, refresh this branch against its merged exact census rather than assuming the preflight denominator still matches.
2. Continue in a fresh human-protected Codex task under the C00 routing correction; rerun the focused live predicate after the dependency refresh and reuse the unchanged scoped receipt unless the tree changes.
3. Attach a structured W02 receipt whose underlying predicate is the focused classifier (never `--verify-work` itself), then run `python3 scripts/positioning-program.py --verify-work PSP-P02-W02` and close only if it passes.

## Risks and prohibitions

- Human gates still unpulled: none, but #2173 is a formal dependency and remains an integration gate.
- Sensitive/private material boundaries: do not add private repository names, descriptions, topics, or timestamps to the public registry, doc, PR body, or issue receipt.
- Files or sibling work that must not be touched: `tasks.yaml`, the W01 branch, and sibling worktrees.
- Rollback route: restore the prior positioning policy only with a newer census receipt; do not expose a private record while rolling back.

## References

- Program manifest: `institutio/positioning/program.yaml`
- GitHub map: `institutio/positioning/github-map.json`
- W01 census receipt: `docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json`
- Pull request / receipt: https://github.com/organvm/limen/pull/2307 (draft, stacked on W01); no W02 issue receipt exists yet

The fresh-agent injection phrase is:

```text
Continue from `docs/receipts/positioning/relays/2026-08-10-psp-p02-w02-estate-classification-preflight.md` on draft PR #2307. Dependency-gated: confirm #2173 is closed before formal W02 refresh or receipt work.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, or permission.
