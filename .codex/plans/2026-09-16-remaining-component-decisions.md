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
