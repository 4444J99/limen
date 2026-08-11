---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex desktop human-protected formal integration task
to: next healthy human-protected Codex task
scope: organvm/limen@codex/psp-p02-w03-flagship-proof-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-P02-W03: formal flagship proof set

## Routing

- Program work ID: `PSP-P02-W03`
- GitHub issue: https://github.com/organvm/limen/issues/2175
- Accepted dependency: https://github.com/organvm/limen/issues/2174#issuecomment-5247059070
- Target repository: `organvm/limen`
- Branch: `codex/psp-p02-w03-flagship-proof-preflight`
- Base: `main`
- Pull request: https://github.com/organvm/limen/pull/2308
- Authority: direct human session `019fed0d-52c4-7a83-b493-88a80035b42c`, Codex, human-protected.

<!-- positioning-formal-relay:start -->
```yaml
schema_version: limen.positioning_flagship_relay_binding.v1
work_id: PSP-P02-W03
state: formal_ratified_receipt_pending
dependency_work_id: PSP-P02-W02
dependency_head: 35134b95650a26185a58eb3b3a82632e5b80b5b2
dependency_issue_state: closed
dependency_marked_receipt: https://github.com/organvm/limen/issues/2174#issuecomment-5247059070
dependency_receipt_sha256: bb83f9bb074ac65d78b5f5cf8d91b475aa098105a9ccb28b84ccf96712d4a09f
dependency_receipt_observed_head: 35134b95650a26185a58eb3b3a82632e5b80b5b2
dependency_pull_request_state: merged
candidate_count: 22
selected_ids: [limen, public_records, ai_chat_exporter]
alternate_ids: [universal_mail, styx, ai_skills, moneta]
excluded_count: 15
```
<!-- positioning-formal-relay:end -->

## Current state

| Item | Verified state |
| --- | --- |
| W02 accepted head | `35134b95650a26185a58eb3b3a82632e5b80b5b2` |
| W02 marked receipt | https://github.com/organvm/limen/issues/2174#issuecomment-5247059070 · receipt SHA-256 `bb83f9bb074ac65d78b5f5cf8d91b475aa098105a9ccb28b84ccf96712d4a09f` |
| W03 integration source | `ac965f20b3cb20cfe115cdae48b6ab5b8253b4ae` · tree `5bd53f6dc110344c5d62d6c110955e954879d5f3` |
| Final PR head | This relay is one receipt-only descendant of the integration source; fetch PR #2308 and require the source above as an ancestor before reusing its receipts. |
| Candidate denominator | 22 public candidates: 15 authoritative W02 rows plus seven typed public additions |
| Verdict | Three selected, four named alternates, 15 explicit exclusions; zero private repository names in the public matrix |
| Formal status | W02 dependency accepted; W03 is admitted and exact-tree verified, but still unmerged, unreceipted, and open |
| External effects | Topic-branch commits and PR updates only; no publication, profile mutation, visibility change, or issue closure |

## Completed work

- [x] Reconciled the complete public candidate denominator to the accepted W01/W02 identity,
  visibility, role, and maturity projections.
- [x] Ratified three distinct public claim roles with structured bounded claims, exact workflow
  identity, candidate-bound endpoints, and no private-only dependency.
- [x] Preserved four alternates with promotion conditions and 15 exclusions with explicit reasons.
- [x] Merged accepted W02/main history without dropping the census, classifier, or flagship gates.
- [x] Bound W02's merged PR commit, closed issue, latest canonical marked receipt, receipt-observed
  head, and main-line ancestry in the executable live predicate.
- [x] Added exact non-circular relay bindings and source-safe documentation for W02 and W03.

## Verification at the immutable integration source

- `python3 scripts/tests/estate-classification.test.py` — 20/20 passed; the accepted W02 privacy
  and classification hardening is present.
- `python3 scripts/tests/flagship-proof-set.test.py` — 32/32 passed, including formal-state,
  receipt, observed-head, and relay-drift mutations.
- `python3 scripts/flagship-proof-set.py --verify-live --json` — passed: 22 candidates, three
  selected, four alternates, 15 exclusions; W02's issue, merged PR head, canonical latest receipt,
  receipt-observed head, main ancestry, identity, maturity, workflow, and endpoint bindings were
  current.
- `bash scripts/verify-scoped.sh` — passed all 23 implicated gates on the committed integration
  source.
- Review and remote CI must be read on the relay descendant pushed to PR #2308; earlier green
  receipts do not substitute for that exact-head check.

## Key decisions

| Decision | Rationale |
| --- | --- |
| W02 is the authoritative public source projection | The executable formal contract binds the merged PR commit, closed issue, latest canonical marked receipt, receipt-observed head, and live 314-repository classification; additions outside its 15 front-door rows are typed and finite. |
| Relay parity is non-circular | Machine-readable W02/W03 relay blocks derive from the matrix and intentionally omit their own commit identity; exact PR head remains a live fetch. |
| Limen uses a dated successful default-branch snapshot | Requiring a same-repository evidence commit to equal moving `main` would invalidate itself; the recorded run remains immutable, dated, and refreshable. |
| Public artifacts derive privacy safety | The registered classifier and W03 custody guard reject private identities without printing them; a self-asserted zero is not accepted as proof. |
| Hard evidence gates override score | A selected row needs a distinct story role, bounded claim, public exact workflow, candidate-bound endpoint, current maturity, and no private-only dependency. |

## Next actions

1. Fetch PR #2308 and require its exact head to descend from
   `ac965f20b3cb20cfe115cdae48b6ab5b8253b4ae` with this relay as the only intended successor delta.
2. Confirm base `main`, all required exact-head checks green, and zero unresolved review threads.
3. Merge only through `bash scripts/await-pr.sh 2308 --repo organvm/limen --merge`.
4. On the actual merged main commit, run bare
   `python3 scripts/flagship-proof-set.py --verify-live --json` and capture its true output digest.
5. Attach the marked `PSP-P02-W03` receipt to #2175, run
   `python3 scripts/positioning-program.py --verify-work PSP-P02-W03`, and close #2175 only if it
   passes.

## Risks and prohibitions

- Private repository names and sensitive metadata remain in sanctioned custody. Do not copy them
  into this relay, matrix, PR body, issue receipt, or public evidence packet.
- Do not edit `tasks.yaml`, bypass the merge rail, force-push, publish, change visibility, or treat
  a green pre-merge tree as the W03 completion receipt.
- Moving `main` is normal. Preserve exact-head receipts and use the sanctioned rail; do not enter a
  repeated rebase/CI loop.
- Rollback is selection-only: revert the W03 selection without deleting evidence, alternates, or
  exclusion history.

## References

- Matrix: `docs/positioning/flagship-proof-set.yaml`
- Public classification: `docs/positioning/estate-classification.md`
- Proof program: `docs/positioning/proof-production-program.md`
- Program manifest: `institutio/positioning/program.yaml`
- Pull request: https://github.com/organvm/limen/pull/2308

This file transfers context and evidence, not identity, lease, approval, or merge authority.
