# Current Session Fanout PLAN-09: domus-preflight-noise

Generated: `2026-06-30`
Packet: `PLAN-09-5aa10d25`
Task: `CSF-CAEB31D8-PLAN-09-5AA10D25`
Theme: `domus-preflight-noise`
Source session: `/Users/4jp/.codex/sessions/2026/06/30/rollout-2026-06-30T06-17-55-019f1809-13b4-7780-9b1f-d4584f872333.jsonl`

This receipt is public-safe. It records hashes, owners, predicates, and local
work status only. It does not copy private prompt or plan bodies.

## Source Proof

- Session hash prefix: `caeb31d8`.
- Full-session prompt coverage: `44` prompt events, `19` unique prompt hashes,
  `78,216` prompt bytes.
- Plan-source coverage: `11` plan events from transcript line `6` through
  transcript line `1450`, with `10` unique plan sources and `1` duplicate.
- Source plan hashes: `7eb608baa99c`, `c93bc2c89ad8`, `dbf49126308e`,
  `3cc93e1d8fbd`, `0cb1773e8fef`, `1a3fd7bbca9d`, `569ac3d1deea`,
  `b0f5c26d40a3`, `f15665fb9ad3`, `21e790435885`.
- First prompt-hash sample: `4c72667b4d9a1d74b666b8e5`,
  `f970b04af2b06193fcaf9ca4`, `5cd8d801fb9ec350968507ad`,
  `5cd8d801fb9ec350968507ad`, `51b4520a624f45dc78be0d98`,
  `51b4520a624f45dc78be0d98`, `4c72667b4d9a1d74b666b8e5`,
  `f970b04af2b06193fcaf9ca4`, `e27388c5c8a724b1070d4aaf`,
  `e27388c5c8a724b1070d4aaf`, `5470f2595dfe3afd1fd6e53b`,
  `5470f2595dfe3afd1fd6e53b`.

## Decision

`domus-preflight-noise` is a local hygiene and preflight reliability stream. It
must be preserved and routed to the Domus owner, but it must not stop global
product selection. If Domus local preflights block, selectors continue with the
other current-session fanout streams and record this one as blocked local work.

## Owner Packets

| Packet | Owner | Executor fit | Status | Purpose |
|---|---|---|---|---|
| `DOMUS-PREFLIGHT-NOISE-01` | `organvm/domus-genoma` | `codex`, then `opencode` only after predicates are explicit | blocked-local-work-recorded | Finish the Atuin and zsh cache hardening without leaking prompt text. |
| `DOMUS-PREFLIGHT-NOISE-02` | `organvm/domus-genoma` | `codex` or `opencode` | blocked-local-work-recorded | Finish governed `domus up` package and storage preflight behavior. |
| `DOMUS-PREFLIGHT-NOISE-03` | `organvm/limen` | `codex` | ready | Keep Limen product selection active while Domus local hygiene remains blocked. |
| `DOMUS-PREFLIGHT-NOISE-04` | local operator / Domus environment | human-gated only | needs-human-if-executed | Mount or resolve storage/package lifecycle blockers when an executor reaches that gate. |

## Blocked Local Work

Current local owner work exists outside this Limen branch at:

`/Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629`

The worktree currently has modified Domus files, including:

- `dot_config/zsh/20-tools.zsh`
- `dot_config/zsh/_cache.zsh`
- `dot_local/bin/executable_domus`
- `dot_local/bin/executable_domus-packages`
- `dot_config/ai-context/scripts/executable_storage-lifecycle-audit`
- `README.md`
- `docs/DOMUS_CLI.md`
- `docs/EXTERNAL_DRIVE.md`
- `docs/ORGANIZATION_STRATEGY.md`
- `docs/STORAGE_LIFECYCLE.md`
- `tests/test-domus-cli.bats`
- `tests/test-domus-packages.bats`

The transcript evidence shows this work was prompted by noisy Atuin/cursor
behavior, Homebrew/package lifecycle preflights, and storage preflight blockers.
The exact package and local-environment details remain in private local command
output and should not be copied into public artifacts.

## Executor Criteria

`DOMUS-PREFLIGHT-NOISE-01` executor criteria:

- Work in the Domus owner checkout, not this Limen planner branch.
- Preserve the existing dirty Domus worktree before changing it.
- Keep Atuin on explicit search; do not let Up Arrow TUI probing add cursor
  noise in agent or PTY surfaces.
- Cache zsh init output by both binary mtime and init command signature, so a
  command change invalidates the cache.
- Update Domus docs and tests for the changed shell behavior.
- Do not run mutating Homebrew commands as part of this packet.

`DOMUS-PREFLIGHT-NOISE-02` executor criteria:

- `domus packages review --json` remains read-only and emits machine-readable
  blocker state.
- `domus up --dry-run` runs package and storage preflights first.
- `domus up --dry-run` does not call `brew outdated` when a preflight blocks.
- `domus up` does not run `brew update`, `brew upgrade --greedy`,
  `brew cleanup`, or `brew doctor` until package and storage preflights pass.
- Full `domus up` remains a local operator action; do not trigger it from Limen
  dispatch.

`DOMUS-PREFLIGHT-NOISE-03` executor criteria:

- Record Domus as a blocked local hygiene stream when its preflights fail.
- Continue selecting non-blocked product/revenue streams from the same
  current-session fanout.
- Do not mark the whole fanout, product ledger, or conductor selection blocked
  because this Domus stream is blocked.
- Route any follow-up executor only with owner repo, worktree/branch, predicate,
  and expected receipt.

## Verification Predicates

Domus owner predicates:

```bash
git -C /Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629 diff --check
git -C /Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629 status --short
cd /Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629 && bats tests/test-domus-cli.bats tests/test-domus-packages.bats
cd /Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629 && ./dot_local/bin/executable_domus packages review --json
cd /Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629 && STORAGE_LIFECYCLE_AUDIT=/bin/false ./dot_local/bin/executable_domus up --dry-run
```

Installed-shell confirmation predicate after the owner repo is applied locally:

```bash
zsh -lic 'cat ~/.cache/domus/atuin.zsh.cmd 2>/dev/null; bindkey -M emacs | rg "atuin|\\^\\[\\[A|\\^R"'
```

Limen planner predicates:

```bash
rg -n "PLAN-09-5aa10d25|domus-preflight-noise|blocked local work|global product selection" docs/current-session-fanout-plan-09-domus-preflight-noise.md
python3 scripts/validate-task-board.py
```

## Product Selection Rule

When `DOMUS-PREFLIGHT-NOISE-01` or `DOMUS-PREFLIGHT-NOISE-02` blocks on local
storage, package, or Homebrew lifecycle state, the selector should record the
Domus blocker and continue with non-blocked streams such as
`alpha-omega-product-ledger`, `full-fleet-overnight`, `dynamic-substrate`,
`repo-salvage-consolidation`, `money-inbound-seo`, and `contrib-mirror`.

No executor may turn this packet into an outward-facing action, Homebrew
mutation, deploy, or mass merge without the relevant gate.
