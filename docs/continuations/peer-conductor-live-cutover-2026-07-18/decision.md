# Live decision protocol

## First probes

```bash
git fetch origin --prune
git rev-parse HEAD origin/work/peer-conductor-mesh-20260718 origin/main
git status --short --branch
gh pr list --repo organvm/limen --head work/peer-conductor-mesh-20260718 \
  --json number,state,isDraft,headRefOid,statusCheckRollup,url
gh pr view 1171 --repo organvm/limen \
  --json state,isDraft,headRefOid,mergeable,statusCheckRollup,url
gh api orgs/organvm/copilot/billing
python3 scripts/task-writer-audit.py --enforce-zero
python3 scripts/credential-wall.py --check
```

Also query the organization profile PR in `organvm/.github`, the deployed Worker URL, current
provider meters, active sessions, host pressure, and the newest two complete campaign receipts. A
missing sensor is an invalid sensor, not permission to guess.

## Routing

- `continue`: one scoped predicate is false and safe, authorized work remains in the current lane.
- `switch`: another healthy native lane has the required capability and a broker reservation.
- `wait_relay`: all reversible code and documentation is durably owned; only a filed credential,
  billing, deployment, provider, or active-peer gate remains.
- `settled`: all finish-line predicates pass twice and the second complete campaign pass is
  zero-growth.
- `invalid`: branch, packet, authority, schema, census, credential, or sensor truth is stale or
  contradictory.

Do not poll a filed gate. Continue other reversible lanes, and emit a successor capsule if context,
resources, or ownership require another boundary.

