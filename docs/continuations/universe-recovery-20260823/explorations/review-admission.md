# Review and runner-admission audit

The named 13-PR lineage contained exactly 156 paginated review threads at observation: 56 resolved,
93 unresolved current, and seven unresolved outdated. All thread/comment cursors reconciled.

| Repository / PR | Current | Outdated |
| --- | ---: | ---: |
| Corpvs #548 | 0 | 0 |
| Domus #373 | 5 | 0 |
| Domus #372 | 4 | 0 |
| Limen #2539 | 10 | 0 |
| Limen #2540 | 2 | 0 |
| Limen #2541 | 0 | 0 |
| Limen #2520 | 19 | 0 |
| Limen #2528 | 23 | 5 |
| Limen #2531 | 2 | 0 |
| Limen #2534 | 7 | 0 |
| Limen #2538 | 4 | 2 |
| Limen #2527 | 14 | 0 |
| Limen #2542 | 3 | 0 |

Limen #2542 was open, non-draft, mergeable but unstable at
`95bc0a572bb4ec2aaffcc75e696c7aac71935a75` over
`f034e3e659c8c8c3b9469b7b66e32c2bc03fdb64`. Its three current threads were unresolved. Ten failed
jobs across five workflow runs had no executed steps and runner identity zero; two checks were
skipped and one review bot check succeeded. This is `CI_ZERO_STEP_ADMISSION`, not code-red or green,
and it does not satisfy merge admission.
