# Census audit

- Exact pagination already exists in `cli/src/limen/github_estate_census.py`; it reconciles totals,
  moving totals, duplicate identities, and cursor exhaustion.
- The cross-owner collector and tracked/private split already exist, but the tracked 2026-08-21
  snapshot is stale launch input rather than current truth.
- The prior contract omitted archive state, default SHA/generation, closed-PR lineage, review
  threads, check-job execution, local refs, worktrees, stashes, and Agy source-instance coverage.
- The protective tranche adds repository generation facts to the existing census, reusable exact
  pagination for historical/review connections, and an aggregate read-only recovery predicate.
- A full current universe refresh remains owned by this capsule and must expose every cursor/API
  failure rather than reducing the denominator.
