# Universe Finish-Line Continuation Capsule

This capsule owns the implementation and evidence tranche started on 2026-08-27. It is
deliberately nonterminal: it does not authorize a merge, deployment, branch deletion, worktree
reclamation, shared-checkout reset, notification canary acceptance, or closure of pull request
#2542.

## Exact lane

- Branch: `corrective/universe-finish-line-20260827`
- Base: `origin/main@8773db631e9c4b2fe00abbb032e758b5264ffc7f`
- Executor: native Codex direct session, human protected by policy
- Writer scope: the isolated universe-finish Limen worktree only
- Conduct state: unavailable because the authenticated broker environment was not present

The shared Limen checkout was observed but not rewritten. Its tracked and untracked residue was
captured in a content-addressed private archive with a redacted tracked receipt and verified
readback before implementation began. The protected private-document, Universal Mail, and original
PR #2542 lanes remain observation-only.

## Delivered tranche

- Opened successor pull request [#2548](https://github.com/4444J99/limen/pull/2548) from current
  default rather than rewriting PR #2542. The exact successor head passed its combined 317-test
  focused shard; all 13 admitted cheap scoped gates passed. Heavy admission was withheld by the
  machine-wide `swap-fraction` guard.
- Added cursor-receipt identity, bounded transient retry, completed-page reuse, cursor corruption
  rejection, total-drift rejection, and source-generation checks to the estate census.
- Added estate-wide local clone/worktree discovery by repository identity and Git common directory.
- Added `UniverseBaselineReceiptV1` aggregation and `limen progress --view universe`, sourced only
  from the persisted aggregate receipt.
- Added explicit notification status, dry-run, recording-canary, and macOS canary/confirmation
  modes with stable estate event identities and truthful incomplete-count handling.
- Hardened dirty-worktree preservation for binary diffs and deterministic untracked payloads. The
  receipt registry now keys exact worktree identity, so same-basename worktrees cannot overwrite one
  another's custody record.
- Corrected protected-lane classification so protected or human-active worktrees cannot enter a
  reclaim plan.
- Supplied the GitHub Actions token to the existing live research-adjudication probe without
  weakening the gate. The remaining live failure is source-profile drift, not token absence or the
  ruleset fixture.

## Frozen observations

Two persisted exhaustive remote generations are retained:

| Observation | Repositories | Connections | Leaves | Failed connections | Remote unaccounted |
| --- | ---: | ---: | ---: | ---: | ---: |
| `2026-08-27T14:58:22.879946Z` | 320 | 1,280 | 13,570 | 0 | 0 |
| `2026-08-27T15:25:52.639931Z` | 320 | 1,280 | 13,572 | 0 | 0 |

The two-leaf change is preserved as live estate movement, not normalized away. The latest
aggregate reports 177 stable repositories of 320, 763 protected open PRs, 10,291 unaccounted
non-default branches, 111 unaccounted local roots, 96 unaccounted worktrees, two local census
failures, and 20,900 aggregate unaccounted leaves. It is therefore correctly `complete: false`.

The current immutable cleanup dry plan contains seven candidates with digest
`8b0217df440fbfb61ae4f7aa045915032a4b7d8c64b0c40780ae08141deb4f19`; strict worktree debt reports
six debt items. No candidate was applied because the aggregate truth plane is incomplete.

## Verification

- Focused implementation batch: `211 passed in 75.26s`.
- Successor PR #2548 focused batch: `317 passed in 82.41s`.
- The first exact-tree scoped wave exposed five cheap-shard defects: static typing, resolver
  selection parity, two census-backed flagship projections, and formatting. All five were repaired;
  their implicated reruns passed (174-file mypy, 43 proof-set tests, 42 evidence tests, resolver
  parity, lint, and format), along with 103 focused local-census/baseline/recovery/debt tests.
- Latest remote census: 320 repositories, 1,280 complete connections, zero failed connections,
  zero remote unaccounted leaves.
- `limen progress --view universe --json-output`: receipt loaded successfully and remained
  fail-closed at `complete: false`.
- `notify-events.py --status`: `count unavailable/incomplete`; ntfy `not_configured`; macOS
  `submission_only_visible_delivery_unverified`.

The unchanged green shards from the scoped wave remain reusable receipts. The admission-gated
heavy wave has not run: live host status denied admission at a 0.3704 swap fraction. The branch
therefore does not claim an aggregate scoped PASS; the hosted PR receipt remains pending.

## One launch command

```bash
PYTHONPATH=cli/src python3 -m limen.cli progress --view universe --json-output
```

The expected result is nonterminal until every partition is terminal or durably protected and the
aggregate has zero failures and zero unaccounted leaves. See [blockers.json](blockers.json) for the
owned predicates and next commands.
