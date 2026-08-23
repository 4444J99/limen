# Remote-reaping audit

- The legacy script mixed classification and mutation, accepted branch-only evidence, allowed a
  global wildcard, and could delete without repository identity, exact-tip CAS, keeper authority,
  a write-ahead journal, or post-delete absence proof.
- Its dry-run also fetched with prune, so it was not strictly read-only.
- The remote acceptance ledger held 129 rows with zero repository fields; the local ledger held 422
  rows with zero repository fields. Historical rows are not upgraded into deletion authority.
- Existing exact branch pagination, paired-custody modules, and the worktree-abandonment journal
  supplied reusable patterns.
- The protective tranche disables the legacy apply path and introduces separated plan, verify,
  capability, effect, and reconciliation surfaces. No capability has been issued and no ref was
  deleted in this tranche.
