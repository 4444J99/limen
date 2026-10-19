# Native reply-order attribution defect

Owner: [#3056](https://github.com/4444J99/limen/issues/3056). Publication: [draft #3087](https://github.com/4444J99/limen/pull/3087).

**Reproduced, not repaired:** the existing capture pairs 29 earlier replies with 28 later input positions across 19 columns. All 29 pairs have matching bound native turn IDs, yet the reply precedes the input in both native ordinal and timestamp. Every selected body matches the preserved native source; all 19 full decoded snapshots still match their captured hashes and stable before/after file metadata. [Machine-readable evidence](reply-order-findings-v1.json) records every pair without copying private source text.

The census covers existing primary prompt rows (3,500 total, including the separate eleven-row Claude example), not derived context frames. All 29 affected pairs are native Codex records.

The `column` values in this version are captured-path fingerprints. [The checked namespace crosswalk](source-key-namespace-v1.md) maps them to the native-header-plus-snapshot keys used by the ordered storage-view graph; original keys and source positions are preserved.

## Root cause and scope

`project_rows` in [capture-native-projection.py](capture-native-projection.py) selects finals for a whole native turn and assigns the same list to every input in that turn. Native turn identity alone therefore permits a prior final to become the alleged result of a later follow-up. It can also suppress the later input's commentary fallback if the only explicit final belongs to its past.

The proposed invariant is narrow: select only replies strictly after each input before choosing explicit finals or a last-commentary fallback. Preserve excluded preceding references. Keep shared-turn uncertainty visible; this is not a proof that all remaining forward replies are uniquely causal.

No affected column has all captured retention flags true. The earlier seven-source branch review is therefore outside this finding. The new nine-sequence review contains one affected input and explicitly excludes its earlier reply. The original capture and catalog are preserved and remain uncorrected.

## Confirmed source pairs

| Legacy path key | Input position | Input native ordinal | Earlier reply native ordinal |
|---|---:|---:|---:|
| 22e9905c43b0 | 20 | 825 | 822 |
| 3dde40cedc8f | 17 | 18446 | 18443 |
| e044f87430cc | 6 | 2677 | 2674 |
| 3fff96b675de | 42 | 8637 | 8634 |
| 3fff96b675de | 43 | 8643 | 8634 |
| 3fff96b675de | 43 | 8643 | 8640 |
| e519eac9c84e | 2 | 2686 | 2683 |
| af18495c8d25 | 3 | 3363 | 3361 |
| 4adc78bce9e8 | 5 | 3565 | 3563 |
| af291bc589fc | 6 | 528 | 526 |
| af291bc589fc | 7 | 554 | 526 |
| 8ea40621c7c3 | 4 | 3204 | 3175 |
| 0eea18215964 | 7 | 2302 | 2300 |
| fd5bc8b7b3d6 | 3 | 537 | 535 |
| 58ef6a507966 | 8 | 538 | 536 |
| f3152fff00ef | 16 | 3108 | 3106 |
| f3152fff00ef | 17 | 3165 | 3106 |
| f3152fff00ef | 18 | 3217 | 3106 |
| afef6db7962b | 5 | 1356 | 1354 |
| 2b653f5e4b39 | 4 | 150 | 148 |
| 2b653f5e4b39 | 5 | 152 | 148 |
| 2ba5f1ccc49d | 3 | 1117 | 1115 |
| 2ba5f1ccc49d | 4 | 1208 | 1115 |
| 2ba5f1ccc49d | 5 | 1244 | 1115 |
| e9f4c64c0ddd | 28 | 6774 | 6772 |
| ea85c85f9575 | 10 | 1280 | 1278 |
| ea85c85f9575 | 11 | 1282 | 1278 |
| ea85c85f9575 | 12 | 1290 | 1278 |
| 1ee193c93d44 | 3 | 309 | 307 |

All 19 sources were verified sequentially using 128 KiB decoded chunks, a 4 MiB selected-record bound, a 128 MiB per-source bound and a 20-second per-source deadline. The stream processed 406,176,098 decoded bytes without retaining full source copies. The negative-order census does not prove complete session ancestry or causal validity of every remaining forward association.

## Regression and admission

Three added cases in [test_native_projection.py](test_native_projection.py) cover the later-final, missing-outcome and commentary-fallback variants. They are expected to fail on the current implementation, but **no red or green test run is claimed**. Automatic approval review rejected both the absolute hermetic-wrapper invocation and a repository-relative invocation with the owned worktree explicitly set, both as `shared-checkout-write`. No alternative interpreter, subprocess transport or guard override was used to route around that rejection.

The source repair is reviewable as [native-reply-order.proposed.patch](native-reply-order.proposed.patch). It is not applied to the active projector. Git's patch-applicability check passed after correcting the draft hunk context; that check is not Python execution or regression success. [repair-native-reply-order.sh](repair-native-reply-order.sh) is the prepared escalation script required after repeated guard rejection. The script itself has not executed or passed syntax/runtime validation.

From the study's isolated checkout, the exact prepared commands are:

```sh
bash docs/continuations/prompt-sequence-study-20261018/repair-native-reply-order.sh --dry-run
bash docs/continuations/prompt-sequence-study-20261018/repair-native-reply-order.sh --apply
```

Dry-run checks only patch applicability. Apply mode is for the owning admitted execution context: it resolves the gate interpreter, requires exactly the three expected baseline assertion failures, applies the proposed source patch and runs the complete fixture file through the mandatory hermetic wrapper. Each test subprocess has a 120-second deadline. Red/green evidence is preserved in the existing private study root; no native database or rollout is written.

After fixture success, the owning lane must re-capture the affected columns, regenerate the existing comparison and reconcile every changed attribution before claiming the artifact repaired. Existing source/cwd admission and full-scoped verification holds remain owned; there is no successful release, deployment, independent review or original-goal completion claim.
