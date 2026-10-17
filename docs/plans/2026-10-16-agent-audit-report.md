# Agent audit report, 2026-10-16

Scope: every AI coding agent on this Mac (Claude Code, Codex, Copilot, Antigravity/agy, Gemini CLI, OpenCode, Cursor, Cline, Aider, Goose, Zed) plus the dotfile layer (chezmoi, domus-genoma) that configures them. Fable planned; Sonnet, Opus and Haiku executed.

## Findings

1. Config split (root cause of "my hooks never run"). `~/.zshenv` routes every agent through `LIMEN_AGENT_RUNTIME_ROOT=~/Workspace/limen/.agent-runtime` (CLAUDE_CONFIG_DIR, CODEX_HOME, GEMINI_CLI_HOME). chezmoi still rendered the Claude user layer to `~/.claude` (symlink to `.agent-runtime/claude/legacy-home`): 27 KB settings with 40+ hooks, ask rules for rm/force-push, env concurrency cap, statusLine, 19 enabledPlugins; 21 hook scripts; 22 slash commands; 10.8 KB CLAUDE.md. Live settings were 514 bytes. 818 transcripts: zero runs of any dotfile hook. Same drift for Codex (`~/.codex` vs `$CODEX_HOME`) and Gemini.
2. About 22 of the 44 legacy hooks could never fire: they read `CLAUDE_TOOL_ARG_*` variables hooks are not given. The force-push, branch-delete and comment-cadence advisories were dead prose.
3. Installation health: native Claude launcher current (2.1.301), no npm leftovers, all settings files parse, no managed policy. Every agent definition on the machine valid (limen scan/synth/verify plus 12 worktree copies; plugin agents; 2 vendor agents). Every SKILL.md parses (Claude, Codex, Cursor, ~/.agents).
4. Unused surfaces: 12 official Claude plugins installed but enabled nowhere; 18 Desktop inline plugins and ~12 claude.ai connectors with zero use in 50 sessions (skill listing visibly truncated by them); Desktop MCP servers filesystem/github/memory/sequential-thinking/serena unused; 16 Codex MCP servers with zero calls in 50 sessions (Codex loads schemas eagerly); 3 duplicate Copilot MCP pairs; deprecated `@githubnext/github-copilot-cli`; Cline unused since Aug 3; Aider no signal; stale Antigravity.app 2.4.3 beside Antigravity IDE 2.5.5.
5. limen/CLAUDE.md at 48,850 chars trips the ~40k large-file warning. AGENTS.md (33.7k) is protocol, nothing derivable.
6. Permissions: user-scope defaultMode auto is healthy (limen pins plan by design). No read-only allow rules proposed: the window's denials were compound `cd … &&` chains, python, git writes, `gh api graphql` mutations, `gh secret set`, and a grep for API keys across ~/Workspace, all correctly blocked.
7. Live admission rail (discovered when absorption went live): `domus-claude-host-hook` → limen `claude-host-admission.py` → `action_admission.py`. Mutations are admitted only from a linked git worktree (main checkout = shared-checkout-write; non-repo cwd = workspace-scope-unavailable); one simple command per call behind an optional `cd <dir> &&`; harness carve-out admits writes only to `plans/`, `jobs/`, `projects/` under the config root; heavy commands gated machine-wide by `swap-fraction`.

## Changes made

| Change | Where | Undo |
|---|---|---|
| Antigravity.app 2.4.3 trashed | `~/.Trash/Antigravity-2.4.3.app` | drag back to /Applications |
| `@githubnext/github-copilot-cli`, `cline`, `aider-chat` uninstalled | npm (/opt/homebrew and ~/.local/share/npm), pipx | reinstall |
| 3 duplicate Copilot MCP entries removed | `~/.copilot/mcp-config.json` | `.bak-doctor-20261016` beside it |
| 5 Desktop MCP servers removed | `~/Library/Application Support/Claude/claude_desktop_config.json` | `.bak-doctor-20261016` beside it; restart Desktop |
| 12 Codex MCP servers `enabled = false` | `$CODEX_HOME/config.toml` | `.bak-doctor-20261016` beside it (superseded by PR #428 on apply) |
| limen CLAUDE.md trim + `data-grounding` skill | worktree `.worktrees/claude-md-trim-20261016`, uncommitted, predicate green, 41.8k chars | `git worktree remove` |
| Legacy Claude layer absorbed into live runtime | `$CLAUDE_CONFIG_DIR`: settings.json merged (hooks, ask, env, statusLine; enabledPlugins dropped; hook paths rewritten to runtime root), 21 hooks, 22 commands, CLAUDE.md, settings.local.json; Gemini ianva merged | `backups/settings.json.pre-absorb-20261016T115113`; remove hooks/ commands/ CLAUDE.md settings.local.json; Gemini `.pre-absorb-*` backup |
| Memory notes saved | `$CLAUDE_CONFIG_DIR/projects/-/memory/` (config layout, "all agents" meaning, minimize principle) | delete files |

Verification (Haiku, read-only): nine checks pass; live session shows the commands, CLAUDE.md and SessionStart hook output loaded; four hook scripts still reference `~/.claude` internally (resolves via symlink; fixed at source in #427).

Dotfiles convergence, open and unapplied in 4444J99/domus-genoma-private:
- #427 feat(agents): render agent config into the shared runtime root (67 files, +670/-1090). Core hook set you chose: guard dispatcher on Bash and Write/Edit, memory-hygiene line, SessionEnd breadcrumb, ask rules, env cap, statusLine. Live UI prefs preserved, seeded only when absent.
- #428 fix(codex): reconcile split modifier with live config (stacked on #427). launchdarkly off; 1password, computer-use, standalone Serena on; other 8 off; MCP_TIMEOUT/UV_CACHE_DIR dropped.
- #429 feat(skills): agent-neutral shared skills for the 22 Claude slash commands (stacked on #427).

## What remains (yours)

1. Review and merge #427, then #428 and #429; run `chezmoi apply --include files`. This distills the absorbed 44 hooks to the core set and lands the Codex and skills changes through the owned path. Afterwards prune hook scripts in `$CLAUDE_CONFIG_DIR/hooks/` that the core set no longer references.
2. Restart Claude Desktop so the MCP removal takes effect.
3. In the Desktop app and claude.ai settings, disable the unused inline plugins and connectors; they are what truncates the skill listing.
4. `brew upgrade copilot-cli` (1.0.98 on PATH vs 1.1.26 app engine).
5. The CLAUDE.md trim: free memory or run `bash scripts/verify-scoped.sh` inside the trim worktree, then let the land session commit, push and open the PR.
6. Optional: archive the finished sessions; the converge session's shell held the domus-genoma write lease until it closed.
