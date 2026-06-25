#!/usr/bin/env bash
# set-credential.sh — the ONE safe, idempotent way to give the conductor any secret.
#
# Why this exists: a leaked GEMINI_API_KEY (copied into .zshrc/.zshenv/.zprofile/.bashrc
# + a screenshot) cost real cleanup. The rule that prevents it: secrets live ONLY in
# ~/.limen.env, are entered via a SILENT prompt (never on a command line, never echoed,
# never cat'd, never in shell history), and the file is chmod 600. This script is that rule,
# executable — so future key setup is one-shot and un-fuck-up-able.
#
#   bash scripts/set-credential.sh GEMINI_API_KEY   # silent prompt → writes to ~/.limen.env
#   bash scripts/set-credential.sh --check          # which expected keys are present (NAMES only)
#   bash scripts/set-credential.sh --list           # all key names in the env file (NAMES only)
#
# Guarantees: value never printed/logged/in argv/in history; add-or-replace (idempotent,
# re-runnable); atomic write; chmod 600; touches ONLY ~/.limen.env (never a shell rc).
set -uo pipefail
ENV_FILE="${LIMEN_ENV:-$HOME/.limen.env}"
# The keys the fleet actually hydrates + reads at the point of use (the enabled creds-hydrate map).
# --check reports on these. Deliberately NOT listed: OPENAI_API_KEY / OPENROUTER_API_KEY (phantom —
# codex uses ChatGPT OAuth, opencode derives a free model; no fleet code reads either; retired
# 2026-06-25), and the Claude token (owned by the credential-race / Rung-0 self-heal, not this floor).
EXPECTED=(GEMINI_API_KEY GOOGLE_GENERATIVE_AI_API_KEY \
          GH_TOKEN GITHUB_TOKEN CLOUDFLARE_API_TOKEN)

ensure_file() { [ -f "$ENV_FILE" ] || touch "$ENV_FILE"; chmod 600 "$ENV_FILE"; }
has_key() { grep -qE "^(export )?$1=" "$ENV_FILE" 2>/dev/null; }

case "${1:-}" in
  --check)
    ensure_file
    echo "Credential presence in $ENV_FILE (names only — values never shown):"
    for k in "${EXPECTED[@]}"; do has_key "$k" && echo "  ✓ $k set" || echo "  ✗ $k missing"; done
    exit 0 ;;
  --list)
    ensure_file
    echo "Keys in $ENV_FILE (names only):"
    sed -nE 's/^(export )?([A-Z0-9_]+)=.*/  \2/p' "$ENV_FILE" | sort -u
    exit 0 ;;
  ""|-h|--help)
    echo "usage: set-credential.sh KEY_NAME | --check | --list"
    echo "  Silent prompt for the value → writes KEY to $ENV_FILE only (chmod 600)."
    echo "  Never echoes the value, never writes a shell rc, idempotent (add-or-replace)."
    exit 0 ;;
esac

KEY="$1"
echo "$KEY" | grep -qE '^[A-Z][A-Z0-9_]*$' \
  || { echo "error: KEY_NAME must be UPPER_SNAKE_CASE (got '$KEY')" >&2; exit 1; }
ensure_file

# SILENT read — value never appears on screen, in argv, or in shell history
printf 'Enter value for %s (input hidden): ' "$KEY" >&2
IFS= read -rs VALUE
echo >&2
[ -n "$VALUE" ] || { echo "error: empty value — aborted, nothing changed" >&2; exit 1; }

# idempotent add-or-replace, atomic, value never echoed
tmp="$(mktemp)"; chmod 600 "$tmp"
grep -vE "^(export )?${KEY}=" "$ENV_FILE" > "$tmp" 2>/dev/null || true
printf 'export %s=%s\n' "$KEY" "$VALUE" >> "$tmp"
mv "$tmp" "$ENV_FILE"
unset VALUE
chmod 600 "$ENV_FILE"

was="updated"; { [ "$(grep -cE "^(export )?${KEY}=" "$ENV_FILE")" = 1 ]; } && true
echo "✓ $KEY written to $ENV_FILE (value hidden · chmod 600 · idempotent)." >&2
echo "  The running daemon loads ~/.limen.env at startup, so apply it with a restart:" >&2
echo "    launchctl kickstart -k gui/\$(id -u)/com.limen.heartbeat" >&2
