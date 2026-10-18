# Plan v3: reconcile agent-surface containment (Claude lens) — status, delta, owners

Issue: #2848
PR: (pending)

- **Date**: 2026-10-18
- **Supersedes nothing.** Reconciles `docs/plans/2026-10-17-unify-contain-agent-surfaces-v2.md` (limen) and OpenCode's
  PR #502 plan (`domus-genoma-private`, `.claude/plans/2026-10-17-agent-surface-unification.md`) against **live disk**.
- `PR: (pending)` is the PR that will *implement* the remaining items, not the PR that ships this document.

## Context

The request repeats, for Claude, what OpenCode answered earlier today: where does the agent exist on disk, what
customizes it, does it read `.agent-runtime`, and how do we contain every provider's files. Two plans already own the
architecture (4-ring model, doorways, custody-first, 8-consumer matrix). A third architecture would fork parallel
substrate. The deliverable is: **what landed, what remains, who owns it.**

## Answers (evidence from the 2026-10-18 session)

### Does Claude get context from `.agent-runtime`? **Yes, by design** (opposite of OpenCode)
`$CLAUDE_CONFIG_DIR` = `.agent-runtime/claude/`. The session loaded `claude/CLAUDE.md` (the rendered adapter, imports
`~/AGENTS.md`) and `claude/projects/-Users-4jp-Workspace-limen/memory/MEMORY.md` from there, plus the repo's
`CLAUDE.md`/`AGENTS.md`. OpenCode instead fell through to `~/AGENTS.md` for want of a shim; that gap is closed
(`~/.config/opencode/AGENTS.md` is live; healthcheck 28 → 42 ok). `~/.claude` is only a doorway to the retired
`claude/legacy-home`; live config does not read it.

### Where Claude exists locally, by ring
| Ring | Path | Size | Contained? |
|---|---|---|---|
| 1 live runtime | `.agent-runtime/claude/` (settings, CLAUDE.md, agents, skills, plugins, projects, memory, history) | 2.4 GB (projects 1.9 GB) | Yes — `$CLAUDE_CONFIG_DIR` |
| 1 retired layer | `claude/legacy-home/` ← `~/.claude`; `legacy-home.json` ← `~/.claude.json` | 331 MB (plans 112, file-history 141) | Doorways in place; retirement gated (Step 8) |
| 2 OS-fixed | `~/Library/Application Support/Claude` (Desktop) | **12 GB; `vm_bundles` 11 GB** | Never symlinked (TCC/codesign); `domus-agent-maintain` |
| 2 OS-fixed | `~/.local/share/claude` (native installer: `versions/`, `ClaudeCode.app`) | 495 MB | Fixed by native install; never move |
| 3 per-repo | `limen/.claude/` (settings, 3 agents, 8 skills, plans, worktrees) + ~190 `.claude/.codex/.gemini` hits across worktrees | — | Tracked project surface; die with their worktree |
| shared | `~/AGENTS.md`, `~/.config/{ai-context,ai-instructions,ai-skills,ai-tools,agents}`, `~/.agents/{skills,teamwork}` | — | Ring 0 liturgy/catalog, chezmoi-managed |

### Claude customizations (two layers)
- **User layer** (`claude/settings.json`, chezmoi-rendered): defaultMode `auto`, model `sonnet`; 7 hooks over 4 events
  (SessionStart ×2, PreToolUse guard-dispatch ×3 matchers, PostToolUse `domus-agent-hook`, SessionEnd closeout);
  16 enabled plugins; 6 env keys (names only); statusline script; 3 agents (builder/scanner/verifier); 4 skill symlinks;
  `CLAUDE.md` adapter.
- **Project layer** (`limen/.claude/`): defaultMode **`plan`** (the repo's entry binding), 55 allow rules, 4 hook events,
  agents `scan/synth/verify`, 8 repo skills, `settings.local.json`.
- Precedence: project overrides user for `defaultMode` — which is why sessions here open in plan.

## Reconciliation of v2 + #502 against live state

| Item | Evidence | Status |
|---|---|---|
| v2 1A `~/.claude.json` relink | `~/.claude.json` is a symlink → `legacy-home.json` | **landed** |
| v2 1B `~/.local/share/codex` custody | no `codex` in `~/.local/share`; `domus-agent-runtime check` ok, 0 unauthorized legacy roots | **landed** |
| v2 4 eleven home doorways | all present as symlinks in `ls -la ~` | **landed** |
| #502 defect 2 OpenCode shim | `~/.config/opencode/AGENTS.md` live; healthcheck 42 ok / 0 fail | **landed** |
| v2 2 Antigravity cutover | `antigravity/` staged; `~/.gemini` still → `legacy-home` | **gated** (rollout Step 8) — no change proposed |
| v2 3 skills reconcile | ≥3 roots: `~/.agents/skills` (30), `.agent-runtime/.agents/skills` (31), `shared/skills-catalog` (69 + registry) | **open** |
| `legacy-home` retirement | 331 MB still behind doorways | **gated** (Step 8) — observe only |
| home-guard | `FAIL`, 1 violation: `.grokbot` route blocked, destination exists | **open** |

Caveat: "landed" rests on filesystem reads, not receipts; closeout re-proves each with its predicate.

## Remaining work and execution owner (one owner per item)

1. **`.grokbot` — domus-genoma PR (`home-surface.yaml`).** Live read corrects the diagnosis: `~/.grokbot` is an *active*
   app (daemon log and supervisor written minutes before the read), not residue. The declared "route to
   `home-residue/.grokbot`" already ran once (residue copy dated Oct 17 13:09) and the app recreated the dir. Fix:
   reclassify from `route_pending` to an `application` `preserve-and-link` doorway → `.agent-runtime/aux/grokbot`,
   guarded by `_exact_process_active()`; reconcile the two trees by inspect-then-merge (never delete, never overwrite
   the residue copy). Linking needs the daemon stopped — flag that sequencing constraint; do not kill it.
2. **Skills (v2 Phase 3) — domus-genoma PR.** Content-hash inventory across the three roots; register survivors in
   `skills-registry.json`; no pruning before Step 8. Close the cross-provider leak seen from Claude's side: two of four
   `claude/skills/*` links resolve into Claude-named paths (`distributions/claude/…`, `limen/.claude/skills/vendor-insights`).
   Canonical home = `ai-skills/` with per-provider fan-out links, never one provider's namespace.
3. **`vm_bundles` 11 GB — limen (owner + predicate).** Same class as OpenCode's `opencode.db`: large, monotonic, no
   named prune owner. File `domus-agent-maintain` as owner with a bounded prune predicate; do **not** symlink (Ring 2).
4. **`legacy-home` — no action** until Step 8; record its 112 MB `plans/` and 141 MB `file-history` as
   custody-before-retire inputs (v2 §4 pattern).
5. **Loose files in the runtime root — limen.** `.agent-runtime/` top level holds four OpenCode session exports
   (~1.8 MB), `correction_drafts/`, `scratch/`, `.recode/`. Quota-bound vendor state is the wrong home for transcripts;
   route to `$LIMEN_CUSTODY_STAGING_ROOT` or the transcript corpus with receipts. (The "contain all *files*" half that
   v2 did not cover.)
6. **Out of scope:** per-repo `.claude/` dirs and worktree copies (v2 disposition #8, separate opt-in track),
   Library/Application Support moves, `~/.agents/teamwork`, and #502's human gate (GitHub/Serena/Jupyter MCP vs `ianva`
   for OpenCode) — OpenCode's gate, already filed; not re-raised.

## Execution rails
- Writer lease first: `python3 scripts/host-work-admission.py status --no-probe` should report `allowed: true`. It
  reported `false` (swap-fraction, 14 Codex leases) on 2026-10-18; this docs-only worktree was created under an explicit
  operator override. Implementation items 1–5 do **not** inherit that override.
- Items 1–2 → one `domus-genoma` worktree PR each; items 3, 5 → one limen docs/predicate PR; one commit per concern.
- Every move writes a rollback receipt under `~/.local/state/domus/home-residue/` (v2 §7 contract).
- Do not dump `env`; the guard denies it. The runtime root is known from `domus-agent-runtime check`.

## Verification (predicates, not prose)
- `domus-home-guard --check` exits 0 (read its own exit code, no pipe).
- `domus-agent-runtime check` stays `ok`, 0 unauthorized legacy roots.
- `agent-surface-healthcheck` stays ≥ 42 ok / 0 fail. Per #502 defect 4 it cannot see directories/globs/symlink
  targets, so green is not proof for skills — add a skills-root census check as part of item 2.
- `scripts/check-session-phase.py` exits 0 for this plan (Issue + PR lines present).
- Re-run the 8-consumer matrix (v2 §6) rows for Claude Code, Claude Desktop, and OpenCode after items 1–2.
