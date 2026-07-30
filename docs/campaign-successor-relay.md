# Campaign successor relay

Institutional campaigns stop admitting work at T−30. That boundary reserves one deterministic
successor identity, consumes at most one launch attempt, and returns `wait_relay` with the exact
lifecycle receipt. It never evaluates Omega or mutates the predecessor trial.

## Reservation contract

The relay identity binds the workstream, committed predecessor receipt Git blob, validated committed
contract digest, and predecessor deadline. Its stable successor slug, branch, and broker session ID
derive from that digest. The first reservation separately preserves its exact remote default-branch
commit as the successor base. If that branch later advances while the committed predecessor remains
unchanged, repeated beats validate the stable relay identity and reuse the first selected base.

The reservation lives in the repository's Git common directory, not in a worktree. Verified
directory descriptors keep every lock and receipt operation inside that store even if a parent path
is swapped concurrently. A mode-`0600` receipt and lock provide cross-worktree and cross-beat
duplicate suppression. First-use directory entries, receipt bytes, and atomic receipt replacement
are fsynced. Repeated beats return the same byte-stable `reserved` record with `attempts=0`.

The local record is worktree-shared crash-recovery state. Before a provider can spawn, its sole
attempt is also claimed through an immutable receipt-only
`refs/heads/limen-relay/attempt/<relay-id>` commit anchored to the reserved exact base. A missing
local store therefore recovers remote readiness or the remote attempt before lane selection,
adopts that durable base even if the default branch has since advanced, and cannot launch the
provider twice. The admitted receipt and readiness mapping use their own dedicated remote refs,
while Institutional Omega issue #1571 remains the campaign lifecycle owner.

Heartbeat output exposes only the path-free relay ID, state, attempt count, successor session ID,
workstream, and next lifecycle predicate. Failures expose only a stable relay error code and
path-free message. Private store paths and raw Git/OS diagnostics never enter heartbeat JSON.

## Finite launch and activation

Before consuming the attempt, the controller derives eligible native lanes from the live capacity
census. No eligible lane leaves the relay at `reserved` with `attempts=0`. Once claimed, the relay
cannot be automatically retried: an interrupted controller reconciles remote readiness or records a
terminal `indeterminate` receipt. One absolute monotonic startup deadline begins at controller entry;
remote recovery, capacity selection, attempt publication, process startup, registration, capsule
validation, activation, and readiness publication consume only its remaining budget.

The selected lane registers with the conduct keeper as dormant. A two-step control channel
authorizes receipt publication and then provider launch; deadline expiry or failed publication
closes that channel before provider exec. The final wrapper emits the exact PID/start identity,
marks both proof descriptors close-on-exec, scrubs relay-only and stale provider identity
variables, and performs the native provider exec. An independent exec-status descriptor reports
`execve` failure, so control-channel EOF alone can never manufacture readiness.

Only after control EOF, exec-status EOF without an error frame, unchanged PID/start identity,
complete bounded output drains, and exact remote publication does the controller activate the
broker session. The keepalive begins dormant and observes the activation marker; it closes inherited
proof descriptors immediately and never keeps a false exec proof alive.

Every non-success readiness push is reconciled against both exact destination refs. A confirmed
absent or mismatched mapping rolls activation back to dormant; a push accepted despite a lost
response remains successful. A result whose exact remote refs cannot be rechecked is instead
`relay_ready_publication_uncertain`: the controller preserves the activation marker and broker
acceptance until the immutable refs can be reconciled. It never rolls back and later re-adopts a
remote ready receipt under contradictory dormant state.

## Remote custody and wake

The admitted receipt-only commit is held by both its topic branch and
`refs/heads/limen-relay/capsule/<publication-commit>`. Readiness is a second receipt-only commit held
by `refs/heads/limen-relay/ready/<relay-id>`. An atomic push also advances the per-workstream
`refs/heads/limen-relay/latest/<workstream>` ref. Each new latest commit includes the prior latest as
a parent, so the catalog advances by fast-forward and historical dedicated refs remain immutable.
If the admitted topic push exits without a trustworthy response, the launcher rereads that exact
topic ref and continues only when it names the intended publication commit.

Campaign wake first discovers active capsules from local Git-tracked receipt files. Only when no
local active receipt remains does its ready-successor fallback read the exact per-workstream latest
ref, filter the structural receipt for the requested active handoff, and validate live topic-branch
and immutable-ref reachability. The supervisor receives the publication commit and its expected
base, and accepts it only when it is a single-parent, receipt-only commit on that exact base. In the
remote fallback, expired or damaged historical topic branches therefore cannot poison a newer
active successor, and the number of retained historical dedicated refs does not create a fixed
catalog ceiling. Duplicate suppression can still recover the dedicated ready mapping if an obsolete
topic branch disappears; ordinary remote wake retains the stronger live-topic reachability contract.

The launch root is derived from the shared Git common directory and verified as its primary
non-bare checkout. Successor activation then validates that the generated worktree belongs to the
same common directory, so reconciliation from any linked worktree reaches the original session
without storing a machine-specific path in the public or private relay receipt. Public heartbeat
wake timeouts are bounded to 300..7200 seconds, preserving the supervisor's fixed closeout margin.

S19 remains immutable historical evidence. The relay always creates a fresh provider-neutral v1
capsule from the exact remote default-branch head reserved for that identity, with an eight-hour
runway and dynamic lane selection. Explicit human-selected Codex profiles continue to use v2
capsules outside this automatic path.
