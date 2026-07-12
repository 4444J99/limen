# SPECVLVM — the contributions mirror

> Outward to learn inward: each upstream is a lens on wiring worth absorbing; community and
> name recognition accrue as byproducts of genuine value. Rendered by
> `scripts/contributions-organ.py` from hub-ledger outputs only (PLAN-06 owner packet 04 —
> limen is the owner surface). **Nothing here sends** — every outbound act is the human's hand.

_Source: committed cache (as of 2026-07-09) · 24 tracked contribution(s)_

## Proof

| merged | open | no-PR | closed | protocol-due | post-close |
|---|---|---|---|---|---|
| 3 | 0 | 3 | 4 | 14 | 0 |

| upstream | contribution | ref | proof |
|---|---|---|---|
| PrefectHQ/fastmcp | fix: serialize object query params per OpenAPI style/explode rules | https://github.com/PrefectHQ/fastmcp/pull/3662 | merged |
| dbt-labs/dbt-mcp | fix: clarify OAuth page wording for non-configuring developers | https://github.com/dbt-labs/dbt-mcp/pull/669 | merged |
| primeinc/github-stars | feat: add CodeQL security analysis workflow | https://github.com/primeinc/github-stars/pull/39 | merged |
| jairus-m/dagster-sdlc | — | — | no-PR |
| m13v/agentic-titan | — | — | no-PR |
| temporalio/sdk-python | — | — | no-PR |
| a2aproject/a2a-python | fix(client): export TenantTransportDecorator and fix docstring | https://github.com/a2aproject/a2a-python/pull/915 | closed |
| aden-hive/hive | feat: add design versioning system for agent reproducibility | https://github.com/aden-hive/hive/pull/6707 | closed |
| databricks/dbt-databricks | feat: include job_id, run_id, and task_key in adapter_response | https://github.com/databricks/dbt-databricks/pull/1376 | closed |
| openai/openai-agents-python | fix(mcp): prevent leaked semaphore warnings during MCPServerStdio cleanup | https://github.com/openai/openai-agents-python/pull/2802 | closed |
| Clyra-AI/gait | feat: add CI/CD pipeline policy template with intent fixtures | https://github.com/Clyra-AI/gait/pull/110 | protocol-due |
| DataDog/guarddog | fix: normalize git URLs in npm_metadata_mismatch to avoid false positives | https://github.com/DataDog/guarddog/pull/703 | protocol-due |
| anthropics/anthropic-sdk-python | fix(bedrock,vertex): add missing 413 and 529 status error handling | https://github.com/anthropics/anthropic-sdk-python/pull/1306 | protocol-due |
| anthropics/skills | feat: add testing-patterns skill | https://github.com/anthropics/skills/pull/723 | protocol-due |
| camel-ai/camel | fix: generalize rate-limit retry to all model providers | https://github.com/camel-ai/camel/pull/3974 | protocol-due |
| dapr/dapr | fix: make DeliverBulk fallthru consistent with Deliver for empty status | https://github.com/dapr/dapr/pull/9719 | protocol-due |
| grafana/k6 | metrics: add Len and ForEach methods to TagSet | https://github.com/grafana/k6/pull/5770 | protocol-due |
| indeedeng/iwf | Add unit tests for timeparser and urlautofix packages | https://github.com/indeedeng/iwf/pull/601 | protocol-due |
| ipqwery/ipapi-py | feat: add Codecov integration for test coverage reporting | https://github.com/ipqwery/ipapi-py/pull/8 | protocol-due |
| langchain-ai/langgraph | feat: add restart-safety coverage for put_writes idempotency | https://github.com/langchain-ai/langgraph/pull/7237 | protocol-due |
| m13v/summarize_recent_commit | feat: add daily auto-trigger with --schedule and --watch modes | https://github.com/m13v/summarize_recent_commit/pull/2 | protocol-due |
| makenotion/notion-mcp-server | fix: correct children items schema in POST /v1/pages to use blockObjectRequest ref | https://github.com/makenotion/notion-mcp-server/pull/242 | protocol-due |
| modelcontextprotocol/python-sdk | fix: accept single supported content type in SSE mode Accept header | https://github.com/modelcontextprotocol/python-sdk/pull/2361 | protocol-due |
| tadata-org/fastapi_mcp | fix: preserve typed array `items` in nullable anyOf schemas | https://github.com/tadata-org/fastapi_mcp/pull/274 | protocol-due |

## Lifecycle (the audit of `LIFECYCLE.md`)

Staleness rule: an open PR untouched since before 2026-06-25 (14d before the source stamp) renders protocol-due — a bump is owed, staged,
and fired one-at-a-time by the human hand (never batch-bumped).

**Lifecycle debt — 7 workspace(s) reap-owed** (terminal PR, no recorded closeout:
archive the tracking repo, settle the fork, mark the ledger entry closed-out):

- `a-organvm/contrib--a2aproject-a2a-python` — closed
- `a-organvm/contrib--adenhq-hive` — closed
- `a-organvm/contrib--databricks-dbt-databricks` — closed
- `a-organvm/contrib--dbt-mcp` — merged
- `a-organvm/contrib--openai-agents-python` — closed
- `a-organvm/contrib--prefecthq-fastmcp` — merged
- `a-organvm/contrib--primeinc-github-stars` — merged

## The autopoietic pool — inward-derived outward opportunities

The scout limb walked our own dependency manifests: these are the upstreams we lean on
hardest and have never engaged — the next places to study wiring. Pooled for
scout/fieldwork vetting; adoption and every send stay human-gated.

| dependency | used across our repos |
|---|---|
| pytest | 34 |
| typescript | 30 |
| vitest | 23 |
| ruff | 22 |
| eslint | 20 |
| pyyaml | 20 |
| react | 15 |
| react-dom | 14 |
| node | 13 |
| pytest-cov | 12 |
| js | 10 |
| jsdom | 9 |

## Backflow (the inward product)

- **ORGAN-III** — 2 signal(s) routed inward
- **ORGAN-IV** — 3 signal(s) routed inward
- **ORGAN-V** — 2 signal(s) routed inward
- **ORGAN-VI** — 22 signal(s) routed inward
- **ORGAN-VII** — 21 signal(s) routed inward

## Estate register (`ESTATE.yaml`)

42 artifacts registered — 38 verified present locally, 3 cited (remote/receipt), 0 DRIFT, 1 optional-absent.

_Optional-absent (expected): `hub-seed-root`_

## The estate this mirror reflects

- Hub: `organvm/contrib` (generated LEDGER; state surface)
- Engines: `organvm_engine.contrib` (A) + `contrib_engine/` in orchestration-start-here (B)
- Workspaces: the `contrib--*` tracking repos, one per upstream
- Rules: `organs/contributions/LIFECYCLE.md` · Register: `organs/contributions/ESTATE.yaml`
- Charter: `organs/contributions/CHARTER.md` · Kernel: `organs/contributions/KERNEL.md`
