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

## Branching & merging

- Never commit to `main` directly. Branch by intent: `feat/`, `fix/`, `heal/`, `chore/`,
  `docs/`, `refactor/`. One PR per branch → `main`, squash-merge, delete the branch.
- A merge to `main` **auto-deploys** the live site/API when the diff touches a deploy-trigger
  path (`web/app/**`, `web/api/**`, `cli/**`, `tasks.yaml`, the deploy workflows). Those PRs
  need green CI before merge. See `CLAUDE.md` → **Merge & Branch Protocol** and
  `scripts/merge-policy.sh` (the predicate that decides each case).

## What we accept

- Bug fixes and regressions (with a test that fails before, passes after)
- Documentation and developer-experience improvements
- Performance and reliability work on the CLI, adapters, and organs
- New capability proposals — open an Issue to discuss before large changes

## Getting help

- Open an Issue for questions or to propose a change.
- Start with `README.md` (overview), `SCHEMA.md` (the task schema), and `AGENTS.md` (protocol).
