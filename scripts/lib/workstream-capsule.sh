#!/usr/bin/env bash

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
  local capsule_dir="$wt/.limen-workstream"
  local readme="$capsule_dir/README.md"
  local manifest="$capsule_dir/manifest.md"
  local intent="$capsule_dir/intent.md"
  local runtime="$capsule_dir/runtime.md"
  local closeout="$capsule_dir/closeout.md"
  local kickstart="$capsule_dir/kickstart.sh"
  local runtime_template="$spec_dir/runtime-interactive.md"
  local required_template created_at head_short upstream_ref origin_url status_line readme_action
  local capsule_changed=0

  mkdir -p "$capsule_dir"
  if [[ "$autonomous" -eq 1 ]]; then
    runtime_template="$spec_dir/runtime-autonomous.md"
  fi
  for required_template in "$runtime_template" "$spec_dir/closeout.md"; do
    if [[ ! -f "$required_template" ]]; then
      echo "capsule template not found: $required_template" >&2
      return 1
    fi
  done

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

This is a historical snapshot. The runtime module requires fresh probes before action.
EOF
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
2. \`.limen-workstream/intent.md\` — objective and owner-specific context;
3. \`.limen-workstream/runtime.md\` — live probes and boundary decision contract;
4. \`.limen-workstream/closeout.md\` — receipt and successor rules.

Resolve them from \`$wt\`. Missing, unreadable, stale, or contradictory modules make the capsule
invalid; stop rather than guessing. The intent fixes scope. Live evidence determines the lane and
ending.

## Launch command

\`\`\`bash
bash "$kickstart"
\`\`\`

For a plain shell, use \`cd "$wt"\` and then \`\${SHELL:-/bin/zsh} -l\`.
EOF
  _capsule_write_module "$kickstart" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$wt"
for module in "$manifest" "$intent" "$runtime" "$closeout"; do
  if [[ ! -s "\$module" ]]; then
    printf 'invalid capsule: missing or empty module %s\n' "\$module" >&2
    exit 2
  fi
done
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --prune
fi
git status --short --branch
if command -v codex >/dev/null 2>&1; then
  if [[ "$autonomous" -eq 1 ]]; then
    capsule_prompt=""
    IFS= read -r -d '' capsule_prompt < "$readme" || true
    exec codex "\$capsule_prompt"
  fi
  exec codex
fi
exec "\${SHELL:-/bin/zsh}" -l
EOF
  if [[ ! -x "$kickstart" ]]; then
    chmod +x "$kickstart"
    capsule_changed=1
  fi

  if [[ "$capsule_changed" -eq 1 ]]; then
    readme_action="wrote"
  else
    readme_action="unchanged"
  fi
  unset -f _capsule_write_module

  echo "capsule index: $readme ($readme_action)"
  echo "capsule modules: $manifest $intent $runtime $closeout"
  echo "kickstart command: bash $kickstart"
}
