# Handoff and reproduction

## Next-session contract

The closeout leaves a generated capsule README and one launch command. The prompt begins by
re-probing remote main, CI, board stability, handoff, provider headroom, mounts, host pressure, and
active sessions. It defines predicates; it does not assert which lane is next or that Omega is
reachable.

The repository-backed capsule is rooted at
`/Users/4jp/Workspace/limen/.worktrees/next-autonomous-epoch-20260714`. Start it with:

```bash
bash "/Users/4jp/Workspace/limen/.worktrees/next-autonomous-epoch-20260714/.limen-workstream/kickstart.sh"
```

The kickstart fetches remote refs, prints local status, and starts Codex with the capsule README index
as its initial prompt. Pushed branch `work/next-autonomous-epoch-20260714` is durable custody.
Launch-time probes, not a frozen branch SHA or provider catalog, determine what the session may do
and when its scoped predicates settle.

## Reproduction

```bash
# Board model/status truth
python3 scripts/validate-task-board.py --tasks tasks.yaml

# Warm-resume and single-writer truth
python3 scripts/tabularius-organ.py --check
python3 scripts/handoff-relay.py --check

# Epoch PR counts
START=2026-07-09T04:00:00Z
END=2026-07-14T13:17:40Z
gh api --method GET search/issues -f q="repo:organvm/limen is:pr created:${START}..${END}" -f per_page=1 --jq .total_count
gh api --method GET search/issues -f q="repo:organvm/limen is:pr merged:${START}..${END}" -f per_page=1 --jq .total_count

# Handoff branch patch-equivalence proof
git show --pretty=format: 2b434e2ec2906179549317c3adb1e8077fed6bfc | git patch-id --stable
git show --pretty=format: b33c013bda2992061016390ef95e717bbc4579d4 | git patch-id --stable
```
