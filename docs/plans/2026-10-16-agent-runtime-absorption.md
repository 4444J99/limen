# Plan: absorb the legacy Claude layer into the shared agent runtime (2026-10-16)

Owner: Fable (planning only). Executors: Sonnet (absorption), Opus (dotfiles convergence), Haiku (verification).

## Why
`~/.zshenv` routes every agent at `$LIMEN_AGENT_RUNTIME_ROOT` (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME`).
chezmoi still renders the Claude user layer to `~/.claude` (= `.agent-runtime/claude/legacy-home`): settings with
40+ hooks, `permissions.ask` for rm/force-push, env (MCP_TIMEOUT, UV_CACHE_DIR, CCE_CORPUS_STORE_ROOT), statusLine,
21 hook scripts, 22 slash commands, CLAUDE.md. 818 live transcripts show none of it ever ran. The user's direction:
bridge by absorption (real files in the live runtime), not symlinks; minimize; one shared runtime; no sprawl.

## Lane 1 — Sonnet: absorb into `$CLAUDE_CONFIG_DIR` (runtime files only)
1. Source of truth for content = `chezmoi cat <target>` (renders the current template read-only). If rendering
   triggers a 1Password/op prompt, stop and fall back to the deployed `~/.claude/*` files, noting the difference.
2. `settings.json`: backup live → `backups/settings.json.pre-absorb-<ts>`. Deep-merge rendered into live, live wins
   on scalar conflicts (`jq -s '.[0] * .[1]' rendered live`). Drop `enabledPlugins` from the rendered side (19 plugins,
   zero live usage, 7 not installed, most need auth). Rewrite hook command paths `/Users/4jp/.claude/hooks/` →
   `$CLAUDE_CONFIG_DIR/hooks/`. Never print `env` values.
3. `hooks/`: write each `chezmoi managed` `.claude/hooks/*` (21) to `$CLAUDE_CONFIG_DIR/hooks/`, executable.
   Every script path referenced by the merged settings must exist there.
4. `commands/`: the 22 managed `.claude/commands/*.md` → `$CLAUDE_CONFIG_DIR/commands/`.
5. `CLAUDE.md`: rendered copy → `$CLAUDE_CONFIG_DIR/CLAUDE.md` verbatim (content fixes are Lane 2's job).
6. `settings.local.json`: the 7 `permissions.allow` rules from `~/.claude/settings.local.json`.
7. Gemini: merge `mcpServers.ianva` from `~/.gemini/settings.json` into `$GEMINI_CLI_HOME/.gemini/settings.json`.
8. Do not touch Codex `config.toml` (live copy is newer and Codex-written), `~/.claude/*`, domus-genoma, or limen.

## Lane 2 — Opus: converge dotfiles (session already running: converge-dotfiles-on-the)
Make chezmoi render the surviving sources into the runtime root via the env variable; preserve the live UI prefs
in the template; fix stale CLAUDE.md claims; update the surfaces manifest; list legacy copies for retirement.
After Lane 1, the live state is the target the templates must reproduce.

## Lane 3 — Haiku: verify (after Lane 1)
`jq empty` on every settings file; every referenced hook script exists and is executable; a fresh `claude` session
lists the 22 commands and loads CLAUDE.md (`/context`); hook timings from the first new transcripts
(SessionStart p50, PreToolUse per-call); report the three slowest hooks for Lane 2 to prune.

## Rollback
Restore `backups/settings.json.pre-absorb-<ts>`; delete `hooks/`, `commands/`, `CLAUDE.md`, `settings.local.json`
in `$CLAUDE_CONFIG_DIR`; restore the Gemini settings backup.
