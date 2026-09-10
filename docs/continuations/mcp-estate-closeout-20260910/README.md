# MCP estate closeout continuation capsule

This capsule carries the post-merge verification and the protected live-root
handoff for the MCP estate successor. The MCP implementation is landed; the
remaining lane is host-owned runtime activation and heartbeat custody.

## Durable receipts

- PR #2607 is merged into `main` at
  `bc19871ac688f6a0892d61bffdd699070b6df620`.
- The immutable Limen runtime is installed at that exact SHA.
- Focused MCP estate validation: `133 passed`.
- `scripts/verify-scoped.sh`: no local modifications to verify.
- `python3 scripts/check-runtime-lag.py`: `OK`.
- `python3 scripts/handoff-relay.py --check`: `OK` after writing `logs/handoff.json`.

## One launch command

```bash
bash docs/continuations/mcp-estate-closeout-20260910/kickstart.sh
```

The command enters the capsule's isolated worktree when available, validates
the finite runway, and re-derives the protected host gate. It is read-only
with respect to branch switching and launchd.

The bounded workstream contract is `workstream.json`; it grants a four-hour
renewable runway and retains runtime/host mutations as operator-gated.

## Current boundary

The live checkout is one commit behind the installed release and the heartbeat
LaunchAgent is absent. `docs/dispatch-health.md` and
`docs/always-working.md` are the owning records. Do not switch the live branch,
reload launchd, or enable asynchronous work without the operator gate emitted
by `live-root-gate.py`.
