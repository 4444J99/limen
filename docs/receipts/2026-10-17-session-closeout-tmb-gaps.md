# Session closeout: TMB/AV acceptance gaps (2026-10-17)

Owner: [limen #2909](https://github.com/4444J99/limen/issues/2909) (stays open).
Session: Claude session `session_0121dSmZoQPAy8CvCNA9z7xa`.
Plan: `docs/plans/2026-10-17-tmb-acceptance-gaps.md` (PR #2911).

This receipt records what the session landed, what it measured, what it did not, and who owns
each remaining item. Status words are evidence-bound and kept separate:

- **merged**: the merge commit is on the default branch (`gh` reports MERGED and a merge-base or compare read shows the commit contained in the default branch).
- **live**: the running checkout or installed runtime contains the commit. Nothing in this receipt is claimed live.
- **observed**: runtime evidence of the behavior itself (a probe or test run that exercised it).

Task completion, session release, estate health and deletion eligibility are distinct claims. This
receipt claims none of task completion for #2909.

## 1. Merged this session

Limen (`4444J99/limen`), squash merges, merge commit on `origin/main` (audit read at limen
`origin/main` = `0f761c08`):

| PR | Merge commit | Subject area |
| --- | --- | --- |
| 2911 | `7e5868e0` | acceptance-gaps plan |
| 2915 | `0f4e6bac` | merge-policy lookup diagnostic |
| 2919 | `5d7f2ef7` | TMB levers |
| 2920 | `ef724cb9` | sealed custody tool |
| 2921 | `cd3d7769` | CLI lock (zstandard) |
| 2927 | `804ca069` | encrypted custody receipt |
| 2932 | `2b49a2d1` | TMB ingress results |
| 2904 | `0a8b91ce` | second-device custody (merged earlier; its ancestry on `origin/main` was not re-verified by the audit; `gh` reports MERGED) |

Time Moment Brief (`4444J99/time-moment-brief`, private), squash merges:

| PR | Merge commit | Subject area |
| --- | --- | --- |
| 3 | `e5900ef9` | public playback clock, generation selection |
| 4 | `44d815c9` | accepted browser repairs, Safari colour |
| 5 | `780800b1` | functional playback boundaries |
| 6 | `0a9976e4` | renderer-parity wording |
| 7 | `3c04843d` | loop-continuity report |
| 8 | `ce93f3ec` | ingress resume tool |
| 9 | `60c6453f` | ingress first hash chain and 100GOPRO onset verdict |
| 10 | `181e2a2f` | native Safari WebCodecs probe (feature mode and sustained harness) |
| 12 | `1ccc13da` | e2e totals receipt |

PRs 1 and 2 on the TMB repo are CLOSED, not merged.

Read evidence for the TMB rows: PRs 3 to 9 and 12 by `git merge-base` printing the merge commit
itself against `origin/main`; PR 10 by the GitHub compare API reporting the default branch ahead of
`181e2a2f` (read after the audit, which predates PR 10's merge).

## 2. Open PRs

| PR | Head | State | Merge condition |
| --- | --- | --- | --- |
| limen 2938 | `f386dbc0` | open, not merged | `verify-scoped` exits 0 on that exact head (never ran: heavy lease denied); fixes the red test in #2933 |
| TMB 11 | `eeb9fa3d` | open, `mergeStateStatus` CLEAN | the 1800 s soak, the proof-page A/V probe, and the two browser guards must run under a heavy lease first; CLEAN status alone is not a merge reason because the changed `worker.js` has never run in a real browser |

## 3. Observed (runtime evidence)

All observations are for one Apple Silicon Mac. None is a claim about Safari beyond the cases named,
a phone, a headset, or capture hardware.

- Full TMB e2e suite at `181e2a2` (CPython 3.14.8, pytest 9.1.1, Playwright 1.61.0, Chromium 149), fully hydrated checkout: 394 collected, 394 passed, 0 failed, 0 skipped, exit 0. This is one clean run; the receipt itself does not show the `TargetClosedError` flake is fixed.
- Native Safari 27.2, Apple GPU, feature mode: PASSED (WebCodecs surface in page and worker realms; `isConfigSupported` true for the tested avc1.640028 sizes; production worker decodes the fixture and a derivative and closes its decoder).
- Ingress first hash chain: 6 originals and 16 derivatives enumerated; the committed census contains no host filesystem paths.
- 100GOPRO onset check: verdict `negative` (peak margins 71.0 percent and 57.25 percent), metadata verdict `no-coverage-likely`. This is a probabilistic elimination, not proof; the fourth camera still needs a new capture (G8).
- FOA loopback probe, light tests only: 12 passed. The probe exits 3 naming `L-TMB-LOOPBACK-AUDIO-DEVICE` because no 2-channel virtual loopback device is present (observed by a read-only audio-device listing).
- Resource and soak lane, non-browser only: 75 tests passed (soak pure tests, private-media exclusion, doc freshness), including Node sandbox checks of `worker.js`.
- Private-media exclusion at TMB `origin/main`: the only tracked file with a media extension (`.mp4 .m4a .mov .wav .webm`) is the synthetic probe fixture. The two tracked zip archives were not inspected (see section 9).

## 4. Merged but NOT observed (or not measured)

- G6 live FOA output: harness committed and pushed at `c1651fcf` on `feat/foa-live-output-harness`, no PR. The four measured tests never ran, `FOA_LIVE_OUTPUT_RESULTS.json` was never written, and the AudioWorklet, MediaStreamSource and realtime AudioContext paths are unexercised. Owner: [TMB #13](https://github.com/4444J99/time-moment-brief/issues/13).
- G7 resource maxima and soak: PR 11 open (above). `N_GENERATION_SOAK_RESULTS.json` says `NOT_RUN`. Three code-reading hypotheses are recorded there as unverified: workers can exceed the declared 12; playback transport stops after the first clip; the synchronizer is asked for scheduler id `generation_03`, which the real manifest does not list. Owner: PR 11.
- G10 Safari sustained lifecycle: PR 10 is merged, but sustained mode is NOT MEASURED (the tab went hidden when a macOS accessibility-authorization dialog took the foreground; the triggering process was not identified; no setting was changed). Not claimed: sustained transport, loop, or lifecycle-over-time on Safari. The normal completion path of the final probe revision was not re-run after its last edits. Owner: [TMB #14](https://github.com/4444J99/time-moment-brief/issues/14).
- G11 phone, headset, lip-sync device acceptance: not run. Human gate (section 7).

## 5. Custody state

- Originals have exactly ONE physical copy. The ingress volume and the encrypted-replica volume share one APFS physical store (same container, same physical store), so losing that store loses the originals. The two encrypted replicas do not substitute for a second physical copy of the originals. Human gate: `L-TMB-INGRESS-SOURCE-MOUNT` (G9).
- Two sealed replicas exist on different volumes: one in custody staging, one on the external volume. The audit observed bundle files mode 600 and their directories mode 700, and the private hash-chain manifest copy mode 600.
- Sealed replica verification printed `ok` with 1544224 bytes on each replica. The two printed ciphertext hashes differ, which the audit flagged as unreconciled. The tool source resolves this: `scripts/sealed-custody.py` documents that each replica is its own seal with a fresh salt, so ciphertext bytes legitimately differ, and `verify` compares each replica only to its own manifest. The discrepancy is explained, not a fault. Whether each `verify` exited 0 remains inferred (section 8).
- `verify-copies.sh` printed 12 MATCH and 0 DIFFER; `verify-media-custody.sh` printed 4 MATCH and 0 DIFFER. Exit codes inferred (section 8).
- The sealed-custody tracked receipt JSON at `origin/main` has zero absolute-path occurrences and no UUID-shaped values.
- "Escrow restore proven" and "sealed on two devices" were not re-checked by the audit round beyond file modes and the shared-store observation.
- Plaintext custody copies are retained until the history-purge decision (G1, declined).
- Nothing was written under the ingress volume after the last audit marker (empty `find -newer` output).

## 6. Ingress findings

- First hash chain done for the originals; derivatives built; the census at `origin/main` carries counts and root hashes only, with no host paths.
- 100GOPRO elimination is onset-based and probabilistic (section 3). G8 needs a human capture of a fourth camera view: `L-TMB-FOURTH-CAMERA`.
- Retained worktrees hold git-ignored private media copies (soak: 16 derivatives and marker clips; e2e totals: 4 private clips). That is a custody and privacy exposure until those worktrees are reaped.

## 7. Open items and owners

| Item | Owner | Next command or condition |
| --- | --- | --- |
| #2909 plan (all gaps) | limen #2909 | stays open; G6, G7, G10 and the human gates are unmet |
| G6 FOA live output | [TMB #13](https://github.com/4444J99/time-moment-brief/issues/13) | run the four tests under a heavy lease, write results, open PR |
| G7 soak and maxima | TMB PR 11 | run the two browser guards, then the soak, then merge the exact head |
| G10 Safari sustained | [TMB #14](https://github.com/4444J99/time-moment-brief/issues/14) | `native_lifecycle_probe.py --mode sustained --duration 600` with Safari frontmost |
| Red main: `test_installed_closeout_uses_its_runtime_python` | limen #2933, fix in PR 2938 | `verify-scoped` on `f386dbc0`, merge only on exit 0 |
| TCC audit load flake | [limen #2941](https://github.com/4444J99/limen/issues/2941) | run the file idle and under load; make the deadline load-aware |
| Stale plan header `PR: (pending)` | [limen #2942](https://github.com/4444J99/limen/issues/2942) | targeted edit via the docs rail |
| Uncaptured audit exit codes | [limen #2943](https://github.com/4444J99/limen/issues/2943) | rerun each check bare and record its exit status |
| Worktree reap | limen #2928 and the `reclaim-worktrees` organ | organ owns the reap after its 6 hour active window (section 10) |

Human-gated levers (registry `his-hand-levers.json`, all attached to #2909, none edited here):

- `L-TMB-INGRESS-SOURCE-MOUNT` (needs_human): second physical device for the originals (G9).
- `L-TMB-FOURTH-CAMERA` (needs_human): new capture of a fourth camera view (G8).
- `L-TMB-DEVICE-ACCEPTANCE` (needs_human): real phone, WebXR headset, capture hardware (G11).
- `L-TMB-LOOPBACK-AUDIO-DEVICE` (needs_human): install a 2-channel virtual loopback device so live FOA output can be captured (G6).
- `L-TMB-HISTORY-REMOVAL` (optional): purge six private media blobs from TMB git history; declined 2026-10-17 because the repository is private, owner-only and fork-free (G1). The six blobs remain in TMB git history, an accepted risk.

## 8. Exit codes: captured versus inferred

The audit shell displayed an exit code only on failure. The following were therefore NOT captured as
exit codes, and each "pass" is inferred from printed output. They are homed for bare re-measurement in
[limen #2943](https://github.com/4444J99/limen/issues/2943).

- `git fetch origin` in the limen and TMB repositories (no output; resulting `origin/main` refs matched live PR state).
- `git merge-base --is-ancestor` for each merged PR in both repositories. Ancestry was instead inferred from `git merge-base MERGE_COMMIT origin/main` printing the merge commit itself.
- `scripts/sealed-custody.py verify` on both replicas (printed `ok`).
- `verify-copies.sh` and `verify-media-custody.sh` (printed MATCH lines, no DIFFER).
- `scripts/check-his-hand.py --check` (printed 112 levers, violations 0) and `scripts/lever-classify.py --check` (printed that every open lever (102) is proven-sovereign or converted to design_debt).

Captured: `test_foa_loopback_probe.py` 12 passed with exit 0; the FOA probe exit 3; the TMB totals run
exit 0 (394 passed); `test_closeout_runtime_python.py` 2 passed on python3.13 and 2 on python3.14.
`test_protected_tcc_audit.py` gave 16 passed and 2 failed under load and 18 of 18 when idle.

## 9. Audit discrepancies and corrections (verbatim where possible)

- Audit: "8 limen worktrees hold 'unpushed, unmerged' commits." Correction: false alarm. Those HEADs match merged PR head SHAs (2915, 2911, 2919, 2921, 2920, 2927, 2932 and 2904); they are squash-merged with their remote branches deleted. The audit's "not on origin/main" check was SHA-based and cannot see squash merges. Nothing is stranded; all are retirable once the reap window allows.
- Audit: "PR 11 mergeStateStatus is UNKNOWN." Later live read: CLEAN and MERGEABLE. The hold is the unrun gate, not a conflict or a blocking review.
- Audit: gate `{"found": false, "waitedSeconds": 0}` for lane H (Safari). Later live read: TMB PR 10 is MERGED at `181e2a2f`. G10 is therefore partly landed (feature mode observed, sustained not measured), not unowned.
- Audit: the two sealed replicas print different ciphertext hashes at the same size. Explained by source (section 5).
- Audit: "The audit could not confirm the hold on limen PR 2938 was deliberate." Lane L1's own report records the hold as pending `verify-scoped`; this is supported but not independent.
- Receipt-internal inconsistencies disclosed in the e2e totals receipt and left unedited: `acceptance-status.json` `software_checks` do not sum internally (238 versus 228 in `total_checks_passed`); `documentation_freshness_checks_passed` is hand-written 16 while `test_tier6_doc_freshness.py` collects 17; `ACCEPTANCE_BROWSER_RESULTS.json` is stale at 84 browser cases against 87 collected now; the 23 older skips (AGENT4: 213 passed, 23 skipped) are unattributed.
- Tracked zip archives at TMB `origin/main` (`exports/time-moment-brief-chat-vault-2026-10-06.zip` and `synchronized-generation-calibration-2026-10-04.zip`) were not inspected; the no-private-media check covered only the five media extensions. Their contents are unverified.
- Origin refs: the limen fetch and several TMB reads used locally cached refs, so merged-status claims hold at fetch time only. The levers audit ran no fetch.
- Squash-merge status of ten TMB worktrees was judged by commit subject only, a heuristic.
- Scratch copies of census and coverage JSON remain in a temp directory outside any repository.

## 10. Worktrees remaining (reap owned by the organ)

No worktree was reclaimed or deleted by this lane. The `reclaim-worktrees` organ has a 6 hour active
window, and [limen #2928](https://github.com/4444J99/limen/issues/2928) owns the release-proof gap
for squash-merged worktrees whose remote branch was deleted. Retention or custody-verified
retirement is the organ's record to write; this list is the inventory, not a disposition.

Limen worktrees (under the limen worktree root):

| Worktree | PR state |
| --- | --- |
| `merge-policy-diag-20261017` | PR 2915 merged |
| `tmb-plan-20261017` | PR 2911 merged |
| `tmb-levers-20261017` | PR 2919 merged |
| `cli-lock-zstandard-20261017` | PR 2921 merged |
| `sealed-custody-20261017` | PR 2920 merged |
| `av-second-device-custody-20261017` | PR 2904 merged |
| `av-encrypted-custody-20261017` | PR 2927 merged |
| `tmb-ingress-results-20261017` | PR 2932 merged |
| `closeout-runtime-test-20261017` | PR 2938 open; retained until it merges |
| `tmb-session-closeout-20261017` | this receipt's PR (section 11) |

TMB worktrees (workspace root, `.wt-tmb-*`):

| Worktree | PR state |
| --- | --- |
| `pr5-verify` | PR 5 merged |
| `parity-wording` | PR 6 merged |
| `loop-continuity` | PR 7 merged |
| `ingress-resume` | PR 8 merged |
| `ingress-pass` | PR 9 merged |
| `safari-probe` | PR 10 merged |
| `e2e-totals` | PR 12 merged; retained, holds ignored private clips and a run log |
| `soak` | PR 11 open; retained, holds ignored private derivatives and marker clips |
| `foa-live` | no PR; branch pushed; retained; owner TMB #13 |
| `agent5-preserve` | no PR; preserve branch (14 commits plus tip); its delta was ported by PR 7; retained pending disposition |

Other limen worktrees not named in this session (for example `dynamic-routing-residue-20261017`,
`hook-bounds-repair-20261017`) were not inspected and are not claimed.

## 11. This receipt

Published through the normal PR rail from a fresh worktree off `origin/main`. This markdown file is
the narrative receipt. It is not a `limen.session_closeout.v1` JSON owner receipt; whether the
session predicate can pass for this session is reported separately in the PR and the closing report.
