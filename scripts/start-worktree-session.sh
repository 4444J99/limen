#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/start-worktree-session.sh [--autonomous] [--agent auto|<canonical-lane>] [--model <id>] [--reasoning-effort <level>] [--sandbox <mode>] [--conduct] [--shell] [--from <branch-or-ref>] [--prompt <text>] [--prompt-file <path>] [--predecessor-receipt <receipt>] [--runway-mode inherit|renew] [--runway <duration>] [--workstream <handle>] <repo-or-alias> <slug>

Examples:
  scripts/start-worktree-session.sh portvs triptych-story
  scripts/start-worktree-session.sh --agent claude portvs triptych-story
  scripts/start-worktree-session.sh --autonomous --agent auto --conduct --runway 8h --prompt-file /tmp/next-session.md limen next-epoch
  scripts/start-worktree-session.sh --shell --prompt-file /tmp/prompt.md domus package-map
  scripts/start-worktree-session.sh --workstream contributions --prompt 'drain the code lane' limen contrib-run
  scripts/start-worktree-session.sh --model gpt-example --reasoning-effort high --sandbox danger-full-access limen explicit-codex
  scripts/start-worktree-session.sh --predecessor-receipt /path/to/docs/continuations/prior/workstream.json danse successor

--agent selects and launches a native agent CLI. "auto" derives an available installed CLI from the
canonical Limen census. Omitting --agent creates the capsule without launching; its kickstart uses
the same live-derived Auto selection with a login-shell fallback.

--model, --reasoning-effort, and --sandbox form one explicit Codex launch profile. All three are
required together. The exact model and effort must exist in the live local Codex catalog at render
and launch time; no substitution is permitted. Omitting --agent records the Codex profile without
launching immediately; an explicit lane whose registry profile uses the Codex adapter launches it.

--model supplied ALONE is a lane tier pin for a non-Codex lane: it is passed to the launched CLI as
--model <value> and nothing else changes. It requires --agent, and the selected registry profile
must declare a verified model-flag form; any other lane refuses the pin rather than ignoring it. A
pin never builds a Codex launch profile, so it needs no effort or sandbox.

--branch-prefix sets the branch namespace for a NEW worktree (work|feat|fix|heal|chore|docs|
refactor; default work). An unknown value is REFUSED, never coerced, and the check runs before any
binary probe so CI reaches the same verdict as a workstation. It affects only newly created
worktrees: `branch` is bound into the capsule identity digest, so an existing capsule keeps the
namespace it was created with and re-entry validation is unaffected.

--conduct registers the launched direct session with the shared broker as human-protected. Broker
credentials are read from the environment, never written into the capsule or command line, and
removed before the native agent process starts.

--workstream pins the worker to ONE purpose channel (contributions/correspondence/… — see
docs/lanes/). It is stamped into the kickoff packet so the session stays single-purpose.

--runway sets the finite workstream admission window (15m..30d; default 1d). The clock starts at the
first kickstart, survives successor sessions, and is never silently reset by a rerender.

--predecessor-receipt creates a validated successor from one committed tracked receipt. The default
--runway-mode inherit copies the predecessor's admitted start and deadline exactly and refuses
--runway. --runway-mode renew requires an explicit --runway and creates a fresh unstarted contract.
The predecessor checkout must be on its declared branch at the exact live origin branch head; that
commit becomes the successor base. Both modes retain provider-neutral workspace-write authorization.
Only the predecessor slug, branch, and SHA-256 receipt digest enter the successor receipt; its local
path is never recorded. Re-rendering must repeat the same predecessor and runway-mode arguments.

--autonomous requires an explicit prompt and turns the README into the selected agent's initial prompt. The
packet defines live probes and completion/switch predicates; it never predeclares the ending.

Aliases:
  portvs, portus  /Users/4jp/Workspace/4444J99/portvs
  limen           /Users/4jp/Workspace/limen
  domus           /Users/4jp/Workspace/domus-genoma
  relpipe         /Users/4jp/Workspace/4444J99/relationship-pipeline

Creates or reuses:
  <repo>/.worktrees/<slug> on branch <branch-prefix>/<slug> (default work/)
  <repo>/.worktrees/<slug>/.limen-workstream/README.md as a thin prompt index
  <repo>/.worktrees/<slug>/.limen-workstream/{manifest,workstream,intent,runtime,closeout}.md
  <repo>/.worktrees/<slug>/docs/continuations/<slug>/workstream.json as a tracked redacted receipt

The target repo's .git/info/exclude is updated so .worktrees/ and the private
capsule never appear as Git noise. The receipt remains visible for commit and remote custody.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/lib/workstream-capsule.sh
source "$script_dir/lib/workstream-capsule.sh"
# shellcheck source=scripts/lib/campaign-relay-capsule.sh
source "$script_dir/lib/campaign-relay-capsule.sh"

autonomous=0
launch_agent=0
launch_shell=0
conduct=0
requested_agent=""
from_ref=""
prompt_text=""
prompt_file=""
runway=""
runway_explicit=0
predecessor_receipt=""
predecessor_head=""
runway_mode="inherit"
runway_mode_explicit=0
workstream=""
launch_model=""
launch_reasoning_effort=""
launch_sandbox=""
# A bare --model on a non-Codex lane. Kept separate from launch_model because a non-empty
# launch_model is what builds the v2 Codex contract, which requires an effort and a sandbox.
launch_lane_model=""
write_readme=1
# The branch namespace for a NEW worktree. `work` reproduces the previous hardcoded behaviour
# exactly, so every existing caller (cli.py, lead-spawn.py, the test harnesses, humans) is
# unaffected by construction. Only a caller that asks gets anything different.
branch_prefix="work"
# The CLAUDE.md branch-cadence table, plus `work` for auto-named isolation branches. An unknown
# prefix is REFUSED, never coerced: silently rewriting it would put the lane on a branch whose name
# the caller did not choose, and `branch` is bound into the capsule identity digest.
VALID_BRANCH_PREFIXES="work feat fix heal chore docs refactor"
campaign_relay=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --campaign-relay)
      if [[ $# -lt 2 ]]; then
        echo "missing value for internal campaign relay identity" >&2
        exit 2
      fi
      campaign_relay="$2"
      shift 2
      ;;
    --autonomous)
      autonomous=1
      shift
      ;;
    --branch-prefix)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --branch-prefix" >&2
        usage >&2
        exit 2
      fi
      branch_prefix="$2"
      shift 2
      continue
      ;;
    --agent)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --agent" >&2
        usage >&2
        exit 2
      fi
      requested_agent="$2"
      launch_agent=1
      shift 2
      ;;
    --conduct)
      conduct=1
      shift
      ;;
    --model)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --model" >&2
        usage >&2
        exit 2
      fi
      launch_model="$2"
      shift 2
      ;;
    --reasoning-effort)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --reasoning-effort" >&2
        usage >&2
        exit 2
      fi
      launch_reasoning_effort="$2"
      shift 2
      ;;
    --sandbox)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --sandbox" >&2
        usage >&2
        exit 2
      fi
      launch_sandbox="$2"
      shift 2
      ;;
    --shell)
      launch_shell=1
      shift
      ;;
    --from)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --from" >&2
        usage >&2
        exit 2
      fi
      from_ref="$2"
      shift 2
      ;;
    --prompt)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --prompt" >&2
        usage >&2
        exit 2
      fi
      prompt_text="$2"
      shift 2
      ;;
    --prompt-file)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --prompt-file" >&2
        usage >&2
        exit 2
      fi
      prompt_file="$2"
      shift 2
      ;;
    --runway)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --runway" >&2
        usage >&2
        exit 2
      fi
      runway="$2"
      runway_explicit=1
      shift 2
      ;;
    --predecessor-receipt)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --predecessor-receipt" >&2
        usage >&2
        exit 2
      fi
      predecessor_receipt="$2"
      shift 2
      ;;
    --runway-mode)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --runway-mode" >&2
        usage >&2
        exit 2
      fi
      runway_mode="$2"
      runway_mode_explicit=1
      shift 2
      ;;
    --workstream|--ws)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --workstream" >&2
        usage >&2
        exit 2
      fi
      workstream="$2"
      shift 2
      ;;
    --no-readme)
      write_readme=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 2
fi

# REFUSE an unknown branch prefix, never coerce — and validate it HERE, among the argument checks,
# far ahead of any binary probe. Argument validity is a property of the arguments, not of what is
# installed, so CI (no agent binary) must reach the same verdict as a workstation that has one.
# This is the same ordering lesson the lane pin and the Codex sandbox each had to be fixed for.
case " $VALID_BRANCH_PREFIXES " in
  *" $branch_prefix "*) ;;
  *)
    echo "unknown --branch-prefix '$branch_prefix' (one of: $VALID_BRANCH_PREFIXES)" >&2
    exit 2
    ;;
esac

if [[ "$autonomous" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--autonomous cannot be combined with --no-readme" >&2
  exit 2
fi
if [[ "$launch_agent" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--agent cannot be combined with --no-readme because launch requires a validated contract" >&2
  exit 2
fi
if [[ "$conduct" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--conduct cannot be combined with --no-readme" >&2
  exit 2
fi
if [[ "$autonomous" -eq 1 && -z "$prompt_text" && -z "$prompt_file" && -z "$campaign_relay" ]]; then
  echo "--autonomous requires --prompt or --prompt-file" >&2
  exit 2
fi
launch_profile_values=0
[[ -n "$launch_model" ]] && launch_profile_values=$((launch_profile_values + 1))
[[ -n "$launch_reasoning_effort" ]] && launch_profile_values=$((launch_profile_values + 1))
[[ -n "$launch_sandbox" ]] && launch_profile_values=$((launch_profile_values + 1))
if [[ "$launch_profile_values" -eq 1 && -n "$launch_model" ]]; then
  # --model ALONE is a lane tier pin: it pins the launched lane's model without claiming the
  # Codex explicit launch profile. Move it out of launch_model so the v2 contract is not built.
  launch_lane_model="$launch_model"
  launch_model=""
  launch_profile_values=0
elif [[ "$launch_profile_values" -ne 0 && "$launch_profile_values" -ne 3 ]]; then
  echo "--model alone pins a non-Codex lane's model; otherwise --model, --reasoning-effort, and --sandbox must be supplied together" >&2
  exit 2
fi
if [[ -n "$launch_lane_model" ]]; then
  if [[ "$launch_agent" -ne 1 ]]; then
    echo "--model alone is a lane tier pin and requires --agent; with no launch nothing would consume it" >&2
    exit 2
  fi
  if [[ "$write_readme" -ne 1 ]]; then
    echo "a lane tier pin cannot be combined with --no-readme" >&2
    exit 2
  fi
fi
if [[ "$launch_profile_values" -eq 3 && "$write_readme" -ne 1 ]]; then
  echo "explicit model launch profiles cannot be combined with --no-readme" >&2
  exit 2
fi
case "$runway_mode" in
  inherit|renew) ;;
  *)
    echo "--runway-mode must be inherit or renew" >&2
    exit 2
    ;;
esac
if [[ -z "$predecessor_receipt" ]]; then
  if [[ "$runway_mode_explicit" -eq 1 ]]; then
    echo "--runway-mode requires --predecessor-receipt" >&2
    exit 2
  fi
elif [[ "$runway_mode" == "inherit" && "$runway_explicit" -eq 1 ]]; then
  echo "--runway-mode inherit copies the admitted predecessor timing and cannot accept --runway" >&2
  exit 2
elif [[ "$runway_mode" == "renew" && "$runway_explicit" -ne 1 ]]; then
  echo "--runway-mode renew requires an explicit --runway" >&2
  exit 2
fi
if [[ -n "$predecessor_receipt" && ( "$launch_profile_values" -ne 0 || -n "$launch_lane_model" ) ]]; then
  echo "a successor derives its launch contract from the predecessor; explicit model flags are not accepted" >&2
  exit 2
fi
if [[ -n "$predecessor_receipt" && "$write_readme" -ne 1 ]]; then
  echo "--predecessor-receipt cannot be combined with --no-readme because successor custody requires a capsule" >&2
  exit 2
fi
if [[ -n "$prompt_file" && ! -f "$prompt_file" ]]; then
  echo "prompt file not found: $prompt_file" >&2
  exit 1
fi

contract_helper="$script_dir/../cli/src/limen/workstream_contract.py"
if [[ ! -f "$contract_helper" ]]; then
  echo "workstream contract helper not found: $contract_helper" >&2
  exit 1
fi
if [[ "$runway_explicit" -eq 1 ]]; then
  if ! normalized_runway="$(python3 "$contract_helper" normalize "$runway")"; then
    exit 2
  fi
  runway="${normalized_runway%%:*}"
fi
if [[ -n "$predecessor_receipt" ]]; then
  if [[ ! -f "$predecessor_receipt" || -L "$predecessor_receipt" ]]; then
    echo "predecessor receipt must be a real committed file" >&2
    exit 2
  fi
  successor_metadata_args=(
    successor-metadata
    --predecessor-receipt "$predecessor_receipt"
    --runway-mode "$runway_mode"
  )
  if [[ "$runway_mode" == "renew" ]]; then
    successor_metadata_args+=(--runway "$runway")
  fi
  if ! successor_metadata="$(python3 "$contract_helper" "${successor_metadata_args[@]}")"; then
    exit 2
  fi
  predecessor_head="$(printf '%s\n' "$successor_metadata" | sed -n '5p')"
  if [[ ! "$predecessor_head" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]; then
    echo "predecessor receipt did not resolve an exact remotely custodied HEAD" >&2
    exit 2
  fi
fi
if [[ -n "$campaign_relay" ]]; then
  if [[ ! "$campaign_relay" =~ ^[0-9a-f]{64}$ \
    || "${LIMEN_CAMPAIGN_RELAY_ID:-}" != "$campaign_relay" \
    || ! "${LIMEN_CAMPAIGN_RELAY_ACK_FD:-}" =~ ^[0-9]+$ \
    || ! "${LIMEN_CAMPAIGN_RELAY_CONTROL_FD:-}" =~ ^[0-9]+$ \
    || ! "${LIMEN_CAMPAIGN_RELAY_EXEC_FD:-}" =~ ^[0-9]+$ \
    || "${LIMEN_CAMPAIGN_RELAY_ACK_FD}" == "${LIMEN_CAMPAIGN_RELAY_CONTROL_FD}" \
    || "${LIMEN_CAMPAIGN_RELAY_ACK_FD}" == "${LIMEN_CAMPAIGN_RELAY_EXEC_FD}" \
    || "${LIMEN_CAMPAIGN_RELAY_CONTROL_FD}" == "${LIMEN_CAMPAIGN_RELAY_EXEC_FD}" \
    || ! "${LIMEN_CAMPAIGN_RELAY_ELIGIBLE_LANES:-}" =~ ^[a-z0-9][a-z0-9_-]*(,[a-z0-9][a-z0-9_-]*)*$ \
    || "$autonomous" -ne 1 \
    || "$launch_agent" -ne 1 \
    || "$requested_agent" != "auto" \
    || "$conduct" -ne 1 \
    || "$runway_explicit" -ne 1 \
    || "$runway" != "8h" \
    || "$workstream" != "institutional-omega" \
    || "$branch_prefix" != "work" \
    || "$launch_shell" -ne 0 \
    || "$write_readme" -ne 1 \
    || -n "$prompt_text" \
    || -n "$prompt_file" \
    || -n "$launch_model" \
    || -n "$launch_reasoning_effort" \
    || -n "$launch_sandbox" \
    || -n "$launch_lane_model" \
    || -n "$predecessor_receipt" \
    || "$runway_mode_explicit" -ne 0 \
    || ! "$from_ref" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ \
    || "${LIMEN_CAMPAIGN_RELAY_BASE:-}" != "$from_ref" \
    || "${LIMEN_WORKSTREAM_SESSION_ID:-}" != "relay-${campaign_relay:0:32}" ]]; then
    echo "invalid internal campaign relay launch shape" >&2
    exit 2
  fi
  if ! python3 - \
    "${LIMEN_CAMPAIGN_RELAY_ACK_FD}" \
    "${LIMEN_CAMPAIGN_RELAY_CONTROL_FD}" \
    "${LIMEN_CAMPAIGN_RELAY_EXEC_FD}" <<'PY'
import os
import stat
import sys

descriptors = []
for raw in sys.argv[1:]:
    try:
        descriptor = int(raw)
        metadata = os.fstat(descriptor)
    except (OSError, ValueError):
        raise SystemExit(1)
    if descriptor < 3 or descriptor > 255 or not stat.S_ISFIFO(metadata.st_mode):
        raise SystemExit(1)
    descriptors.append(descriptor)
if len(set(descriptors)) != 3:
    raise SystemExit(1)
PY
  then
    echo "invalid internal campaign relay control or exec-status channel" >&2
    exit 2
  fi
  unset LIMEN_HUMAN_PROTECTED LIMEN_NATIVE_RUN_ID LIMEN_NATIVE_SESSION_ID \
    LIMEN_PROVIDER_IDENTITY LIMEN_RUN_ID
  prompt_text="Continue only the institutional Omega workstream from its durable owner receipts. Preserve the predecessor trial and frozen evaluator byte-for-byte. Do not mutate launcher, ARCA, custody, host, credential, signer, service, protected-session, retirement, deletion, or paid-plan state. Re-derive live predicates and proceed only through the bounded provider-neutral workstream contract."
fi

agent=""
registry_binary=""
agent_capabilities=""
allow_shell_fallback=1
if [[ -n "$requested_agent" ]]; then
  allow_shell_fallback=0
fi
agent_resolution="$(
  PYTHONPATH="$script_dir/../cli/src${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "${requested_agent:-auto}" "$launch_profile_values" "$autonomous" <<'PY'
import os
import shutil
import sys

from limen.capacity import select_lanes
from limen.census import VENDORS, by_name, canonical
from limen.workstream_provider import workstream_binary_candidates, workstream_launchable


requested = sys.argv[1].strip().lower()
require_codex_adapter = sys.argv[2] == "3"
if sys.argv[3] not in {"0", "1"}:
    raise SystemExit("invalid autonomous workstream selection mode")
autonomous = sys.argv[3] == "1"
if requested == "auto":
    relay_order = [
        canonical(value)
        for value in os.environ.get("LIMEN_CAMPAIGN_RELAY_ELIGIBLE_LANES", "").split(",")
        if value
    ]
    if relay_order:
        if len(relay_order) != len(set(relay_order)):
            raise SystemExit("campaign relay eligible lanes are not unique")
        ordered = [by_name(name) for name in relay_order]
        if any(vendor is None for vendor in ordered):
            raise SystemExit("campaign relay eligible lane is not canonical")
        live = set(select_lanes("auto"))
        ordered = [vendor for vendor in ordered if vendor.name in live]
        if not ordered:
            raise SystemExit("campaign relay has no remaining live provider capacity before launch")
    else:
        preferred = canonical(os.environ.get("LIMEN_AGENT"))
        ordered = list(VENDORS)
        if preferred and by_name(preferred):
            ordered.sort(key=lambda vendor: vendor.name != preferred)
    eligible = [
        vendor
        for vendor in ordered
        if vendor is not None
        if vendor.status.available
        and vendor.status.state == "live"
        and workstream_launchable(vendor, autonomous=autonomous)
        if not require_codex_adapter or vendor.execution.workstream_adapter == "codex"
    ]
    selected = next(
        (
            (vendor, binary)
            for vendor in eligible
            for binary in workstream_binary_candidates(vendor, os.environ)
            if shutil.which(binary)
        ),
        None,
    )
    if selected is None:
        if not eligible:
            raise SystemExit("no live canonical Limen lane supports native execution")
        vendor = eligible[0]
        binary = next(iter(workstream_binary_candidates(vendor, os.environ)), vendor.name)
    else:
        vendor, binary = selected
else:
    name = canonical(requested)
    vendor = by_name(name)
    if vendor is None:
        allowed = ", ".join(item.name for item in VENDORS)
        raise SystemExit(f"unknown Limen agent lane {requested!r}; canonical lanes: {allowed}")
    if not workstream_launchable(vendor, autonomous=autonomous):
        if vendor.execution.workstream_adapter == "jules" and not autonomous:
            raise SystemExit(f"Limen agent lane {vendor.name!r} requires --autonomous")
        raise SystemExit(f"Limen agent lane {vendor.name!r} has no verified native workstream adapter")
    binary = next(
        (item for item in workstream_binary_candidates(vendor, os.environ) if shutil.which(item)),
        vendor.name,
    )

print(vendor.name)
print(binary)
profile = getattr(vendor, "execution", None)
capabilities = profile.capabilities if profile is not None else frozenset({"code", "conduct", "review"})
print(" ".join(sorted(capabilities)))
print(profile.workstream_adapter if profile is not None else "positional")
print("1" if profile is not None and profile.workstream_model_flag else "0")
PY
)"
agent="$(printf '%s\n' "$agent_resolution" | sed -n '1p')"
registry_binary="$(printf '%s\n' "$agent_resolution" | sed -n '2p')"
agent_capabilities="$(printf '%s\n' "$agent_resolution" | sed -n '3p')"
agent_launch_adapter="$(printf '%s\n' "$agent_resolution" | sed -n '4p')"
agent_model_flag="$(printf '%s\n' "$agent_resolution" | sed -n '5p')"
case "$agent_launch_adapter" in
  codex|jules|positional|prompt-flag|prompt-interactive) ;;
  *)
    echo "canonical lane $agent has an unsupported workstream launch adapter" >&2
    exit 2
    ;;
esac
case "$agent_model_flag" in
  0|1) ;;
  *)
    echo "canonical lane $agent has an invalid workstream model-flag contract" >&2
    exit 2
    ;;
esac
if [[ "$launch_profile_values" -eq 3 && "$agent_launch_adapter" != "codex" ]]; then
  echo "explicit model launch profiles require the Codex native lane" >&2
  exit 2
fi
if [[ -n "$launch_lane_model" ]]; then
  # Ordered BEFORE the binary-existence probe on purpose: a flag combination is invalid
  # regardless of what happens to be installed, and CI (no codex binary) must reach the same
  # verdict as a workstation that has one.
  # Refuse rather than swallow. Verified --model flag forms only; codex keeps its own triple so
  # there stays exactly one way to launch it explicitly.
  if [[ "$agent_launch_adapter" == "codex" ]]; then
      echo "lane tier pin refused: the codex lane requires the validated --model/--reasoning-effort/--sandbox profile, not a bare pin" >&2
      exit 2
  elif [[ "$agent_model_flag" != "1" ]]; then
    echo "lane tier pin refused: lane $agent has no verified --model flag form; remove the pin or extend its registry profile" >&2
    exit 2
  fi
fi
if [[ "$launch_profile_values" -eq 3 && -n "$launch_sandbox" ]]; then
  # STATIC sandbox validation, ordered before EVERY binary probe for the same reason the lane tier
  # pin above is: an invalid --sandbox value is invalid regardless of what is installed, so CI (no
  # codex binary) must reach the same verdict as a workstation that has one. Ordered before the
  # generic probe on the next line, not merely before the codex-specific one further down — that
  # generic probe is what fires first, and it exits 127 before the bad value is ever looked at.
  # validate-codex-launch re-runs this same authorization itself, so this strictly ADDS a gate.
  if ! python3 "$contract_helper" validate-codex-sandbox --sandbox "$launch_sandbox" >/dev/null; then
    exit 2
  fi
fi
if [[ "$launch_agent" -eq 1 ]] && ! workstream_native_binary "$agent" "$registry_binary" >/dev/null; then
  echo "native CLI not found for canonical lane $agent" >&2
  exit 127
fi
if [[ "$launch_profile_values" -eq 3 ]]; then
  if ! codex_binary="$(workstream_native_binary "$agent" "$registry_binary")"; then
    echo "native CLI not found for canonical lane $agent" >&2
    exit 127
  fi
  if ! python3 "$contract_helper" validate-codex-launch \
    --binary "$codex_binary" \
    --model "$launch_model" \
    --reasoning-effort "$launch_reasoning_effort" \
    --sandbox "$launch_sandbox" >/dev/null; then
    exit 2
  fi
fi

repo_arg="$1"
raw_slug="$2"

case "$repo_arg" in
  portvs|portus)
    repo="/Users/4jp/Workspace/4444J99/portvs"
    ;;
  limen)
    repo="/Users/4jp/Workspace/limen"
    ;;
  domus|domus-genoma)
    repo="/Users/4jp/Workspace/domus-genoma"
    ;;
  relationship-pipeline|relpipe|maddie)
    repo="/Users/4jp/Workspace/4444J99/relationship-pipeline"
    ;;
  *)
    if [[ -d "$repo_arg" ]]; then
      repo="$repo_arg"
    elif [[ -d "/Users/4jp/Workspace/$repo_arg" ]]; then
      repo="/Users/4jp/Workspace/$repo_arg"
    elif [[ -d "/Users/4jp/Workspace/4444J99/$repo_arg" ]]; then
      repo="/Users/4jp/Workspace/4444J99/$repo_arg"
    else
      echo "repo not found: $repo_arg" >&2
      exit 1
    fi
    ;;
esac

repo="$(cd "$repo" && pwd -P)"
if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git repo: $repo" >&2
  exit 1
fi
if [[ -n "$predecessor_receipt" ]]; then
  if ! git -C "$repo" cat-file -e "${predecessor_head}^{commit}" 2>/dev/null; then
    echo "predecessor HEAD is not present in the target repository" >&2
    exit 2
  fi
  if [[ -n "$from_ref" ]]; then
    requested_from_head="$(git -C "$repo" rev-parse --verify "${from_ref}^{commit}" 2>/dev/null || true)"
    if [[ "$requested_from_head" != "$predecessor_head" ]]; then
      echo "--from must resolve to the exact predecessor HEAD" >&2
      exit 2
    fi
  fi
  # Canonicalize the successor base to the remotely custodied predecessor commit. The local
  # receipt path remains an input only and is never written into the successor capsule.
  from_ref="$predecessor_head"
fi
if [[ -n "$campaign_relay" ]]; then
  relay_root_head="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
  relay_root_status="$(git -C "$repo" status --porcelain=v1 --untracked-files=all 2>/dev/null || true)"
  if [[ "$relay_root_head" != "$from_ref" || -n "$relay_root_status" ]]; then
    echo "internal campaign relay requires a clean exact-base checkout" >&2
    exit 2
  fi
fi

slug="$(
  printf '%s' "$raw_slug" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
)"
if [[ -z "$slug" ]]; then
  echo "slug collapsed to empty: $raw_slug" >&2
  exit 1
fi
if [[ -n "$campaign_relay" && "$slug" != "institutional-omega-${campaign_relay:0:16}" ]]; then
  echo "internal campaign relay slug does not match its stable identity" >&2
  exit 2
fi

if [[ -n "$workstream" ]]; then
  workstream="$(
    printf '%s' "$workstream" \
      | tr '[:upper:]' '[:lower:]' \
      | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
  )"
fi

branch="$branch_prefix/$slug"
wt="$repo/.worktrees/$slug"

if [[ -n "$campaign_relay" ]]; then
  if [[ -e "$wt" || -L "$wt" ]] \
    || git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
    echo "internal campaign relay requires an absent deterministic target branch and worktree" >&2
    exit 2
  fi
fi

if [[ -n "$predecessor_receipt" ]]; then
  existing_target_ref=""
  successor_identity="$wt/.limen-workstream/capsule.identity"
  successor_receipt="$wt/docs/continuations/$slug/workstream.json"
  if [[ -d "$wt" ]] && git -C "$wt" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [[ ! -s "$successor_identity" || ! -s "$successor_receipt" ]]; then
      existing_target_ref="HEAD"
    fi
  elif git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
    existing_target_ref="refs/heads/$branch"
  fi
  if [[ -n "$existing_target_ref" ]]; then
    if [[ "$existing_target_ref" == "HEAD" ]]; then
      existing_target_head="$(git -C "$wt" rev-parse --verify "HEAD^{commit}" 2>/dev/null || true)"
    else
      existing_target_head="$(git -C "$repo" rev-parse --verify "${existing_target_ref}^{commit}" 2>/dev/null || true)"
    fi
    if [[ "$existing_target_head" != "$predecessor_head" ]]; then
      echo "existing uncapsuled successor target does not match the exact predecessor HEAD" >&2
      exit 2
    fi
  fi
fi

git_info_dir="$(git -C "$repo" rev-parse --path-format=absolute --git-path info)"
mkdir -p "$git_info_dir"
exclude_file="$git_info_dir/exclude"
touch "$exclude_file"
if ! grep -qxF ".worktrees/" "$exclude_file"; then
  {
    printf '\n'
    printf '.worktrees/\n'
  } >> "$exclude_file"
fi
if ! grep -qxF ".limen-workstream/" "$exclude_file"; then
  {
    printf '\n'
    printf '.limen-workstream/\n'
  } >> "$exclude_file"
fi

if [[ -z "$from_ref" ]]; then
  origin_head="$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -n "$origin_head" ]]; then
    from_ref="$origin_head"
  elif git -C "$repo" show-ref --verify --quiet refs/remotes/origin/main; then
    from_ref="origin/main"
  else
    from_ref="$(git -C "$repo" branch --show-current)"
  fi
fi

mkdir -p "$(dirname "$wt")"

if [[ -d "$wt" ]]; then
  if ! git -C "$wt" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "path exists but is not a git worktree: $wt" >&2
    exit 1
  fi
  created="reused"
elif git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo" worktree add "$wt" "$branch" >/dev/null
  created="created"
else
  git -C "$repo" worktree add -b "$branch" "$wt" "$from_ref" >/dev/null
  created="created"
fi

echo "$created worktree: $wt"
echo "branch: $branch"
[[ -n "$workstream" ]] && echo "workstream: $workstream"
echo "agent: $agent"
if [[ "$conduct" -eq 1 ]]; then
  if [[ -n "$campaign_relay" ]]; then
    echo "conduct: deterministic relay session"
  else
    echo "conduct: human-protected direct session"
  fi
fi

if [[ "$write_readme" -eq 1 ]]; then
  capsule_dir="$wt/.limen-workstream"
  readme="$capsule_dir/README.md"

  if [[ -n "$prompt_file" ]]; then
    prompt_payload="$(cat "$prompt_file")"
  elif [[ -n "$prompt_text" ]]; then
    prompt_payload="$prompt_text"
  else
    prompt_payload="No explicit prompt was supplied. Add one bounded objective and its owner contract before execution."
  fi

  render_workstream_capsule \
    "$wt" "$repo" "$slug" "$branch" "$workstream" "$from_ref" "$autonomous" \
    "$prompt_payload" "$script_dir/../spec/continuation-capsule" "$runway" "$contract_helper" \
    "$agent" "$registry_binary" "$conduct" "$allow_shell_fallback" "$agent_capabilities" \
    "$launch_model" "$launch_reasoning_effort" "$launch_sandbox" "$launch_lane_model" \
    "$agent_launch_adapter" "$agent_model_flag" "$predecessor_receipt" "$runway_mode"
  if [[ -n "$campaign_relay" ]]; then
    workstream_prepare_campaign_relay_capsule \
      "$wt" "$slug" "$branch" "$workstream" "$campaign_relay"
  fi
fi

if [[ "$launch_agent" -eq 1 ]]; then
  exec bash "$wt/.limen-workstream/kickstart.sh"
fi

if [[ "$launch_shell" -eq 1 ]]; then
  cd "$wt"
  exec "${SHELL:-/bin/zsh}" -l
fi

echo
echo "Next:"
echo "  cd $wt"
if [[ "$write_readme" -eq 1 ]]; then
  echo "  bash $wt/.limen-workstream/kickstart.sh"
else
  echo "  $registry_binary"
fi
