# Runtime and dependency state

## Transfer freeze

Fifteen scheduled, deployment, release, agent-dispatch, and review-automation workflows remain
disabled. Recovery CI is the only transfer-sensitive workflow restored. `MONETA`, `PR Gate`,
`validate`, and `CodeQL`, plus four GitHub-managed dynamic surfaces, also remain active. The dynamic
Copilot, Dependabot, and App surfaces are observations to re-query, not ordinary workflow files to
toggle. App access could not be enumerated with the current credential, so every App-dependent
workflow remains fail-closed.

Repository ID `1255213941` transferred successfully to `4444J99/limen`. Both authenticated
coordinates resolve the same numeric repository, and anonymous reads of `organvm/limen` redirect
once to the personal coordinate. The final private preflight and postflight manifests compare
cleanly after exact semantic restoration of GitHub's organization-only issue types. The accepted,
redacted proof is [public-postflight-receipt.json](public-postflight-receipt.json).

The recovery CI path is pinned to GitHub's standard `ubuntu-latest` public runner. A zero-step job
is `CI_ZERO_STEP_ADMISSION`, is not retryable, and cannot satisfy admission. A successful remote
receipt must bind the exact workflow, run, job, runner ID, executed-step count, controller SHA,
target SHA, and receipt digest.

Manual run `32885966196` on the transferred default SHA proved `CI_EXECUTED_STEP_ADMISSION`: four
non-skipped jobs carried positive runner IDs and executed 53 steps. Worker, Web, and Python passed;
the aggregate Verify job then failed inside the hermetic omega fixture, after admission. The exact
run/job census and failure classification are bound in
[public-ci-admission-receipt.json](public-ci-admission-receipt.json). The default-head run is not
retried; its focused fixture failure is corrected on the combined recovery head.

## Protected lanes

The Agy implementation was folded into the isolated recovery branch; its original checkout was not
rewritten. OpenCode remains active and protected. It wrote its own runtime database/history/log
between the two read-only captures, so the captures do not support a false byte-equality claim.
The accepted transfer postflight attributes the exact protected-path and process deltas to the
native Agy/OpenCode lanes and records that the transfer actor touched neither lane. Their branch,
remote, session, process, files, and leases were not altered to manufacture equality.

## Recovery dependency rail

- Limen PR #2543 is the combined implementation rail. Before this branch update it was at
  `371539499406f9135af218fb6d0fce58893f5212` with four unresolved current threads.
- Limen PR #2544 at `ccdb04c88164b3639b93f4621b1fcaa8fd96dada` is folded into #2543; its nine
  findings must be closed against the combined exact head before #2544 is retired as superseded.
- Limen PR #2542 remains at `95bc0a572bb4ec2aaffcc75e696c7aac71935a75` with three unresolved
  current threads. It is corrected once, after #2543 merges, and must incorporate the ten unresolved
  threads from merged #2539 and two from merged #2540.
- Notification restoration remains independent: Corpvs #548 is at
  `6421748be2f8ac512bb73005434643951172f04c` with zero unresolved threads; Domus #373 is at
  `56880c92d8cfa91b480e9a374c8196cfee02ef0c` with five unresolved current threads; Domus #372
  stays separate at `d11f196949ccf2d4ca812173595bea284979aafb` with four unresolved current
  threads. Merged Limen #2528 still carries 23 current and five outdated unresolved threads, and
  merged #2531 carries two current unresolved threads.

The repository transfer, postflight proof, and recovery-CI enable/admission proof are complete. No
merge, notification install, activation, deployment, or restart had been performed at this receipt
point; those effects remain owned by the continuing system lane and proceed only through their
predicates.
