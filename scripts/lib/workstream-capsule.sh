#!/usr/bin/env bash

workstream_native_binary() {
  local agent="$1"
  local registry_binary="$2"
  local env_suffix env_key override candidate

  env_suffix="$(printf '%s' "$agent" | tr '[:lower:]-' '[:upper:]_')"
  env_key="LIMEN_${env_suffix}_BIN"
  override="$(printenv "$env_key" 2>/dev/null || true)"
  # Match renderer selection exactly: explicit override, registry binary, then the canonical ID
  # only as a compatibility fallback. Validation and exec must never choose different binaries.
  for candidate in "$override" "$registry_binary" "$agent"; do
    if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

workstream_jules_repository() {
  local repository=""
  local origin="$(git remote get-url origin 2>/dev/null || true)"

  case "$origin" in
    git@github.com:*) repository="${origin#git@github.com:}" ;;
    https://*@github.com/*) repository="${origin#*@github.com/}" ;;
    https://github.com/*) repository="${origin#https://github.com/}" ;;
    ssh://git@github.com/*) repository="${origin#ssh://git@github.com/}" ;;
  esac
  while [[ "$repository" == */ ]]; do
    repository="${repository%/}"
  done
  repository="${repository%.git}"

  if [[ ! "$repository" =~ ^[^/[:space:]]+/[^/[:space:]]+$ ]]; then
    return 1
  fi
  printf '%s\n' "$repository"
}

workstream_jules_validate_default_base() {
  local contract_helper="${LIMEN_CAPSULE_DIR:-}/workstream-contract.py"
  local timeout_seconds="${LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}"
  local current_head="" remote_line="" remote_head=""
  local branch="" receipt="" receipt_rel="" current_parent="" current_subject=""
  local remote_branch_line="" remote_branch_head=""

  workstream_jules_reuse_reservation=0
  if [[ ! -f "$contract_helper" ]]; then
    printf 'Jules workstream launch requires the capsule contract helper\n' >&2
    return 2
  fi
  if ! current_head="$(git rev-parse HEAD 2>/dev/null)"; then
    printf 'Jules workstream launch could not resolve the worktree HEAD\n' >&2
    return 2
  fi
  if ! remote_line="$(
    GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
      --timeout-seconds "$timeout_seconds" -- git ls-remote origin HEAD
  )"; then
    printf 'Jules workstream launch could not resolve the live remote default HEAD\n' >&2
    return 2
  fi
  remote_head="${remote_line%%[[:space:]]*}"
  if [[ ! "$remote_head" =~ ^[0-9a-fA-F]{40,64}$ ]]; then
    printf 'Jules workstream launch received an invalid remote default HEAD\n' >&2
    return 2
  fi
  if [[ "$current_head" == "$remote_head" ]]; then
    return 0
  fi

  branch="$(git branch --show-current 2>/dev/null || true)"
  receipt="${LIMEN_WORKTREE:-}/docs/continuations/${LIMEN_CAPSULE_ID:-}/workstream.json"
  receipt_rel="${receipt#"${LIMEN_WORKTREE:-}/"}"
  current_parent="$(git rev-parse HEAD^ 2>/dev/null || true)"
  current_subject="$(git log -1 --format=%s 2>/dev/null || true)"
  if [[ -z "$branch" || "$current_parent" != "$remote_head"
    || "$current_subject" != "chore: reserve Jules launch "*
    || "$receipt_rel" == "$receipt" || ! -f "$receipt_rel"
    || ! -f "$contract_helper" ]]; then
    printf 'Jules workstream launch requires current HEAD to equal the live remote default HEAD or its owned unbound reservation\n' >&2
    return 2
  fi
  if ! git cat-file -e "HEAD:$receipt_rel" 2>/dev/null ||
    ! git diff --quiet HEAD -- "$receipt_rel"; then
    printf 'Jules workstream launch found an invalid unbound reservation receipt\n' >&2
    return 2
  fi
  if ! remote_branch_line="$(
    GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
      --timeout-seconds "$timeout_seconds" -- \
      git ls-remote origin "refs/heads/$branch"
  )"; then
    printf 'Jules workstream launch could not resolve its remote reservation branch\n' >&2
    return 2
  fi
  remote_branch_head="${remote_branch_line%%[[:space:]]*}"
  if [[ "$remote_branch_head" != "$current_head" ]]; then
    printf 'Jules workstream launch reservation no longer owns its remote branch\n' >&2
    return 2
  fi
  workstream_jules_reuse_reservation=1
}

workstream_jules_validate_clean_worktree() {
  local dirty="" receipt="" receipt_rel=""

  receipt="${LIMEN_WORKTREE:-}/docs/continuations/${LIMEN_CAPSULE_ID:-}/workstream.json"
  receipt_rel="${receipt#"${LIMEN_WORKTREE:-}/"}"
  if [[ "$receipt_rel" == "$receipt" || ! -f "$receipt_rel" ]]; then
    printf 'Jules workstream launch could not resolve its validated receipt path\n' >&2
    return 2
  fi
  if ! dirty="$(git status --porcelain --untracked-files=all -- . ":(exclude)$receipt_rel" 2>/dev/null)"; then
    printf 'Jules workstream launch could not inspect the worktree state\n' >&2
    return 2
  fi
  if [[ -n "$dirty" ]]; then
    printf 'Jules workstream launch requires a clean worktree; local changes are not visible in cloud\n' >&2
    return 2
  fi
}

workstream_jules_provider_run_id() {
  local receipt="$1"
  local expected_provider="${2:-jules}"

  python3 - "$receipt" "$expected_provider" <<'PY'
import json
import sys
from pathlib import Path

receipt_path = Path(sys.argv[1])
expected_provider = sys.argv[2]
try:
    receipt = json.loads(receipt_path.read_text())
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid Jules session receipt target: {exc}")
provider_run = receipt.get("provider_run")
if provider_run is None:
    raise SystemExit(1)
run_id = provider_run.get("id") if isinstance(provider_run, dict) else None
if (
    not isinstance(run_id, str)
    or not run_id.isdigit()
    or provider_run != {
        "provider": expected_provider,
        "id": run_id,
        "url": f"https://jules.google.com/session/{run_id}",
    }
):
    raise SystemExit("invalid Jules provider run identity")
print(run_id)
PY
}

workstream_jules_reserve_receipt_branch() {
  local contract_helper="${LIMEN_CAPSULE_DIR:-}/workstream-contract.py"
  local timeout_seconds="${LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}"
  local branch="" current_head="" receipt="" receipt_rel=""
  local reservation_index="" reservation_tree="" reservation_id="" reservation_commit=""

  branch="$(git branch --show-current 2>/dev/null || true)"
  current_head="$(git rev-parse HEAD 2>/dev/null || true)"
  receipt="${LIMEN_WORKTREE:-}/docs/continuations/${LIMEN_CAPSULE_ID:-}/workstream.json"
  receipt_rel="${receipt#"${LIMEN_WORKTREE:-}/"}"
  if [[ -z "$branch" || -z "$current_head" || ! -f "$contract_helper"
    || "$receipt_rel" == "$receipt" || ! -f "$receipt_rel" ]]; then
    printf 'Jules workstream launch could not resolve its receipt branch, tracked path, or contract helper\n' >&2
    return 2
  fi
  if ! reservation_index="$(mktemp "${TMPDIR:-/tmp}/limen-jules-reservation-index.XXXXXX")"; then
    printf 'Jules workstream launch could not allocate its reservation index\n' >&2
    return 2
  fi
  rm -f "$reservation_index"
  if ! GIT_INDEX_FILE="$reservation_index" git read-tree "$current_head" ||
    ! GIT_INDEX_FILE="$reservation_index" git add -- "$receipt_rel" ||
    ! reservation_tree="$(GIT_INDEX_FILE="$reservation_index" git write-tree)"; then
    rm -f "$reservation_index"
    printf 'Jules workstream launch could not build its durable receipt reservation\n' >&2
    return 2
  fi
  rm -f "$reservation_index"
  reservation_id="${LIMEN_SESSION_ID:-workstream}:$$:${RANDOM:-0}"
  if ! reservation_commit="$(printf 'chore: reserve Jules launch %s\n' "$reservation_id" | \
    git -c commit.gpgsign=false commit-tree "$reservation_tree" -p "$current_head")"; then
    printf 'Jules workstream launch could not create its reservation commit\n' >&2
    return 2
  fi
  if ! GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
    --timeout-seconds "$timeout_seconds" -- \
    git push --set-upstream origin "$reservation_commit:refs/heads/$branch"; then
    printf 'Jules workstream launch could not reserve a unique durable receipt branch\n' >&2
    return 2
  fi
  if ! git reset --mixed "$reservation_commit" >/dev/null; then
    printf 'Jules workstream launch could not bind its local reservation commit\n' >&2
    return 2
  fi
}

workstream_jules_sync_receipt() {
  local receipt="$1"
  local session_id="$2"
  local session_url="$3"
  local provider="${4:-jules}"

  python3 - "$receipt" "${LIMEN_WORKTREE:-}" "$session_id" "$session_url" "$provider" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

receipt_path = Path(sys.argv[1])
worktree = Path(sys.argv[2])
session_id = sys.argv[3].strip()
session_url = sys.argv[4].strip()
provider = sys.argv[5].strip()
expected_url = f"https://jules.google.com/session/{session_id}"
try:
    worktree_resolved = worktree.resolve(strict=True)
    receipt_resolved = receipt_path.resolve(strict=True)
    receipt = json.loads(receipt_path.read_text())
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid Jules session receipt target: {exc}")
if (
    receipt_path.is_symlink()
    or not receipt_resolved.is_relative_to(worktree_resolved)
    or not isinstance(receipt, dict)
    or receipt.get("schema") != "limen.workstream.receipt.v1"
):
    raise SystemExit("invalid Jules session receipt target")
if (
    not session_id.isdigit()
    or not session_id
    or session_url != expected_url
    or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", provider)
):
    raise SystemExit("invalid Jules session ID or URL")
receipt["provider_run"] = {
    "provider": provider,
    "id": session_id,
    "url": session_url,
}
temporary = receipt_path.with_name(f".{receipt_path.name}.tmp.{os.getpid()}")
temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
os.replace(temporary, receipt_path)
PY
}

workstream_jules_publish_receipt() {
  local receipt="$1"
  local session_id="$2"
  local contract_helper="${LIMEN_CAPSULE_DIR:-}/workstream-contract.py"
  local timeout_seconds="${LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}"
  local branch="" receipt_rel="" publish_commit=""
  local staged_paths="" current_subject="" changed_paths="" parent_subject="" clean_rc=0

  branch="$(git branch --show-current 2>/dev/null || true)"
  receipt_rel="${receipt#"${LIMEN_WORKTREE:-}/"}"
  if [[ -z "$branch" || "$receipt_rel" == "$receipt" || ! -f "$receipt_rel" ]]; then
    printf 'Jules session receipt could not resolve its topic branch or tracked path\n' >&2
    return 2
  fi
  workstream_jules_validate_clean_worktree || clean_rc=$?
  if [[ "$clean_rc" -ne 0 ]]; then
    return "$clean_rc"
  fi
  if ! git add -- "$receipt_rel"; then
    printf 'Jules session receipt could not be staged\n' >&2
    return 2
  fi
  if ! git diff --cached --quiet -- "$receipt_rel"; then
    staged_paths="$(git diff --cached --name-only)"
    if [[ "$staged_paths" != "$receipt_rel" ]]; then
      printf 'Jules session receipt publish found unrelated staged paths\n' >&2
      return 2
    fi
    if ! git -c commit.gpgsign=false commit -qm \
      "chore: preserve Jules session $session_id receipt" -- "$receipt_rel"; then
      printf 'Jules session receipt could not be committed\n' >&2
      return 2
    fi
  elif ! git diff --quiet -- "$receipt_rel"; then
    printf 'Jules session receipt has unstaged changes after staging\n' >&2
    return 2
  fi
  publish_commit="$(git rev-parse HEAD 2>/dev/null || true)"
  current_subject="$(git log -1 --format=%s 2>/dev/null || true)"
  changed_paths="$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true)"
  parent_subject="$(git log -1 --format=%s HEAD^ 2>/dev/null || true)"
  if [[ -z "$publish_commit"
    || "$current_subject" != "chore: preserve Jules session $session_id receipt"
    || "$changed_paths" != "$receipt_rel"
    || "$parent_subject" != "chore: reserve Jules launch "* ]]; then
    printf 'Jules session receipt publish requires the exact receipt-only commit on its reservation\n' >&2
    return 2
  fi
  GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
    --timeout-seconds "$timeout_seconds" -- \
    git push --set-upstream origin "$publish_commit:refs/heads/$branch"
}

workstream_exact_remote_ref_head() {
  local rows="$1"
  local expected_ref="$2"
  local observed_head="" observed_ref=""

  if [[ -z "$rows" ]]; then
    return 0
  fi
  if [[ "$rows" == *$'\n'* || "$rows" != *$'\t'* ]]; then
    return 2
  fi
  observed_head="${rows%%$'\t'*}"
  observed_ref="${rows#*$'\t'}"
  if [[ ! "$observed_head" =~ ^[0-9a-fA-F]{40,64}$ || "$observed_ref" != "$expected_ref" ]]; then
    return 2
  fi
  printf '%s\n' "$observed_head"
}

workstream_validate_launch_environment() {
  local timeout_seconds="$1"
  local contract_helper="${LIMEN_CAPSULE_DIR:-}/workstream-contract.py"
  local git_paths="" git_dir="" common_git_dir=""

  if [[ ! -f "$contract_helper" ]]; then
    printf 'launch-environment error: capsule contract helper is unavailable\n' >&2
    return 2
  fi
  if ! git_paths="$(git rev-parse --path-format=absolute --git-dir --git-common-dir 2>/dev/null)"; then
    printf 'launch-environment error: linked worktree Git metadata could not be resolved\n' >&2
    return 2
  fi
  git_dir="$(printf '%s\n' "$git_paths" | sed -n '1p')"
  common_git_dir="$(printf '%s\n' "$git_paths" | sed -n '2p')"
  if [[ -z "$git_dir" || -z "$common_git_dir"
    || "$git_dir" != /* || "$common_git_dir" != /* ]]; then
    printf 'launch-environment error: linked worktree Git metadata resolved to an invalid path\n' >&2
    return 2
  fi
  if [[ ! -d "$git_dir" || ! -w "$git_dir" ]]; then
    printf 'launch-environment error: linked worktree Git directory is not writable: %s\n' "$git_dir" >&2
    return 2
  fi
  if [[ ! -d "$common_git_dir" || ! -w "$common_git_dir" ]]; then
    printf 'launch-environment error: common Git directory is not writable: %s\n' "$common_git_dir" >&2
    return 2
  fi
  if git remote get-url origin >/dev/null 2>&1; then
    if ! GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
      --timeout-seconds "$timeout_seconds" -- git ls-remote origin HEAD >/dev/null 2>&1; then
      printf 'launch-environment error: configured remote origin is unavailable\n' >&2
      return 2
    fi
  fi
}

workstream_mark_provider_active() {
  local actual_worktree=""

  actual_worktree="$(pwd -P)"
  if [[ -z "${LIMEN_CAPSULE_ID:-}" || -z "${LIMEN_WORKTREE:-}"
    || -z "${LIMEN_SESSION_ID:-}" || "$actual_worktree" != "$LIMEN_WORKTREE" ]]; then
    printf 'workstream provider launch is missing its admitted capsule, worktree, or session binding\n' >&2
    return 2
  fi
  export LIMEN_WORKSTREAM_PROVIDER_ACTIVE=1
  export LIMEN_WORKSTREAM_PROVIDER_CAPSULE_ID="$LIMEN_CAPSULE_ID"
  export LIMEN_WORKSTREAM_PROVIDER_WORKTREE="$LIMEN_WORKTREE"
  export LIMEN_WORKSTREAM_PROVIDER_SESSION_ID="$LIMEN_SESSION_ID"
}

workstream_publish_admitted_receipt() {
  local receipt="$1"
  local expected_branch="$2"
  local slug="$3"
  local contract_helper="${LIMEN_CAPSULE_DIR:-}/workstream-contract.py"
  local timeout_seconds="${LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}"
  local branch="" current_head="" receipt_rel="" dirty="" staged_paths="" publish_commit=""
  local topic_ref="" remote_line="" remote_head=""
  local current_subject="" changed_paths="" parent_head=""

  # Preserve backward compatibility for local-only fixture and owner-native repositories. A
  # configured remote, however, makes durable publication a hard pre-provider gate.
  if ! git remote get-url origin >/dev/null 2>&1; then
    return 0
  fi

  branch="$(git branch --show-current 2>/dev/null || true)"
  topic_ref="refs/heads/$branch"
  current_head="$(git rev-parse HEAD 2>/dev/null || true)"
  receipt_rel="${receipt#"${LIMEN_WORKTREE:-}/"}"
  if [[ -z "$branch" || "$branch" != "$expected_branch" || -z "$current_head"
    || ! -f "$contract_helper" || "$receipt_rel" == "$receipt" || ! -f "$receipt_rel" ]]; then
    printf 'workstream launch could not resolve its admitted receipt publication boundary\n' >&2
    return 2
  fi
  if ! dirty="$(git status --porcelain --untracked-files=all -- . ":(exclude)$receipt_rel" 2>/dev/null)"; then
    printf 'workstream launch could not inspect the admitted receipt worktree\n' >&2
    return 2
  fi
  if [[ -n "$dirty" ]]; then
    printf 'workstream launch requires a clean worktree before admitted receipt publication\n' >&2
    return 2
  fi

  if ! remote_line="$(
    GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
      --timeout-seconds "$timeout_seconds" -- \
      git ls-remote origin "$topic_ref"
  )"; then
    printf 'workstream launch could not resolve its remote receipt branch\n' >&2
    return 2
  fi
  if ! remote_head="$(workstream_exact_remote_ref_head "$remote_line" "$topic_ref")"; then
    printf 'workstream launch received an invalid remote receipt branch head\n' >&2
    return 2
  fi
  if [[ -n "$remote_head" && "$remote_head" != "$current_head" ]]; then
    current_subject="$(git log -1 --format=%s 2>/dev/null || true)"
    changed_paths="$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true)"
    parent_head="$(git rev-parse HEAD^ 2>/dev/null || true)"
    if [[ "$current_subject" != "docs: publish admitted $slug runway"
      || "$changed_paths" != "$receipt_rel" || "$parent_head" != "$remote_head" ]] ||
      ! git diff --quiet HEAD -- "$receipt_rel"; then
      printf 'workstream launch no longer owns its remote receipt branch\n' >&2
      return 2
    fi
  fi

  if ! git add -- "$receipt_rel"; then
    printf 'workstream admitted receipt could not be staged\n' >&2
    return 2
  fi
  staged_paths="$(git diff --cached --name-only)"
  if [[ -n "$staged_paths" ]]; then
    if [[ "$staged_paths" != "$receipt_rel" ]]; then
      printf 'workstream admitted receipt publication found unrelated staged paths\n' >&2
      return 2
    fi
    if ! git -c commit.gpgsign=false commit -qm \
      "docs: publish admitted $slug runway" -- "$receipt_rel"; then
      printf 'workstream admitted receipt could not be committed\n' >&2
      return 2
    fi
  elif ! git cat-file -e "HEAD:$receipt_rel" 2>/dev/null ||
    ! git diff --quiet HEAD -- "$receipt_rel"; then
    printf 'workstream admitted receipt is not durably committed\n' >&2
    return 2
  fi
  if ! dirty="$(git status --porcelain --untracked-files=all 2>/dev/null)" ||
    [[ -n "$dirty" ]] || ! git diff --quiet || ! git diff --cached --quiet; then
    printf 'workstream admitted receipt publication left uncommitted state\n' >&2
    return 2
  fi

  publish_commit="$(git rev-parse HEAD 2>/dev/null || true)"
  if [[ -z "$publish_commit" ]]; then
    printf 'workstream admitted receipt publication lost its exact head\n' >&2
    return 2
  fi
  if ! GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
    --timeout-seconds "$timeout_seconds" -- \
    git push --set-upstream origin "$publish_commit:$topic_ref"; then
    if ! remote_line="$(
      GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
        --timeout-seconds "$timeout_seconds" -- \
        git ls-remote origin "$topic_ref"
    )"; then
      printf 'workstream admitted receipt publication outcome is uncertain; exact topic ref is unreachable\n' >&2
      return 2
    fi
    if ! remote_head="$(workstream_exact_remote_ref_head "$remote_line" "$topic_ref")"; then
      printf 'workstream admitted receipt publication outcome is uncertain; exact topic ref is malformed\n' >&2
      return 2
    fi
    if [[ "$remote_head" != "$publish_commit" ]]; then
      printf 'workstream admitted receipt publication was confirmed absent or mismatched\n' >&2
      return 2
    fi
  fi
  printf 'admitted workstream receipt published: %s\n' "$receipt_rel"
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

workstream_write_conduct_keepalive_status() {
  local status_path="$1"
  local capsule_dir="$2"
  local session_id="$3"
  local state="$4"
  local target_pid="$5"
  local keepalive_pid="$6"
  local deadline_epoch="$7"
  local refresh_count="$8"
  local last_success_epoch="$9"
  local last_failure_epoch="${10}"
  local detail="${11}"

  python3 - "$status_path" "$capsule_dir" "$session_id" "$state" "$target_pid" \
    "$keepalive_pid" "$deadline_epoch" "$refresh_count" "$last_success_epoch" \
    "$last_failure_epoch" "$detail" <<'PY'
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

(
    raw_status,
    raw_capsule,
    session_id,
    state,
    raw_target_pid,
    raw_keepalive_pid,
    raw_deadline,
    raw_refresh_count,
    raw_last_success,
    raw_last_failure,
    detail,
) = sys.argv[1:]
status_path = Path(raw_status)
capsule_dir = Path(raw_capsule)
try:
    resolved_capsule = capsule_dir.resolve(strict=True)
    resolved_parent = status_path.parent.resolve(strict=True)
except OSError as exc:
    raise SystemExit(f"conduct keepalive status path is invalid: {exc}")
if (
    capsule_dir.is_symlink()
    or resolved_parent != resolved_capsule
    or status_path.name != "conduct-keepalive.json"
    or status_path.is_symlink()
):
    raise SystemExit("conduct keepalive status must be a real file inside the private capsule")
if state not in {"active", "refresh_failed", "stopped"}:
    raise SystemExit("conduct keepalive status has an invalid state")


def optional_epoch(raw: str) -> int | None:
    if not raw:
        return None
    value = int(raw)
    if value < 0:
        raise ValueError("epoch must be non-negative")
    return value


observed_epoch = int(datetime.now(UTC).timestamp())
payload = {
    "schema": "limen.workstream.conduct-keepalive.v1",
    "session_id": session_id,
    "state": state,
    "target_pid": int(raw_target_pid),
    "keepalive_pid": int(raw_keepalive_pid),
    "deadline_epoch": int(raw_deadline),
    "refresh_count": int(raw_refresh_count),
    "last_success_epoch": optional_epoch(raw_last_success),
    "last_failure_epoch": optional_epoch(raw_last_failure),
    "observed_epoch": observed_epoch,
    "observed_at": datetime.fromtimestamp(observed_epoch, UTC).isoformat().replace("+00:00", "Z"),
    "detail": detail[:512],
}
temporary = status_path.with_name(f".{status_path.name}.tmp.{os.getpid()}")
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, status_path)
    os.chmod(status_path, 0o600)
finally:
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY
}

workstream_conduct_target_is_live() {
  local target_pid="$1"
  local target_started="$2"
  local observed_started=""

  if ! kill -0 "$target_pid" 2>/dev/null; then
    return 1
  fi
  observed_started="$(ps -o lstart= -p "$target_pid" 2>/dev/null || true)"
  [[ -n "$observed_started" && "$observed_started" == "$target_started" ]]
}

workstream_conduct_keepalive_is_ready() {
  local status_path="$1"
  local session_id="$2"
  local target_pid="$3"
  local keepalive_pid="$4"
  local minimum_observed_epoch="$5"

  python3 - "$status_path" "$session_id" "$target_pid" "$keepalive_pid" \
    "$minimum_observed_epoch" <<'PY'
import json
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
if status_path.is_symlink():
    raise SystemExit(1)
try:
    payload = json.loads(status_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
expected = {
    "schema": "limen.workstream.conduct-keepalive.v1",
    "session_id": sys.argv[2],
    "target_pid": int(sys.argv[3]),
    "keepalive_pid": int(sys.argv[4]),
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
if payload.get("state") not in {"active", "refresh_failed"}:
    raise SystemExit(1)
if payload.get("observed_epoch", -1) < int(sys.argv[5]):
    raise SystemExit(1)
PY
}

workstream_existing_active_session() {
  local capsule_dir="$1"
  local status_path="$capsule_dir/conduct-keepalive.json"
  local record=""
  local session_id=""
  local target_pid=""
  local keepalive_pid=""

  if [[ ! -d "$capsule_dir" || -L "$capsule_dir" || ! -f "$status_path" || -L "$status_path" ]]; then
    return 1
  fi
  if ! record="$(python3 - "$capsule_dir" "$status_path" "$(date +%s)" <<'PY'
import json
import re
import stat
import sys
from pathlib import Path

capsule_dir = Path(sys.argv[1])
status_path = Path(sys.argv[2])
now = int(sys.argv[3])
try:
    capsule = capsule_dir.resolve(strict=True)
    resolved_status = status_path.resolve(strict=True)
    info = status_path.lstat()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
if (
    capsule_dir.is_symlink()
    or status_path.is_symlink()
    or not stat.S_ISREG(info.st_mode)
    or resolved_status.parent != capsule
    or resolved_status.name != "conduct-keepalive.json"
    or not isinstance(payload, dict)
    or payload.get("schema") != "limen.workstream.conduct-keepalive.v1"
    or payload.get("state") != "active"
):
    raise SystemExit(1)
session_id = payload.get("session_id")
if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", session_id):
    raise SystemExit(1)
for key in ("target_pid", "keepalive_pid", "deadline_epoch", "observed_epoch"):
    if type(payload.get(key)) is not int:
        raise SystemExit(1)
if (
    payload["target_pid"] <= 0
    or payload["keepalive_pid"] <= 0
    or payload["deadline_epoch"] <= now
    or payload["observed_epoch"] > now
    or now - payload["observed_epoch"] > 360
):
    raise SystemExit(1)
print(f"{session_id}\t{payload['target_pid']}\t{payload['keepalive_pid']}")
PY
)"; then
    return 1
  fi
  IFS=$'\t' read -r session_id target_pid keepalive_pid <<< "$record"
  if ! kill -0 "$target_pid" 2>/dev/null || ! kill -0 "$keepalive_pid" 2>/dev/null; then
    return 1
  fi
  printf '%s\n' "$session_id"
}

workstream_conduct_keepalive_loop() {
  local agent="$1"
  local wt="$2"
  local capabilities="$3"
  local target_pid="$4"
  local target_started="$5"
  local deadline_epoch="$6"
  local status_path="$7"
  local capsule_dir="$8"
  local interval_seconds="$9"
  local retry_seconds="${10}"
  local poll_seconds="${11}"
  local limen_binary="${12}"
  local conduct_token="${13}"
  local capability
  local capability_args=()
  local keepalive_pid
  local now_epoch next_refresh refresh_count=1
  local last_success_epoch last_failure_epoch=""
  local register_rc=0 detail="initial registration passed"

  trap 'exit 0' HUP INT TERM
  # Apple's Bash 3.2 does not expose BASHPID. A direct child reports this
  # background subshell as its PPID, which is the exact PID returned by $!.
  keepalive_pid="$(/bin/sh -c 'printf "%s\n" "$PPID"')"
  case "$keepalive_pid" in
    ""|*[!0-9]*) return 2 ;;
  esac
  for capability in $capabilities; do
    capability_args+=(--capability "$capability")
  done
  now_epoch="$(date +%s)"
  last_success_epoch="$now_epoch"
  next_refresh=$((now_epoch + interval_seconds))
  workstream_write_conduct_keepalive_status \
    "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" active "$target_pid" "$keepalive_pid" \
    "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
  while workstream_conduct_target_is_live "$target_pid" "$target_started"; do
    now_epoch="$(date +%s)"
    if (( now_epoch >= deadline_epoch )); then
      detail="capsule deadline reached"
      break
    fi
    if (( now_epoch < next_refresh )); then
      sleep "$poll_seconds"
      continue
    fi
    register_rc=0
    LIMEN_CONDUCT_TOKEN="$conduct_token" "$limen_binary" conduct register \
      --agent "$agent" \
      --surface workstream \
      --session-id "$LIMEN_SESSION_ID" \
      --origin direct \
      "${capability_args[@]}" \
      --worktree "$wt" \
      --human-protected \
      --concurrency 1 >/dev/null 2>&1 || register_rc=$?
    now_epoch="$(date +%s)"
    if [[ "$register_rc" -eq 0 ]]; then
      refresh_count=$((refresh_count + 1))
      last_success_epoch="$now_epoch"
      detail="protected session refreshed"
      next_refresh=$((now_epoch + interval_seconds))
      workstream_write_conduct_keepalive_status \
        "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" active "$target_pid" "$keepalive_pid" \
        "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
    else
      last_failure_epoch="$now_epoch"
      detail="conduct registration refresh failed with exit $register_rc"
      next_refresh=$((now_epoch + retry_seconds))
      workstream_write_conduct_keepalive_status \
        "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" refresh_failed "$target_pid" "$keepalive_pid" \
        "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
    fi
  done
  if [[ "$detail" != "capsule deadline reached" ]]; then
    detail="provider process exited or changed identity"
  fi
  workstream_write_conduct_keepalive_status \
    "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" stopped "$target_pid" "$keepalive_pid" \
    "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
}

workstream_start_conduct_keepalive() {
  local agent="$1"
  local wt="$2"
  local capabilities="$3"
  local target_pid="$4"
  local deadline_epoch="$5"
  local capsule_dir="$6"
  local limen_binary="${LIMEN_CLI_BIN:-limen}"
  local interval_seconds="${LIMEN_CONDUCT_KEEPALIVE_SECONDS:-180}"
  local retry_seconds="${LIMEN_CONDUCT_KEEPALIVE_RETRY_SECONDS:-30}"
  local poll_seconds="${LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS:-5}"
  local status_path="$capsule_dir/conduct-keepalive.json"
  local target_started=""
  local launched_epoch=""
  local ready=0
  local attempt

  for value in "$target_pid" "$deadline_epoch" "$interval_seconds" "$retry_seconds" "$poll_seconds"; do
    case "$value" in
      ""|*[!0-9]*)
        printf 'invalid conduct keepalive numeric contract\n' >&2
        return 2
        ;;
    esac
  done
  if (( interval_seconds < 1 || interval_seconds > 240
    || retry_seconds < 1 || retry_seconds > 60
    || poll_seconds < 1 || poll_seconds > 30
    || deadline_epoch <= $(date +%s) )); then
    printf 'conduct keepalive interval, retry, poll, or deadline is out of bounds\n' >&2
    return 2
  fi
  target_started="$(ps -o lstart= -p "$target_pid" 2>/dev/null || true)"
  if [[ -z "$target_started" ]]; then
    printf 'conduct keepalive could not bind the provider process identity\n' >&2
    return 2
  fi
  launched_epoch="$(date +%s)"
  (
    exec 9>&-
    workstream_conduct_keepalive_loop \
      "$agent" "$wt" "$capabilities" "$target_pid" "$target_started" "$deadline_epoch" \
      "$status_path" "$capsule_dir" "$interval_seconds" "$retry_seconds" "$poll_seconds" \
      "$limen_binary" "${workstream_conduct_token:-}"
  ) </dev/null >/dev/null 2>&1 &
  workstream_conduct_keepalive_pid=$!
  unset workstream_conduct_token
  for ((attempt = 0; attempt < 50; attempt++)); do
    if ! kill -0 "$workstream_conduct_keepalive_pid" 2>/dev/null; then
      break
    fi
    if workstream_conduct_keepalive_is_ready \
      "$status_path" "$LIMEN_SESSION_ID" "$target_pid" \
      "$workstream_conduct_keepalive_pid" "$launched_epoch"; then
      ready=1
      break
    fi
    sleep 0.1
  done
  if [[ "$ready" -ne 1 ]]; then
    kill "$workstream_conduct_keepalive_pid" 2>/dev/null || true
    wait "$workstream_conduct_keepalive_pid" 2>/dev/null || true
    printf 'conduct keepalive did not acknowledge a live protected-session channel\n' >&2
    return 2
  fi
  export LIMEN_CONDUCT_KEEPALIVE_PID="$workstream_conduct_keepalive_pid"
  printf 'started protected conduct keepalive: %s\n' "$workstream_conduct_keepalive_pid"
}

workstream_register_conduct_session() {
  local agent="$1"
  local wt="$2"
  local capabilities="$3"
  local limen_binary="${LIMEN_CLI_BIN:-limen}"
  local register_rc=0
  local register_output=""
  local capability
  local capability_args=()

  unset LIMEN_WORKSTREAM_ALREADY_RUNNING
  workstream_conduct_token="${LIMEN_CONDUCT_TOKEN:-}"
  if ! command -v "$limen_binary" >/dev/null 2>&1; then
    unset workstream_conduct_token
    unset LIMEN_CONDUCT_TOKEN
    printf 'conduct registration requires the limen CLI (set LIMEN_CLI_BIN to its path)\n' >&2
    return 127
  fi

  for capability in $capabilities; do
    capability_args+=(--capability "$capability")
  done

  if register_output="$("$limen_binary" conduct register \
    --agent "$agent" \
    --surface workstream \
    --session-id "$LIMEN_SESSION_ID" \
    --origin direct \
    "${capability_args[@]}" \
    --worktree "$wt" \
    --human-protected \
    --concurrency 1 2>&1)"; then
    :
  else
    register_rc=$?
  fi
  # The broker client consumes its credential; the native model process must not inherit it.
  unset LIMEN_CONDUCT_TOKEN
  if [[ "$register_rc" -ne 0 ]]; then
    unset workstream_conduct_token
    if [[ "$register_output" == *"worktree is already owned by healthy session"* ]]; then
      export LIMEN_WORKSTREAM_ALREADY_RUNNING=1
      printf 'This workstream is already running. Continue in its existing session; no second process was started.\n'
      return 0
    fi
    if [[ -n "$register_output" ]]; then
      printf '%s\n' "$register_output" >&2
    fi
    return "$register_rc"
  fi
  export LIMEN_HUMAN_PROTECTED=1
  printf 'registered protected conduct session: %s (%s)\n' "$LIMEN_SESSION_ID" "$agent"
}

workstream_hydrate_conduct_environment() {
  local cache="${LIMEN_CONDUCT_ENV_FILE:-$HOME/.limen.env}"
  local hydrated=""

  if [[ -n "${LIMEN_CONDUCT_URL:-}" && -n "${LIMEN_CONDUCT_TOKEN:-}" ]]; then
    return 0
  fi
  if [[ ! -e "$cache" ]]; then
    return 0
  fi
  # This function is serialized into kickstart.sh with `declare -f`. Bash 5 indents a
  # here-document delimiter while printing a function, which turns the following shell body into
  # Python stdin on Linux. Keep the ownership predicate in `-c` so serialization is byte-stable
  # across the macOS Bash 3.2 renderer and GitHub's Bash 5 runtime.
  if ! python3 -c '
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    info = path.lstat()
except OSError:
    raise SystemExit(1)
if path.is_symlink() or not stat.S_ISREG(info.st_mode):
    raise SystemExit(1)
if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
    raise SystemExit(1)
' "$cache"; then
    printf 'conduct environment cache must be a user-owned mode-600 regular file: %s\n' "$cache" >&2
    return 2
  fi
  if ! hydrated="$(
    bash -c '
      set -a
      . "$1" >/dev/null
      set +a
      [[ -n "${LIMEN_CONDUCT_URL:-}" && -n "${LIMEN_CONDUCT_TOKEN:-}" ]] || exit 2
      printf "export LIMEN_CONDUCT_URL=%q\nexport LIMEN_CONDUCT_TOKEN=%q\n" \
        "$LIMEN_CONDUCT_URL" "$LIMEN_CONDUCT_TOKEN"
    ' _ "$cache"
  )"; then
    printf 'conduct environment cache does not define LIMEN_CONDUCT_URL and LIMEN_CONDUCT_TOKEN\n' >&2
    return 2
  fi
  eval "$hydrated"
  unset hydrated
}

workstream_launch_native_agent() {
  local agent="$1"
  local registry_binary="$2"
  local autonomous="$3"
  local readme="$4"
  local allow_shell_fallback="$5"
  local launch_model="${6:-}"
  local launch_reasoning_effort="${7:-}"
  local launch_sandbox="${8:-}"
  local launch_contract_helper="${9:-}"
  # Positional and defaulted, so a capsule rendered before the lane pin existed still calls this
  # with nine arguments and behaves exactly as it did.
  local launch_lane_model="${10:-}"
  local launch_adapter="${11:-}"
  local model_flag="${12:-}"
  local -a lane_args=()
  local binary capsule_prompt="" jules_repo="" intent_path=""
  local contract_helper="" timeout_seconds=""
  local provider_instruction="This session is already admitted; read the modules and continue. Do not execute the operator launch command."
  local jules_output="" jules_rc=0 jules_session_id="" jules_session_url="" jules_receipt=""
  local jules_reserved_this_launch=0
  local -a codex_args=()

  # Provider IDs are mutable registry data. Older generated capsules called this helper with ten
  # arguments, so retain their historical mapping only as a compatibility fallback; current
  # capsules carry the stable invocation adapter and model-flag capability from the registry.
  if [[ -z "$launch_adapter" ]]; then
    case "$agent" in
      codex|jules) launch_adapter="$agent" ;;
      opencode) launch_adapter="prompt-flag" ;;
      agy|gemini) launch_adapter="prompt-interactive" ;;
      *) launch_adapter="positional" ;;
    esac
  fi
  if [[ -z "$model_flag" ]]; then
    case "$agent" in
      claude|gemini|agy|opencode) model_flag=1 ;;
      *) model_flag=0 ;;
    esac
  fi
  case "$launch_adapter" in
    codex|jules|positional|prompt-flag|prompt-interactive) ;;
    *)
      printf 'workstream launch adapter is unsupported for registry lane %s\n' "$agent" >&2
      return 2
      ;;
  esac
  case "$model_flag" in
    0|1) ;;
    *)
      printf 'workstream model-flag contract is invalid for registry lane %s\n' "$agent" >&2
      return 2
      ;;
  esac

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

  if [[ -n "$launch_model" || -n "$launch_reasoning_effort" || -n "$launch_sandbox" ]]; then
    if [[ "$launch_adapter" != "codex" || -z "$launch_model" || -z "$launch_reasoning_effort" \
      || -z "$launch_sandbox" || ! -f "$launch_contract_helper" ]]; then
      printf 'invalid explicit native launch profile\n' >&2
      return 2
    fi
    if ! python3 "$launch_contract_helper" validate-codex-launch \
      --binary "$binary" \
      --model "$launch_model" \
      --reasoning-effort "$launch_reasoning_effort" \
      --sandbox "$launch_sandbox" >/dev/null; then
      return 2
    fi
    codex_args=(
      --model "$launch_model"
      --config "model_reasoning_effort=\"$launch_reasoning_effort\""
      --ask-for-approval never
      --sandbox "$launch_sandbox"
    )
  else
    codex_args=(--ask-for-approval never --sandbox workspace-write)
  fi

  # ── lane tier pin ────────────────────────────────────────────────────────────
  # A bare `--model` for a NON-Codex lane. Codex keeps its own validated triple above and is
  # rejected here on purpose, so there stays exactly one way to launch Codex explicitly.
  #
  # The allowlist is lanes whose `--model <value>` form was verified against the installed CLI's
  # own --help (2026-07-29):
  #   claude    "--model <model>            Model for the current session"
  #   gemini    "-m, --model                Model  [string]"
  #   agy       "--model                    Model for the current CLI session"
  #   opencode  "-m, --model                model to use in the format of provider/model"
  # opencode takes a provider-qualified value; the operator owns the string, this only proves the
  # flag exists. Any lane not listed REFUSES the pin rather than dropping it — a silently ignored
  # pin is precisely the defect this closes (the lane would run on the inherited default and look
  # pinned).
  if [[ -n "$launch_lane_model" ]]; then
    if [[ "$launch_adapter" == "codex" ]]; then
        printf 'lane tier pin refused: the codex lane requires the validated --model/--reasoning-effort/--sandbox profile, not a bare pin\n' >&2
        return 2
    elif [[ "$model_flag" != "1" ]]; then
      printf 'lane tier pin refused: lane %s has no verified --model flag form; remove the pin or extend its registry profile\n' "$agent" >&2
      return 2
    fi
    lane_args=(--model "$launch_lane_model")
  fi

  workstream_mark_provider_active || return $?

  if [[ "$autonomous" -eq 1 ]]; then
    IFS= read -r -d '' capsule_prompt < "$readme" || true
    capsule_prompt="$provider_instruction

$capsule_prompt"
    case "$launch_adapter" in
      codex)
        if [[ -t 0 && -t 1 ]]; then
          exec "$binary" "${codex_args[@]}" "$capsule_prompt"
        fi
        # Shell runners do not provide a terminal; use Codex's noninteractive transport.
        exec "$binary" "${codex_args[@]}" exec "$capsule_prompt"
        ;;
      prompt-flag)
        exec "$binary" "${lane_args[@]+"${lane_args[@]}"}" --prompt "$capsule_prompt"
        ;;
      prompt-interactive)
        exec "$binary" "${lane_args[@]+"${lane_args[@]}"}" --prompt-interactive "$capsule_prompt"
        ;;
      jules)
        if ! jules_repo="$(workstream_jules_repository)"; then
          printf 'Jules workstream launch could not derive an owner/repo from the GitHub origin\n' >&2
          return 2
        fi
        if workstream_jules_validate_default_base; then
          :
        else
          return $?
        fi
        jules_rc=0
        workstream_jules_validate_clean_worktree || jules_rc=$?
        if [[ "$jules_rc" -ne 0 ]]; then
          return "$jules_rc"
        fi
        intent_path="${readme%/*}/intent.md"
        if [[ ! -s "$intent_path" ]]; then
          printf 'Jules workstream launch requires a non-empty intent module\n' >&2
          return 2
        fi
        IFS= read -r -d '' capsule_prompt < "$intent_path" || true
        capsule_prompt="$provider_instruction

Do NOT ask for feedback or approval. Work autonomously and return the requested durable receipts. $capsule_prompt"
        # The pre-session push is the durable recovery capsule. Preserve it if a later provider
        # step fails; deleting it after Jules may have started would orphan the cloud run.
        if [[ "${workstream_jules_reuse_reservation:-0}" != "1" ]]; then
          workstream_jules_reserve_receipt_branch || jules_rc=$?
          if [[ "$jules_rc" -ne 0 ]]; then
            return "$jules_rc"
          fi
          jules_reserved_this_launch=1
        fi
        jules_rc=0
        workstream_jules_validate_default_base || jules_rc=$?
        if [[ "$jules_rc" -ne 0 ]]; then
          return "$jules_rc"
        fi
        if [[ "${workstream_jules_reuse_reservation:-0}" == "1"
          && "$jules_reserved_this_launch" != "1" ]]; then
          printf 'unbound Jules launch reservation requires recovery: bind the existing numeric session receipt before relaunch; refusing a duplicate remote session\n' >&2
          return 2
        fi
        contract_helper="${LIMEN_CAPSULE_DIR:-}/workstream-contract.py"
        timeout_seconds="${LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}"
        jules_rc=0
        jules_output="$(python3 "$contract_helper" run-bounded \
          --timeout-seconds "$timeout_seconds" -- \
          "$binary" remote new --repo "$jules_repo" --session "$capsule_prompt" 2>&1)" || jules_rc=$?
        printf '%s\n' "$jules_output"
        jules_session_id="$(printf '%s\n' "$jules_output" | sed -n 's/^ID:[[:space:]]*//p' | tr -d '\r' | tail -n 1)"
        jules_session_url="$(printf '%s\n' "$jules_output" | sed -n 's/^URL:[[:space:]]*//p' | tr -d '\r' | tail -n 1)"
        jules_receipt="${LIMEN_WORKTREE:-}/docs/continuations/${LIMEN_CAPSULE_ID:-}/workstream.json"
        if [[ "$jules_session_id" =~ ^[0-9]+$
          && "$jules_session_url" == "https://jules.google.com/session/$jules_session_id" ]]; then
          if ! workstream_jules_sync_receipt \
            "$jules_receipt" "$jules_session_id" "$jules_session_url" "$agent"; then
            printf 'Jules workstream launch could not bind the session to its receipt\n' >&2
            return 2
          fi
          if declare -F validate_capsule_receipt >/dev/null && ! validate_capsule_receipt; then
            return 2
          fi
          if ! workstream_jules_publish_receipt "$jules_receipt" "$jules_session_id"; then
            printf 'Jules workstream launch created a session but could not publish its receipt\n' >&2
            return 2
          fi
          printf 'Jules session receipt: %s\n' "$jules_receipt"
          if [[ "$jules_rc" -ne 0 ]]; then
            printf 'Jules returned nonzero after emitting a durable session receipt\n' >&2
            return "$jules_rc"
          fi
          return 0
        fi
        if [[ "$jules_rc" -ne 0 ]]; then
          return "$jules_rc"
        fi
        printf 'Jules workstream launch did not emit a valid session ID and URL\n' >&2
        return 2
        ;;
      *)
        exec "$binary" "${lane_args[@]+"${lane_args[@]}"}" "$capsule_prompt"
        ;;
    esac
  fi

  case "$launch_adapter" in
    codex)
      exec "$binary" "${codex_args[@]}"
      ;;
    prompt-interactive)
      # Prompt-interactive adapters have no argument-free workstream session.
      if [[ -s "$readme" ]]; then
        IFS= read -r -d '' capsule_prompt < "$readme" || true
        capsule_prompt="$provider_instruction

$capsule_prompt"
        exec "$binary" "${lane_args[@]+"${lane_args[@]}"}" --prompt-interactive "$capsule_prompt"
      fi
      ;;
  esac
  exec "$binary" "${lane_args[@]+"${lane_args[@]}"}"
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
import re
import sys
from pathlib import Path

contract_path, receipt_path, slug, branch, workstream = sys.argv[1:6]
predecessor_slug, predecessor_branch, predecessor_digest = (sys.argv[6:9] + ["", "", ""])[:3]
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
if predecessor_slug or predecessor_branch or predecessor_digest:
    if (
        not predecessor_slug
        or not predecessor_branch
        or not re.fullmatch(r"[0-9a-f]{64}", predecessor_digest)
    ):
        raise SystemExit("invalid capsule receipt: predecessor lineage is incomplete")
    expected["predecessor"] = {
        "slug": predecessor_slug,
        "branch": predecessor_branch,
        "receipt_sha256": predecessor_digest,
    }
provider_run = receipt.get("provider_run")
if provider_run is not None:
    if not isinstance(provider_run, dict):
        raise SystemExit("invalid capsule receipt: provider run must be an object")
    run_id = provider_run.get("id")
    expected_url = f"https://jules.google.com/session/{run_id}"
    provider = provider_run.get("provider")
    if (
        not isinstance(provider, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", provider)
        or provider_run != {"provider": provider, "id": run_id, "url": expected_url}
        or not isinstance(run_id, str)
        or not run_id.isdigit()
    ):
        raise SystemExit("invalid capsule receipt: provider run identity mismatch")
    expected["provider_run"] = provider_run
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
  local launch_model="${17:-}"
  local launch_reasoning_effort="${18:-}"
  local launch_sandbox="${19:-}"
  # The lane tier pin is DELIBERATELY a separate variable from launch_model. launch_model being
  # non-empty is what triggers the v2 Codex contract build below, and a v2 contract requires a
  # reasoning effort and a sandbox; reusing it for a bare pin raises ContractError at render.
  local launch_lane_model="${20:-}"
  local launch_adapter="${21:-}"
  local model_flag="${22:-}"
  local predecessor_receipt="${23:-}"
  local runway_mode="${24:-inherit}"
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
  local actual_branch effective_runway input_digest identity_action successor_metadata successor_runway
  local predecessor_slug="" predecessor_branch="" predecessor_receipt_sha256="" predecessor_head=""
  local runtime_source_digest closeout_source_digest contract_source_digest capsule_real wt_real lock_status
  local q_wt q_capsule_dir q_capsule_lock q_receipt q_identity q_readme q_manifest q_contract q_contract_helper
  local q_intent q_runtime q_closeout q_kickstart q_slug q_branch q_workstream q_input_digest
  local q_agent q_registry_binary q_conduct q_allow_shell_fallback q_agent_capabilities
  local q_launch_model q_launch_reasoning_effort q_launch_sandbox q_launch_lane_model
  local q_launch_adapter q_model_flag q_predecessor_slug q_predecessor_branch q_predecessor_receipt_sha256
  local -a contract_launch_args=() successor_configure_args=()
  local capsule_preexisting=0
  local capsule_changed=0

  if [[ -z "$launch_adapter" ]]; then
    case "$agent" in
      codex|jules) launch_adapter="$agent" ;;
      opencode) launch_adapter="prompt-flag" ;;
      agy|gemini) launch_adapter="prompt-interactive" ;;
      *) launch_adapter="positional" ;;
    esac
  fi
  if [[ -z "$model_flag" ]]; then
    case "$agent" in
      claude|gemini|agy|opencode) model_flag=1 ;;
      *) model_flag=0 ;;
    esac
  fi

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

  if [[ -n "$predecessor_receipt" ]]; then
    local -a successor_metadata_args=(
      successor-metadata
      --predecessor-receipt "$predecessor_receipt"
      --runway-mode "$runway_mode"
    )
    if [[ "$runway_mode" == "renew" ]]; then
      successor_metadata_args+=(--runway "$runway_requested")
    fi
    successor_metadata="$(
      python3 "$contract_source" "${successor_metadata_args[@]}" 9>&-
    )" || exit 1
    predecessor_slug="$(printf '%s\n' "$successor_metadata" | sed -n '1p')"
    predecessor_branch="$(printf '%s\n' "$successor_metadata" | sed -n '2p')"
    predecessor_receipt_sha256="$(printf '%s\n' "$successor_metadata" | sed -n '3p')"
    successor_runway="$(printf '%s\n' "$successor_metadata" | sed -n '4p')"
    predecessor_head="$(printf '%s\n' "$successor_metadata" | sed -n '5p')"
    if [[ -z "$predecessor_slug" || -z "$predecessor_branch" \
      || ! "$predecessor_receipt_sha256" =~ ^[0-9a-f]{64}$ || -z "$successor_runway" \
      || ! "$predecessor_head" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]; then
      echo "invalid predecessor successor metadata" >&2
      exit 1
    fi
    if [[ "$from_ref" != "$predecessor_head" ]]; then
      echo "successor base does not match the exact predecessor HEAD" >&2
      exit 1
    fi
  fi

  effective_runway="$runway_requested"
  if [[ -n "$predecessor_receipt" ]]; then
    effective_runway="$successor_runway"
  elif [[ -z "$effective_runway" && "$capsule_preexisting" -eq 1 ]]; then
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
  # CONDITIONAL ON PURPOSE. An unconditional new digest field would change the recomputed
  # invocation digest of every capsule already on disk, and the pre-existing-capsule path below
  # runs `verify-identity` against the stored one and exits 1 on mismatch — that would brick every
  # live capsule on its next render. Appending only when a pin is actually set leaves the unpinned
  # digest byte-identical to what it has always been, while still binding a pin to the identity.
  local -a lane_pin_digest_field=()
  if [[ -n "$launch_lane_model" ]]; then
    lane_pin_digest_field=("launch-lane-model=$launch_lane_model")
  fi
  local legacy_launch_adapter="positional" legacy_model_flag="0"
  case "$agent" in
    codex|jules) legacy_launch_adapter="$agent" ;;
    opencode) legacy_launch_adapter="prompt-flag" ;;
    agy|gemini) legacy_launch_adapter="prompt-interactive" ;;
  esac
  case "$agent" in
    claude|gemini|agy|opencode) legacy_model_flag="1" ;;
  esac
  local -a registry_profile_digest_fields=()
  if [[ "$launch_adapter" != "$legacy_launch_adapter" || "$model_flag" != "$legacy_model_flag" ]]; then
    registry_profile_digest_fields=(
      "launch-adapter=$launch_adapter"
      "model-flag=$model_flag"
    )
  fi
  local -a predecessor_digest_fields=()
  if [[ -n "$predecessor_receipt" ]]; then
    predecessor_digest_fields=(
      "predecessor-slug=$predecessor_slug"
      "predecessor-branch=$predecessor_branch"
      "predecessor-receipt-sha256=$predecessor_receipt_sha256"
      "runway-mode=$runway_mode"
    )
  fi
  input_digest="$(
    _limen_capsule_input_digest \
      "limen.workstream.capsule-identity.v2" \
      "$repo" "$wt" "$slug" "$branch" "$workstream" "$from_ref" \
      "$autonomous" "$effective_runway" "$prompt_payload" \
      "agent=$agent" "registry-binary=$registry_binary" "conduct=$conduct" \
      "allow-shell-fallback=$allow_shell_fallback" "agent-capabilities=$agent_capabilities" \
      "launch-model=$launch_model" "launch-reasoning-effort=$launch_reasoning_effort" \
      "launch-sandbox=$launch_sandbox" \
      "runtime-source-sha256=$runtime_source_digest" \
      "closeout-source-sha256=$closeout_source_digest" \
      "contract-source-sha256=$contract_source_digest" \
      "${lane_pin_digest_field[@]+"${lane_pin_digest_field[@]}"}" \
      "${registry_profile_digest_fields[@]+"${registry_profile_digest_fields[@]}"}" \
      "${predecessor_digest_fields[@]+"${predecessor_digest_fields[@]}"}"
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
    if ! _limen_capsule_validate_receipt \
      "$contract" "$receipt" "$slug" "$branch" "$workstream" \
      "$predecessor_slug" "$predecessor_branch" "$predecessor_receipt_sha256"; then
      echo "invalid existing capsule receipt; emit a successor capsule" >&2
      exit 1
    fi
    echo "capsule index: $readme (unchanged)"
    echo "capsule modules: $manifest $contract $intent $runtime $closeout"
    echo "capsule receipt: $receipt"
    echo "kickstart command: bash $kickstart"
    exit 0
  fi

  if [[ -n "$launch_model" ]]; then
    contract_launch_args=(
      --agent "$launch_adapter"
      --model "$launch_model"
      --reasoning-effort "$launch_reasoning_effort"
      --sandbox "$launch_sandbox"
    )
  fi
  # A successor performs its second, authoritative custody validation before any capsule module
  # is written. If the predecessor or origin changes after successor-metadata, configure-successor
  # fails with only the empty capsule root and its owned lock left behind, so an exact retry can
  # reuse the worktree instead of inheriting a stranded partial capsule.
  if [[ -n "$predecessor_receipt" ]]; then
    successor_configure_args=(
      configure-successor
      --path "$contract"
      --predecessor-receipt "$predecessor_receipt"
      --runway-mode "$runway_mode"
      --expected-receipt-sha256 "$predecessor_receipt_sha256"
    )
    if [[ "$runway_mode" == "renew" ]]; then
      successor_configure_args+=(--runway "$runway_requested")
    fi
    contract_action="$(
      python3 "$contract_source" "${successor_configure_args[@]}" 9>&- | sed -n '1p'
    )" || exit 1
    if [[ "$contract_action" == "changed" || "$contract_action" == "unchanged" ]]; then
      [[ "$contract_action" == "changed" ]] && capsule_changed=1
    else
      echo "invalid workstream contract helper response: $contract_action" >&2
      exit 1
    fi
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
      workstream_jules_repository \
      workstream_jules_validate_default_base \
      workstream_jules_validate_clean_worktree \
      workstream_jules_provider_run_id \
      workstream_jules_reserve_receipt_branch \
      workstream_jules_sync_receipt \
      workstream_jules_publish_receipt \
      workstream_exact_remote_ref_head \
      workstream_validate_launch_environment \
      workstream_publish_admitted_receipt \
      workstream_export_context \
      workstream_mark_provider_active \
      workstream_write_conduct_keepalive_status \
      workstream_conduct_target_is_live \
      workstream_conduct_keepalive_is_ready \
      workstream_conduct_keepalive_loop \
      workstream_start_conduct_keepalive \
      workstream_hydrate_conduct_environment \
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
- Primary model: \`${launch_model:-${launch_lane_model:-provider-auto}}\`
- Primary reasoning effort: \`${launch_reasoning_effort:-provider-auto}\`
- Primary sandbox: \`${launch_sandbox:-workspace-write}\`
- Conduct: \`$([[ "$conduct" -eq 1 ]] && printf yes || printf no)\`

This is a historical snapshot. The runtime module requires fresh probes before action.
EOF
  fi
  _capsule_write_module "$contract_helper" < "$contract_source"
  if [[ ! -x "$contract_helper" ]]; then
    chmod +x "$contract_helper"
    capsule_changed=1
  fi
  if [[ -z "$predecessor_receipt" ]]; then
    if [[ -n "$runway_requested" ]]; then
      contract_action="$(
        python3 "$contract_helper" configure --path "$contract" --runway "$runway_requested" \
          "${contract_launch_args[@]+"${contract_launch_args[@]}"}" 9>&-
      )" || exit 1
    else
      contract_action="$(
        python3 "$contract_helper" configure --path "$contract" \
          "${contract_launch_args[@]+"${contract_launch_args[@]}"}" 9>&-
      )" || exit 1
    fi
    if [[ "$contract_action" == "changed" || "$contract_action" == "unchanged" ]]; then
      [[ "$contract_action" == "changed" ]] && capsule_changed=1
    else
      echo "invalid workstream contract helper response: $contract_action" >&2
      exit 1
    fi
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

## Host-shell-only launch command

Run this command exactly once from the host shell. A provider launched by it is already admitted
and must continue from the modules above without executing this operator command.

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
  printf -v q_launch_model '%q' "$launch_model"
  printf -v q_launch_reasoning_effort '%q' "$launch_reasoning_effort"
  printf -v q_launch_sandbox '%q' "$launch_sandbox"
  printf -v q_launch_lane_model '%q' "$launch_lane_model"
  printf -v q_launch_adapter '%q' "$launch_adapter"
  printf -v q_model_flag '%q' "$model_flag"
  printf -v q_predecessor_slug '%q' "$predecessor_slug"
  printf -v q_predecessor_branch '%q' "$predecessor_branch"
  printf -v q_predecessor_receipt_sha256 '%q' "$predecessor_receipt_sha256"
  _capsule_write_module "$kickstart" <<EOF
#!/usr/bin/env bash
set -euo pipefail
$launch_helpers

expected_worktree=$q_wt
expected_slug=$q_slug
expected_branch=$q_branch
expected_workstream=$q_workstream
expected_predecessor_slug=$q_predecessor_slug
expected_predecessor_branch=$q_predecessor_branch
expected_predecessor_receipt_sha256=$q_predecessor_receipt_sha256
if [[ "\${LIMEN_WORKSTREAM_PROVIDER_ACTIVE:-}" == "1"
  && -n "\${LIMEN_WORKSTREAM_PROVIDER_SESSION_ID:-}"
  && "\${LIMEN_WORKSTREAM_PROVIDER_CAPSULE_ID:-}" == "\$expected_slug"
  && "\${LIMEN_WORKSTREAM_PROVIDER_WORKTREE:-}" == "\$expected_worktree"
  && "\${LIMEN_WORKSTREAM_PROVIDER_SESSION_ID:-}" == "\${LIMEN_SESSION_ID:-}"
  && "\${LIMEN_CAPSULE_ID:-}" == "\$expected_slug"
  && "\${LIMEN_WORKTREE:-}" == "\$expected_worktree" ]]; then
  printf 'This session is already admitted; continue directly without launching another provider.\n'
  exit 0
fi
cd "\$expected_worktree"
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
expected_invocation_sha256=$q_input_digest
agent=$q_agent
registry_binary=$q_registry_binary
conduct=$q_conduct
allow_shell_fallback=$q_allow_shell_fallback
agent_capabilities=$q_agent_capabilities
launch_model=$q_launch_model
launch_reasoning_effort=$q_launch_reasoning_effort
launch_sandbox=$q_launch_sandbox
launch_lane_model=$q_launch_lane_model
launch_adapter=$q_launch_adapter
model_flag=$q_model_flag
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
  python3 - "\$contract" "\$receipt" "\$expected_slug" "\$expected_branch" "\$expected_workstream" \
    "\$expected_predecessor_slug" "\$expected_predecessor_branch" \
    "\$expected_predecessor_receipt_sha256" "\$agent" 9>&- <<'PY'
import json
import re
import sys
from pathlib import Path

(
    contract_path,
    receipt_path,
    slug,
    branch,
    workstream,
    predecessor_slug,
    predecessor_branch,
    predecessor_digest,
    expected_provider,
) = sys.argv[1:]
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
if predecessor_slug or predecessor_branch or predecessor_digest:
    if (
        not predecessor_slug
        or not predecessor_branch
        or not re.fullmatch(r"[0-9a-f]{64}", predecessor_digest)
    ):
        raise SystemExit("invalid capsule receipt: predecessor lineage is incomplete")
    expected["predecessor"] = {
        "slug": predecessor_slug,
        "branch": predecessor_branch,
        "receipt_sha256": predecessor_digest,
    }
provider_run = receipt.get("provider_run")
if provider_run is not None:
    if not isinstance(provider_run, dict):
        raise SystemExit("invalid capsule receipt: provider run must be an object")
    run_id = provider_run.get("id")
    expected_url = f"https://jules.google.com/session/{run_id}"
    if (
        provider_run != {"provider": expected_provider, "id": run_id, "url": expected_url}
        or not isinstance(run_id, str)
        or not run_id.isdigit()
    ):
        raise SystemExit("invalid capsule receipt: provider run identity mismatch")
    expected["provider_run"] = provider_run
if receipt != expected:
    raise SystemExit("invalid capsule receipt: identity or contract mismatch")
PY
}
workstream_export_context \
  "\$agent" "\$PWD" "\$capsule_dir" "\$expected_slug" "\$expected_workstream" "\$agent_capabilities"
validate_capsule_receipt
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
workstream_validate_launch_environment "\$preflight_timeout"
if [[ "\$launch_adapter" == "jules" ]]; then
  bound_session_id=""
  if bound_session_id="\$(workstream_jules_provider_run_id "\$receipt" "\$agent")"; then
    if workstream_jules_publish_receipt "\$receipt" "\$bound_session_id"; then
      printf 'Jules session receipt republished: %s\n' "\$receipt"
      exit 0
    fi
    printf 'Jules bound session receipt could not be republished\n' >&2
    exit 2
  fi
fi
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
    --predecessor-slug "\$expected_predecessor_slug" \
    --predecessor-branch "\$expected_predecessor_branch" \
    --predecessor-receipt-sha256 "\$expected_predecessor_receipt_sha256" \
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
if git remote get-url origin >/dev/null 2>&1 9>&-; then
  if ! GIT_TERMINAL_PROMPT=0 python3 "\$contract_helper" run-bounded \
    --timeout-seconds "\$preflight_timeout" -- git fetch --prune >/dev/null 2>&1 9>&-; then
    printf 'launch-environment error: bounded fetch from origin failed\n' >&2
    exit 2
  fi
fi
if ! python3 "\$contract_helper" run-bounded \
  --timeout-seconds "\$preflight_timeout" -- git status --short --branch >/dev/null 2>&1 9>&-; then
  printf 'launch-environment error: bounded Git status failed\n' >&2
  exit 2
fi
if [[ "\$launch_adapter" == "jules" ]]; then
  # Jules can only see the live remote default HEAD (or its own already-published reservation).
  # Prove that custody before runway admission so an incompatible exact successor base cannot
  # start its clock or rewrite its receipt and then fail at provider handoff.
  workstream_jules_validate_default_base
fi
if [[ "\$conduct" -eq 1 ]]; then
  workstream_hydrate_conduct_environment
  workstream_register_conduct_session "\$agent" "\$PWD" "\$agent_capabilities"
  if [[ "\${LIMEN_WORKSTREAM_ALREADY_RUNNING:-}" == "1" ]]; then
    exit 0
  fi
fi
# Admit only after every launch-environment preflight and conduct registration has succeeded.
refresh_workstream_runway
# Recheck the absolute deadline at the final boundary before publication and provider handoff. The
# first admission may start or observe a runway with only one second remaining; this second read is
# intentionally separate so expiry during that boundary is denied rather than published.
refresh_workstream_runway
if [[ "\$launch_adapter" != "jules" ]]; then
  workstream_publish_admitted_receipt "\$receipt" "\$expected_branch" "\$expected_slug"
  exec 9>&-
fi
if [[ "\$conduct" -eq 1 ]]; then
  workstream_start_conduct_keepalive \
    "\$agent" "\$PWD" "\$agent_capabilities" "\$\$" "\$LIMEN_WORKSTREAM_DEADLINE_EPOCH" "\$capsule_dir"
fi
workstream_launch_native_agent \
  "\$agent" "\$registry_binary" "$autonomous" "\$readme" "\$allow_shell_fallback" \
  "\$launch_model" "\$launch_reasoning_effort" "\$launch_sandbox" "\$contract_helper" \
  "\$launch_lane_model" "\$launch_adapter" "\$model_flag"
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
    --predecessor-slug "$predecessor_slug" \
    --predecessor-branch "$predecessor_branch" \
    --predecessor-receipt-sha256 "$predecessor_receipt_sha256" \
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
  if ! _limen_capsule_validate_receipt \
    "$contract" "$receipt" "$slug" "$branch" "$workstream" \
    "$predecessor_slug" "$predecessor_branch" "$predecessor_receipt_sha256"; then
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
