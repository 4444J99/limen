# Capability Substrate Ledger

Generated: `2026-07-06T09:12:28+00:00`

## Canonical Decision

- This ledger resurfaces local skills, plugins, MCP/ACP markers, and scheduled capability roots by names, counts, paths, and activation routes only.
- It does not read or print `SKILL.md` bodies, `*.skill` bodies, plugin manifest contents, credential values, or raw prompt/session text.
- Current Codex-session skills remain the active baseline; legacy Claude/custom archives are activation candidates, not automatically installed tools.
- Activation means owner review, body review, then a small checked-in or Codex-home skill/plugin change with its own verification.

## Coverage

- Roots seen: `10`.
- Scanned files: `62063`; truncated roots: `1`.
- Skill files: `467`; unique skill names: `356`.
- Plugin/MCP manifests: `43`; MCP/ACP markers: `182`.
- Capability bytes counted by metadata only: `2.5 GiB`.
- Lanes: `claude-plugin-cache` 1, `codex-plugin-cache` 1, `codex-user-skills` 1, `domus-genoma-config` 1, `limen-local-skills` 2, `limen-mcp` 1, `organvm-agent-archive` 1, `organvm-runtime-tasks` 1, `workspace-mirror` 1.
- Domains: `agent_orchestration` 22, `data_research` 18, `mcp_acp` 6, `other` 313, `product_frontend` 21, `repo_delivery` 29, `security_ops` 8, `session_corpus` 15, `verification_quality` 22, `writing_docs` 13.

## Roots

| Root | Lane | State | Skills | Unique | Plugin/MCP | MCP/ACP | Files | Route |
|---|---|---|---:|---:|---:|---:|---:|---|
| `~/.local/share/codex/skills` | `codex-user-skills` | `available` | 6 | 6 | 0 | 0 | 53 | Already visible to Codex when the skill registry loads; keep as the active baseline. |
| `~/.local/share/codex/plugins` | `codex-plugin-cache` | `available-vendor-cache` | 179 | 166 | 36 | 11 | 2559 | Already surfaced by installed Codex plugins; do not port cache internals by hand. |
| `~/.claude/plugins` | `claude-plugin-cache` | `legacy-plugin-cache` | 0 | 0 | 3 | 0 | 46 | Treat as Claude-side plugin state; inspect only through its plugin owner. |
| `~/Workspace/organvm/_agent` | `organvm-agent-archive` | `custom-agent-archive` | 164 | 164 | 0 | 11 | 1155 | Converge legacy global skills and MCP registry pieces into the current capability layer. |
| `~/Workspace/organvm/claude-runtime-state` | `organvm-runtime-tasks` | `scheduled-runtime-archive` | 17 | 17 | 0 | 17 | 3915 | Convert scheduled-task skills into Limen packets or LaunchAgent receipts, not chat-only memory. |
| `~/Workspace/domus-genoma` | `domus-genoma-config` | `config-mcp-wrapper-substrate` | 74 | 20 | 3 | 98 | 50000 | Keep as dotfile/config owner state; activate through chezmoi and MCP wrapper receipts. |
| `~/Workspace/4444J99` | `workspace-mirror` | `mirror-candidate` | 24 | 19 | 1 | 36 | 4323 | Use only after checking the source owner; count it so duplicate capability copies are visible. |
| `~/Workspace/limen/.agents` | `limen-local-skills` | `repo-local-active` | 2 | 2 | 0 | 0 | 2 | Keep mirrored local skills minimal and tested by Limen verification. |
| `~/Workspace/limen/.claude/skills` | `limen-local-skills` | `repo-local-active` | 1 | 1 | 0 | 0 | 1 | Keep mirrored local skills minimal and tested by Limen verification. |
| `~/Workspace/limen/mcp` | `limen-mcp` | `active-mcp-server` | 0 | 0 | 0 | 9 | 9 | Treat as Limen MCP implementation; verify through API/CLI and adapter predicates. |

## Activation Queue

| Rank | Capability | Domain | Lane | Score | Source | Route |
|---:|---|---|---|---:|---|---|
| 1 | `closeout` | `other` | `limen-local-skills` | 122 | `~/Workspace/limen/.claude/skills/closeout/SKILL.md` | Already repo-local; keep mirrored only when Limen verification needs it. |
| 2 | `session-lifecycle-patterns` | `session_corpus` | `organvm-agent-archive` | 122 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/session-lifecycle-patterns/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 3 | `agent-swarm-orchestrator` | `agent_orchestration` | `organvm-agent-archive` | 106 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/agent-swarm-orchestrator/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 4 | `cross-agent-handoff` | `agent_orchestration` | `organvm-agent-archive` | 106 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/cross-agent-handoff/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 5 | `skill-creator` | `other` | `codex-user-skills` | 102 | `~/.local/share/codex/skills/.system/skill-creator/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 6 | `skill-installer` | `other` | `codex-user-skills` | 102 | `~/.local/share/codex/skills/.system/skill-installer/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 7 | `agent-testing-patterns` | `agent_orchestration` | `organvm-agent-archive` | 100 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/agent-testing-patterns/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 8 | `skill-chain-prompts` | `session_corpus` | `organvm-agent-archive` | 100 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/skill-chain-prompts/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 9 | `specstory-session-summary` | `session_corpus` | `organvm-agent-archive` | 96 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/specstory-session-summary/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 10 | `github-repo-curator` | `repo_delivery` | `organvm-agent-archive` | 94 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/github-repo-curator/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 11 | `github-repository-standards` | `repo_delivery` | `organvm-agent-archive` | 94 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/github-repository-standards/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 12 | `imagegen` | `other` | `codex-user-skills` | 94 | `~/.local/share/codex/skills/.system/imagegen/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 13 | `openai-docs` | `writing_docs` | `codex-user-skills` | 94 | `~/.local/share/codex/skills/.system/openai-docs/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 14 | `plugin-creator` | `other` | `codex-user-skills` | 94 | `~/.local/share/codex/skills/.system/plugin-creator/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 15 | `uma-ops-semantic-layer` | `other` | `codex-user-skills` | 94 | `~/.local/share/codex/skills/uma-ops-semantic-layer/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 16 | `agy_conductor` | `other` | `limen-local-skills` | 92 | `~/Workspace/limen/.agents/skills/agy_conductor/SKILL.md` | Already repo-local; keep mirrored only when Limen verification needs it. |
| 17 | `artifact-resurfacing` | `session_corpus` | `organvm-agent-archive` | 92 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/artifact-resurfacing/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 18 | `artifacts-builder` | `session_corpus` | `organvm-agent-archive` | 92 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/artifacts-builder/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 19 | `prompt-engineering-patterns` | `session_corpus` | `organvm-agent-archive` | 92 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/prompt-engineering-patterns/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 20 | `web-artifacts-builder` | `session_corpus` | `organvm-agent-archive` | 92 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/web-artifacts-builder/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 21 | `deployment-cicd` | `repo_delivery` | `organvm-agent-archive` | 90 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/deployment-cicd/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 22 | `mcp-builder` | `mcp_acp` | `organvm-agent-archive` | 90 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/mcp-builder/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 23 | `mcp-integration-patterns` | `mcp_acp` | `organvm-agent-archive` | 90 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/mcp-integration-patterns/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 24 | `mcp-server-orchestrator` | `agent_orchestration` | `organvm-agent-archive` | 90 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/mcp-server-orchestrator/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 25 | `agent-development-pack` | `agent_orchestration` | `organvm-agent-archive` | 88 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/agent-development-pack/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 26 | `continuous-learning-agent` | `agent_orchestration` | `organvm-agent-archive` | 88 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/continuous-learning-agent/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 27 | `multi-agent-workforce-planner` | `agent_orchestration` | `organvm-agent-archive` | 88 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/multi-agent-workforce-planner/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 28 | `knowledge-architecture` | `session_corpus` | `organvm-agent-archive` | 86 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/knowledge-architecture/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 29 | `knowledge-graph-builder` | `session_corpus` | `organvm-agent-archive` | 86 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/knowledge-graph-builder/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |
| 30 | `verification-loop` | `verification_quality` | `organvm-agent-archive` | 85 | `~/Workspace/organvm/_agent/_agent.claudebrain/global/skills/verification-loop/SKILL.md` | Converge the legacy agent skill into the current Codex skill format. |

## High-Signal Groups

- `agent_orchestration`: `agent-swarm-orchestrator`, `cross-agent-handoff`, `agent-testing-patterns`, `mcp-server-orchestrator`, `agent-development-pack`, `continuous-learning-agent`, `multi-agent-workforce-planner`.
- `mcp_acp`: `mcp-builder`, `mcp-integration-patterns`.
- `other`: `closeout`, `skill-creator`, `skill-installer`, `imagegen`, `plugin-creator`, `uma-ops-semantic-layer`, `agy_conductor`.
- `repo_delivery`: `github-repo-curator`, `github-repository-standards`, `deployment-cicd`.
- `session_corpus`: `session-lifecycle-patterns`, `skill-chain-prompts`, `specstory-session-summary`, `artifact-resurfacing`, `artifacts-builder`, `prompt-engineering-patterns`, `web-artifacts-builder`, `knowledge-architecture`, `knowledge-graph-builder`.
- `verification_quality`: `verification-loop`.
- `writing_docs`: `openai-docs`.

## Duplicate Names

- `daily-orphan-plans` x9, `daily-pr-execute-by-tier` x9, `daily-pr-promote-and-triage` x9, `daily-push-feature-branches` x9, `daily-unpushed-commits` x9, `daily-code-review` x5, `daily-dependabot-merge` x5, `daily-hook-drift` x5, `daily-operational-heartbeat` x5, `daily-pr-management` x5, `daily-repo-hygiene` x5, `daily-worktree-triage-and-cleanup` x5.

## Private Output

- Private capability index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/capability-substrate-index.json`.
- The private index keeps path-level evidence and metadata counts; it still contains no skill body text, plugin manifest content, secret values, or raw prompts.

## Commands

- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`
- Refresh parked blockers after capability resurfacing: `python3 scripts/session-blockers-ledger.py --write`
- Refresh ranked attack paths: `python3 scripts/session-attack-paths.py --write`
