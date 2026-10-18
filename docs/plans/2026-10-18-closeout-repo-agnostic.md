# Make /closeout repo-agnostic

Issue: #2995
PR: (pending)

Implementing PRs (other repos, so not expressible as a Limen `#M`): `4444J99/a-i--skills#50`
(copy A) and `4444J99/domus-genoma-private#505` (copy B). Stamp `PR:` when both land.

## Context

`/closeout` has four copies, and the one Claude actually loads is the least portable:

| Copy | Path (source of truth) | State |
|------|------------------------|-------|
| **A** ai-skills | `4444J99/a-i--skills` → `skills/tools/closeout/SKILL.md` (installed at `~/.local/share/ai-skills/current/distributions/claude/skills/closeout`, symlinked into the Claude/Codex/OpenCode runtime roots) | **What Claude loads** (its description is the one in the skill list). Hardcodes `~/.Codex/plans`, `prompt-atoms.json`, `organvm refresh`, `claude-md-autogen-gate`, IRF/DONE-NNN, `.conductor/active-handoff.md`, `/Users/4jp/Workspace/*.txt`. |
| **B** Domus global entry | `domus-genoma/dot_agents/skills/closeout/SKILL.md.tmpl` → `~/.agents/skills/closeout` | "From any directory", but every path routes through `domus-limen-runtime protocol-root` and Limen's scripts. A non-Limen repo gets Limen's predicate. |
| **C** Limen canonical | `limen/.agents/skills/closeout/SKILL.md` | Limen-specific by design (`no-tasks-on-me.sh`, `reap-branches.py`, `check-live-checkout.py`). **Stays as is.** |
| **D** Limen adapter | `limen/.claude/skills/closeout/SKILL.md` | Pointer to C. **Stays as is.** |

Intended outcome (user decision: "both — Domus should also be generic and speak to what closeout is"):
**A** becomes the one canonical, repo-neutral procedure. **B** becomes a generic, self-describing
global entry that states what a closeout *is* and how a repo's own protocol is discovered, rather than
a Limen-only redirect. **C/D** become the Limen *overlay* by convention, unchanged.

## Design: generic core + discovered overlay

The universal floor (repo-neutral, from the parts of A and C that don't name a repo):

1. **Resolve scope.** Native session id, the real worktree (`git rev-parse --show-toplevel`), and any additional roots for multi-repo sessions. Never adopt a sibling checkout to get a green result.
2. **Discover the repo's own protocol (overlay), in order:** `<root>/.agents/skills/closeout/SKILL.md` (if distinct from this skill) → `<root>/.claude/skills/closeout/SKILL.md` → a "Closeout" section in `<root>/AGENTS.md`/`CLAUDE.md` → a committed `closeout`/`done` predicate (`scripts/closeout*`, `done.sh`, Makefile target). If found, it governs repo-specific steps and the final predicate; this core supplies only the floor below. If none, the floor stands alone.
3. **Read-only inventory:** `git status --short`, branch vs upstream, unpushed commits, stashes, `git worktree list`, open PRs for session branches (`gh pr list --head`, only if `gh` and a remote exist), plans/tasks/issues the session touched in the repo's *own* plan/task location (discovered, never hardcoded).
4. **Home every item** in a durable terminal form: merged, open PR with owner, filed issue/plan/task, or one explicit `BLOCKED: <atom>`. Never batch-close without confirmation; never delete plans (move to the repo's abandoned/archive convention if it has one).
5. **Verify once per changed tree** using the discovered predicate/CI/test target. Read the predicate's own exit code, never a pipeline's.
6. **Evidence-bound status words**, reported separately: *merged* = SHA is ancestor of the fetched default branch; *live* = the running checkout/install contains it; *observed* = runtime evidence of the behavior. No "verified end-to-end" without *observed*.
7. **Handoff** only for unfinished work, written to the repo's existing handoff/continuation owner (e.g. `.conductor/active-handoff.md` if present). No new files unless the overlay asks.
8. **Idempotent fixed point:** run the session predicate twice, both bare exit 0, second run mutates nothing. Emit `CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items` only after that; nothing follows it. Never push/merge beyond the authority the session was given; never touch other sessions' worktrees.

Nothing is deleted. The ORGANVM six-step ritual (plan classification EXECUTED/IN-PROGRESS/ABANDONED,
atom walk, `claude-md-autogen-gate` Step 4.5, `active-handoff`, `CLOSEOUT_SUMMARY.md`, the 90.4%
orphan-rate rationale) moves verbatim to `references/organvm-plan-ledger-overlay.md`, keeping its Step
numbering, and the core names it as an example overlay triggered by the `ORGANVM:AUTO` sentinel in
`CLAUDE.md`. That is the Reliquary rule: relocate with a breadcrumb, never delete.

## Changes

### 1. `4444J99/a-i--skills` (copy A) — PR

No local working checkout exists (`~/.local/share/ai-skills/source` is the installer's cache and must stay clean for `git pull --ff-only`; `chamber_worktrees/.../a-i--skills` is empty). Fresh clone into `~/Workspace/.worktrees/ai-skills-closeout-generic-<date>/` on branch `refactor/closeout-repo-agnostic`, after checking the writer lease.

- `skills/tools/closeout/SKILL.md` — rewrite to the core above. Frontmatter: keep `name: closeout` (must equal dir), `license: MIT`; new description with no `~/.Codex`, CLOSEOUT_SUMMARY, or IRF text; generic tags (`session-management`, `hygiene`, `close-out`, `handoff`); drop `hall-monitor`, `directive-traceability`, `CLOSEOUT_SUMMARY-md`/`abandoned-plans-moved` outputs.
- `skills/tools/closeout/references/organvm-plan-ledger-overlay.md` — the preserved ritual (new file, verbatim content, Step numbers intact).
- `skills/tools/artifact-resurfacing/references/composition-with-closeout.md` and `skills/tools/transcript-promotion/references/composition-with-closeout.md` — they cite closeout "Step 1–6 / 4.5" and `CLOSEOUT_SUMMARY.md`. Re-point those rows at "closeout's plan-ledger overlay (`closeout/references/organvm-plan-ledger-overlay.md`)" so the cross-skill contract stays true.
- Regenerate tracked outputs (`distributions/**`, `skills-registry.json`, `skills-lock.json`) with `scripts/refresh_skill_collections.py`; CI requires them current. Never hand-edit a generated file.

### 2. `domus-genoma` (copy B) — PR

Worktree under `~/Workspace/.worktrees/domus-closeout-generic-<date>/`, branch `refactor/closeout-generic-entry`.

- `dot_agents/skills/closeout/SKILL.md.tmpl` — rewrite as the generic, self-describing entry (~30 lines, **contract only, no commands**, so it cannot drift from A): what a closeout is (proves every obligation of *this session* is homed; session release ≠ task completion ≠ estate health ≠ deletion eligibility), the discovery order from step 2, the evidence-bound status words, the terminal statement, and "detailed procedure: the `closeout` skill from the ai-skills distribution when installed; the floor above is sufficient without it".
- Limen becomes one registered *provider*, not the default: use `{{ .chezmoi.homeDir }}/.local/bin/domus-limen-runtime --root "…" protocol-root` only when the repo is Limen or the session is registered with the Limen conduct broker. Keep the multi-repo v2 guidance (`--scope-root ID=PATH`, `kind: retired` + `limen.scope_retirement.v1`) verbatim, moved under that provider section. Keep the "never claim readiness from an installed-runtime receipt whose payload is missing or changed" guard.
- Keep the existing `{{ .chezmoi.homeDir }}` / `{{ dir .limen_runtime_rel }}` template variables; do not hardcode `/Users/4jp`.

### 3. Limen (C/D) — no edits

C already sits at the overlay discovery path (`.agents/skills/closeout/SKILL.md`), so the new core finds and defers to it in this repo. `check-agent-docs.py` and CLAUDE.md → Closeout Definition keep pointing at C unchanged. Optional follow-up (not in this scope): one line in C naming itself the Limen overlay.

## Reuse

- `scripts/validate_skills.py`, `scripts/refresh_skill_collections.py`, `scripts/validate_generated_dirs.py`, `scripts/skill_health_check.py --skill closeout` (a-i--skills).
- The existing chezmoi template variables and the `domus-limen-runtime protocol-root` contract (Domus).
- Limen's C text for the floor wording (steps 5–8 are already repo-neutral prose).

## Verification

a-i--skills (bare commands, each exit code read directly):
- `python3 scripts/validate_skills.py --collection example --unique --check-links` → 0
- `python3 scripts/refresh_skill_collections.py` then `python3 scripts/validate_generated_dirs.py` → 0
- `python3 scripts/skill_health_check.py --skill closeout` → no new warnings
- `python3 -m pytest` → pass
- `grep -nE "Codex|prompt-atoms|organvm|ORGANVM|IRF-|DONE-[0-9N]|CLOSEOUT_SUMMARY|/Users/4jp" skills/tools/closeout/SKILL.md` → only the deliberate opt-in pointer to the overlay (Step 2 and Related); no procedural dependency, no home path. (Amended during execution: "no matches" was too strict, since the core must be able to name the overlay it defers ORGANVM repos to.)

Domus:
- `chezmoi execute-template < dot_agents/skills/closeout/SKILL.md.tmpl` renders with no unresolved variables; `chezmoi diff ~/.agents/skills/closeout` shows only the intended change (Rule #6/#10: diff before apply).

Behavioral (the real test is a non-Limen repo):
- In a scratch git repo with no overlay: the core completes on the floor alone and never invokes a Limen/organvm path.
- In `/Users/4jp/Workspace/limen`: the core discovers C and defers to it (`no-tasks-on-me.sh` is still the final predicate).

Status words to report separately at the end: **merged** (each PR's SHA on its default branch), **live** (installed `current/distributions/claude/skills/closeout/SKILL.md` and `~/.agents/skills/closeout/SKILL.md` match merged source — needs `git pull --ff-only` + `python3 scripts/skills_install.py install` in the ai-skills cache via the Domus-owned update, and `chezmoi apply` for B), **observed** (the skill list shows the new description in a fresh session).

## Merge path

Each repo's merge rail is derived from its registry at merge time (fast-lane `gh pr merge … --squash --match-head-commit <SHA>`, otherwise one `scripts/merge-drain.py` submission); no polling, no `--admin`, no force-push. Residual reviewer findings become issues; at most two fix-on-review rounds.
