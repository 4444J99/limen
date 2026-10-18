# Plan: Codex config: auto-review approvals + broader feature set

Issue: (none; operator-direct request, home is the domus-genoma PR below)
PR: 4444J99/domus-genoma-private#512 (merged as 86f334fa; applied to the live codex config.toml and observed via `codex features list` / `codex doctor` 2026-10-18)

## Context

The operator pasted Codex 0.163.0 `--help` text (`--approve-for-me`,
`--dangerously-bypass-approvals-and-sandbox`, `--dangerously-bypass-hook-trust`) plus
`codex features list` and asked to "update config", with "most features enabled".

Findings (verified on disk / against the binary):

- Codex's deployed config (`.agent-runtime/codex/config.toml`) is **split-ownership**. The
  source is `domus-genoma/Workspace/limen/private_dot_agent-runtime/private_codex/modify_private_config.toml.tmpl`,
  a section-level splice that asserts only owner atoms declared in
  `domus-genoma/.chezmoidata/config-ownership.json`. Editing the deployed file is futile.
- `--dangerously-bypass-approvals-and-sandbox` is **already the persisted state**:
  `approval_policy = "never"` + `sandbox_mode = "danger-full-access"` (app/operator-owned,
  passed through by the splice). Nothing to add.
- `--approve-for-me` maps to `approvals_reviewer = "auto_review"` (binary also knows the
  legacy `guardian_subagent`). `approvals_reviewer` is an existing owner atom, currently `"user"`.
- `--dangerously-bypass-hook-trust` has **no config key** (invocation-only). Operator chose
  **not** to persist it: the only persistent form is a flag in the `codex()` zsh wrapper
  (`dot_config/zsh/25-agent-runtime.zsh`), which would drop the trust boundary for every
  launch including cloned-repo `.codex/hooks.json`. Existing `[hooks.state]` entries
  (several `enabled = false`) are deliberately left alone.

Operator decisions (AskUserQuestion): bypass + auto_review; do not persist hook-trust bypass;
stable + curated under-development features.

## Changes (all in `organvm/domus-genoma`, one topic branch `chore/codex-auto-review-features`)

1. `modify_private_config.toml.tmpl`
   - `TOP_LEVEL["approvals_reviewer"]`: `"user"` -> `"auto_review"`. Inert while
     `approval_policy = "never"`, effective wherever approvals still apply (profiles,
     sub-agents, on-request runs); no behavior regression.
   - `SECTIONS_KEY_MERGE["features"]`: add the 15 flags below as `True` (existing four
     stay). Key-merge asserts only named keys, so app-added flags such as `js_repl` still pass through.
2. `.chezmoidata/config-ownership.json`: add the same 15 keys to
   `owner_managed.sections_key_merge.features`. Predicate D fails when the template has an
   unregistered key, so this must land in the same commit.
3. `tests/test_modify_codex_config.py`: add tests that (a) `approvals_reviewer` converges to
   `auto_review` from `user` and is idempotent, (b) each new feature is asserted `true`
   from absent and from `false`, f(f(x)) == f(x), and an app-added flag survives.
4. `docs/codex-host-cartridge.md`: one short note on the reviewer atom and why hook-trust
   bypass is not persisted.

### Feature allowlist (15)

- Stable but off (3): `multi_agent_v2`, `recommended_plugins`, `secret_auth_storage`.
- Under development, additive/user-facing (12): `credential_masking`, `current_time_reminder`,
  `image_resize_notice`, `terminal_visualization_instructions`, `cwd_relative_turn_diffs`,
  `standalone_web_search`, `mcp_oauth_refresh_coordination`, `enable_mcp_apps`,
  `external_agent_memory_import`, `agent_message_board`, `send_message_to_user_async`, `artifact`.

Deliberately excluded: removed (no-ops) and deprecated flags; mode-switching `code_mode*`
(`code_mode_only*`); limit-adding `token_budget`, `rollout_budget`,
`subagent_default_context_limits`; `skip_host_skill_discovery` (would disable skills);
`non_prefixed_mcp_tool_names` (renames tools, breaks hook matchers); `step_model_switching`
(violates model routing policy); `guardianv2*` (table-typed in this config, owner removes a
key under it); `local_thread_store_compression` (touches quota-bound stores);
`default_mode_request_user_input` / `request_permissions_tool` / `exec_permission_approvals`
(would reintroduce prompts, against no-stall); internal plumbing (`psp`, `use_xaa`, `prefer_mxc`, ...).

Risk-ordered rollback: `secret_auth_storage` (could migrate auth off `auth.json`) and
`multi_agent_v2` (overlaps stable `multi_agent`; interacts with `agents.max_threads = 3`) are
verified individually after apply and removed from the allowlist if they misbehave.

## Process

- **Admission gate:** `scripts/host-work-admission.py status --no-probe` returned
  `allowed: false` (reasons `swap-fraction` 0.72, `vitals-shed`; 13 codex writer leases held)
  at planning time. Re-check before implementing; take a fresh domus-genoma worktree off
  `origin/main` (it is 1 behind; `.worktrees/` holds many stale ones: reuse none, nest nothing).
- Branch `chore/codex-auto-review-features`, one PR, merged per the domus-genoma rail.
- Apply: `chezmoi diff <codex config target>` first (Rule #10), then
  `chezmoi apply <that one target>` only, never a blanket apply (the repo has unrelated drift).

## Verification (bare commands, read each one's own exit code)

1. `python3 -m pytest tests/test_modify_codex_config.py tests/test_config_ownership.py -q` in the worktree.
2. `python3 check-config-ownership.py` -> exit 0 (predicate D parity).
3. Pre-apply preview, zero writes: `codex features list --enable <flag> ...` shows the
   15 flags effective `true` (confirmed this mechanism works for `credential_masking`).
4. Round-trip proof: `python3 check-config-ownership.py --prove-diff <before.toml> <after.toml>`
   -> `GREEN` (only owner-managed paths changed).
5. Post-apply: `codex features list` (15 true, nothing else flipped), `codex doctor`
   clean, `codex login status` still authenticated (guards `secret_auth_storage`), and
   `grep approvals_reviewer .agent-runtime/codex/config.toml` -> `auto_review`.
6. Report status words separately: merged (on origin/main) vs applied (live config.toml
   contains it) vs observed (`codex features list` / `doctor` output).
