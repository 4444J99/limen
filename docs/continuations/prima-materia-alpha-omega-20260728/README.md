# Prima Materia Alpha-to-Omega Continuation

## Objective

Land PR #1606 as an honest admission gate. Do not begin repository evacuation,
private-data movement, reclaim, eviction, or dematerialization until that head
is merged through the queue, installed as the immutable runtime, and a
successor worktree is launched from the merged SHA.

## Authorities and prohibitions

- Delivery receipt: PR #1606. Derive its exact head and checks live.
- Current installed/runtime authority is recorded in `frozen-wave.json`; never
  treat the active PR checkout as the control-plane anchor.
- Protection registry:
  `institutio/governance/reconciliation-protected-exclusions.json`.
- Source registry:
  `institutio/governance/prima-materia-source-registry.json`.
- Live evidence:
  `live-reconciliation.json`.
- Frozen denominator and independent inputs:
  `frozen-wave.json`, `source-inventory.json`, `resource-task-graph.json`, and
  `reclaim-census.json`.
- Never mutate, signal, preserve, archive, prune, remove, or repair a protected
  owner root, branch, registration, file, or process.
- Never apply a reclaim plan without its unchanged expected digest and required
  custody/acceptance receipts.
- Never represent an interrupted or timed-out census as zero.

## First probes

```bash
domus-limen-runtime status
git ls-remote origin refs/heads/main
git status --short --branch
uv run --project cli python scripts/reclaim-worktrees.py \
  --repository-root /path/to/canonical-limen --check --json
uv run --project cli python scripts/alpha-omega-reconcile.py --help
```

## Completion and switch predicates

This α workstream ends when the exact PR head has green `python` and `pr-gate`
checks and is published ready for Anthony's merge-queue admission. The
post-merge successor begins only after the merged SHA is installed and the
direct session is registered `human_protected`.

The overall campaign ends only when `live-reconciliation.json` reports:

- `fixed_point.complete = true`;
- `fixed_point.unchanged = true`;
- `fixed_point.lambda_passed = true`;
- `fixed_point.omega_admitted = true`.

A context, resource, or provider boundary switches sessions only after the
current exact head and this capsule have remote custody.

## Ownership

The career-portal session exclusively owns the protected career lane and its
`OmegaOwnerReceiptV1`. This continuation only consumes that receipt. It never
mutates, signals, registers, prunes, or retires the protected lane.

The conduct broker owns claims and lifecycle transitions. If its authenticated
capabilities endpoint is unavailable, inspection and already-leased local work
may continue, but no new β–Ω packet or transition may be invented locally.

## Launch

```bash
cd "${LIMEN_ROOT:-$HOME/Workspace/limen}/.worktrees/prima-materia-alpha-omega-20260728" \
  && bash .limen-workstream/kickstart.sh
```
