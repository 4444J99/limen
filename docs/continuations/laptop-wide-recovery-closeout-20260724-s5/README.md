# Laptop-wide recovery closeout S5

Continue only the authorized, non-destructive recovery lanes from the S4 receipt in
`evidence.json`. Re-derive live state before acting; the receipt is a historical boundary, not
permission to reuse a stale manifest.

## Objective

Reach the next authorized fixed point without disturbing the dirty live Limen checkout, PR #1493,
or any active Claude lease. Do not claim Omega while an owner predicate is red. Do not edit
`tasks.yaml`, delete branches/worktrees/data, handle credentials beyond the documented promptless
bootstrap, mutate or restart Backblaze, spend money, publish messages, or launch unreserved
children.

## First probes

1. Validate `workstream.json`, admit its finite runway, and compare the exact topic head with its
   remote.
2. Read `evidence.json`; then refresh remote main, broker capabilities, GitHub authentication,
   host admission, mounted custody, `/System/Volumes/Data`, and the two owner predicates below.
3. Run the exact 11-owner GITVS predicate from `tasks.yaml`. Submit a transition only through a
   broker lease and only when the authenticated exhaustive census is zero-untyped.
4. Run `python3 scripts/reclaim-worktrees.py --check --json`. Treat the returned plan SHA and full
   candidate set as a new authorization object. Never apply a prior six- or seven-candidate digest.
5. From the clean Domus owner worktree, run the zero-write Backblaze dry-run. Apply only with an
   unexpired, signed `domus.host_mutation_authorization.v2` receipt matching the live host, target,
   source, result, plan, and attempt. Restart remains a separate gate.

## Owners and predicates

- Credential and authenticated conduct/GitHub access: Limen issue #320. Bootstrap once, without
  tracing or printing values; if still unavailable, leave task state unchanged.
- Disk and worktree custody: Limen issue #685. Green means at least 200 GiB internal free space,
  zero safely reapable unlocked roots, and a durable owner receipt for every survivor.
- Backblaze exclusions: `organvm/domus-genoma` issue #322 and the
  `work/backblaze-exclusions-20260724` owner worktree. Green requires matching signed authorization,
  exact apply/postflight/readback, and a separately authorized restart.
- GITVS: `GITVS-UNCAPPED-PR-DEBT-0715`. Green means the exact authenticated 11-owner predicate is
  exhaustive with zero untyped PRs and its broker receipt is accepted.
- PR #1493 and its Claude worktree remain `lifecycle:active-human`; observe only.

Run scoped predicates once per unchanged exact head. Run strict Omega only after every prerequisite
sensor and owner gate is current and green. Before this successor runway expires, either reach its
fixed point or emit another finite capsule; never extend the admitted deadline in place.

## Launch command

```bash
git -C /Users/4jp/Workspace/limen fetch origin work/laptop-wide-recovery-closeout-20260724-s4 && limen workstream /Users/4jp/Workspace/limen laptop-wide-recovery-closeout-20260724-s5 --from origin/work/laptop-wide-recovery-closeout-20260724-s4 --workstream lifecycle-recovery --runway 8h --agent auto --prompt 'Read and execute docs/continuations/laptop-wide-recovery-closeout-20260724-s5/README.md and workstream.json. Re-derive every live predicate before mutation, preserve all named owner boundaries, and stop or successor-route before the admitted deadline.'
```
