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
| Exact implementation head | `973872567bad19a4432201ce58252caf9e90c0fd` — full-diff private-name guard and focused regression included |
| Exact remote branch checkpoint | `973872567bad19a4432201ce58252caf9e90c0fd` on `origin/codex/psp-p02-w02-estate-classification-preflight` before this relay refresh; fetch before resuming |
| Exact target repository heads | `organvm/limen` only; the focused live classifier ran against the W01 denominator on 2026-08-10 |
| Working tree | Relay pending commit; otherwise clean |
| Acceptance condition | Partial: the policy and live classifier satisfy coverage, but #2173 remains open and W02 has no conduct-backed receipt |
| Task-specific predicate | Not run as a completion claim; it must remain deferred until #2173 formally closes and a receipt is attached |
| Focused underlying predicate | `python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w01-estate-census-preflight` passed: 314 total, 235 public, 79 private, exactly one primary role each; the private-name guard now scans the entire reviewed diff |
| Scoped verification | `scripts/verify-scoped.sh` passed all 15 implicated cheap-wave gates on exact implementation head `973872567bad19a4432201ce58252caf9e90c0fd` |
| Receipt verifier | No W02 receipt and no issue comment posted |
| Phase exit proof | Not applicable; P02 remains open |
| Omega observation | Not applicable |
| External effects | None: no visibility change, merge, publication, or issue closure |

## Completed work

- Added the public-safe taxonomy and ordered policy to `institutio/github/estate.yaml`.
- Added `docs/positioning/estate-classification.md` with aggregate coverage, public/private rule, and finite uncertainty queue.
- Added a live classifier plus unit tests. It does not persist private repository names and rejects newly added private names in the reviewed public diff.

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| First-match primary role | Existing doctrine already owns the discriminators: access grants, GitHub archived fact, governance class, and product ledger. Ordered precedence makes partner/product and proof/product overlaps deterministic. |
| Public output is aggregate only | `organvm/limen` is public; the W01 receipt confirms the private denominator but does not disclose names. The classifier keeps private metadata in process and checks the diff for new private-name leakage. |
| Uncertainty remains explicit | 118 fallback experiments require role evidence; one public partner surface requires an explicit collaboration disposition. Neither ambiguity authorizes a visibility change. |

## Next actions

1. Wait for https://github.com/organvm/limen/issues/2173 to close, then refresh this branch against its merged exact census rather than assuming the preflight denominator still matches.
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
