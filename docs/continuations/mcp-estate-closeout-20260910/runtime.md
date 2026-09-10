# Runtime state

- Repository: `4444J99/limen`
- Merged PR: `#2607`
- Merge commit: `bc19871ac688f6a0892d61bffdd699070b6df620`
- Installed runtime: exact merge SHA, verified by `scripts/check-runtime-lag.py`
- Local MCP estate proof: `133 passed`
- Handoff proof: `python3 scripts/handoff-relay.py --check`
- Working tree at capsule creation: generated ledgers pending explicit commit

The live-root predicate reports one protected mismatch: the live checkout is
one commit behind the release, and the heartbeat LaunchAgent is not present.
The gate's own packet requires operator approval before reconciliation or
launchd activation. This capsule does not claim those effects.
