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
tmpcfg=""
cleanup_done=0

secret_temp_receipt() {
  local path="$1"
  local private_root="${LIMEN_PRIVATE_ROOT:-${LIMEN_ROOT:-$(pwd)}/.limen-private}"
  local receipt_file="$private_root/secret-temp-cleanups.jsonl"
  mkdir -p "$private_root" 2>/dev/null || return 1
  SECRET_TEMP_PATH="$path" SECRET_TEMP_RECEIPT="$receipt_file" python3 - <<'PY'
import datetime as dt
import hashlib
import json
import os

path = os.environ["SECRET_TEMP_PATH"]
receipt = os.environ["SECRET_TEMP_RECEIPT"]
file_count = 0
byte_count = 0
for root, _dirs, files in os.walk(path):
    for name in files:
        file_count += 1
        try:
            byte_count += os.path.getsize(os.path.join(root, name))
        except OSError:
            pass
record = {
    "timestamp": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "surface": "scripts/claude-fleet-auth-probe.sh",
    "classification": "secret-temp-cleanup",
    "path_sha256": hashlib.sha256(path.encode("utf-8")).hexdigest(),
    "file_count": file_count,
    "byte_count": byte_count,
    "archive_proof": "raw secret-bearing Claude temp config is not archived; private redacted receipt only",
    "redaction_proof": "receipt excludes token, content, filenames, and raw path; stores counts and path hash",
    "planned_action": "delete temp config after receipt",
}
with open(receipt, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record, sort_keys=True) + "\n")
print(receipt)
PY
}

cleanup_tmpcfg() {
  [ "$cleanup_done" = 0 ] || return 0
  cleanup_done=1
  [ -n "${tmpcfg:-}" ] || return 0
  [ -e "$tmpcfg" ] || return 0
  local receipt_file
  if receipt_file="$(secret_temp_receipt "$tmpcfg")"; then
    if rm -rf -- "$tmpcfg"; then
      echo "redacted secret-temp cleanup receipt: $receipt_file" >&2
    else
      echo "WARNING: redacted receipt written but secret temp config removal failed: $tmpcfg" >&2
    fi
  else
    echo "WARNING: retained secret temp config because redacted receipt failed: $tmpcfg" >&2
  fi
}

trap cleanup_tmpcfg EXIT
trap 'cleanup_tmpcfg; exit 130' INT
trap 'cleanup_tmpcfg; exit 143' TERM

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
safe_out="$(PROBE_OUT="$out" TOK_TO_REDACT="$TOK" python3 - <<'PY'
import os

print(os.environ["PROBE_OUT"].replace(os.environ["TOK_TO_REDACT"], "[REDACTED_TOKEN]"), end="")
PY
)"
unset TOK
cleanup_tmpcfg

keychain_present && after=present || after=absent
echo "Keychain '$SVC' AFTER  probe: $after" >&2
echo "probe call exit=$rc; reply=$(printf '%s' "$safe_out" | tr '\n' ' ' | head -c 100)" >&2
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
