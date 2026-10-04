# Runtime decision contract

Read `workstream.json` before routing work. Its finite runway and authorization fields are executable
inputs, not prose: the kickstart validates them and exports the total, deadline, and live remaining
seconds. Full approval means proceed without confirmation for in-scope reversible work. Destructive,
credential, paid-spend, public-send, and runtime/host mutations remain gated.

Before selecting or mutating work, re-probe current reality:

1. Compare exact local, base, default, and CI heads.
2. Read the nearest instructions and typed owner contracts.
3. Check handoff age, pause state, provider headroom, mounted substrates, host pressure, active
   sessions, and lifecycle custody through their owning probes.
4. Act as the conductor: derive provider and lane from live capabilities and gates, then route
   independently bounded packets to healthy agents. Never pin a future model, provider table,
   resource threshold, or completion percentage.
5. Treat unknown, stale, malformed, or contradictory sensor truth as `invalid`.
6. Before every packet boundary, re-read the admitted contract and remaining runway. Do not start a
   packet that cannot close or successor-route before zero. Expiry denies a new session; it does not
   preempt or kill a provider process already running.

At each boundary derive one state:

- `continue`: a scoped predicate is false and safe dispatchable work exists;
- `switch`: this lane is blocked but another authorized lane is safe;
- `wait_relay`: no safe lane can run and every residual already has a durable owner;
- `settled`: scoped predicates pass twice, the second pass is byte-identical/no-growth, and every
  discovered leaf has terminal custody or a named external gate;
- `invalid`: packet, base, contract, module, or sensor truth cannot be trusted.

Reality determines the state. Never edit evidence, thresholds, or status records to manufacture an
ending. If a boundary requires another session, emit its successor capsule and launch command.
