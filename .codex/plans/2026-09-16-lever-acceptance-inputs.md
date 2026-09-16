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
