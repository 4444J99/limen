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

# Relay — PSP-P02-W02: estate-classification integration

## Routing

- Program work ID: `PSP-P02-W02`
- GitHub issue: https://github.com/organvm/limen/issues/2174
- Target repository: `organvm/limen`
- Branch: `codex/psp-p02-w02-estate-classification-preflight`
- Authority receipt: human-authorized fresh Codex task under the merged C00 routing correction; W01 is formally closed, so W02 is admitted for integration, but this relay does not claim its merge, marked receipt, or closure.

## Verified current state

| Item | Live state |
|---|---|
| Exact verified implementation/evidence source | `2451d7a409168f70bb9ba6fc83674ddd74aede44` (tree `946d68d6950bb9262d3fe7ae915e3b3063f9e447`) — current classifier, policy, scoped-gate registration, and all 20 focused regressions |
| Exact remote branch checkpoint | PR #2307 carries only relay commits after immutable source `2451d7a409168f70bb9ba6fc83674ddd74aede44`; fetch the PR head, require that source as an ancestor, and use the PR body for the exact outer relay head |
| Accepted W01 dependency | Main integration commit `10cf8476d5e88309c71d5fac25167ec7b7af59c4`; marked receipt https://github.com/organvm/limen/issues/2173#issuecomment-5246643968; issue #2173 closed |
| Exact target repository heads | `organvm/limen` only; the focused live classifier ran against the accepted W01 denominator on 2026-08-10 |
| Working tree | Clean at the exact evidence source; every descendant after it is relay-only and changes no executable or policy blob |
| Acceptance condition | W02 is admitted for formal integration because W01 is closed; #2307 is not yet merged, #2174 has no marked receipt, and W02 is not closed |
| Task-specific predicate | Not run as a completion claim; after sanctioned merge and a marked W02 receipt, run `python3 scripts/positioning-program.py --verify-work PSP-P02-W02` and close only if it passes |
| Focused tests | `python3 scripts/tests/estate-classification.test.py` passed all 20 cases on exact source `2451d7a409168f70bb9ba6fc83674ddd74aede44` |
| Focused underlying predicate | `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w01-estate-census-preflight` passed on exact source `2451d7a409168f70bb9ba6fc83674ddd74aede44`: 314 total, 235 public, 79 private, exactly one primary role each; the guard scans the complete reviewed diff, treats GitHub identifiers case-insensitively, and retains added content beginning with `++` |
| Scoped verification | Bare `bash scripts/verify-scoped.sh` passed all 22 implicated cheap-wave gates for the final relay tree, reusing the unchanged focused/live evidence source `2451d7a409168f70bb9ba6fc83674ddd74aede44`; the registered `estate-classification-test` passed within the batch |
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

1. Adopt PR #2307 at its exact outer relay head, confirm it still descends from verified source `2451d7a409168f70bb9ba6fc83674ddd74aede44`, and reconcile required checks plus review threads without rewriting the verified source.
2. Merge through the sanctioned integration rail; do not bypass branch protection or write directly to `main`.
3. Attach the marked W02 receipt to #2174 with the accepted merge head and focused classifier as its underlying predicate (never `--verify-work` itself), then run `python3 scripts/positioning-program.py --verify-work PSP-P02-W02` and close only if it passes.

## Risks and prohibitions

- Human gates still unpulled: none. W01/#2173 is satisfied; the remaining gates are W02 exact-head integration, marked receipt, and executable issue predicate.
- Sensitive/private material boundaries: do not add private repository names, descriptions, topics, or timestamps to the public registry, doc, PR body, or issue receipt.
- Files or sibling work that must not be touched: `tasks.yaml`, the W01 branch, and sibling worktrees.
- Rollback route: restore the prior positioning policy only with a newer census receipt; do not expose a private record while rolling back.

## References

- Program manifest: `institutio/positioning/program.yaml`
- GitHub map: `institutio/positioning/github-map.json`
- W01 census receipt: `docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json`
- W01 marked receipt: https://github.com/organvm/limen/issues/2173#issuecomment-5246643968
- Pull request / receipt target: https://github.com/organvm/limen/pull/2307 (open against `main`, admitted for sanctioned integration); no W02 issue receipt exists yet

The fresh-agent injection phrase is:

```text
Continue from `docs/receipts/positioning/relays/2026-08-10-psp-p02-w02-estate-classification-preflight.md` on PR #2307. W01/#2173 is closed with its marked receipt and W02 is admitted: fetch the exact PR head, require verified source `2451d7a409168f70bb9ba6fc83674ddd74aede44` as an ancestor, then integrate, mark the W02 receipt, and run its executable predicate without bypass or direct-main writes.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, or permission.
