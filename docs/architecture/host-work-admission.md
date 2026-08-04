# Host Work Admission

Limen admits local execution through one per-user, machine-wide admission root and lock. Its legacy
and scoped state views are shared by every checkout and worktree, live under a private non-backed
temporary root, and never signal, stop, restart, or retune a peer process. Admission denies or
defers new work; work that already owns a lease may refresh and finish a bounded closeout.

## Contracts

The public CLI exposes action-scoped writer operations:

```bash
limen host-admission acquire execution --cwd PATH
limen host-admission status --cwd PATH --json
limen host-admission release execution --cwd PATH
```

The lower-level `scripts/host-work-admission.py` remains the bounded JSON interface for guarded
heavy entrypoints and exact lease refresh/release. An admitted mutation exits `0`; a denied mutation
exits `3`; invalid input exits `64`. `status` always exits `0` because it is report-only. Responses
use `limen.host_admission_decision.v1` and include stable reason codes, current leases, pressure
observations, and cleanup receipts.

There are two admission dimensions:

- `execution:<scope_hash>`: one writer for one linked worktree. The hash is SHA-256 over the
  canonical Git common-dir and worktree git-dir identities; raw paths are not stored;
- `heavy`: one heavy local surface across Codex, Claude, OpenCode, Agy, and Limen workers.

The admission root has two state views under the same `.lock`:

- `state.json` retains the v1 schema and may contain only legacy `execution` and `heavy` records, so
  an older checkout never encounters a kind it cannot parse;
- `scoped-state.json` uses `limen.host_admission_scoped_state.v1` and may contain only
  `execution:<scope_hash>` records.

Current readers load the union and publish both views while holding the shared lock. If a valid
scoped record is found in `state.json` during rollout, the next current operation moves it to the
sibling file. Malformed input remains in place and fails closed. The current owner's legacy record
can upgrade in place. A different live owner's record is scoped only after its PID/start identity
and cwd resolve to a Git worktree. Distinct proven scopes proceed; the same scope denies; an
unprovable legacy scope blocks only the attempted mutation and is never deleted. Legacy unscoped
records remain readable for migration, but current Codex session startup never creates one.

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

Project Codex controls set `agents.max_threads = 3` and `agents.max_depth = 1`. `UserPromptSubmit`
is not an admission boundary and always admits concurrent roots; it never acquires a global
execution lease. When the installed client exposes stable structured denial, `PreToolUse` makes the
action decision. When it does not, session startup still proceeds and no legacy one-root fallback is
created. Guarded heavy entrypoints remain fail-closed through their internal lease acquisition.

`PreToolUse` covers `Bash`, `apply_patch`, `Edit`, and `Write`:

- known read-only actions acquire no lease;
- sanctioned Limen status, workstream, conduct, fanout, and remote-dispatch controls rely on their
  internal locking;
- writes require a linked worktree and its scoped writer lease;
- guarded heavy commands must pass the live global-heavy/pressure check;
- raw unguarded heavy commands are denied with the sanctioned equivalent.

The Bash allowlist is deliberately narrow. Redirection, mutation-capable Git commands, unknown
commands, and ambiguous compound commands are writes. The primary checkout receives
`shared-checkout-write`; aliases and symlinks resolve to the same canonical scope. Structured denials
use the hook's `permissionDecision=deny` channel. Warnings use `systemMessage`; conversation stops
use `stopReason`; one decision is never emitted through both.

The same heavy lease is acquired again inside authoritative entrypoints:

- scoped verification, around its heavy and serialized tiers;
- whole verification, after its older verifier flock;
- each live local agent dispatch.

Descendant heavy entrypoints inherit their live parent lease instead of deadlocking themselves.
They never release the parent record.

`Stop` performs no transcript, worktree, or governance scan. If Codex explicitly identifies a
first Stop-hook pass and the current topic branch has unpreserved tracked work owned by that
session's writer scope, it may request exactly one lightweight closeout continuation. The next Stop
releases only that exact scoped lease (plus an exact owner-matched legacy record during migration).

Project hooks are inert until the operator reviews and trusts their current definitions through
`/hooks`. Global hook deployment and the host's verified non-backed governance scratch location
belong to the Domus cartridge. Limen must not edit home-directory hooks, backup policy, or global
host configuration directly.

`limen.codex_host_admission_capabilities.v1` exposes the reader protocol, policy revision, both
state schemas, supported lease kinds, stable action-denial behavior, single rejection-channel
contract, and migration identity. Both `scripts/host-work-admission.py capabilities` and
`scripts/hooks/codex-host-admission.py --capabilities` return the same eight-field document.

The project hook also stages an immutable delegation entrypoint:
`scripts/hooks/codex-host-admission.py --delegate-immutable PATH`. It requires the installed target's
complete capability document within one second, then invokes only that target using its installed
runtime interpreter. Missing, slow, malformed, or incompatible policy never blocks
`UserPromptSubmit`; it allows observation and denies mutation through one event-appropriate channel
with a safe `domus-limen-runtime status` diagnostic. The project hook runner invokes this boundary
with the installed runtime at
`~/.local/share/limen/current/source/scripts/hooks/codex-host-admission.py`. The
`LIMEN_IMMUTABLE_ADMISSION_ENTRYPOINT` override is reserved for focused compatibility testing; host
activation still installs and proves an exact runtime SHA before this cutover may merge.

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
