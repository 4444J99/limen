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
