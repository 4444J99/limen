#!/usr/bin/env bash
# claude-fleet-auth-probe.sh — DISCOVER whether the FREE fleet-auth path is safe on THIS Mac.
#
# The daemon's concurrent `claude -p` and your interactive session share ONE rotating macOS
# Keychain OAuth credential, so simultaneous refreshes race and flap "Not logged in"
# (anthropics/claude-code#48786). The cure is to give the FLEET its own stable credential. The
# FREE option — a `claude setup-token` supplied as ANTHROPIC_AUTH_TOKEN (NOT the Keychain-wiping
# CLAUDE_CODE_OAUTH_TOKEN) — is UNDOCUMENTED on two points:
#   (1) does it leave your interactive Keychain INTACT (vs the #37512 wipe-on-exit)?  [this probes]
#   (2) does it bill to your SUBSCRIPTION (vs API credits)?                            [check usage]
#
# Run it ONCE, in a quiet moment (no other live claude session you care about):
#   1) generate the token:   claude setup-token        # browser OAuth, subscription-gated
#   2) probe it:             bash scripts/claude-fleet-auth-probe.sh   # paste the token (hidden)
#
# It NEVER prints the token, snapshots your Keychain before/after, and if the call WIPED it tells
# you the one command to restore it. Verdict picks the rung: free LIMEN_CLAUDE_AUTH_TOKEN, or the
# paid-but-documented LIMEN_CLAUDE_API_KEY fallback. Nothing is changed until you act on the verdict.
set -uo pipefail
SVC="Claude Code-credentials"
keychain_present() { security find-generic-password -s "$SVC" >/dev/null 2>&1; }

printf 'Paste the setup-token to probe (input hidden): ' >&2
IFS= read -rs TOK; echo >&2
[ -n "$TOK" ] || { echo "empty token — aborted, nothing changed" >&2; exit 1; }

keychain_present && before=present || before=absent
echo "Keychain '$SVC' BEFORE probe: $before" >&2

TO="$(command -v timeout || command -v gtimeout || true)"
tmpcfg="$(mktemp -d)"
# ONLY the bearer token in env: drop the Keychain-wiping var AND any API key so we test the
# ANTHROPIC_AUTH_TOKEN path in isolation. Throwaway CLAUDE_CONFIG_DIR keeps the real config clean.
out="$(${TO:+$TO 90} env -u CLAUDE_CODE_OAUTH_TOKEN -u ANTHROPIC_API_KEY \
        ANTHROPIC_AUTH_TOKEN="$TOK" CLAUDE_CONFIG_DIR="$tmpcfg" \
        claude -p 'reply with exactly: OK' 2>&1)"; rc=$?
rm -rf "$tmpcfg"; unset TOK

keychain_present && after=present || after=absent
echo "Keychain '$SVC' AFTER  probe: $after" >&2
echo "probe call exit=$rc; reply=$(printf '%s' "$out" | tr '\n' ' ' | head -c 100)" >&2
echo >&2

wiped=0; [ "$before" = present ] && [ "$after" = absent ] && wiped=1
if [ "$rc" = 0 ] && [ "$wiped" = 0 ]; then
  echo "VERDICT: ✓ FREE PATH SAFE — the bearer token works and your Keychain survived." >&2
  echo "  Activate it (subscription-billed, fleet-isolated, no API \$):" >&2
  echo "    bash scripts/set-credential.sh LIMEN_CLAUDE_AUTH_TOKEN   # paste the SAME token" >&2
  echo "    launchctl kickstart -k gui/\$(id -u)/com.limen.heartbeat" >&2
  echo "  Then confirm the next claude-lane runs bill to your SUBSCRIPTION (not API credits) on the usage view." >&2
else
  echo "VERDICT: ✗ NOT the free path (call rc=$rc, keychain_wiped=$wiped) — use the documented-safe fallback." >&2
  [ "$wiped" = 1 ] && echo "  Your interactive Keychain was deleted (#37512) — run \`claude /login\` ONCE to restore it." >&2
  echo "    bash scripts/set-credential.sh LIMEN_CLAUDE_API_KEY     # an Anthropic Console API key (API-billed)" >&2
  echo "    launchctl kickstart -k gui/\$(id -u)/com.limen.heartbeat" >&2
fi
