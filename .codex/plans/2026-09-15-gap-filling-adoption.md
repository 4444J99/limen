# Gap-filling adoption and continuation

Owner: Codex, branch fix/gap-filling-adoption-20260915. The full scope and all
uncompleted obligations in 2026-09-15-gap-filling-implementation.md remain active.

PR #2623 landed as 16fd02e1a72d7ee8d5432d637221938aa94e3cf5 with an identical
reviewed tree. The manual Worker deployment succeeded and its live identity
matches. The digest-reviewed bounded heartbeat is installed and verified; its
receipt reports finding rather than blanket health. No old daemon was revived.

Default CI now passes the original worker fixture and fails later at session
orientation: missing private custody escapes its broad Exception handler. This
branch adds an explicit custody exception path that reports unmeasured, preserves
the private-board boundary, and makes the owning gate scoped. Seven focused tests
and the full component predicate pass locally. Re-establish successful default CI
after landing this repair; retain downstream failures if more are found.

Inventory activation remains owned by #269 and credential wall #320. The deployed
endpoint now responds with the expected collector-role restriction; the documented
local dedicated collector credential is absent. Do not add this role to the ordinary
conductor, expand fleet capacity, or relax 250/900 limits. Provisioning remains the
exact account-authority atom; continue all independent estate and lever work.

Receipts: docs/receipts/gap-filling-progress-20260915.json and the source-bound
review dispositions file. Next integration is one exact-head PR on Limen's
registered single-owner rail. All 79 unreviewed decisions, six-target relay
activation/coverage, Editorial prerequisites, template/security and product
obligations remain in the full objective.
