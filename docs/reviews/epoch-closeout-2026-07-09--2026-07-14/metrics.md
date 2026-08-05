# Epoch metrics

## GitHub custody

| Measure | Result |
|---|---:|
| PRs opened in window | 244 |
| Merge events in window | 187 |
| Closed-unmerged events | 24 |
| Opened cohort merged by cutoff | 170 (69.67%) |
| Opened cohort closed unmerged | 23 (9.43%) |
| Opened cohort still in flight | 51 (20.90%) |
| Durable yield among terminal opened-cohort PRs | 170 / 193 = 88.08% |
| Merge-to-unmerged-close ratio | 7.79 : 1 |

The `187` merged PR receipts are the defensible work-unit measure. The `834` first-parent commits in
the same window are inflated by board preservation and integration shape and must not be presented
as 834 independent accomplishments.

## Board accounting

| Measure | July 9 baseline | July 14 snapshot | Change |
|---|---:|---:|---:|
| Total tasks | 2,324 | 2,609 | +285 |
| Terminal (`done` + `archived`) | 1,613 | 1,792 | +179 |
| Nonterminal | 711 | 817 | +106 |
| Closure stock | 69.4% | 68.7% | -0.7 pp |

Current snapshot: `1,333 done`, `459 archived`, `404 open`, `315 failed_blocked`, and
`98 needs_human`. The terminal count rose materially; the percentage fell because new obligations
entered faster than old obligations closed.

## Motion versus closure

| Measure | Result |
|---|---:|
| Dispatch events | 1,072 |
| Reopen events | 971 |
| Tasks reopened at least three times | 109 |
| Recent terminal transitions | 150 across 147 tasks |
| Terminal transitions with URL evidence | 130 |
| HEAL dispatches | 779 |
| HEAL reopens | 598 |

The reopen-to-dispatch event ratio was `90.6%`; HEAL's was `76.8%`. These are not failure rates for
individual jobs, but they prove that a large share of fleet motion revisited earlier work instead of
creating a new terminal receipt.

## Prompt and evidence authority

| Measure | Result |
|---|---:|
| Represented prompt events | 136,694 |
| Review batches | 309 |
| Batches with durable evidence | 292 (94.5%) |
| Batches with verified terminal outcomes under the strict contract | 0 |
| Open tasks with predicate + receipt target | 82 / 404 (20.3%) |
| Open tasks with underwriting fields | 1 / 404 (0.25%) |

The `0` is a contract result, not a claim that nothing was completed. Evidence exists; the stricter
prompt-to-predicate seal has not yet certified a batch as terminal. Evidence coverage and completion
must remain separate bars.

## Lifecycle and portfolio

| Measure | Result |
|---|---:|
| Current worktree roots | 296 |
| Classified worktree debt | 166 (73 dirty, 53 unpushed, 40 not merged) |
| Preservation receipts | 181 |
| Currently clean + merged + idle | 2 |
| Local worktree/corpus state | 35.5 GB |
| Portfolio repos observed | 308 |
| Open portfolio PRs | approximately 1,056 |
| Immediately harvest-shaped PRs | 84 (about 8.0%) |

Lifecycle debt is not intrinsically bad. Unowned, unpreserved, or falsely terminal debt is bad. The
closeout target is zero unowned residuals, not zero historical branches.

## Progress bars

```text
Task terminal stock       [##############------]  68.7%
Recent intake PASS        [##################--]  92.2%
Prompt evidence recorded  [###################-]  94.5%
Prompt terminal outcomes  [--------------------]   0.0%
Heal outcome coverage     [#######-------------]  33.8%
Immediate PR harvest      [##------------------]   8.0%
Worktree classified debt  [###########---------]  56.1%
```
