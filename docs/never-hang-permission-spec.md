# Never-hang permission spec — the operator's standing requirements

> Synthesized 2026-07-09 by a 10-agent sweep of every session source on the host —
> 1,224 Claude transcript directories, codex/gemini CLI history, memory files, the
> charter, `his-hand-levers.json`, and issues #183/#289/#320/#762 — after the operator
> demanded the fix honor *every* time he has raised this, not just the latest eruption.
> **25 distinct raisings, 2026-06-12 → 2026-07-09.** Verbatim quote ledger (raw prompt
> text never lands in this public repo): `.limen-private/session-corpus/never-hang-permission-ledger.md`.
>
> Implementing artifacts: `scripts/hooks/allow-trusted-cd-git.sh` (an interactive fast path),
> `scripts/tests/allow-trusted-cd-git.test.sh` (its decision matrix), and the fail-closed
> fleet launch contract in `cli/src/limen/dispatch.py`, proven by
> `cli/tests/test_claude_no_modal_dispatch.py`.

## The requirements (R1–R13)

| # | Requirement | Anchors |
|---|-------------|---------|
| R1 | **Zero approval questions for non-destructive work is the default.** A prompt on safe work is a defect. | 2026-06-23, 2026-07-01 sessions; fleet `dontAsk` contract |
| R2 | **The request itself IS the authorization** — never re-gate what was asked for. | charter §Standing Autonomy; memory `asking-is-the-authorization` |
| R3 | **Solve root-to-leaf; a fixed prompt-class must never recur.** Idempotent verification, not incremental patching. | 2026-06-24 TCC directive; `dialogs-silenced.sh` |
| R4 | **Broaden to the whole command class, never re-approve one literal string.** | charter §Standing Autonomy; #762: "Grant broad, root-to-leaf permission rules… so Claude doesn't stall on repeated prompts" |
| R5 | **Fleet/plan/auto agents must not be flooded by the compound-`cd` guard** (upstream #32985; no allow rule suppresses it — only a PreToolUse hook). | lever L-AGENT-BASH-PROMPT (#183); PR #202 |
| R6 | **CLI flags must not silently re-enable prompts.** The fleet launch mode is validated at runtime before Claude starts. | memory `permission-prompts-auto-mode-override` |
| R7 | **Permission state is consistent across all modes** (agents mode, chat, headless, daemon). | 2026-06-21, 2026-07-08 sessions |
| R8 | **Credentials/tokens/secrets are never a chat question** — organ-owned (Wall #320). | 2026-06-25 session; charter §Credentials |
| R9 | **Save/commit/push/deploy/merge/release run autonomously** — shipment steps are not gates. | 2026-06-22/25 sessions; memory `saving-pushing-never-needs-him` |
| R10 | **Never hang/stall a session on a prompt for exempt work** — the hang IS the failure, headless jobs freeze. | 2026-07-09 session; #762 |
| R11 | **Permission hooks/allowlists are version-controlled** — canonical sources in-repo, deployed copies drift-checked. | PR #202 lesson; `dialogs-silenced.sh` 1b |
| R12 | **Reroute blocked steps through compliant paths; never surface a reroutable gate as human work.** | charter §Compliant Gate Reroute |
| R13 | **Verify the real property at the owning invocation path.** Limen can guarantee its daemon/headless launch; interactive and user-started sessions remain separately configured. | memory `macos-tcc-gatekeeper-dialogs-solved` multi-vector rule |

## Calibration — what never asks vs. what still gates

**Never asks (auto-approved):**

- Limen-owned Claude dispatch: the explicit build-tool surface is pre-approved and every
  unresolved permission decision is denied rather than presented to a human.
- Non-destructive, reversible work of any kind, including commit/push/deploy/merge
  (subject only to the website guardrail below).
- Deletion of **disposable session artifacts**: worktrees under `.claude/worktrees`,
  `~/.claude/jobs`, `/tmp`, `$TMPDIR`, and build artifacts strictly *inside* a repo
  under `~/Workspace`/`~/Code`. Reap traffic (`rm -rf <worktree>`,
  `git worktree remove --force`, `git branch -D`) is the dominant prompt source and is
  pre-authorized by path, per #762's "pre-authorize specific destructive operations".
- Read-only diagnostics measured from real prompt fossils: `ps`, `route -n get`,
  `diskutil list|info`, `tmutil` read verbs, `gh repo view|list|clone`.

**Still gates (his deliberate exceptions — do not "fix" these):**

- Destruction of non-disposable things: any path outside the trusted classes, a repo
  root itself, `~`, `/`, the worktrees container as a whole, `main`/`master` branch
  deletion, `git reset --hard`/`git clean` in a **primary** checkout (a fleet reset
  once wiped the live checkout — disposable-roots-only).
- Force-push in any form, remote branch deletion (`push --delete` / `:refspec` /
  `+refspec`) — the charter reroutes these (new branch + superseding PR), it does not
  approve them.
- `sudo`, `dd`, `mkfs`, `shred`, `chmod/chown -R`, `curl|sh`, `xargs rm`,
  `find -delete` — hard class, never hook-approved.
- Website-sensitive merges require green CI first (charter §Merge & Branch Protocol).
- Mass cross-org merges, anything that **sends**, wipes remotes at scale, or spends.

**Irreducible human atoms (accepted as legitimate guardrails, not bugs):**

- Widening the agent's own live permission files (`~/.claude/settings.json`,
  `~/.claude/hooks/*`) is classifier-blocked — the agent lands the canonical repo
  source + hands ONE `install -m 755` paste; `dialogs-silenced.sh` 1b prints it on drift.
- `sudo`-gated OS changes (Application Firewall — lever L-FIREWALL-PROMPT/#289).

## Design consequences (the real no-modal boundary)

1. Limen invokes Claude with `-p --permission-mode dontAsk` and explicitly pre-approves
   file mutation. Bash/network authorization remains in effective user/project/managed
   rules; Limen does not inject a blanket shell grant. Anything unresolved is denied
   instead of invoking a permission callback. The dispatcher can then fail/cascade the
   attempt; it never waits for a person who is not present.
2. `acceptEdits` still prompts for Bash. `auto` reduces prompts but can fall back to them
   after classifier denials. `bypassPermissions` removes the safety boundary and still has
   root/home deletion circuit breakers, so it is not the host fleet contract.
3. Permission rules and hooks remain useful policy layers, but a hook allow does not
   override matching deny/ask rules. In fleet `dontAsk`, those residual policy decisions
   become hard denials. User/managed settings remain untouched.
4. A runtime assertion rejects missing, duplicate, prompt-capable, or bypass modes before
   launch. The same contract is regression-tested through the actual `_agent_argv` seam,
   including model injection and the required mutation tools.
5. Generated Codex workstreams launch with `--ask-for-approval never --sandbox workspace-write`;
   `cli/tests/test_workstream_command.py` proves both interactive and autonomous kickstarts keep
   reversible in-scope work no-modal without widening the sandbox or mutating home configuration.
6. Dispatch adapters realize the same conducted-packet contract without pretending every CLI has
   Codex-shaped controls. Codex places `never` and `workspace-write` before `exec`. Agy uses
   sandboxed print mode with a finite print timeout and never uses its dangerous permission bypass.
   OpenCode uses pure noninteractive `run`, pins `--dir` to the isolated worktree, disables sharing
   and external skills, and applies a post-config deny-by-default permission overlay: repository
   reads/edits remain available (secret env reads excluded), while Bash, subagents, questions,
   external paths, network tools, and plan-mode transitions are denied. This makes OpenCode an
   edit-capable packet lane, not a build/test lane. Pre-spawn assertions reject drift before any
   provider task process starts; unresolved actions deny/cascade rather than open a modal.

## Evolution (no true conflicts)

The trajectory across the 25 raisings: *fix this prompt* (June 12–23) → *fix this
class, root-to-leaf* (June 24–25) → *never be asked at all; only destruction gates,
pre-authorized up front* (July 1–9). The destructive-only boundary is stable across
the whole window; what shrank is tolerance for how it is enforced. The operator's own
`--dangerously-skip-permissions` stopgap (July 3, both `claude` and gemini CLIs) is
broader than his stated calibration. Limen resolves its own unattended lane toward the
stated boundary with a pre-approved build surface plus fail-closed denials. Interactive
Claude remains outside that launch seam and must be configured separately.

## Scope beyond Claude Bash prompts (same demand, other surfaces — already homed)

macOS TCC/Gatekeeper (memory: solved; move/unregister, never click Allow) · macOS
Application Firewall (#289, sudo-gated lever) · 1Password/Touch-ID (`op` opt-in +
service-account lane, `dialogs-silenced.sh` class 2) · claude.ai connector re-auth
(L-IANVA-CLOUD) · Chrome bridge auto-recovery (relaunch + retry, never a parked
blocker) · cross-CLI parity (codex/gemini run with their own skip flags by his hand).
