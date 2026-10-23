# Runtime restoration continuation - October 19

Owner: [Limen #2848](https://github.com/4444J99/limen/issues/2848).
This receipt continues the October 15 evidence refresh and the October 19 audit.
It proves the native API restoration scope below; the larger rollout stays open.

The existing ten-turn fixture passed all 40 isolated checks and all 20 managed
checks across standalone, packaged daemon, plugin, VS Code and ChatGPT readers.
The managed checks used each installed binary through the supported Domus launcher,
read nonempty history, resumed it, completed one verification exchange, restarted
the reader and compared retained history. Five verification turns were appended
to the pre-existing verification thread. Original history stayed intact.
Both fresh receipts passed validation and were atomically installed. The operation
completed in 156.414 seconds under normal heavy admission. No live history conversion,
compression or deletion occurred. Existing user sessions were not restarted;
GUI acceptance is not claimed.

| Predicate | Result |
|---|---|
| Isolated native compatibility | 40/40 checks passed |
| Managed native API restoration | 20/20 checks passed |
| Exact-current-reader receipt installation | Both receipts validated and installed |
| Controller observations | Pending normal heavy admission; first attempt denied by another session's lease |
| Original October 13 watch | Coverage failure retained; no reset or backfill |
| Physical cleanup attributable to this run | Zero bytes |

The earlier clock blocker no longer reproduces: Apple NTP measured a 0.054587
second offset with 0.032568 second uncertainty at 15:27:57 UTC. No clock setting,
census tolerance or receipt expiry was changed. This supersedes the October 15
clock observation only; it does not repair the failed historical watch.

A real bootstrap failure exposed a separate source defect: worktree inventory
reservation used bare PATH Python even when the running CLI had its dependencies.
The source repair supplies the CLI interpreter only to the two reservation
calls, preserving their broker and storage predicates. The regressions reproduce
the missing-rfc8785 failure before the change and cover new/existing branches
afterward. All 37 workstream tests passed. All 19 cheap scoped gates passed
(typecheck, lint, format and documentation included); the broad CLI/API gates
were not admitted, so the corrected scoped predicate exited 75. The first run's
undeclared-parameter failure was corrected in the owning registry. All 32
credential atoms passed. Publication and native installation are separate; this report does not
claim the currently installed immutable CLI contains the repair.

Cleanup remains evidence-gated. Shared .recode is a 2,077,659,136-byte change-history
database with old/new content and rollback metadata, zero free pages and no open
handle observed in one probe. Its producing application and restoration owner
remain unresolved; it is retained. A narrow check of three regenerable cache
locations found no eligible candidates. Native databases and sidecars, legacy
stores, VM images and custody partials remain retained under their existing owners.

The audit's Cursor/OpenCode/Copilot configuration repairs and OpenCode archive
completion remain source-owned work under #2848. Native external permission
acceptance stays with #1703. No cleanup, global estate release or original watch
success follows from the restoration proof.

Exact reader identities, per-reader checks, old/new receipt hashes and evidence
limits are in [observations.json](observations.json). Raw RPC history, preimages
and failed attempts remain private in the retained continuation checkout's
custody-staging directory, outside the quota-bound vendor runtime. The smaller
initial staging attempt under the live custody root is also retained. No peer
task reservation was accepted; broker reads/submission attempts returned 409.
The audit checkout's foreign local lease was preserved and an inactive related
checkout was reused without creating another checkout or local branch.

Generated-cache cleanup resolved a local growth-admission failure. Two type-checker
caches with 6,231 path entries were renamed into the existing private custody owner;
nothing was deleted. The checkout census fell from 14,008 to 7,783 paths beneath
the unchanged 10,000-path bound. Corrected verification directs its cache into that
same custody root, preserving both old caches and the admission limit.

Private RPC payloads and fixture families remain retained. A 7,049,282-byte private
archive was created, but the existing vault rejected a new artifact id before
writing ciphertext: public recovery admission allows only four bootstrap ids.
No allowlist or recovery predicate changed. Independent custody of these new
private evidence artifacts remains unverified under #2848; session release and
checkout retirement are not claimed.

BLOCKED: normal heavy admission for two controller records and the broad CLI/API
gates. The observed holder was another session's verify-scoped process. After its
owner releases that lease, the existing bounded controller acceptance and scoped
verification must run with the retained external cache location. Native histories,
peer work and guard thresholds stay protected.
