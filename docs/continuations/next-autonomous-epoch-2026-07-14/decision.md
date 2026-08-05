# Live decision protocol

## First probes

Run these or their current canonical replacements before selecting work. An absent or stale command
is evidence of an invalid sensor, not permission to guess.

```bash
git fetch origin main --quiet
git rev-parse HEAD origin/main
git status --short --branch
gh run list --repo organvm/limen --branch main --limit 10
python3 scripts/tabularius-organ.py --check
python3 scripts/handoff-relay.py --check
python3 scripts/autonomy-governor.py mode
python3 scripts/validate-task-board.py --tasks tasks.yaml
df -h /
mount
```

Also derive provider headroom, lifecycle custody, active-session ownership, and exact PR state from
their live owner surfaces. Do not rely on counts frozen in the prior report.

## Boundary state

At every meaningful boundary derive exactly one state:

- `continue`: a scoped predicate remains false and safe dispatchable work exists;
- `switch`: the current lane is blocked but another authorized lane is safe and underwritten;
- `wait_relay`: all safe execution is blocked and every residual leaf already has a durable owner;
- `settled`: all scoped predicates pass twice, the second pass is byte-identical/no-growth, and every
  discovered leaf is merged, owner-PR'd, preserved, or externally gated;
- `invalid`: packet, base, contract, or sensor truth is stale, malformed, or contradictory.

Do not target a predetermined ending. A human/external gate may justify `wait_relay`; it never
justifies a false `settled`. Require whole-estate strict Omega only when the live scope genuinely is
the whole estate; otherwise use the narrowest owner predicate that proves the admitted work.
