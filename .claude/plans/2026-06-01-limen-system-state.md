# System State — 2026-06-01

## Dashboard
- URL: https://device-streaming-067d747a.web.app
- Source: ~/Workspace/limen/web/app/
- Deploy: firebase deploy --only hosting --project device-streaming-067d747a
- Rebuild: auto (cron hourly) + push trigger

## Repos in scope

| Repo | Org | State |
|------|-----|-------|
| limen | 4444J99 | Active — dashboard + task pipeline |
| peer-audited--behavioral-blockchain | a-organvm | Active — 2 PRs merged 2026-06-01 |
| public-record-data-scrapper | a-organvm | Active — TS fix merged |
| conversation-corpus-engine | organvm-i-theoria | Active — codex_to_bundle merged |
| organvm-corpvs-testamentvm | a-organvm | LIMEN-011 pending |
| organvm-engine | a-organvm | Issues available for dispatch |
| the-actual-news | a-organvm | Clean |
| petasum-super-petasum | a-organvm | Issues available for dispatch |

## Agent Fleet

| Agent | Daily Budget | Today Used | Role |
|-------|-------------|------------|------|
| Jules | 100 | 0 | Code fixes, PRs |
| Claude | — | ~5 | Orchestration, architecture |
| Gemini | 10 | 0 | Audits, research |

## Blockers

1. PyPI token — cannot publish limen CLI
2. KV namespace ID — PR #640 deployed but namespace placeholder
3. opencode permission — needs restart to apply
