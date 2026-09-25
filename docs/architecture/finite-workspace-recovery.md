## Finite recovery and approved priorities

The existing autonomy policy owns dispatch eligibility separately from completion.
During workspace recovery only one recovery writer proceeds; preserve human sessions
and monitoring. Resume only explicitly approved outcomes, never the unrestricted backlog.
A merged recovery PR or expired pause does not grant new priorities.

Autonomous implementation is limited to two tasks estate-wide and one heavy local
workload. Each attempt has 30 minutes, including at most 10 minutes of verification;
an approved outcome has 120 cumulative agent-minutes across descendants and replacements.
One corrective retry requires changed relevant inputs. Renaming, restarting, or splitting
work cannot replenish its allowance. Exhaustion checkpoints unfinished work and stops
automatic continuation. Discoveries stay in their owning registry without automatic fanout.

Release includes a checkout disposition: retain active/dirty/advanced/unbacked work,
or retire the disposable copy through the existing reclaimer after custody verification.
Preservation is not completion. Resume interrupted cleanup from its receipts and verify
that a second pass makes no changes. Use configured runtime roots for scratch.

Local disposable-worktree admission measures available bytes on the target volume. Below
50 GiB free, it latches new worktree creation closed; it reopens only at 200 GiB free.
The latch is kept in the user's state directory across producer and machine restarts.
An unreadable or invalid latch fails closed. Existing checkouts and their running work
remain available; the gate applies only to new worktree reservations.


Verification stores bounded success receipts for every passing gate. Reuse requires
an unchanged content, dependency, environment and gate-definition fingerprint.
Command gates opt in through `cache.mode: content` and explicit relative input
closures in the existing gate registry; syntax checks are deterministic by default.
Live integration and deployment checks execute on each implicated run.

Local agent subprocesses inherit the keeper's original attempt deadline. Remote
providers without a demonstrated hard deadline are explicitly unavailable for new
autonomous implementation, while observation and recovery remain available. This
includes Jules, Codex Cloud and the current 45-minute GitHub Actions agent job.
A bounded provider adapter must prove deadline enforcement before admission; a
worker restart cannot replace a missing original deadline with a new allowance.

The task release routes are local dispatch, Jules landing, fanout landing and ship-docs, followed
by the existing worktree reclaimer for interrupted or retained cleanup. Ignored
payloads require custody proof even when their directory names resemble caches.
The tool-cache reclaimer owns its separate generated-cache allowlist; no blanket
home-folder relocation or ignored-file purge is a task-release action.

Fanout landing roots are private, admitted and deterministic per work identity under
the configured worktree root. A failed provider application stays available for custody
recovery instead of disappearing with a temporary directory. A successful landing saves
its exact run receipt atomically before retiring disposable copies. Cleanup restart
revalidates remote PR/head evidence, resumes the existing detach lifecycle and consumes
no replacement checkout reservation. The supporting clone remains an explicitly indexed
recovery anchor; unfinished payloads are never discarded to manufacture a clean release.

Provider-result predicates use the same keeper-owned verification deadline as the
verification runner, including across retries and restarts. Check admission before
creating their verification checkout; use the existing process-group timeout helper
for the actual predicate. Input hashing consumes the verification allowance too.
