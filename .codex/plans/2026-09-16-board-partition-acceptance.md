# Board partition executable acceptance

Owner: Codex; L-BOARD-PARTITION-DECISION, #2069. Full gap-filling scope remains active.

Replace the stale PR-number acceptance description with a read-only check of the current default file, authenticated private board, and expected deployed keeper identity. Require deployed-source ancestry on the default branch. Compare the entire public document to the counts-only projection, reject malformed private IDs/statuses/priorities, and re-read both snapshots, runtime identity and repository identity before returning acceptance. Changed sources or unavailable inputs return unmeasured (77); stable mismatch returns failure (1). Error output never includes private task fields or provider error text. All transport calls have finite deadlines; no POST, projection write or task transition is exposed.

Live observation at 2026-09-16T04:44:34Z passed: 3,186 tasks, public blob 2d140cab1389f29eaa0cdb2538f60e10c5260e03, default c11d749c0ce82e197940ae84af8e348b72935e90, keeper 16fd02e1a72d7ee8d5432d637221938aa94e3cf5 / deployment 4839ca12-ac13-4b48-a215-57b727117243. This is a current observation, not a perpetual receipt. A later keeper deployment requires an explicitly captured expected SHA.

The previous two-amendment keeper publication receipt remains separate evidence. No lever lifecycle or historical record is reopened or discharged. This adds one executable predicate; the other unimplemented acceptance definitions remain in the original denominator.
