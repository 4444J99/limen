# Deployment

Production deployment is separate from the agent dispatch protocol in `AGENTS.md`. Follow this file
when a task explicitly asks for SaaS deployment or deployment configuration.

## Required environment

For the web API:

| Variable | Required | Description |
|----------|----------|-------------|
| `LIMEN_API_TOKEN` | Yes | Bearer token for API auth |
| `LIMEN_ROOT` | Yes | Path to the Limen root on disk |
| `LIMEN_TASKS` | No | Alternative path to `tasks.yaml` |

For the Next.js dashboard, set `NEXT_PUBLIC_API_URL` to the API endpoint. Local development defaults
to `http://localhost:8000`.

GitHub-backed production adapters are read-only projections. They may read
`tasks.yaml` from the configured branch, but mutation requests fail with the
typed TABVLARIVS deferral before any GitHub Contents write. Durable board
changes are published by the queue-owned `tabularius/board-projection` PR rail.

## Railway API

```bash
railway login
railway init
railway up
```

## Vercel dashboard

```bash
vercel login
vercel --prod
```

## Safety checks

- Do not paste tokens or secret values into logs, PRs, commits, or task output.
- Treat deploy-trigger paths as website-sensitive; follow `CLAUDE.md` → **Merge & Branch Protocol**
  and `scripts/merge-policy.sh`.
- Record deployment evidence with the target environment, command, result, and rollback path.
