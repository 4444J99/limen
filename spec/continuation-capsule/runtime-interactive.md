# Runtime contract

Read `workstream.json` before work. Its validated finite runway and authorization are executable
inputs. Full approval means proceed without confirmation for in-scope reversible work; destructive,
credential, paid-spend, public-send, and runtime/host mutations remain gated.

Keep the session bounded to the capsule objective and owner. Re-probe repository state before a
mutation, use the narrowest executable predicate, and act as conductor when there are independent
packets: derive healthy lanes live and route them without pinning a provider or model. Re-check
remaining runway at every packet boundary and stop or successor-route before zero. Expiry denies a
new session; it never preempts a provider process already running. Unknown or contradictory state is
a blocker, not permission to guess.
