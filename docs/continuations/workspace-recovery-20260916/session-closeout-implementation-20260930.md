# Session implementation evidence — 2026-09-30

Owner: https://github.com/4444J99/limen/pull/2785

Implemented scope and six-session findings: docs/session-closeout.md.

On implementation head 3eafefc7b, 36 focused closeout/watcher tests pass; changed module mypy and pinned Ruff lint pass. Instruction drift and diff hygiene pass. Prior unchanged shards: whole Python mypy, resolver and governance checks passed in the scoped batch.

Task-completion predicate remains nonzero: scoped verification exits 1 on the immutable public evidence for a candidate now private/archived. Heavy CLI/API testing was attempted through host admission and exited 75 (swap-fraction,disk-throughput). The same admission denied Codex native catalog testing; OpenCode discovery passed from three directories, zero model turns. These are owned by this open PR and Limen #2763, not proof of task completion. Next command after evidence/admission reconciliation: scripts/verify-scoped.sh --base 3b888f722656cd162fe0ee87c6bd2cae34d1efae --total-timeout-seconds 600 using actual Ruff 0.15.8.

Custody: this isolated implementation checkout has no untracked deliverables. Ignored files are Python/test/lint caches and the default generated observe-only autonomy-policy.json. No private payload was created or imported into it. Implementation is published on fix/session-closeout-20260930, with an open PR owner; remote publication is independently checked live. The six historical protected checkouts and their private custody obligations remain untouched. Temporary observations are reduced into the redacted tracked implementation report; raw session bodies were not read or published.

Domus source landed in PR #405 (64b4e4ef). Targeted chezmoi deployment excluded scripts. The immutable candidate installation is source adoption only, not a Limen main merge. No existing peer process was killed, root migrated, or successor session created.

Credential ownership predicate: `python3 scripts/credential-wall.py --check` exited 0; all 31 secret atoms registered. No new credential was created or copied.

Final observer correction: the live checker initially counted its own lsof child. The correction excludes only that launched observation PID; the source census now returns zero retained processes. The changed session checker suite passes 24 tests, and changed-module mypy and pinned Ruff pass; 13 unchanged watcher/historical tests retain their earlier pass. The final task-completion observation is an explicit source-landing predicate: GitHub reports PR #2785 merged=false, exit 1. Earlier external-evidence and admission failures remain recorded above, without claiming their rerun.

Explicit resume: authenticated metadata covered all 54 historical public candidates; 27 now positively restricted candidates have full-row-bound withdrawals. The final new-delta scoped batch (base 6ce4c8558) exited 0 across all eight selected gates, including 57+16 readiness tests, public live observation (27 verified heads / 27 unverified withdrawals), instruction drift, document manifest, exports, links and hygiene. Denominator 62 and transfer eligibility zero remain unchanged. The public-evidence blocker is resolved at this observation. Heavy CLI/API admission was attempted once on resume and still exited 75 for swap-fraction,disk-throughput; no peer was altered. Required source landing remains false (GitHub PR merged=false, exit 1). Thus the existing PR continues to own completion; scoped release is a handoff. The only new work products are the published registry, test, protocol-document and manifest edits.

Operator-authorized pressure exception: the human explicitly stated `authorize override host admission`. A process-local wrapper filtered only swap-fraction and disk-throughput reasons for the pending verification and native-discovery calls. Live pressure observations were retained, the normal exclusive heavy lease and verifier lock were acquired, two pytest workers ran, and no installed policy, peer, or permanent threshold changed. At execution, disk-throughput was the waived reason.

On published head 3586be046, the CLI gate reached 93 percent then hit its 550-second bound (one failure marker was emitted; no final traceback survived the bounded interruption, and no failure name was persisted). The CLI gate is failed/incomplete, never green. The API gate passed all 52 tests in 2.04 seconds. Codex native discovery then passed from home, Domus checkout and temp, with zero model turns. The ten-minute verification allowance is exhausted; no broad retry was started. The outstanding completion owner is still PR #2785. Next diagnostic command on an explicitly resumed verification attempt: `bash scripts/run-pytest-hermetic.sh cli/tests -q -n 2 -x --tb=short`, under the normal lease and the explicit operator pressure exception if still necessary; fail-fast must preserve the first traceback before any full-suite continuation. No merge was attempted on this failed CLI result.

## Final authorized continuation

The human explicitly resumed with “walk this all the way home.” The preceding
failed/incomplete records are historical attempts, superseded by the evidence here.
The fail-fast diagnostic captured startup races in the background-child PID receipt,
MCP EOF probe, and shell-helper pressure fixture. Repairs preserve the original
cleanup/protocol/lease assertions: capture the OS child PID directly, allow a finite
10-second MCP probe, and supply deterministic healthy pressure to the real CLI and
lease store. Production admission is unchanged.

The next bounded four-worker run passed 6,808 cases before a relay fixture startup
race. That fixture now acknowledges startup and wrapper exit before starting its
0.3-second descendant-cleanup deadline. Unchanged passing cases were retained;
the entire changed relay file and all unexecuted cases ran in a 1,448-case shard:
1,446 passed, two skipped. Mechanical set reconciliation proves coverage of all
8,223 collected node IDs, with zero missing IDs and no unresolved failed case.
Sorted node IDs joined with a final newline have SHA-256
`53757d069e17fcebeb68f8311b11e7d0b9f0fe818e5eb218b57f29b6d4d1d1d4`.
The skips are the real remote-sandbox integration and installed Praxis registry
integration cases; neither is counted as a pass. Reproduction entrypoint remains
`bash scripts/run-pytest-hermetic.sh cli/tests -q -n 4 --tb=short`; the bounded
continuation retained passing node IDs and invalidated each changed test file.

The verification runner correctly rejected a live process after otherwise passing
tests. Instrumented process-group inspection and a one-case reproduction identified
the lock fixture's orphaned `sleep 30`. The fixture now owns and cleans its process
group. A full workstream-file run then exposed the registration monitor's expected
poll tail; the ordering fixture now waits for its terminal receipt and process exit.
The final complete workstream shard passes all 31 cases and the unchanged runner
cleanup guard (27.17 seconds). No production guard was relaxed. Aggregate accepted
CLI coverage is 8,221 passed / two skipped, with passing unchanged shards retained;
this is not a claim that the earlier failed monolithic invocations exited zero.

Unchanged evidence retained: API 52 passed; Domus runtime 52 passed; Codex and
OpenCode each discovered the installed entry in all three native locations with
zero model turns; whole Python typing and prior scoped governance/readiness gates
passed. Final changed-tree cheap predicates are run before publication. No new
credential was used; the credential-wall predicate remains part of final release.

Custody update: full CLI tests generated ignored cache, observation/status logs,
and organ-health build outputs inside this isolated checkout. They contain no
imported private payload or independent deliverable; their relevant outcomes are
reduced into this tracked evidence. Protected historical checkouts remain untouched.
The terminal receipt is evaluated only after PR #2785 is merged and its exact
default-branch SHA is installed. GitHub's merge receipt and the runtime's immutable
manifest provide the external landing/adoption proof without a successor worktree.

Final changed-tree cheap batch: all ten selected gates passed (syntax, diff hygiene, instruction drift, parameters, test hygiene, docs manifest, exports, note links, whole-estate pinned Ruff lint and format). Unchanged typed source, API and readiness receipts remain valid.
