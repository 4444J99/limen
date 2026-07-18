# Host Work Admission

Limen admits local execution through one per-user, machine-wide lease store. The store is shared by
every checkout and worktree, lives under a private non-backed temporary root, and never signals,
stops, restarts, or retunes a peer process. It denies or defers new work; work that already owns a
lease may refresh and finish a bounded closeout.

## Contracts

`scripts/host-work-admission.py` exposes four JSON operations:

```bash
python3 scripts/host-work-admission.py acquire \
  --kind heavy --owner OWNER --surface SURFACE --pid PID
python3 scripts/host-work-admission.py refresh \
  --lease-id ID --owner OWNER --pid PID
python3 scripts/host-work-admission.py release \
  --lease-id ID --owner OWNER --pid PID
python3 scripts/host-work-admission.py status
```

An admitted mutation exits `0`; a denied mutation exits `3`; invalid input exits `64`. `status`
always exits `0` because it is report-only—its `allowed` field says whether a new heavy lease would
be admitted. Responses use `limen.host_admission_decision.v1` and include stable reason codes,
current leases, pressure observations, and cleanup receipts.

There are two exclusive lease kinds:

- `execution`: one non-plan Codex root turn in Limen at a time;
- `heavy`: one heavy local surface across Codex, Claude, OpenCode, Agy, and Limen workers.

A lease binds an unpredictable ID, bounded owner and surface labels, PID, process-start identity,
and finite expiry. All updates run under `fcntl.flock` and publish with fsync plus atomic replace.
Cleanup removes only records proven stale by TTL, a dead PID, or a changed process-start identity.
An unavailable process identity never becomes deletion authority. Corrupt or unsafe state is
preserved and blocks new admission.

## Pressure decision

A new heavy lease is denied when any live observation is strictly beyond its declared parameter:

| Reason | Decision |
|---|---|
| `backblaze-cpu` | aggregate Backblaze client CPU is above 50% |
| `backblaze-rss` | aggregate Backblaze client RSS is above 1 GiB |
| `swap-fraction` | swap use is above 25% of physical RAM |
| `swap-growth` | two recent samples prove growth above 512 MiB/min |
| `disk-throughput` | both post-baseline `iostat` samples exceed 100 MiB/s |
| `vitals-shed` | VITALS reports `shed` |
| `pressure-sensor-unavailable` | a required macOS pressure probe is unavailable |

One hot disk sample is insufficient. A threshold equality is insufficient. Backblaze is observed,
never controlled. Refresh and release remain available under pressure.

All thresholds, timeouts, the state root, and the lease TTL are declared in
`institutio/governance/parameters.yaml`.

## Enforcement layers

Project Codex controls set `agents.max_threads = 3` and `agents.max_depth = 1`.
`UserPromptSubmit` acquires the execution lease and can stop a second non-plan root.
`SubagentStart` supplies the finite family bounds but cannot block creation.
`PreToolUse` emits an early denial warning for supported heavy calls, but current Codex hooks do not
provide a reliable hard-deny field for that event. The same lease is therefore acquired inside the
entrypoints:

- scoped verification, around its heavy and serialized tiers;
- whole verification, after its older verifier flock;
- each live local agent dispatch, with an additional execution lease for Codex.

Descendant heavy entrypoints inherit their live parent lease instead of deadlocking themselves.
They never release the parent record.

`Stop` performs no transcript, worktree, or governance scan. If Codex explicitly identifies a
first Stop-hook pass and the current topic branch has unpreserved tracked work, it may request
exactly one lightweight closeout continuation. The next Stop releases the execution lease.

Project hooks are inert until the operator reviews and trusts their current definitions through
`/hooks`. Global hook deployment and the host's verified non-backed governance scratch location
belong to the Domus cartridge. Limen must not edit home-directory hooks, backup policy, or global
host configuration directly.

## Lock order and recovery

`verify-whole.sh` takes the legacy verifier flock first and the shared heavy lease second. Scoped
verification takes the heavy lease before its serialized tail; if another heavy surface already
owns the host it exits temporarily unavailable instead of waiting and amplifying pressure.

Do not delete the store to seize admission. Inspect it with `status`. A live lease names its owner
and expiry; a stale/dead/PID-reused lease is reaped on the next operation. A corrupt store is an
owner-routed blocker because silently replacing it would make concurrent work look absent.

The SessionEnd lifecycle refresh separately preserves the useful low-priority closeout ideas from
draft PR #744 against current `main`: one dead-PID/stale-safe singleton, a process-group timeout,
`nice -n 10`, a narrower worktree-debt timeout, and a declared maximum number of roots per size
scan with explicit partial receipts. Combined with host admission and the existing bounded
`closeout-fast` queue/test timeouts, this supersedes #744; its old conflicting branch is not merge
or cherry-pick authority.
