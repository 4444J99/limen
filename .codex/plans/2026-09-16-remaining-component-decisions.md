# Remaining component decisions

Owner: Codex. Continues the full gap-filling implementation plan.

Five decisions now follow inspected component owners: reserved capacity and
opening constraints use current provider metadata, conduct deployment preserves
collector isolation, PR classification requires complete scope, and MCP repair
uses the desired/observed reducer plus the narrow Domus contract. Historical
fixed model snippets, parked green checks and retired global repair commands are
not acceptance evidence. Native adoption and external grants remain separate.

The registry contains 37 selected decisions and 60 still requiring component
review across 97 nonterminal entries. All 107 IDs and lifecycle states remain
unchanged. Acceptance definitions are still incomplete (two predicates declared,
95 missing); the updated behavioral conditions do not claim completed outcomes.
Continue the remaining component review and acceptance implementation here.

## Next component review: closeout reconciliation

The current `scripts/reconcile-closeouts.py:classify_claim` calls a subject-matching
merged PR VERIFIED. This proves a merge reference, not executable acceptance or
external outcomes. Codex owns correction under this continuation and
L-CLOSEOUT-OBSERVE-ARM: distinguish merge evidence from acceptance, preserve
unknown/missing predicate evidence, and cover the distinction before activation.
Do not infer missing remote references from transport failure or accept a named
external path as verified custody. Inspect the current classifier consumers before
changing verdict vocabulary.

## Verification receipt

Eight cheap scoped gates passed. Full CLI: 7,680 passed, two failed, two
skipped in 278.59 seconds. Failures were the paired-custody stderr output-limit
case and the closeout fixed-point test's 30-second timeout. An immediate isolated
rerun of both output-limit variants plus the closeout case passed all three in
47.24 seconds. No production code or timeout limit changed. Root cause of the
full-suite-only failures is unverified; retain that result instead of claiming a
clean full run. Codex owns any recurrence under this PR.

## Closeout reference-evidence correction

The classifier now emits MERGE_OBSERVED rather than VERIFIED, and failed PR
lookups emit PR_UNMEASURED rather than asserting absence. The report explicitly
limits its evidence to PR references and lists acceptance-unmeasured claims. CLI
exit 77 distinguishes incomplete acceptance from a known contradiction (exit 1).
Unknown PR reads do not generate missing-PR remediation tasks. External home
names also remain acceptance-unmeasured. Four focused tests and classifier doctor
pass. This does not implement authoritative acceptance-receipt ingestion; that
remaining requirement stays with this component owner.

Closeout correction verification: all 28 implicated scoped gates passed.

## Dispatch evidence follow-through

Failed PR reads now populate PR_UNMEASURED, not PR_MISSING. The observer returns
77 and the board shows unknown coverage without counting it as recoverable work
or printing a healthy verdict. Invalid/missing PR state is not guessed OPEN.
Closeout loads code helpers from its own source directory while runtime state
continues to use LIMEN_ROOT. Verification: 33 focused dispatch, healer and closeout
tests, Ruff, classifier doctor, gate validation and diff hygiene passed. Existing
unaffected verification receipts remain evidence; no full-suite rerun claimed.

## Immutable privacy-receipt publication

The sensitive-history postflight writer had a check-then-write race. It now
flushes a complete temporary file and publishes through a same-directory hard
link, which atomically refuses replacement. Temporary files are removed on
success or failure. Five privacy-verifier tests pass, including an actual target
creation between preflight and publication and inspection of complete bytes
before the target appears. Ruff passes. No private packet or external removal
request was accessed or executed. L-GITHUB-PR2532-HISTORY-REMOVAL retains its
separate custody, support-action, postflight and immutable merged-receipt gates.

## Successful default-branch verification

GitHub run 35039390911 completed successfully at default SHA
3edef1e770ada792af8e16fc047ef27bf16cc5a8, including the actual whole-repository
verify-whole.sh step plus web, Python, Worker and dependency-audit jobs. Compat
was skipped and is not claimed as executed. This supersedes the earlier failing
default result for code verification only; draft changes, runtime adoption and
external outcomes remain separate obligations.

## Consolidation and shared workflow continuation

The e330b7081 consolidation run passed all 37 cheap gates. Heavy verification
was refused by host admission (swap-fraction), exit 75; PR #2627 therefore
remains draft and no completed verification is inferred. Owner: this PR; next
command is verify-scoped.sh against 3edef1e77 after admitted capacity is available.

Shared CLA template repair is published at organvm/.github#26, head
63cc652d74392460479d3df4a52726b4a00cbe70. It gates the job to PR-related events
and pins existing v2.6.1 to the upstream commit. YAML and structural policy
preservation checks passed. A single merge-drain submission owns integration;
consumer propagation and runner admission remain separate.

Shared-template submission result: DEFERRED — ERR (exit 2). No merge receipt;
repository integration remains the owner. Do not re-arm this unchanged head.

## Shared-template integration diagnosis

organvm/.github#26 remains open at its submitted head. Runs 35041033387,
35041033369 and 35041033514 each failed with zero executed job steps. Check-run
104620714103 reports a billing-related account lock; account state and remedy
were not independently verified. Owner: repository/account administrator;
acceptance requires admitted execution after the account-side gate is resolved.
No unchanged-head merge submission was repeated.

The merge tool's ERR came from an unreadable required-check list: gh returned no
required-check JSON. This now reports REQUIRED-CHECKS-UNMEASURED, preserving the
refusal. Twenty-five focused merge-drain tests and Ruff pass. No rule was weakened.

## Privacy and custody decisions

Four further decisions derive from the publication, identity, exact history-removal
and paired-custody components. Public history is not private custody; source
lineage must survive in authorized private storage. Identity presence is not
factual correctness or disclosure consent. Removal requires exact postflight and
a merged immutable receipt. Paired custody requires real device independence,
equal source coverage, restores and matching reopened records.

Current count: 41 selected, 56 requiring component review, 95 missing acceptance
definitions. All 107 IDs and lifecycle states are unchanged. Twenty-two focused
registry tests and structural validation pass. Heavy verification remains
incomplete under the recorded host-admission gate; no live private data or device
action was performed.

## Observation and outbound decisions

Four more components now have selected behavior: bounded observatory proposals,
closeout observation with unmeasured acceptance, per-route outbound preflight
separate from message authorization, and a two-repository hosted read scope.
Source references resolve; all 107 IDs and lifecycle states are unchanged.
Current count: 45 selected, 52 requiring component review, 95 missing acceptance
definitions. Twenty-two focused registry tests pass. No settings, grants, sends
or recurring operations were activated.

## Authentication and access decisions

Seven further records now distinguish account capability, implementation and
authorized effects. Social publishing remains refused by the current scheduler;
a token is not an implemented adapter or permission to send. OpenCode uses its
current catalog and admitted native smoke. Cloud adoption requires verified
actual ciphertext pushes. Provider exports require private lineage and measured
coverage. NAS retains its written agreement and credential-organ boundary.
LaunchDarkly consent is conditional on current semantic authentication evidence.
Claude settings must derive from current owned sources, never the August /tmp
candidate or historical numeric limits.

Current count: 52 selected, 45 requiring component review, 95 missing acceptance
definitions. No lifecycle, credential, settings, egress or publication state was
changed. Source references resolve; executable acceptance remains outstanding.

## Required identity verification modes

A hermetic probe reproduced identity.py verify returning exit 0 and claiming one
required atom present when its verification mode was unsupported. The verifier
now reports UNMEASURED and exits 77 for unsupported modes; a simultaneous known
missing fact still exits 1 with both observations visible. Unknown mode payloads
are not printed. Presence remains presence evidence, not factual correctness.

Six regression cases plus 27 registry/classifier cases pass (33 total). Personal
facts structural validation and focused Ruff pass. The dedicated scoped gate
tracks the verifier, its tests and the personal-facts registry. No private home
was read by these fixtures.

Consolidated verification at 7444cf024 passed all 42 cheap gates. Heavy
verification was again refused by the machine-wide swap-fraction admission
check (exit 75). PR #2627 remains draft; no admission bypass or unchanged-tree
retry was performed. This updates the existing PR-owned verification blocker.

## Publication and source-installation decisions

Four additional decisions preserve private clinical operation, evidence-bound
positioning, scoped cartridge installation and exact social-post authorization.
The health record's historical daemon deadline supplies no publication authority.
A matching cartridge remote is connection evidence only; its fail-open missing
probe is not adoption evidence. The social scheduler still has no send adapter.

Current count: 56 selected, 41 requiring component review; 95 executable acceptance
definitions remain missing. Source references resolve. No publishing, account,
private-data relocation or live settings action was performed.

## HOSPES scoped-claim readback

Issue #2404 remains open. Its regression test already landed in #2623 and is
included in the successful default whole-repository verification. Fresh
authenticated keeper readback now finds GH-organvm-hospes-9 open, no longer
stuck in_progress. Its historical August 15 compatibility run is succeeded with
a released lease and no run receipts; that is not a fresh execution receipt or
HOSPES product completion. No task state was changed.

The broader release safety review remains owned here: the legacy non-Jules
route uses task age without a broker liveness/protection decision, and the
release rung search reaches the retired heartbeat loop rather than the current
bounded heartbeat. Next implementation must preserve active/human-protected
leases and use broker-authoritative transitions, with current runtime coverage.
Do not revive the retired daemon or infer authorization from stale local state.

## Broker ownership before stale release

The legacy release command now obtains bounded read-only broker evidence before
routing candidates. Active runs, healthy owners, human protection, unsettled
leases and malformed/missing evidence hold the claim. A terminal, inactive,
unprotected broker owner permits the existing provider-specific route, not a
local transition. Actual executors resolve target_agent:any before Jules absence
checks. Interrupted failed-to-open relisting retains those checks.

Canonical pre-read failures and missing/malformed rows no longer fall back to a
remote caller's local projection. All broker I/O precedes the queue lock; a claim
that appears after the snapshot is held. The explicit local test adapter retains
its own temporary projection contract. Writes still use broker compare-and-swap.

The current heartbeat contract is read-only and already reaches lane-liveness
observation. No release effector was added to it and no retired daemon was revived.
The change belongs to the explicit release command; runtime installation and live
release evidence remain distinct. Focused development probes passed 61 cases;
consolidated verification follows this implementation batch. No live task was
mutated.

Verification update: the 10fa90322 consolidated batch passed 31 cheap gates and
failed type annotation and gate-owner checks. Both were corrected; complete
Python typechecking and gate validation then passed. The final executor-report
field passed the 61-case ownership/provider shard; focused lint and format pass.
Heavy verification did not run, so the draft's existing admission/whole-suite
obligation remains open. No green sibling gate was replayed solely for the two
metadata/type corrections.

## Design, routing and publication authority

Four more decisions now derive pinned token adoption, intended-versus-observed
URL routing, bounded broker-owned DECORVM filing and current publication scope.
The publication effector cites standing authority plus fresh sweeps, which differs
from the historical lever's released-state recipe. No visibility change or new
authorization is inferred from this review. The current read-only heartbeat is
not armed for filing by an environment flag.

Current count: 60 selected, 37 requiring component review, 95 executable acceptance
definitions still missing. All original records and lifecycle fields are retained.
No DNS, publication, design adoption or recurring process was changed.

Authority qualification: PUBLICATION-POLICY.md still requires a publication click,
while apply-visibility.py cites a later standing directive. The decision records
this unresolved policy/prompt-lineage conflict. Neither source alone is treated
as permission for a visibility change in this implementation tranche. Owner:
publication policy and L-PORTAL-PUBLISH-WAVE-1; next action is a scoped lineage
review before any effect.
