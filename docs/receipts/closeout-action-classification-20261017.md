# Canonical read-only closeout admission

The session checker was classified as an unknown mutation, so its transcript and
scope inputs were treated as writes outside the worktree. Four regression cases
failed before this correction: canonical absolute/relative invocation, no-writer
operation, and a receipt name containing a heavy-command filename.

The new observation path accepts only explicit session-mode calls to the checker
under the source root of the policy that is actually loaded. It validates known
flags and interpreter forms. A copied script name, leaf symlink, unknown or
duplicate options, estate mode, shell chaining and output redirection remain
outside this observation path. The global installed policy therefore requires its
own installed protocol checker; an arbitrary mutable checkout is not trusted by
name. This does not disable writer admission.

Validation: 68 focused admission and owner-process tests passed in 12.05 seconds,
including all 16 new regressions. Ruff lint, format, diff hygiene and the gates
registry predicate passed. The expanded admission gate owns future coverage.
The complete scoped command was not run: native host admission rejected it with
heavy-lease-held. No full CLI/API pass or native policy adoption is claimed.

Native acceptance remains with Domus issue #487. Two fresh sessions, paired
allow/deny evidence, representative events and the original 24-hour observation
are unchanged. Scope checks, trust hashes and timestamps were not fabricated.
