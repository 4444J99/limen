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

The task release routes are local dispatch, Jules landing and ship-docs, followed
by the existing worktree reclaimer for interrupted or retained cleanup. Ignored
payloads require custody proof even when their directory names resemble caches.
The tool-cache reclaimer owns its separate generated-cache allowlist; no blanket
home-folder relocation or ignored-file purge is a task-release action.
