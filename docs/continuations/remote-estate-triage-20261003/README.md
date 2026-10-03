# Limen remote-estate triage — 2026-10-03

## What is complete

The [snapshot](snapshot.json) routes every enumerated item in the canonical
`4444J99/limen` repository: **362 open issues, 27 open PRs, 239 branches**.
The approved human review anchor was 362 / 25 / 235; two PRs and four branches
appeared during enumeration. The snapshot includes 2,272 historical PR records.
This is an observed point-in-time denominator, not a continuously refreshed board.

Routing is complete; acceptance, review closure, custody, and deletion eligibility
are **not** certified. No issue was closed, branch deleted, or task transitioned.
Issue URLs are durable intake owners, not proof of an assigned executor. Most
issues have no GitHub assignee; broker ownership must be checked separately.
Closed historical PRs are lineage only; unfinished non-PR branches route to
[branch reconciliation #2614](https://github.com/4444J99/limen/issues/2614).

## Next five, in dependency order

| Rank | Durable owner | Work and acceptance |
| --- | --- | --- |
| 1 | [#2776](https://github.com/4444J99/limen/issues/2776), [PR #2777](https://github.com/4444J99/limen/pull/2777) | Prevent ignored/untracked data loss. Preserve the explicit human-review hold on #2777. Resolve #2780's empty comparison through lineage evidence, not a merge. #2826 guards a different retirement scanner and is not a replacement. |
| 2 | [#2537](https://github.com/4444J99/limen/issues/2537), [#2355](https://github.com/4444J99/limen/issues/2355), [PR #2778](https://github.com/4444J99/limen/pull/2778) | Privacy and fail-closed control safety. Require exact-head scoped predicates; #2778's reported baseline failures are not a green receipt. Preserve personal custody and credential boundaries. |
| 3 | [#2763](https://github.com/4444J99/limen/issues/2763), [#2742](https://github.com/4444J99/limen/issues/2742) | Resolve overlap among #2823, #2825, #2802, #2805 and #2799. Compare current heads and preserve each review finding. #2825 advanced during audit; prior-head evidence cannot certify its new head. |
| 4 | [#2739](https://github.com/4444J99/limen/issues/2739) | Remote-first recovery: source publication (#2740), custody (#2742), cloud acceptance (#2745), then eligible retirement cohorts. Report remote-ready, retired and measured free-space gain separately. |
| 5 | [#2760](https://github.com/4444J99/limen/issues/2760), [#2664](https://github.com/4444J99/limen/issues/2664), [#2680](https://github.com/4444J99/limen/issues/2680) | Finish controls before dependent production work. PR #2779 was inspected and exact-head scoped verification attempted; it failed, so it remains open rather than being presented as merge-ready. |

Use at most two implementation lanes and one recovery writer. Existing protected
human sessions are never adopted or reaped. These ranks are the approved intent
translation, not canonical task-state edits or new dispatch leases.

## All-item routing

Every issue, PR and branch has an owner URL, evidence-qualified category and
inspection command or linked owner in the JSON ledger. PR rows bind the inspected
head; branch rows bind their tip and the snapshot main using short identifiers and
SHA-256 bindings. Titles, bodies, credentials and local absolute paths are omitted.

Issues: 3 safety reviews; 9 recovery; 9 control acceptance; 12 credential-owner
rechecks; 80 human-gate-owner rechecks; 86 program-dependency reviews; 163
intent/evidence reviews. A needs-human label is an observation to recheck, not
proof of a genuinely human-gated atom.

PRs: 20 exact-head verification reviews; 4 verification-admission reviews;
1 explicit review hold; 1 preservation-only; 1 empty-comparison lineage review.
An inspection category does not assert a passing test or closed review finding.

Branches: 179 historical-successor reviews; 18 open-PR-owned; 17 local-worktree
owner reviews; 10 unique-owner reviews; 8 ancestry-proven but still requiring
review/custody; 5 intentional preservation; 2 protected trunk/service.
All 239 have deletion eligibility false. An ancestor or closed PR is not a
retirement receipt.

## Execution evidence and retained owner

Read-only collection and static coverage validation succeeded. The collector's
six adversarial tests passed. PR #2779 was checked in a separate, session-owned
detached checkout at `47a255de8b2f`, against snapshot main `1bc457fcde30`:

```sh
bash scripts/verify-scoped.sh --base 1bc457fcde30cd28467da76133848d0722fd3f48 --require-base --total-timeout-seconds 180
```

Its direct exit code was **1**: the cheap wave failed on `ruff-lint`, including a
bounded-output-limit failure; `ruff-format` reported 867 formatted files.
No merge occurred and no full acceptance is claimed. The detached verification
checkout is retained under PR #2779 / issue #2664 pending a scoped disposition;
it is not a peer checkout and is not implicitly retirement-eligible.

Reproduce coverage validation and adversarial checks:

```sh
python3 scripts/remote-estate-triage.py --check docs/continuations/remote-estate-triage-20261003/snapshot.json
python3 scripts/tests/remote-estate-triage.test.py
```

A refresh uses `--review-anchor` with the last human review point, not the last
automated run. Reconcile count/head deltas before applying a routing decision.
The collector itself performs no remote mutation.

