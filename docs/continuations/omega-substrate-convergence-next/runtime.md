# Runtime

Derive current truth at every packet boundary. Start with:

```bash
git fetch --prune
gh pr view 1705 --repo organvm/limen --json headRefOid,state,mergeStateStatus,statusCheckRollup
gh pr view 6 --repo organvm/portvs --json headRefOid,state,mergeStateStatus,statusCheckRollup
gh pr view 361 --repo organvm/domus-genoma --json headRefOid,state,mergeStateStatus,statusCheckRollup
python3 scripts/substrate-convergence.py \
  --manifest "$HOME/Workspace/4444J99/portvs/.worktrees/omega-substrate-literal/governance/workspace-manifest.yaml" \
  --workspace-root "$HOME/Workspace" --json
bash "$HOME/Workspace/4444J99/portvs/.worktrees/omega-substrate-literal/jack.sh" --plan --json
python3 "$HOME/Workspace/domus-genoma/.worktrees/omega-substrate-literal/dot_local/bin/executable_domus-home-guard.tmpl" --check --json
```

Those compatibility paths are probes, not permanent architecture. Once each
repository occupies its manifest-declared canonical home, use
`WORKSPACE_ROOT`, `PORTVS_ROOT`, `LIMEN_ROOT`, and `DOMUS_ROOT` exclusively.

Re-derive active process CWDs, dirty branches, stashes, remotes, sealed
inventories, restoration receipts, free storage, and trial state before any
mutation. Preserve unchanged green shard receipts. Route every newly found
gap to its existing owner before switching sessions.
