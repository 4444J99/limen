# Capability Substrate Ledger

Generated: `2026-06-28T15:04:52+00:00`

## Canonical Decision

- This ledger resurfaces local skills, plugins, MCP/ACP markers, and scheduled capability roots by names, counts, paths, and activation routes only.
- It does not read or print `SKILL.md` bodies, `*.skill` bodies, plugin manifest contents, credential values, or raw prompt/session text.
- Current Codex-session skills remain the active baseline; legacy Claude/custom archives are activation candidates, not automatically installed tools.
- Activation means owner review, body review, then a small checked-in or Codex-home skill/plugin change with its own verification.

## Coverage

- Roots seen: `11`.
- Scanned files: `20264`; truncated roots: `0`.
- Skill files: `1317`; unique skill names: `374`.
- Plugin/MCP manifests: `45`; MCP/ACP markers: `150`.
- Capability bytes counted by metadata only: `739.6 MiB`.
- Lanes: `claude-plugin-cache` 1, `codex-plugin-cache` 1, `codex-user-skills` 1, `domus-genoma-config` 1, `limen-local-skills` 2, `limen-mcp` 1, `organvm-agent-archive` 1, `organvm-ai-skills` 1, `organvm-runtime-tasks` 1, `workspace-mirror` 1.
- Domains: `agent_orchestration` 85, `data_research` 58, `mcp_acp` 37, `other` 726, `product_frontend` 104, `repo_delivery` 73, `security_ops` 43, `session_corpus` 84, `verification_quality` 50, `writing_docs` 57.

## Roots

| Root | Lane | State | Skills | Unique | Plugin/MCP | MCP/ACP | Files | Route |
|---|---|---|---:|---:|---:|---:|---:|---|
| `~/.codex/skills` | `codex-user-skills` | `available` | 6 | 6 | 0 | 0 | 53 | Already visible to Codex when the skill registry loads; keep as the active baseline. |
| `~/.codex/plugins` | `codex-plugin-cache` | `available-vendor-cache` | 179 | 166 | 36 | 11 | 2559 | Already surfaced by installed Codex plugins; do not port cache internals by hand. |
| `~/.claude/plugins` | `claude-plugin-cache` | `legacy-plugin-cache` | 0 | 0 | 3 | 0 | 42 | Treat as Claude-side plugin state; inspect only through its plugin owner. |
| `~/Workspace/organvm/_agent` | `organvm-agent-archive` | `custom-agent-archive` | 163 | 163 | 0 | 11 | 908 | Converge legacy global skills and MCP registry pieces into the current capability layer. |
| `~/Workspace/organvm/claude-runtime-state` | `organvm-runtime-tasks` | `scheduled-runtime-archive` | 17 | 17 | 0 | 17 | 3908 | Convert scheduled-task skills into Limen packets or LaunchAgent receipts, not chat-only memory. |
| `~/Workspace/organvm/a-i--skills` | `organvm-ai-skills` | `custom-skill-archive` | 907 | 183 | 4 | 32 | 5469 | Port selected high-signal skills into the current Codex skill registry after body review. |
| `~/Workspace/domus-genoma` | `domus-genoma-config` | `config-mcp-wrapper-substrate` | 24 | 19 | 1 | 34 | 3153 | Keep as dotfile/config owner state; activate through chezmoi and MCP wrapper receipts. |
| `~/Workspace/4444J99` | `workspace-mirror` | `mirror-candidate` | 19 | 19 | 1 | 36 | 4161 | Use only after checking the source owner; count it so duplicate capability copies are visible. |
| `~/Workspace/limen/.agents` | `limen-local-skills` | `repo-local-active` | 1 | 1 | 0 | 0 | 1 | Keep mirrored local skills minimal and tested by Limen verification. |
| `~/Workspace/limen/.claude/skills` | `limen-local-skills` | `repo-local-active` | 1 | 1 | 0 | 0 | 1 | Keep mirrored local skills minimal and tested by Limen verification. |
| `~/Workspace/limen/mcp` | `limen-mcp` | `active-mcp-server` | 0 | 0 | 0 | 9 | 9 | Treat as Limen MCP implementation; verify through API/CLI and adapter predicates. |

## Activation Queue

| Rank | Capability | Domain | Lane | Score | Source | Route |
|---:|---|---|---|---:|---|---|
| 1 | `session-lifecycle-patterns` | `session_corpus` | `organvm-ai-skills` | 126 | `~/Workspace/organvm/a-i--skills/skills/tools/session-lifecycle-patterns/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 2 | `closeout` | `other` | `limen-local-skills` | 122 | `~/Workspace/limen/.claude/skills/closeout/SKILL.md` | Already repo-local; keep mirrored only when Limen verification needs it. |
| 3 | `agent-swarm-orchestrator` | `agent_orchestration` | `organvm-ai-skills` | 110 | `~/Workspace/organvm/a-i--skills/skills/tools/agent-swarm-orchestrator/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 4 | `cross-agent-handoff` | `agent_orchestration` | `organvm-ai-skills` | 110 | `~/Workspace/organvm/a-i--skills/skills/tools/cross-agent-handoff/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 5 | `agent-testing-patterns` | `agent_orchestration` | `organvm-ai-skills` | 104 | `~/Workspace/organvm/a-i--skills/skills/development/agent-testing-patterns/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 6 | `skill-chain-prompts` | `session_corpus` | `organvm-ai-skills` | 104 | `~/Workspace/organvm/a-i--skills/skills/tools/skill-chain-prompts/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 7 | `skill-creator` | `other` | `codex-user-skills` | 102 | `~/.codex/skills/.system/skill-creator/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 8 | `skill-installer` | `other` | `codex-user-skills` | 102 | `~/.codex/skills/.system/skill-installer/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 9 | `session-governance-audit` | `session_corpus` | `organvm-ai-skills` | 100 | `~/Workspace/organvm/a-i--skills/skills/tools/session-governance-audit/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 10 | `specstory-session-summary` | `session_corpus` | `organvm-ai-skills` | 100 | `~/Workspace/organvm/a-i--skills/skills/integrations/specstory-session-summary/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 11 | `github-repo-curator` | `repo_delivery` | `organvm-ai-skills` | 98 | `~/Workspace/organvm/a-i--skills/skills/github-repo-curator.skill` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 12 | `github-repository-standards` | `repo_delivery` | `organvm-ai-skills` | 98 | `~/Workspace/organvm/a-i--skills/skills/documentation/github-repository-standards/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 13 | `artifact-resurfacing` | `session_corpus` | `organvm-ai-skills` | 96 | `~/Workspace/organvm/a-i--skills/skills/tools/artifact-resurfacing/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 14 | `artifacts-builder` | `session_corpus` | `organvm-ai-skills` | 96 | `~/Workspace/organvm/a-i--skills/skills/development/artifacts-builder/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 15 | `prompt-atom-formalization` | `session_corpus` | `organvm-ai-skills` | 96 | `~/Workspace/organvm/a-i--skills/skills/data/prompt-atom-formalization/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 16 | `prompt-engineering-patterns` | `session_corpus` | `organvm-ai-skills` | 96 | `~/Workspace/organvm/a-i--skills/skills/tools/prompt-engineering-patterns/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 17 | `transcript-promotion` | `session_corpus` | `organvm-ai-skills` | 96 | `~/Workspace/organvm/a-i--skills/skills/tools/transcript-promotion/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 18 | `web-artifacts-builder` | `session_corpus` | `organvm-ai-skills` | 96 | `~/Workspace/organvm/a-i--skills/skills/development/web-artifacts-builder/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 19 | `deployment-cicd` | `repo_delivery` | `organvm-ai-skills` | 94 | `~/Workspace/organvm/a-i--skills/skills/deployment-cicd.skill` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 20 | `imagegen` | `other` | `codex-user-skills` | 94 | `~/.codex/skills/.system/imagegen/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 21 | `mcp-builder` | `mcp_acp` | `organvm-ai-skills` | 94 | `~/Workspace/organvm/a-i--skills/skills/development/mcp-builder/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 22 | `mcp-integration-patterns` | `mcp_acp` | `organvm-ai-skills` | 94 | `~/Workspace/organvm/a-i--skills/skills/integrations/mcp-integration-patterns/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 23 | `mcp-server-orchestrator` | `agent_orchestration` | `organvm-ai-skills` | 94 | `~/Workspace/organvm/a-i--skills/skills/mcp-server-orchestrator.skill` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 24 | `openai-docs` | `writing_docs` | `codex-user-skills` | 94 | `~/.codex/skills/.system/openai-docs/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 25 | `plugin-creator` | `other` | `codex-user-skills` | 94 | `~/.codex/skills/.system/plugin-creator/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 26 | `uma-ops-semantic-layer` | `other` | `codex-user-skills` | 94 | `~/.codex/skills/uma-ops-semantic-layer/SKILL.md` | Already active in the Codex skill registry; keep as baseline. |
| 27 | `agent-development-pack` | `agent_orchestration` | `organvm-ai-skills` | 92 | `~/Workspace/organvm/a-i--skills/skills/tools/agent-development-pack/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 28 | `continuous-learning-agent` | `agent_orchestration` | `organvm-ai-skills` | 92 | `~/Workspace/organvm/a-i--skills/skills/development/continuous-learning-agent/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 29 | `multi-agent-workforce-planner` | `agent_orchestration` | `organvm-ai-skills` | 92 | `~/Workspace/organvm/a-i--skills/skills/tools/multi-agent-workforce-planner/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |
| 30 | `corpus-persona-extraction` | `session_corpus` | `organvm-ai-skills` | 90 | `~/Workspace/organvm/a-i--skills/skills/data/corpus-persona-extraction/SKILL.md` | Port after body review into `~/.codex/skills` or a checked-in Limen skill. |

## High-Signal Groups

- `agent_orchestration`: `agent-swarm-orchestrator`, `cross-agent-handoff`, `agent-testing-patterns`, `mcp-server-orchestrator`, `agent-development-pack`, `continuous-learning-agent`, `multi-agent-workforce-planner`.
- `mcp_acp`: `mcp-builder`, `mcp-integration-patterns`.
- `other`: `closeout`, `skill-creator`, `skill-installer`, `imagegen`, `plugin-creator`, `uma-ops-semantic-layer`.
- `repo_delivery`: `github-repo-curator`, `github-repository-standards`, `deployment-cicd`.
- `session_corpus`: `session-lifecycle-patterns`, `skill-chain-prompts`, `session-governance-audit`, `specstory-session-summary`, `artifact-resurfacing`, `artifacts-builder`, `prompt-atom-formalization`, `prompt-engineering-patterns`, `transcript-promotion`, `web-artifacts-builder`.
- `writing_docs`: `openai-docs`.

## Duplicate Names

- `api-design-patterns` x8, `audio-engineering-patterns` x8, `closeout` x8, `creative-writing-craft` x8, `cv-resume-builder` x8, `evaluation-to-growth` x8, `github-repo-curator` x8, `grant-proposal-writer` x8, `portfolio-presentation` x8, `product-requirements-designer` x8, `project-orchestration` x8, `accessibility-patterns` x7.

## Private Output

- Private capability index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/capability-substrate-index.json`.
- The private index keeps path-level evidence and metadata counts; it still contains no skill body text, plugin manifest content, secret values, or raw prompts.

## Commands

- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`
- Refresh parked blockers after capability resurfacing: `python3 scripts/session-blockers-ledger.py --write`
- Refresh ranked attack paths: `python3 scripts/session-attack-paths.py --write`
