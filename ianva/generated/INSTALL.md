# ianva — generated agent config entries

One entry per agent, in its native format. These are STAGED for review — applying them
to real config files is a separate, explicit step (`ianva install-configs` / the installer).

| agent | config file | transport | apply |
|---|---|---|---|
| Claude Code | `/Users/4jp/.claude.json` | http | Run this command (writes the user-scope mcpServers entry into ~/.claude.json). |
| Codex (OpenAI) | `/Users/4jp/.codex/config.toml` | http | Append this [mcp_servers.ianva] table to ~/.codex/config.toml. |
| Gemini CLI | `/Users/4jp/.gemini/settings.json` | http | Merge the "ianva" key under "mcpServers" in /Users/4jp/.gemini/settings.json (create the file with this content if absent). |
| opencode | `/Users/4jp/.config/opencode/opencode.jsonc` | http | Merge the "ianva" key under the top-level "mcp" object in /Users/4jp/.config/opencode/opencode.jsonc. |
| antigravity (agy) | `/Users/4jp/.gemini/config/mcp_config.json` | stdio | Merge the "ianva" key under "mcpServers" in /Users/4jp/.gemini/config/mcp_config.json (create the file with this content if absent). |
| GitHub Copilot CLI | `/Users/4jp/.copilot/mcp-config.json` | stdio | Merge the "ianva" key under "mcpServers" in /Users/4jp/.copilot/mcp-config.json (create the file with this content if absent). |
| Cline | `/Users/4jp/.cline/data/settings/cline_mcp_settings.json` | stdio | Merge the "ianva" key under "mcpServers" in /Users/4jp/.cline/data/settings/cline_mcp_settings.json (create the file with this content if absent). |
