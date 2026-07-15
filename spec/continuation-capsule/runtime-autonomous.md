# Runtime decision contract

Before selecting or mutating work, re-probe current reality:

1. Compare exact local, base, default, and CI heads.
2. Read the nearest instructions and typed owner contracts.
3. Check handoff age, pause state, provider headroom, mounted substrates, host pressure, active
   sessions, and lifecycle custody through their owning probes.
4. Derive provider and lane from live capabilities and gates. Never pin a future model, provider
   table, task count, duration, resource threshold, or completion percentage.
5. Treat unknown, stale, malformed, or contradictory sensor truth as `invalid`.

At each boundary derive one state:

- `continue`: a scoped predicate is false and safe dispatchable work exists;
- `switch`: this lane is blocked but another authorized lane is safe;
- `wait_relay`: no safe lane can run and every residual already has a durable owner;
- `settled`: scoped predicates pass twice, the second pass is byte-identical/no-growth, and every
  discovered leaf has terminal custody or a named external gate;
- `invalid`: packet, base, contract, module, or sensor truth cannot be trusted.

Reality determines the state. Never edit evidence, thresholds, or status records to manufacture an
ending. If a boundary requires another session, emit its successor capsule and launch command.
