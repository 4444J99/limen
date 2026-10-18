#!/usr/bin/env bash
# Operator-run read-only recovery check; never recreate or register the subject.
set -euo pipefail

subject="/Users/4jp/Workspace/limen/.claude/worktrees/chore-fewer-permission-prompts-20261018"
session_id="cb335bab-9f3b-44c5-a4b8-51759e66dd64"
receipt_rel="docs/receipts/session-closeout-fewer-permission-prompts-20261018/session-closeout.json"
mode="${1:---dry-run}"

if [[ "$#" -gt 1 ]]; then
  printf 'usage: bash %s [--dry-run|--apply|--check]\n' "$0" >&2
  exit 2
fi
case "$mode" in
  --dry-run)
    printf '%s\n' "Would resolve the verified installed protocol, validate the exact native subject and receipt, hydrate the canonical conduct environment without displaying credentials, then run the read-only session predicate twice."
    printf '%s\n' "Subject: $subject" "Native session: $session_id" "Owner: https://github.com/4444J99/limen/issues/3023"
    printf '%s\n' "No checkout, session, receipt, lease or custody proof is created; absent or invalid evidence exits 2."
    exit 0
    ;;
  --apply|--check) ;;
  *) printf 'unknown mode: %s\n' "$mode" >&2; exit 2 ;;
esac

if [[ ! -d "$subject" || -L "$subject" ]]; then
  printf '%s\n' '{"status":"unmeasured","session_released":false,"reason":"original subject checkout absent or unsafe; reconcile custody/retirement evidence in issues 2970 and 3023"}'
  exit 2
fi
receipt="$subject/$receipt_rel"
if [[ ! -f "$receipt" ]]; then
  printf '%s\n' '{"status":"unmeasured","session_released":false,"reason":"native subject receipt absent"}'
  exit 2
fi
if ! jq -e --arg id "$session_id" '.session_id == $id' "$receipt" >/dev/null; then
  printf '%s\n' '{"status":"unmeasured","session_released":false,"reason":"receipt does not bind exact native identity; cloud alias alone is insufficient"}'
  exit 2
fi
resolved="$(/Users/4jp/.local/bin/domus-limen-runtime --root /Users/4jp/.local/share/limen protocol-root)"
protocol_root="$(printf '%s' "$resolved" | jq -er 'select(.status == "ready") | .protocol_root')"
source "$protocol_root/scripts/lib/workstream-capsule.sh"
workstream_hydrate_conduct_environment
bash "$protocol_root/scripts/no-tasks-on-me.sh" --session-id "$session_id" --worktree "$subject" --receipt "$receipt" --json
bash "$protocol_root/scripts/no-tasks-on-me.sh" --session-id "$session_id" --worktree "$subject" --receipt "$receipt" --json
