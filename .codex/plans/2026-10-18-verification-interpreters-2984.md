# Verification interpreter consistency - issue 2984

Owner: existing gate-python-resolver branch; no new worktree.

1. Merge current origin/main normally.
2. Add selection wrapper and resolve whole and hermetic Python.
3. Test fresh-shell selection, argument/status forwarding, environment isolation; update runnable docs.
4. Run scoped verification once; stop on admission denial and report before publication.

Issue 2983 CLI capability contract remains separate.

Implementation evidence: 18 focused tests and 2 subtests passed; agent-docs, check-gates, Ruff, and diff checks passed. The shipped whole verifier was exercised only inside a temporary fixture stopping at a controlled compile failure; no full whole-system run occurred.

BLOCKED: one canonical scoped verification attempt was refused by the host hook with swap-fraction,vitals-shed before execution. Preserve the implementation through the existing branch and PR; rerun scoped verification only after the owning host-pressure predicates clear. The PyYAML-only fallback remains fail-closed when pytest is absent; later-candidate retry and CLI capability remain separate resolver work.
