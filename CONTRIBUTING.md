# Contributing to Limen

Limen is a cross-agent, cross-repo, budget-capped task intake system. This guide is for
**human** contributors. If you are an **AI agent**, read `AGENTS.md` (the dispatch contract)
and, for Claude Code specifically, `CLAUDE.md` (the operating charter) instead.

## Project layout

| Path | What it is |
|------|-----------|
| `cli/` | The `limen` CLI (Python / Click) — dispatch, harvest, status, capacity, converge |
| `web/api/` | FastAPI runtime adapter |
| `web/worker/` | Cloudflare Worker — the live runtime (GitHub-Contents storage) |
| `web/app/` | Next.js dashboard (static export → Firebase Hosting) |
| `mcp/`, `ianva/` | MCP server + doorway/aggregator |
| `spec/contracts/` | Portable JSON Schemas the generated surfaces must satisfy |
| `scripts/` | The operational fleet (heartbeat, verification, merge policy, organs) |
| `tasks.yaml` | The single source of truth for the task board |

## Getting set up

```bash
pip install -e 'cli[test]'     # CLI + test extras
pip install -e mcp/            # MCP server (optional)
(cd web/app && npm install)    # dashboard (optional)
```

## The gate matrix — run before every PR

```bash
python -m ruff check cli/src cli/tests web/api mcp     # lint (py311, line-length 120)
python -m pytest web/api/tests cli/tests -q            # tests
python scripts/check-agent-docs.py                     # agent-doc ↔ code state-vocab drift
node scripts/validate-contract-schemas.mjs             # surface contracts
scripts/verify-whole.sh                                # whole-system predicate (exit 0 ⟺ green)
```

Run one test file or case:

```bash
python -m pytest cli/tests/test_dispatch.py -q
python -m pytest cli/tests/test_dispatch.py::test_x
```

## Coding style

- Python targets 3.11. Use Ruff (`line-length = 120`) and keep CLI behavior in small, testable
  modules under `cli/src/limen/`.
- Tests use pytest. Put CLI tests under `cli/tests/` and API tests under `web/api/tests/`; name
  files `test_*.py` and cases `test_<behavior>`.
- TypeScript/JavaScript checks are owned by each web package. Use `npm run check` in `web/worker`
  and `npm run build` in `web/app` for affected changes.
- Shell scripts should be idempotent, explicit about side effects, and safe to re-run. Prefer
  `set -euo pipefail` for new Bash scripts.

## Branching & merging

- Never commit to `main` directly. Branch by intent: `feat/`, `fix/`, `heal/`, `chore/`,
  `docs/`, `refactor/`. One PR per branch → `main`, squash-merge, delete the branch.
- A merge to `main` **auto-deploys** the live site/API when the diff touches a deploy-trigger
  path (`web/app/**`, `web/api/**`, `cli/**`, `tasks.yaml`, the deploy workflows). Those PRs
  need green CI before merge. See `CLAUDE.md` → **Merge & Branch Protocol** and
  `scripts/merge-policy.sh` (the predicate that decides each case).

## Pull request checklist

- Describe the user-visible change and the affected components.
- Link the issue, task, or PR that motivated the change when one exists.
- Paste the commands you ran and their outcomes; say explicitly if a gate was not run.
- Include screenshots or contract diffs for dashboard/API surface changes.
- Keep secrets, tokens, private customer data, and local machine paths out of PR text.

## Maintaining agent instructions

When changing `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or generated instruction templates, keep
the root protocol authoritative and run `python scripts/check-agent-docs.py`. Status vocabulary,
precedence, agent names, and referenced scripts should stay machine-checked rather than manually
remembered.

## What we accept

- Bug fixes and regressions (with a test that fails before, passes after)
- Documentation and developer-experience improvements
- Performance and reliability work on the CLI, adapters, and organs
- New capability proposals — open an Issue to discuss before large changes

## Getting help

- Open an Issue for questions or to propose a change.
- Start with `README.md` (overview), `SCHEMA.md` (the task schema), `AGENTS.md` (protocol), and
  `docs/deployment.md` (deployment).
