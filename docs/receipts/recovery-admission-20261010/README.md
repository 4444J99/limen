# Recovery admission implementation checkpoint

Owner: this Limen change and 4444J99/ops#6; quota source owner: 4444J99/domus-genoma.

The exact prior rejected ops work key is `ops6-coordinate-20261009`. Owner-held
policy source was located at the previous successful policy installation; the local
empty observe-only projection was not used or changed. Authenticated live GET of
`/api/conduct/execution/policy` returned HTTP 404. See policy-admission.json.
This proves the readback capability is unavailable, not that administrator
credentials are unavailable. No policy replacement, capacity reservation, native
subagent, deployment custody or production apply occurred in this attempt.

The added readback returns only a canonical policy fingerprint and deployed runtime
identity to authenticated conductors. The additive reconciler refuses a mismatched
owner source and preserves unrelated priorities and every existing limit. After
the readback is deployed, the next owner operation is the reconciler with the
existing source, exact work key and `--install`, followed by bounded broker admission.
No installation is safe before matching that generation. The installation rechecks
generation immediately before the existing headless Wrangler secret route; provider
secret installation has no CAS, so deployment custody must exclude concurrent writers.

`scripts/ops6-recovery-graph.py` now builds ops-specific WorkPacketV1 packets.
Construction with `--original-deadline` remains read-only. Explicit `--submit`
first requires exhaustive keeper allowance and zero prior reservation evidence,
then uses one atomic submit_graph transaction. Its fanout root has only the
accepted recovery authority; A has the exclusive external deployment claim,
B has narrower hosted-idempotency authority, and C is read-only. Dependencies
are A -> B -> C. Four fixed reservations consume all 120 broker minutes, share
the first admitted deadline, and cannot admit a fifth run. This command launches
no worker. Deployment is separately gated through accepted ops source
08d493caf5cf6fe7a64cbb67f6ed7e6b07ea119e and pinned runtime
62469ec5b402460a5610145e67901fcdd0ca00b9. C records unavailable window evidence
without sleeping or renewing a deadline. Hosted ALREADY_DEPLOYED and full incident
acceptance remain independently unproven.

Storage now separates capacity pools and shares APFS container restrictions. Missing
mounts fail explicitly. The internal legacy latch remains authoritative. The additive
repair command requires keeper-installed recovery authority, reserves durably,
checks estimated and actual allocated bytes, and preserves ambiguous failures.
Ordinary thresholds remain 50/200 GiB. Retained state is not an automatic release.

Live Domus observation at approximately 00:08 UTC found Codex at 12,896,141,528 bytes
against 12,884,901,888 bytes; all runtime vendors totaled 18,635,649,844 bytes against
25,769,803,776 bytes. These sizes are apparent quota bytes, not physical recovery.
No inactive downloaded release directory exists in the observed Codex runtime.
History restoration/replica acceptance was not established, so history, databases,
sidecars and partials were retained. Quota reduction: zero; physical recovery:
zero claimed. Native history retirement remains with the existing custody owner.

Two small isolated source checkouts were created under the implementation instruction,
using existing Git stores, sparse paths and no clone. They are retained as PR-owned
implementation checkouts; no prior checkout or peer process was altered. The initial
isolation was manual under this instruction, not attributed to the new repair adapter
or a broker lease. Allocation measurements and verification are recorded alongside
the PR publication. Broader code deployment and ops acceptance remain open.

Final verification and delivery measurements are in [verification.json](verification.json).
All 14 scoped cheap gates passed with the pinned toolchain. The scoped heavy wave
returned exit 75 on `swap-fraction,disk-throughput`; no override was attempted.
Limen owner: https://github.com/4444J99/limen/pull/2840 (draft).
Domus owner: https://github.com/4444J99/domus-genoma/pull/415; the targeted managed
runtime file is applied with empty post-apply diff. Its exact-head merge submission
returned `DEFERRED — LIFECYCLE-UNKNOWN`; it was submitted once, without polling.

## October 10 continuation

Domus #415's base was corrected from master to main and lifecycle:delivery added.
The unchanged 71afd2e076eaed06356eac1182a4a076f054ec3f head has exactly three
files. One new submission after that material correction returned MERGED, at
91c770b01b65df95040a05c3e5ace5a6d6b63eae. The merged runtime blob is
60d70a18bf44d05ee7b4904d805272ad84f4bca0; it matches the retained accepted
source and the deployed target. Target-specific Chezmoi diff with that accepted
source is empty. The primary Domus checkout still points to an older master;
its default diff would remove protections and was not applied.

The native policy record at the supplied line 257 was parsed without executing
history or emitting policy contents. Its canonical fingerprint is
9d954a8f2fac6a04fef2cc0587181ba9ca4d161635672984bd435dec996e6249.
The reconciler can read that record directly. Live policy readback still returns
404, so this source has NOT been matched to live policy and no replacement occurred.

A fresh 00:54:37 UTC host probe materially improved from swap fraction 0.582 to
0.173, disk samples 179/190 to 31/20 MiB/s, and vitals ok. That admitted one
scoped retry on the final source tree. All 16 cheap gates and the heavy API/Worker
wave passed; Worker tests: 373 passing. Focused packet/policy tests: 11 passing;
with existing execution-limit tests: 30 passing in total across the final runs.
The serialized full CLI gate timed out at its default 300-second command limit,
after approximately 82% and nine failure markers. Actual resolver exit: 1;
individual failure identities and causes were not emitted before timeout.
A bounded diagnostic was then denied by host admission with swap-fraction and
vitals-shed before pytest started. No unchanged retry, threshold change or merge
override occurred. Credential wall and diff hygiene passed.

At 00:58:22 UTC, authenticated headless administration captured the live Worker
source, settings, all 20 bindings, active version and rollback identity privately.
Source capture SHA256: 1fba50ca31706dfedf2d1e1e1364221ff24b017207d95223739d7aad9684eb86.
Settings SHA256: 6ab630ae08d4b3eab1ea13aa31858a4bec33dc6e32d8741d9046124f8e99b1f5.
Active/rollback version: a0c5aa90-6538-4382-833a-b9844072d7a5, 100%; runtime source
f93f3dd9076992ce6d38f4d697a5f7176b776013. No Worker or secret was changed.
The earlier rejected coordinator has zero retained runs and zero active leases;
its bounded audit cannot prove exhaustive outcome allowance. New allowance
readback over the complete keeper ledger remains undeployed.

GES #496 remains draft at 3db2831f7b37852414bd77d330a240d7a0f9a35b, different
from the correction freeze 6c893c957f8d491d079414f3e127e37efdd44fe0. The bounded
native search found 14 candidate files, including replacement roots outside GES,
18 unique completed turns, two inherited duplicates, no conflicting duration_ms
records and one unfinished turn. Candidate native active duration totals 76.9666
minutes; elapsed timestamps use a different meter and cannot be substituted.
These candidates include mixed-outcome work and are not exhaustive outcome
attribution. The separate legacy native store has no October 2026 session tree.
Remaining GES allowance is UNKNOWN, never 43.0334 minutes. No GES cwd consumer
was observed, but that absence is not positive owning-writer release or an
accepted recovery lease. All seven implementation items remain HOLD, predecessor
claims/candidate bytes unchanged, delivery Staged and all wider gates retained.

Integration blocker owner: #2840; predicate: final implicated CLI verification.
Next action requires changed host evidence, isolation of actual failing tests,
then the implicated gate within the original verification allowance. No Limen
merge, managed CLI installation, policy installation, ops reservation or production
apply is claimed. Existing CLI remains ff6b2714a013e82c3132205183ca10302a0ce0c3;
actual new maintenance-intake routing is not yet adopted. Codex remains above
quota by 29,882,864 apparent bytes at the observed read; no payload was removed.

## Bounded CLI diagnostic and exhaustion

The original Limen verification allowance was reconstructed from the two owning
native sessions, counting earlier failed checks and retries conservatively,
including overlap. Prior recorded execution totaled 514.881652415 seconds of
600. The separate Domus outcome was excluded from this Limen meter.

One heavy-leased diagnostic on `c083165d5c13468d80f3ee84cd8a5bb4de5aa3ef`
used two workers, verbose names and `--maxfail=1`. Its cap was the remaining
85.118347585 seconds. It emitted 958 passing reports and the failure
`cli/tests/test_agent_state_cli.py::test_resume_requires_explicit_run_id`.
The process-group deadline expired before pytest printed the traceback or
terminal summary, at 11% progress. Actual exit: 124. Recorded execution was
85.174304083 seconds, including 0.055956498 seconds of bounded cleanup beyond
the deadline. The heavy lease was released; no leases remained at readback.

The original allowance is exhausted. Partial suite progress is not a passing
gate. The original nine failure causes remain unresolved; no source fix or
verified-head merge is claimed. The next owner action must resolve the exhausted
verification limit before any further tests, then target the observed subprocess
failure with retained traceback. Restarts cannot renew this allowance.

The script imports `limen` before argument validation while the test suite pins
the worktree source only in its parent process. That is an inspection lead for
the subprocess import environment, not a verified failure cause.

Accounting and retained sanitized output are in
[cli-verification-exhaustion.json](cli-verification-exhaustion.json) and
[cli-diagnostic-20261010.log.gz](cli-diagnostic-20261010.log.gz).
CLI installation, Worker deployment, policy installation and ops reservations
remain gated on unresolved CLI verification. GES #496 was re-read at the same
draft head; exhaustive outcome attribution and positive checkout custody remain
unproven, so all seven HOLDs and Staged delivery remain. The existing Limen
checkout is retained under #2840; no history or custody payload was removed.

## Standalone checkout import correction

Source review found that `scripts/verify.py` exports the owning checkout's
`cli/src`, while the standalone hermetic pytest wrapper did not. The CLI
conftest inserts that path only into the parent interpreter. The wrapper now
prepends its own absolute source path to `PYTHONPATH`, preserving the inherited
tail for dependencies. New regression variants launch the real wrapper from an
unrelated directory with either no inherited path or a foreign package path,
then check parent and child package identity.

This correction is UNVERIFIED. The user explicitly authorized 60 additional
seconds with all original usage retained. Fresh heavy admission denied
`swap-fraction` before pytest or any regression ran. The attempt used
2.442659250 seconds; 57.557340750 remain in the separately recorded allowance.
There was no lease, unchanged retry or override. See
[cli-import-path-verification.json](cli-import-path-verification.json).

The original nine scoped failures remain unexplained: the scoped verifier already
supplied `PYTHONPATH`. The named diagnostic failure has no captured traceback, so
its suspected import cause is not yet proved by execution. No passing final-tree
CLI receipt, merge, installation, deployment, policy replacement or reservation is
claimed. #2840 remains draft, and the GES seven HOLDs remain independent.
