# Running Claude session binding

Owner: #2966; continuation: #3022.

A running background job may have loaded settings before the registration hook
was installed. A hook on disk and a zero hook exit code do not prove a binding.
SessionStart emits a warning when no successful registration is observed,
including when the general orientation uses its cached digest.

From the actual Claude job, resolve the gate Python interpreter as documented in
AGENTS.md, then run scripts/bind-running-claude-session.py with --session-id set
to its exact native session ID and --worktree set to its .claude/worktrees root.
CLAUDE_JOB_DIR must identify that running job. Never invent a replacement ID.
The command verifies the Claude principal and its registration role before any hook
write, then drives the existing registration hook and requires authenticated live
readback of the same ID, Claude identity, exact worktree and protected healthy
record. It reads only the Claude lane bearer from the owned 0600 cache or explicit
lane environment; it refuses the default bearer. Missing or ambiguous evidence
returns unmeasured and exit 2.

The ID remains unchanged from the native payload through LIMEN_SESSION_ID,
conduct register --session-id, and the session-closeout lookup. Throwaway fixture
tests cover that chain. They are not a measured live Claude closeout.
Use the existing no-tasks-on-me predicate and real owner receipt twice for that
separate acceptance. Codex does not fabricate a Claude transcript or register
another provider's live identity.

R1 source application was denied twice by the tool bridge. The single prepared
operator helper is scripts/repair-workstream-destination-3022.py. Run --check
to inspect its exact-base diff; --apply writes that same patch only on the owning
topic branch, refusing any moved source generation. It retains ordinary growth
reservation and target-volume checks. It does not extend an agent deadline or
authorize custody, deletion, deployment or unrestricted dispatch.
