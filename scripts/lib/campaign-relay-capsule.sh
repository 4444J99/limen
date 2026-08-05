#!/usr/bin/env bash
# Relay-only capsule transformation. Source after workstream-capsule.sh.

workstream_prepare_campaign_relay_capsule() {
  local wt="$1"
  local slug="$2"
  local branch="$3"
  local workstream="$4"
  local relay_id="$5"
  local capsule_dir="$wt/.limen-workstream"
  local kickstart="$capsule_dir/kickstart.sh"
  local identity="$capsule_dir/capsule.identity"
  local contract="$capsule_dir/workstream.json"
  local contract_helper="$capsule_dir/workstream-contract.py"
  local readme="$capsule_dir/README.md"
  local manifest="$capsule_dir/manifest.md"
  local intent="$capsule_dir/intent.md"
  local runtime="$capsule_dir/runtime.md"
  local closeout="$capsule_dir/closeout.md"
  local receipt="$wt/docs/continuations/$slug/workstream.json"
  local invocation_sha256=""
  local relay_control_rc=0

  if [[ ! "$relay_id" =~ ^[0-9a-f]{64}$ \
    || "$slug" != "institutional-omega-${relay_id:0:16}" \
    || "$branch" != "work/$slug" \
    || "$workstream" != "institutional-omega" ]]; then
    printf 'invalid campaign relay capsule identity\n' >&2
    return 2
  fi
  # shellcheck disable=SC2154  # sourced owner defines script_dir before this helper loads
  local relay_control_helper="${script_dir}/lib/campaign-relay-control.py"
  python3 "$relay_control_helper" "$kickstart" "$relay_id" || relay_control_rc=$?
  if [[ "$relay_control_rc" -ne 0 ]]; then
    return "$relay_control_rc"
  fi

if ! invocation_sha256="$(
    python3 - "$identity" <<'PY'
import json
import sys
from pathlib import Path

try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"campaign relay capsule identity is unreadable: {exc}")
value = payload.get("invocation_sha256")
if not isinstance(value, str) or len(value) != 64:
    raise SystemExit("campaign relay capsule invocation digest is invalid")
print(value)
PY
  )"; then
    return 2
  fi
  python3 "$contract_helper" sync-identity \
    --identity "$identity" \
    --invocation-sha256 "$invocation_sha256" \
    --module "README.md=$readme" \
    --module "manifest.md=$manifest" \
    --module "workstream.json=$contract" \
    --module "workstream-contract.py=$contract_helper" \
    --module "intent.md=$intent" \
    --module "runtime.md=$runtime" \
    --module "closeout.md=$closeout" \
    --module "kickstart.sh=$kickstart" >/dev/null || return $?
  python3 "$contract_helper" sync-receipt \
    --contract "$contract" \
    --receipt "$receipt" \
    --slug "$slug" \
    --branch "$branch" \
    --workstream "$workstream" \
    --module "README.md=$readme" \
    --module "manifest.md=$manifest" \
    --module "workstream.json=$contract" \
    --module "workstream-contract.py=$contract_helper" \
    --module "intent.md=$intent" \
    --module "runtime.md=$runtime" \
    --module "closeout.md=$closeout" \
    --module "kickstart.sh=$kickstart" \
    --module "capsule.identity=$identity" >/dev/null || return $?
  _limen_capsule_validate_receipt \
    "$contract" "$receipt" "$slug" "$branch" "$workstream"
}
