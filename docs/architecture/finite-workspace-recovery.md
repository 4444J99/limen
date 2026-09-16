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

