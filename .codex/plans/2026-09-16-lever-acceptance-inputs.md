# Acceptance input validation

Owner: Codex. Continue the full gap-filling plan after decision coverage landed
in Limen #2630. Ninety-five executable acceptance definitions remain missing;
this repair prevents malformed inputs from entering the existing debt executor.

The classifier now validates the entire record set before list or dissolve
can execute a predicate. Duplicate/missing IDs, non-object entries, malformed
implementation/debt fields and invalid command types fail without mutation.
An unreadable or non-object armed registry also fails before execution.
Terminal histories are validated without reopening or changing their lifecycle.

Thirteen focused tests pass, including malformed mixed records, duplicate IDs,
non-object armed registry preservation and existing nested-consent behavior.
No live dissolution or acceptance predicate was run. Production registry records
are unchanged. Full scoped verification precedes integration.

Next: bind real component acceptance predicates to each condition, preserving
engineering evidence separately from consent and external outcomes. Do not fill
missing predicate fields with commands that cover only part of the condition.

## Verified required-check absence

The acceptance-input repair at 7963833ec passed 11 cheap gates, 7,714 CLI tests
(two skipped), and 52 API tests. Its unchanged receipts remain evidence.

Independent diagnosis found GitHub CLI's no-required-checks response is non-JSON.
The merge reader now accepts that response only after a read of the exact base
branch confirms protected=false and a second read returns an empty effective
rules list. Authorization errors, unknown base, malformed responses and any
active rules remain unmeasured. No protection setting is changed.

Twenty-eight focused merge tests pass, including missing/present policy,
authorization failures, encoded branch names and existing required failures.
Live read-only verification of organvm/laurea confirms no failing required checks;
no unchanged-head merge submission was repeated. Reference:
https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch
