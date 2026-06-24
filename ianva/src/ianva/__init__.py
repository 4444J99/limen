"""ianva — the fleet's single MCP doorway.

Latin *ianua*: the door / gateway. It sits at the *limen* (threshold). Every agent —
Claude Code, Codex, Gemini, antigravity (agy), opencode, Copilot, Cline — passes through
this one doorway to reach every MCP server. ianva connects to each upstream ONCE, holds its
OAuth refresh token, and auto-renews forever, so no agent ever sees an auth prompt again.

Four faces (all built, per the "all options, not reduction" mandate):
  1. core    — MCPHub holds upstream OAuth 2.1 + persistent auto-refresh (the hard part, wrapped not rebuilt).
  2. local   — a single stdio/HTTP endpoint every local agent points at (one config entry each).
  3. cloud   — a public self-authenticating HTTPS connector so the claude.ai cloud connectors stop re-prompting.
  4. docker  — the Docker MCP gateway as an alternate aggregation backend (documented; docker not required).

Credential discipline is inherited verbatim from the fleet's credential-race fix:
secrets live only in ~/.limen.env (chmod 600), refreshes are single-writer (flock-serialized so
a rotating refresh token is never double-spent), CLAUDE_CODE_OAUTH_TOKEN is never propagated
(it deletes the macOS Keychain item on exit — anthropics/claude-code#37512), and an auth-blip
triggers exactly one self-healing retry.
"""

__version__ = "0.1.0"
