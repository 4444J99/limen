# Limen Gemini Adapter

This file explains Gemini's native transport. It does not define a separate conductor role, task
lifecycle, or authority model. `AGENTS.md` → **Peer Conductor Contract** is canonical.

## Conductor Swarm MCP Integration

Gemini reaches the authenticated Limen MCP surface through ianva. Conductor is a temporary
capability, never a rank; Gemini may conduct, execute, or review only within the authority and
resource claims of its registered session and leased work packet.

The shared MCP interface is:

- `conduct_capabilities`
- `conduct_register`
- `conduct_submit`
- `conduct_split`
- `conduct_graph`
- `conduct_heartbeat`
- `conduct_report`
- `conduct_harvest`
- `conduct_adopt`
- `conduct_cancel`
- `conduct_request_stop`

Legacy task tools are compatibility adapters to the same broker events. They do not authorize a
Gemini process to write the local `tasks.yaml` projection.

## Execution Protocols

1. Register with `agent: gemini`, the real native session/run identity, capabilities, worktree, and
   protection status.
2. Query live capabilities and submit or accept a schema-valid `WorkPacketV1`. Treat
   `preferred_agent` as a routing hint; never substitute another provider identity.
3. Begin mutation only after the broker returns a lease covering the task and all write resources.
   Use an isolated worktree based on the packet's observed remote head and claimed path scope.
4. Before starting any Gemini subagent or other separate capacity, reserve it with `conduct_split`.
   Hidden native fanout is rejected.
5. Heartbeat the lease, recheck exact remote heads before push, run the packet predicate, and return
   a schema-valid `RunReceiptV1` with exact-head evidence and spend.
6. Use `conduct_harvest` for child results. A dead parent does not cancel children; use
   `conduct_adopt` only after the broker proves absence. Never adopt, cancel, signal, stash, reset,
   or reap a protected human session.

PR waiting and merge mechanics remain those in `CLAUDE.md` → **Merge & Branch Protocol**:
`scripts/await-pr.sh` is the only synchronous waiter, and the packet's authority envelope decides
whether a merge is allowed.
