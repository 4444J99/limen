# RELAY

**What changed:** The MCP estate successor was reconciled with current
`main`, pushed, verified, and squash-merged as #2607.

**Proof:** Merge commit
`bc19871ac688f6a0892d61bffdd699070b6df620`; focused MCP estate suites
`133 passed`; exact merged runtime installed; runtime-lag predicate `OK`;
handoff relay `OK`; scoped verification reports no local diff.

**Launch:** `python3 scripts/live-root-gate.py --write --fetch`

**Owner boundary:** The only remaining residue is the protected live-root and
heartbeat activation gate recorded in `docs/dispatch-health.md` and
`docs/always-working.md`. It requires operator approval and is not silently
reclassified as complete.
