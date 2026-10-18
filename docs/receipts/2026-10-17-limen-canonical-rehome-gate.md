# Limen canonical-path rehome — gate receipt (2026-10-17)

**Trigger:** every new shell prints
`domus: …/library/engine/organvm/limen is not a checkout; using legacy …/Workspace/limen (fallback expired 2026-09-30T00:00:00Z)`.
**Request:** the operator asked for the migration to be carried out. This receipt records what the live
state allows, what was deliberately not done, and the one step that remains gated.

## What the warning is

`_domus_repository_root()` (`~/.config/zsh/15-env.zsh:109-126`, rendered from Domus) prefers
`$HOME/Workspace/library/engine/organvm/limen` when it holds a `.git`, else falls back to
`$HOME/Workspace/limen`. Past `expires_at` the fallback still works and warns on stderr by design
("keep the live legacy root and say so loudly"). `PORTVS_ROOT` carries the same 2026-09-30 date.
The warning is accurate, not a malfunction: the rehome never happened.

## Live evidence (read 2026-10-17, this host)

| Fact | Evidence |
|---|---|
| Canonical path is not a checkout | `ls -la …/organvm/limen` → only `logs/` (no `.git`) |
| Canonical `logs/` is being written to | `live-checkout-currency.json` 20:02, `tabularius-organ-state.json` 19:44, `vendor-insights/opencode/index.json` 20:01 |
| Registered worktrees on the live checkout | `git worktree list` → 38 entries, each `.git` file holds an absolute pointer, e.g. `gitdir: /Users/4jp/Workspace/limen/.git/worktrees/ab-parent-2938-20261017` |
| Live execution leases on it | `host-work-admission.py status --no-probe` → 5 `codex-worktree-write` leases (pid 13911, valid to ~2026-10-18T18:00Z) + 1 `heavy` lease |
| Live processes with cwd under the legacy path | `lsof -a -d cwd -Fn` → 21 |
| Agent runtime roots live inside the legacy checkout | `CLAUDE_CONFIG_DIR=/Users/4jp/Workspace/limen/.agent-runtime/claude` (config, memory, jobs) |
| Hardcoded legacy consumers | `~/Library/LaunchAgents/com.limen.creds-hydrate.plist` sets `LIMEN_ROOT` and `PYTHONPATH` to `/Users/4jp/Workspace/limen` |
| Declared gate is red | `docs/continuations/omega-substrate-literal/migration-blockers.json` → `protected-legacy-cwds` ("zero active CWD consumers") blocks "repository rehome" |
| Tooling named by the continuation is absent | `scripts/substrate-convergence.py`, `scripts/check-substrate-paths.py` do not exist on `main`; the named PORTVS manifest worktree is gone (manifest now at `4444J99/portvs/governance/workspace-manifest.yaml`) |

## Why a move or clone was not done

- **`mv` now** — breaks the absolute `gitdir:` pointer of all 38 worktrees, deletes the cwd and the config/memory
  root out from under 21 live processes (this session included), and crosses
  `omega-substrate-literal/README.md` § Prohibitions ("Do not move or reap a path used by a live Claude,
  Codex, or other provider process"). `S0-coordinator-writer.txt` records that the expired allowance
  "does not authorize a broad migration".
- **Clone / second worktree at the canonical path** — the resolver would flip `LIMEN_ROOT` on the next shell,
  splitting beats and launchers between two roots while every lease, worktree and runtime root stays in legacy.
  `15-env.zsh:129-131` states a provisioned canonical clone is not authoritative until the owner migrates.
- **Extending `expires_at`** — the warning is the designed loud signal; silencing it is manufacturing green
  (AGENTS.md "Green is additive").

## Findings to own

1. **Split-brain writer.** Something exports `LIMEN_ROOT` = canonical and writes beat/sensor state into the
   non-checkout directory today. Nothing in this repo composes that path (`grep engine/organvm` over
   `scripts/ cli/src/ institutio/ mcp/ web/worker/` → no hits), and `launchctl getenv LIMEN_ROOT`, `~/.zshenv`,
   `~/.limen.env` and the LaunchAgents do not set it. The likely source is an agent/session env that
   defaults to `${LIMEN_ROOT:-$WORKSPACE_ROOT/library/engine/organvm/limen}` (the continuation capsule launcher
   uses exactly that expression). Effect: `scripts/check-live-checkout.py` reports
   `state: unverifiable-here` for the canonical root, so the live-checkout-currency receipt there is blind.
   The directory must be preserved, not deleted, and must be moved aside before the rehome (a populated
   target blocks the move).
2. **Continuation tooling gap.** The convergence/path-audit scripts the Omega capsule says to run are not in
   `main`; the terminal predicate for the rehome cannot currently be executed.

## Executable rehome procedure (run only at zero active CWD consumers)

Preconditions — all must hold; stop at the first that fails:

```bash
python3 scripts/host-work-admission.py status --no-probe     # no codex-worktree-write / heavy leases
git -C "$HOME/Workspace/limen" worktree list                  # every worktree clean + pushed, or preserved by receipt
lsof -a -d cwd -Fn                                            # zero cwd under $HOME/Workspace/limen
```

Steps:

1. Preserve the stray canonical directory (it is runtime state, never delete it):
   `mv "$HOME/Workspace/library/engine/organvm/limen" "$LIMEN_CUSTODY_STAGING_ROOT/limen-canonical-logs-$(date -u +%Y%m%dT%H%M%SZ)"`
2. Re-render consumers from their Domus source (never hand-edit deployed files): the
   `com.limen.creds-hydrate` plist, the agent-runtime roots (`LIMEN_AGENT_RUNTIME_ROOT`, `CLAUDE_CONFIG_DIR`,
   `CODEX_HOME`, `GEMINI_CLI_HOME`) and the `~/.local/share/limen/current` shim, then `chezmoi apply`.
3. `mv "$HOME/Workspace/limen" "$HOME/Workspace/library/engine/organvm/limen"`.
4. From the new root, repair every worktree pointer:
   `git -C "$HOME/Workspace/library/engine/organvm/limen" worktree repair <each worktree path>…`
   then `git worktree list` must show no `prunable` entries.
5. Restore `logs/` runtime state from step 1 if still wanted, then confirm
   `python3 scripts/check-live-checkout.py` reports `current` and a fresh shell prints no `domus:` warning.
6. Two consecutive bare-exit-0 runs of the session closeout predicate.

## Disposition

- Shell warning: **accepted as accurate**; it clears only when step 3 lands.
- Rehome (steps 1–6): **BLOCKED: quiesce every session with cwd/lease under `~/Workspace/limen`
  (5 Codex leases to ~2026-10-18T18:00Z, 21 cwd consumers) and re-render the Domus-owned consumers.**
  Filed under the existing owner `L-CONTAINER-CUTOVER` / `docs/continuations/omega-substrate-literal/migration-blockers.json`
  (`protected-legacy-cwds`); not re-surfaced.
- Findings 1–2: carried by this receipt; the split-brain writer and the missing convergence scripts are
  follow-up engineering for the Omega continuation owner.
