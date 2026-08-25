# Runtime and dependency state

## Transfer freeze

Sixteen scheduled, deployment, release, agent-dispatch, and review-automation workflows are
disabled. `MONETA`, `PR Gate`, `validate`, and `CodeQL`, plus four GitHub-managed dynamic surfaces,
remain active. The dynamic Copilot, Dependabot, and App surfaces are observations to re-query, not
ordinary workflow files to toggle. App access could not be enumerated with the current credential,
so every App-dependent workflow remains fail-closed.

The recovery CI path is pinned to GitHub's standard `ubuntu-latest` public runner. A zero-step job
is `CI_ZERO_STEP_ADMISSION`, is not retryable, and cannot satisfy admission. A successful remote
receipt must bind the exact workflow, run, job, runner ID, executed-step count, controller SHA,
target SHA, and receipt digest.

## Protected lanes

The Agy implementation was folded into the isolated recovery branch; its original checkout was not
rewritten. OpenCode remains active and protected. It wrote its own runtime database/history/log
between the two read-only captures, so the captures do not support a false byte-equality claim.
The transfer postflight must take immediate before/after snapshots, keep the process running, and
attribute any delta; it may never change OpenCode's branch, remote, session, process, files, or
lease.

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

No transfer, merge, workflow re-enable, notification install, activation, deployment, or restart
has been performed by this implementation lane.
