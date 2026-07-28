# Prima Materia Alpha-to-Omega Continuation

## Objective

Drive the live estate from the redacted reconciliation receipt to two equal λ
state digests, while retaining the career-portal lane as an externally owned
hard exclusion until its owner closes it independently.

## Authorities and prohibitions

- Base implementation SHA:
  `4a86f3825ef3a2acf308e1bbd3a0c8463c42d0e1`.
- Protection registry:
  `institutio/governance/reconciliation-protected-exclusions.json`.
- Source registry:
  `institutio/governance/prima-materia-source-registry.json`.
- Live evidence:
  `live-reconciliation.json`.
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
uv run --project cli python scripts/reclaim-worktrees.py --check --json
uv run --project cli python scripts/alpha-omega-reconcile.py --help
```

## Completion and switch predicates

The workstream ends only when `live-reconciliation.json` reports:

- `fixed_point.unchanged = true`;
- `fixed_point.lambda_passed = true`;
- `fixed_point.omega_admitted = true`.

A context, resource, or provider boundary switches sessions only after the
current exact head and this capsule have remote custody.

## Ownership

The career-portal session exclusively owns the protected career lane. This
continuation owns all other λ evidence, including a complete bounded reclaim
census, repository reconstruction receipts, two-device private restoration,
and empty-scratch hydration/replay/composition/dematerialization receipts.

## Launch

```bash
cd "${LIMEN_ROOT:-$HOME/Workspace/limen}/.worktrees/prima-materia-alpha-omega-20260728" \
  && bash .limen-workstream/kickstart.sh
```
