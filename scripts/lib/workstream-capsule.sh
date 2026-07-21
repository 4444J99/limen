#!/usr/bin/env bash

workstream_native_binary() {
  local agent="$1"
  local registry_binary="$2"
  local env_suffix env_key override candidate

  env_suffix="$(printf '%s' "$agent" | tr '[:lower:]-' '[:upper:]_')"
  env_key="LIMEN_${env_suffix}_BIN"
  override="$(printenv "$env_key" 2>/dev/null || true)"
  for candidate in "$override" "$agent" "$registry_binary"; do
    if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

workstream_export_context() {
  local agent="$1"
  local wt="$2"
  local capsule_dir="$3"
  local slug="$4"
  local workstream="$5"
  local capabilities="$6"
  local inherited_agent inherited_session generated_session conductor_agent_default conductor_session_default

  inherited_agent="${LIMEN_AGENT:-}"
  inherited_session="${LIMEN_SESSION_ID:-}"
  generated_session="workstream-${slug}-$(date -u +'%Y%m%dT%H%M%SZ')-$$"
  conductor_agent_default="$agent"
  conductor_session_default="$generated_session"
  if [[ -n "$inherited_agent" && -n "$inherited_session" ]]; then
    conductor_agent_default="$inherited_agent"
    conductor_session_default="$inherited_session"
  fi

  export LIMEN_AGENT="$agent"
  export LIMEN_SURFACE="workstream"
  export LIMEN_WORKTREE="$wt"
  export LIMEN_WORKSTREAM="$workstream"
  export LIMEN_AGENT_CAPABILITIES="$capabilities"
  export LIMEN_CAPSULE_ID="$slug"
  export LIMEN_CAPSULE_DIR="$capsule_dir"
  export LIMEN_CAPSULE_README="$capsule_dir/README.md"
  export LIMEN_SESSION_ID="${LIMEN_WORKSTREAM_SESSION_ID:-$generated_session}"
  export LIMEN_RUN_ID="${LIMEN_RUN_ID:-$LIMEN_SESSION_ID}"
  export LIMEN_ROOT_RUN_ID="${LIMEN_ROOT_RUN_ID:-$LIMEN_RUN_ID}"
  export LIMEN_PARENT_RUN_ID="${LIMEN_PARENT_RUN_ID:-}"
  export LIMEN_CONDUCTOR_AGENT="${LIMEN_CONDUCTOR_AGENT:-$conductor_agent_default}"
  export LIMEN_CONDUCTOR_SESSION_ID="${LIMEN_CONDUCTOR_SESSION_ID:-$conductor_session_default}"
  export LIMEN_TASK_ID="${LIMEN_TASK_ID:-}"
  export LIMEN_LEASE_GENERATION="${LIMEN_LEASE_GENERATION:-}"
  export LIMEN_EXECUTION_HASH="${LIMEN_EXECUTION_HASH:-}"
}

workstream_register_conduct_session() {
  local agent="$1"
  local wt="$2"
  local capabilities="$3"
  local limen_binary="${LIMEN_CLI_BIN:-limen}"
  local register_rc=0
  local capability
  local capability_args=()

  if ! command -v "$limen_binary" >/dev/null 2>&1; then
    unset LIMEN_CONDUCT_TOKEN
    printf 'conduct registration requires the limen CLI (set LIMEN_CLI_BIN to its path)\n' >&2
    return 127
  fi

  for capability in $capabilities; do
    capability_args+=(--capability "$capability")
  done

  if "$limen_binary" conduct register \
    --agent "$agent" \
    --surface workstream \
    --session-id "$LIMEN_SESSION_ID" \
    --origin direct \
    "${capability_args[@]}" \
    --worktree "$wt" \
    --human-protected \
    --concurrency 1 >/dev/null; then
    :
  else
    register_rc=$?
  fi
  # The broker client consumes its credential; the native model process must not inherit it.
  unset LIMEN_CONDUCT_TOKEN
  if [[ "$register_rc" -ne 0 ]]; then
    return "$register_rc"
  fi
  export LIMEN_HUMAN_PROTECTED=1
  printf 'registered protected conduct session: %s (%s)\n' "$LIMEN_SESSION_ID" "$agent"
}

workstream_launch_native_agent() {
  local agent="$1"
  local registry_binary="$2"
  local autonomous="$3"
  local readme="$4"
  local allow_shell_fallback="$5"
  local binary capsule_prompt=""

  # A broker credential belongs to the registration client, never to the model process.
  unset LIMEN_CONDUCT_TOKEN
  if ! binary="$(workstream_native_binary "$agent" "$registry_binary")"; then
    if [[ "$allow_shell_fallback" -eq 1 ]]; then
      printf 'native %s CLI not found; opening a login shell\n' "$agent" >&2
      exec "${SHELL:-/bin/zsh}" -l
    fi
    printf 'native CLI not found for canonical lane %s\n' "$agent" >&2
    return 127
  fi

  if [[ "$autonomous" -eq 1 ]]; then
    IFS= read -r -d '' capsule_prompt < "$readme" || true
    case "$agent" in
      codex)
        if [[ -t 0 && -t 1 ]]; then
          exec "$binary" --ask-for-approval never --sandbox workspace-write "$capsule_prompt"
        fi
        # Shell runners do not provide a terminal; use Codex's noninteractive transport.
        exec "$binary" --ask-for-approval never --sandbox workspace-write exec "$capsule_prompt"
        ;;
      opencode)
        exec "$binary" --prompt "$capsule_prompt"
        ;;
      agy|gemini)
        exec "$binary" --prompt-interactive "$capsule_prompt"
        ;;
      *)
        exec "$binary" "$capsule_prompt"
        ;;
    esac
  fi

  case "$agent" in
    codex)
      exec "$binary" --ask-for-approval never --sandbox workspace-write
      ;;
    agy)
      # Agy has no argument-free interactive session.
      if [[ -s "$readme" ]]; then
        IFS= read -r -d '' capsule_prompt < "$readme" || true
        exec "$binary" --prompt-interactive "$capsule_prompt"
      fi
      ;;
  esac
  exec "$binary"
}

_limen_capsule_input_digest() {
  printf '%s\0' "$@" \
    | python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())' 9>&-
}

_limen_capsule_file_digest() {
  python3 - "$1" 9>&- <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

_limen_capsule_validate_receipt() {
  python3 - "$@" 9>&- <<'PY'
import json
import sys
from pathlib import Path

contract_path, receipt_path, slug, branch, workstream = sys.argv[1:]
modules = [
    "README.md",
    "manifest.md",
    "workstream.json",
    "workstream-contract.py",
    "intent.md",
    "runtime.md",
    "closeout.md",
    "kickstart.sh",
    "capsule.identity",
]
try:
    contract = json.loads(Path(contract_path).read_text())
    receipt = json.loads(Path(receipt_path).read_text())
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid capsule receipt: {exc}")
expected = {
    "schema": "limen.workstream.receipt.v1",
    "slug": slug,
    "branch": branch,
    "workstream": workstream.strip() or None,
    "contract": contract,
    "private_capsule": {
        "content": "redacted",
        "modules": modules,
    },
}
if receipt != expected:
    raise SystemExit("invalid capsule receipt: identity or contract mismatch")
PY
}

# Render one modular continuation capsule. The caller owns worktree creation and launch behavior.
render_workstream_capsule() {
  local wt="$1"
  local repo="$2"
  local slug="$3"
  local branch="$4"
  local workstream="$5"
  local from_ref="$6"
  local autonomous="$7"
  local prompt_payload="$8"
  local spec_dir="$9"
  local runway_requested="${10:-}"
  local contract_source="${11:-}"
  local agent="${12}"
  local registry_binary="${13}"
  local conduct="${14}"
  local allow_shell_fallback="${15}"
  local agent_capabilities="${16}"
  local capsule_dir="$wt/.limen-workstream"
  local readme="$capsule_dir/README.md"
  local manifest="$capsule_dir/manifest.md"
  local contract="$capsule_dir/workstream.json"
  local contract_helper="$capsule_dir/workstream-contract.py"
  local intent="$capsule_dir/intent.md"
  local runtime="$capsule_dir/runtime.md"
  local closeout="$capsule_dir/closeout.md"
  local kickstart="$capsule_dir/kickstart.sh"
  local identity="$capsule_dir/capsule.identity"
  local capsule_lock="$capsule_dir/.capsule.lock"
  local receipt_rel="docs/continuations/$slug/workstream.json"
  local receipt="$wt/$receipt_rel"
  local runtime_template="$spec_dir/runtime-interactive.md"
  local required_template created_at head_short upstream_ref origin_url status_line readme_action contract_action receipt_action
  local launch_helpers
  local actual_branch effective_runway input_digest identity_action
  local runtime_source_digest closeout_source_digest contract_source_digest capsule_real wt_real lock_status
  local q_wt q_capsule_dir q_capsule_lock q_receipt q_identity q_readme q_manifest q_contract q_contract_helper
  local q_intent q_runtime q_closeout q_kickstart q_slug q_branch q_workstream q_input_digest
  local q_agent q_registry_binary q_conduct q_allow_shell_fallback q_agent_capabilities
  local capsule_preexisting=0
  local capsule_changed=0

  if [[ "$autonomous" -eq 1 ]]; then
    runtime_template="$spec_dir/runtime-autonomous.md"
  fi
  for required_template in "$runtime_template" "$spec_dir/closeout.md"; do
    if [[ ! -f "$required_template" ]]; then
      echo "capsule template not found: $required_template" >&2
      return 1
    fi
  done
  if [[ -z "$contract_source" ]]; then
    contract_source="$(cd "$spec_dir/../../cli/src/limen" && pwd -P)/workstream_contract.py"
  fi
  if [[ ! -f "$contract_source" ]]; then
    echo "workstream contract helper not found: $contract_source" >&2
    return 1
  fi
  if ! python3 "$contract_source" validate-receipt-metadata \
    --slug "$slug" --branch "$branch" --workstream "$workstream" >/dev/null; then
    return 1
  fi
  if ! git -C "$wt" ls-files --error-unmatch -- "$receipt_rel" >/dev/null 2>&1 \
    && git -C "$wt" check-ignore -q -- "$receipt_rel"; then
    echo "capsule receipt path is ignored: $receipt_rel" >&2
    return 1
  fi
  if [[ -L "$capsule_dir" || ( -e "$capsule_dir" && ! -d "$capsule_dir" ) ]]; then
    echo "capsule root must be a real directory inside the worktree" >&2
    return 1
  fi
  if [[ ! -e "$capsule_dir" ]]; then
    mkdir "$capsule_dir"
  fi
  if [[ -L "$capsule_dir" || ! -d "$capsule_dir" ]]; then
    echo "capsule root must be a real directory inside the worktree" >&2
    return 1
  fi
  wt_real="$(cd "$wt" && pwd -P)"
  capsule_real="$(cd "$capsule_dir" && pwd -P)"
  if [[ "$capsule_real" != "$wt_real/.limen-workstream" ]]; then
    echo "capsule root escapes the worktree" >&2
    return 1
  fi
  if [[ -L "$capsule_lock" || ( -e "$capsule_lock" && ! -f "$capsule_lock" ) ]]; then
    echo "capsule lock path is unsafe" >&2
    return 1
  fi

  (
  set -e
  exec 9>> "$capsule_lock"
  lock_status=0
  python3 -c \
    'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' \
    9>&9 || lock_status=$?
  if [[ "$lock_status" -ne 0 ]]; then
    echo "capsule is busy with another render or launch; retry or emit a successor capsule" >&2
    exit 1
  fi

  for required_template in "$readme" "$manifest" "$contract" "$contract_helper" "$intent" \
    "$runtime" "$closeout" "$kickstart" "$identity" "$receipt"; do
    if [[ -e "$required_template" ]]; then
      capsule_preexisting=1
      break
    fi
  done
  if [[ "$capsule_preexisting" -eq 1 && ! -f "$contract" ]]; then
    echo "invalid existing capsule: workstream contract is missing; emit a successor capsule" >&2
    exit 1
  fi

  effective_runway="$runway_requested"
  if [[ -z "$effective_runway" && "$capsule_preexisting" -eq 1 ]]; then
    effective_runway="$(
      python3 - "$contract" 9>&- <<'PY'
import json
import sys
from pathlib import Path

try:
    value = json.loads(Path(sys.argv[1]).read_text())
    requested = value["runway"]["requested"]
except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid existing capsule contract: {exc}")
if not isinstance(requested, str) or not requested:
    raise SystemExit("invalid existing capsule contract: runway request is missing")
print(requested)
PY
    )"
  elif [[ -z "$effective_runway" ]]; then
    effective_runway="1d"
  fi
  runtime_source_digest="$(_limen_capsule_file_digest "$runtime_template")"
  closeout_source_digest="$(_limen_capsule_file_digest "$spec_dir/closeout.md")"
  contract_source_digest="$(_limen_capsule_file_digest "$contract_source")"
  input_digest="$(
    _limen_capsule_input_digest \
      "limen.workstream.capsule-identity.v2" \
      "$repo" "$wt" "$slug" "$branch" "$workstream" "$from_ref" \
      "$autonomous" "$effective_runway" "$prompt_payload" \
      "agent=$agent" "registry-binary=$registry_binary" "conduct=$conduct" \
      "allow-shell-fallback=$allow_shell_fallback" "agent-capabilities=$agent_capabilities" \
      "runtime-source-sha256=$runtime_source_digest" \
      "closeout-source-sha256=$closeout_source_digest" \
      "contract-source-sha256=$contract_source_digest"
  )"
  actual_branch="$(git -C "$wt" branch --show-current)"
  if [[ "$actual_branch" != "$branch" ]]; then
    echo "existing capsule worktree branch identity changed; emit a successor capsule" >&2
    exit 1
  fi

  if [[ "$capsule_preexisting" -eq 1 ]]; then
    if [[ ! -s "$identity" ]]; then
      echo "invalid existing capsule: launch identity is missing; emit a successor capsule" >&2
      exit 1
    fi
    for required_template in "$readme" "$manifest" "$contract" "$contract_helper" "$intent" \
      "$runtime" "$closeout" "$kickstart"; do
      if [[ ! -s "$required_template" ]]; then
        echo "invalid existing capsule: missing or empty module $required_template; emit a successor capsule" >&2
        exit 1
      fi
    done
    if ! python3 "$contract_source" verify-identity \
      --identity "$identity" \
      --invocation-sha256 "$input_digest" \
      --module "README.md=$readme" \
      --module "manifest.md=$manifest" \
      --module "workstream.json=$contract" \
      --module "workstream-contract.py=$contract_helper" \
      --module "intent.md=$intent" \
      --module "runtime.md=$runtime" \
      --module "closeout.md=$closeout" \
      --module "kickstart.sh=$kickstart" >/dev/null 9>&-; then
      echo "existing capsule launch identity changed; emit a successor capsule before rerendering" >&2
      exit 1
    fi
    if [[ ! -s "$receipt" ]]; then
      echo "invalid existing capsule: missing or empty module $receipt; emit a successor capsule" >&2
      exit 1
    fi
    if ! _limen_capsule_validate_receipt "$contract" "$receipt" "$slug" "$branch" "$workstream"; then
      echo "invalid existing capsule receipt; emit a successor capsule" >&2
      exit 1
    fi
    echo "capsule index: $readme (unchanged)"
    echo "capsule modules: $manifest $contract $intent $runtime $closeout"
    echo "capsule receipt: $receipt"
    echo "kickstart command: bash $kickstart"
    exit 0
  fi

  created_at=""
  if [[ -f "$manifest" ]]; then
    # shellcheck disable=SC2016
    created_at="$(sed -n 's/^- Created: `\(.*\)`$/\1/p' "$manifest" | head -n 1)"
  fi
  if [[ -z "$created_at" && -f "$readme" ]]; then
    created_at="$(sed -n 's/^Created: //p' "$readme" | head -n 1)"
  fi
  if [[ -z "$created_at" ]]; then
    created_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  fi
  head_short="$(git -C "$wt" rev-parse --short HEAD)"
  upstream_ref="$(git -C "$wt" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  origin_url="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
  status_line="$(git -C "$wt" status --short --branch | head -n 1)"
  launch_helpers="$(
    declare -f \
      workstream_native_binary \
      workstream_export_context \
      workstream_register_conduct_session \
      workstream_launch_native_agent
  )"

  _capsule_write_module() {
    local destination="$1"
    local temporary="${destination}.tmp.$$"
    cat > "$temporary"
    if [[ -f "$destination" ]] && cmp -s "$temporary" "$destination"; then
      rm -f "$temporary"
    else
      mv "$temporary" "$destination"
      capsule_changed=1
    fi
  }

  if [[ ! -f "$manifest" ]]; then
    _capsule_write_module "$manifest" <<EOF
# Capsule manifest

- Created: \`$created_at\`
- Repo: \`$repo\`
- Worktree: \`$wt\`
- Branch: \`$branch\`
- Workstream: \`${workstream:-unassigned}\`
- Base ref: \`$from_ref\`
- HEAD at capsule write: \`$head_short\`
- Upstream: \`${upstream_ref:-none yet}\`
- Origin: \`${origin_url:-none}\`
- Status at capsule write: \`$status_line\`
- Autonomous: \`$([[ "$autonomous" -eq 1 ]] && printf yes || printf no)\`
- Agent: \`$agent\`
- Agent capabilities: \`$agent_capabilities\`
- Conduct: \`$([[ "$conduct" -eq 1 ]] && printf yes || printf no)\`

This is a historical snapshot. The runtime module requires fresh probes before action.
EOF
  fi
  _capsule_write_module "$contract_helper" < "$contract_source"
  if [[ ! -x "$contract_helper" ]]; then
    chmod +x "$contract_helper"
    capsule_changed=1
  fi
  if [[ -n "$runway_requested" ]]; then
    contract_action="$(python3 "$contract_helper" configure --path "$contract" --runway "$runway_requested" 9>&-)" \
      || exit 1
  else
    contract_action="$(python3 "$contract_helper" configure --path "$contract" 9>&-)" || exit 1
  fi
  if [[ "$contract_action" == "changed" || "$contract_action" == "unchanged" ]]; then
    [[ "$contract_action" == "changed" ]] && capsule_changed=1
  else
    echo "invalid workstream contract helper response: $contract_action" >&2
    exit 1
  fi
  _capsule_write_module "$intent" <<EOF
$prompt_payload
EOF
  _capsule_write_module "$runtime" < "$runtime_template"
  _capsule_write_module "$closeout" < "$spec_dir/closeout.md"
  _capsule_write_module "$readme" <<EOF
# Continuation capsule: $slug

This README is the initial prompt index, not a concatenated brief. Before acting, read these local
modules in order:

1. \`.limen-workstream/manifest.md\` — historical location and custody snapshot;
2. \`.limen-workstream/workstream.json\` — validated runway, conductor, and authorization contract;
3. \`.limen-workstream/intent.md\` — objective and owner-specific context;
4. \`.limen-workstream/runtime.md\` — live probes and boundary decision contract;
5. \`.limen-workstream/closeout.md\` — receipt and successor rules.

Resolve them from \`$wt\`. Missing, unreadable, stale, or contradictory modules make the capsule
invalid; stop rather than guessing. The intent fixes scope. Live evidence determines the lane and
ending.

The private capsule remains local and ignored. Its tracked redacted custody receipt is
\`$receipt_rel\`; the first launched session commits and pushes that receipt after admission.
The kickstart acquires the capsule lock and validates \`.limen-workstream/capsule.identity\`
plus that receipt before it admits the runway or launches a provider.

## Launch command

\`\`\`bash
bash "$kickstart"
\`\`\`

For a plain shell, use \`cd "$wt"\` and then \`\${SHELL:-/bin/zsh} -l\`.
EOF
  printf -v q_wt '%q' "$wt"
  printf -v q_capsule_dir '%q' "$capsule_dir"
  printf -v q_capsule_lock '%q' "$capsule_lock"
  printf -v q_receipt '%q' "$receipt"
  printf -v q_identity '%q' "$identity"
  printf -v q_readme '%q' "$readme"
  printf -v q_manifest '%q' "$manifest"
  printf -v q_contract '%q' "$contract"
  printf -v q_contract_helper '%q' "$contract_helper"
  printf -v q_intent '%q' "$intent"
  printf -v q_runtime '%q' "$runtime"
  printf -v q_closeout '%q' "$closeout"
  printf -v q_kickstart '%q' "$kickstart"
  printf -v q_slug '%q' "$slug"
  printf -v q_branch '%q' "$branch"
  printf -v q_workstream '%q' "$workstream"
  printf -v q_input_digest '%q' "$input_digest"
  printf -v q_agent '%q' "$agent"
  printf -v q_registry_binary '%q' "$registry_binary"
  printf -v q_conduct '%q' "$conduct"
  printf -v q_allow_shell_fallback '%q' "$allow_shell_fallback"
  printf -v q_agent_capabilities '%q' "$agent_capabilities"
  _capsule_write_module "$kickstart" <<EOF
#!/usr/bin/env bash
set -euo pipefail
$launch_helpers

cd $q_wt
capsule_dir=$q_capsule_dir
capsule_lock=$q_capsule_lock
receipt=$q_receipt
identity=$q_identity
readme=$q_readme
manifest=$q_manifest
contract=$q_contract
contract_helper=$q_contract_helper
intent=$q_intent
runtime=$q_runtime
closeout=$q_closeout
kickstart=$q_kickstart
expected_slug=$q_slug
expected_branch=$q_branch
expected_workstream=$q_workstream
expected_invocation_sha256=$q_input_digest
agent=$q_agent
registry_binary=$q_registry_binary
conduct=$q_conduct
allow_shell_fallback=$q_allow_shell_fallback
agent_capabilities=$q_agent_capabilities
if [[ -L "\$capsule_dir" || ! -d "\$capsule_dir" \
  || "\$(cd "\$capsule_dir" && pwd -P)" != "\$capsule_dir" ]]; then
  printf 'invalid capsule: private root is not the expected real directory\n' >&2
  exit 2
fi
if [[ -L "\$capsule_lock" || ( -e "\$capsule_lock" && ! -f "\$capsule_lock" ) ]]; then
  printf 'invalid capsule: lock path is unsafe\n' >&2
  exit 2
fi
exec 9>> "\$capsule_lock"
lock_status=0
python3 -c \
  'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' \
  9>&9 || lock_status=\$?
if [[ "\$lock_status" -ne 0 ]]; then
  printf 'invalid capsule: another render or launch holds the capsule lock\n' >&2
  exit 2
fi
for module in "\$readme" "\$manifest" "\$contract" "\$contract_helper" "\$intent" "\$runtime" \
  "\$closeout" "\$kickstart" "\$identity" "\$receipt"; do
  if [[ ! -s "\$module" ]]; then
    printf 'invalid capsule: missing or empty module %s\n' "\$module" >&2
    exit 2
  fi
done
verify_capsule_identity() {
  python3 - "\$identity" "\$expected_invocation_sha256" "\$capsule_dir" \
    "\$readme" "\$manifest" "\$contract" "\$contract_helper" "\$intent" "\$runtime" \
    "\$closeout" "\$kickstart" 9>&- <<'PY'
import hashlib
import json
import sys
from pathlib import Path

identity_path = Path(sys.argv[1])
invocation_sha256 = sys.argv[2]
capsule_dir = Path(sys.argv[3])
names = [
    "README.md",
    "manifest.md",
    "workstream.json",
    "workstream-contract.py",
    "intent.md",
    "runtime.md",
    "closeout.md",
    "kickstart.sh",
]
paths = [Path(raw) for raw in sys.argv[4:]]
try:
    resolved_capsule = capsule_dir.resolve(strict=True)
    actual = json.loads(identity_path.read_text())
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid capsule identity: {exc}")
if capsule_dir.is_symlink() or identity_path.is_symlink() or identity_path.parent.resolve() != resolved_capsule:
    raise SystemExit("invalid capsule identity path")
digests = {}
for name, path in zip(names, paths, strict=True):
    if path.name != name or path.is_symlink() or not path.is_file() or path.resolve().parent != resolved_capsule:
        raise SystemExit(f"invalid capsule module path: {name}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    digests[name] = digest.hexdigest()
expected = {
    "schema": "limen.workstream.capsule-identity.v2",
    "invocation_sha256": invocation_sha256,
    "modules": digests,
}
if actual != expected:
    raise SystemExit("invalid capsule identity: module bytes changed; emit a successor capsule")
PY
}
verify_capsule_identity
if [[ "\$(git branch --show-current 9>&-)" != "\$expected_branch" ]]; then
  printf 'invalid capsule: worktree branch identity mismatch; emit a successor capsule\n' >&2
  exit 2
fi
validate_capsule_receipt() {
  python3 - "\$contract" "\$receipt" "\$expected_slug" "\$expected_branch" "\$expected_workstream" 9>&- <<'PY'
import json
import sys
from pathlib import Path

contract_path, receipt_path, slug, branch, workstream = sys.argv[1:]
modules = [
    "README.md",
    "manifest.md",
    "workstream.json",
    "workstream-contract.py",
    "intent.md",
    "runtime.md",
    "closeout.md",
    "kickstart.sh",
    "capsule.identity",
]
try:
    contract = json.loads(Path(contract_path).read_text())
    receipt = json.loads(Path(receipt_path).read_text())
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid capsule receipt: {exc}")
expected = {
    "schema": "limen.workstream.receipt.v1",
    "slug": slug,
    "branch": branch,
    "workstream": workstream.strip() or None,
    "contract": contract,
    "private_capsule": {
        "content": "redacted",
        "modules": modules,
    },
}
if receipt != expected:
    raise SystemExit("invalid capsule receipt: identity or contract mismatch")
PY
}
validate_capsule_receipt
refresh_workstream_runway() {
  local runway_fields=""
  if runway_fields="\$(python3 "\$contract_helper" admit-identity \
    --contract "\$contract" \
    --identity "\$identity" \
    --invocation-sha256 "\$expected_invocation_sha256" \
    --module "README.md=\$readme" \
    --module "manifest.md=\$manifest" \
    --module "workstream.json=\$contract" \
    --module "workstream-contract.py=\$contract_helper" \
    --module "intent.md=\$intent" \
    --module "runtime.md=\$runtime" \
    --module "closeout.md=\$closeout" \
    --module "kickstart.sh=\$kickstart" \
    9>&-)"; then
    :
  else
    return \$?
  fi
  python3 "\$contract_helper" sync-receipt \
    --contract "\$contract" \
    --receipt "\$receipt" \
    --slug "\$expected_slug" \
    --branch "\$expected_branch" \
    --workstream "\$expected_workstream" \
    --module "README.md=\$readme" \
    --module "manifest.md=\$manifest" \
    --module "workstream.json=\$contract" \
    --module "workstream-contract.py=\$contract_helper" \
    --module "intent.md=\$intent" \
    --module "runtime.md=\$runtime" \
    --module "closeout.md=\$closeout" \
    --module "kickstart.sh=\$kickstart" \
    --module "capsule.identity=\$identity" \
    >/dev/null 9>&-
  validate_capsule_receipt
  verify_capsule_identity
  IFS=: read -r LIMEN_WORKSTREAM_REQUESTED LIMEN_WORKSTREAM_RUNWAY_SECONDS LIMEN_WORKSTREAM_STARTED_EPOCH LIMEN_WORKSTREAM_DEADLINE_EPOCH LIMEN_WORKSTREAM_REMAINING_SECONDS <<< "\$runway_fields"
  export LIMEN_WORKSTREAM_REQUESTED LIMEN_WORKSTREAM_RUNWAY_SECONDS LIMEN_WORKSTREAM_STARTED_EPOCH LIMEN_WORKSTREAM_DEADLINE_EPOCH LIMEN_WORKSTREAM_REMAINING_SECONDS
}
refresh_workstream_runway
preflight_timeout="\${LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}"
case "\$preflight_timeout" in
  ""|*[!0-9]*)
    printf 'invalid capsule preflight timeout: %s\n' "\$preflight_timeout" >&2
    exit 2
    ;;
esac
if (( preflight_timeout < 1 || preflight_timeout > 300 )); then
  printf 'capsule preflight timeout must be between 1 and 300 seconds\n' >&2
  exit 2
fi
if git remote get-url origin >/dev/null 2>&1 9>&-; then
  GIT_TERMINAL_PROMPT=0 python3 "\$contract_helper" run-bounded \
    --timeout-seconds "\$preflight_timeout" -- git fetch --prune 9>&-
fi
python3 "\$contract_helper" run-bounded \
  --timeout-seconds "\$preflight_timeout" -- git status --short --branch 9>&-
workstream_export_context \
  "\$agent" "\$PWD" "\$capsule_dir" "\$expected_slug" "\$expected_workstream" "\$agent_capabilities"
if [[ "\$conduct" -eq 1 ]]; then
  workstream_register_conduct_session "\$agent" "\$PWD" "\$agent_capabilities"
fi
refresh_workstream_runway
exec 9>&-
workstream_launch_native_agent \
  "\$agent" "\$registry_binary" "$autonomous" "\$readme" "\$allow_shell_fallback"
EOF
  if [[ ! -x "$kickstart" ]]; then
    chmod +x "$kickstart"
    capsule_changed=1
  fi
  if identity_action="$(python3 "$contract_helper" sync-identity \
    --identity "$identity" \
    --invocation-sha256 "$input_digest" \
    --module "README.md=$readme" \
    --module "manifest.md=$manifest" \
    --module "workstream.json=$contract" \
    --module "workstream-contract.py=$contract_helper" \
    --module "intent.md=$intent" \
    --module "runtime.md=$runtime" \
    --module "closeout.md=$closeout" \
    --module "kickstart.sh=$kickstart" 9>&-)"; then
    [[ "$identity_action" == "changed" ]] && capsule_changed=1
  else
    exit 1
  fi
  if [[ "$identity_action" != "changed" && "$identity_action" != "unchanged" ]]; then
    echo "invalid capsule identity helper response: $identity_action" >&2
    exit 1
  fi

  if receipt_action="$(python3 "$contract_helper" sync-receipt \
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
    --module "capsule.identity=$identity" 9>&-)"; then
    [[ "$receipt_action" == "changed" ]] && capsule_changed=1
  else
    exit 1
  fi
  if [[ "$receipt_action" != "changed" && "$receipt_action" != "unchanged" ]]; then
    echo "invalid capsule receipt helper response: $receipt_action" >&2
    exit 1
  fi
  if ! _limen_capsule_validate_receipt "$contract" "$receipt" "$slug" "$branch" "$workstream"; then
    echo "capsule receipt failed final validation" >&2
    exit 1
  fi
  if [[ "$capsule_changed" -eq 1 ]]; then
    readme_action="wrote"
  else
    readme_action="unchanged"
  fi
  unset -f _capsule_write_module

  echo "capsule index: $readme ($readme_action)"
  echo "capsule modules: $manifest $contract $intent $runtime $closeout"
  echo "capsule receipt: $receipt"
  echo "kickstart command: bash $kickstart"
  )
}
