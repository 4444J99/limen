# Machine-Wide Host Admission

> Relocated verbatim from `AGENTS.md` (2026-08-06) under the instruction-surface byte budget
> (`institutio/governance/gates.yaml` → `instruction_surfaces`, check S). The binding stub in
> `AGENTS.md` points here; this file is the full doctrine.

Every heavy local Codex, Claude, OpenCode, Agy, or Limen surface must enter through the shared host
admission boundary documented in [`host-work-admission.md`](host-work-admission.md).
Codex conversation roots may always open concurrently: `UserPromptSubmit` never acquires a global
execution lease, even when stable action denial is unavailable. Source mutations require a linked
worktree and one scoped writer lease per worktree; distinct worktrees may have concurrent writers.
At most one heavy local surface remains machine-wide. New heavy work is denied under declared
Backblaze, swap, disk, or VITALS pressure; existing work is never killed, restarted, or retuned and
may perform bounded closeout.

The installed Codex client's structured `PreToolUse` denial is the action boundary for project-hook
mutations. A missing or unstable action-denial capability must never fall back to a blanket one-root
session lock. Guarded heavy entrypoints still acquire the same atomic heavy lease internally, and
`SubagentStart` remains advisory. Leases bind PID plus process-start identity, refresh finitely, and
clean up only dead, reused, or stale owners. Never delete the lease store or signal a peer to seize
capacity.

Project Codex families are capped at three threads and depth one. Global hook deployment and the
verified non-backed scratch root belong to the Domus cartridge; Limen must not patch home-directory
hooks or backup configuration directly.
