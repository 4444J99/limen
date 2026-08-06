# Bind the session entry phase — every session opens in PLAN, and a plan carries an issue and a PR

Issue: #1843
PR: #1846

## Context

The operator's ask: *"every session, unless this is illogical, begins with a planning phase … a plan
should always be implemented, and a GitHub issue should be logged, a PR should be open."*

This is not a new capability. It is the **Phase-2 gate that `session-phases.yaml` left open.**

`~/.config/ai-context/session-phases.yaml` (authored 2026-05-27, the canonical cross-agent surface)
already declares the full 12-phase lifecycle — `explore → plan → branch → code → verify → push →
wait → review → amend → merge → closeout` — with stages FRAME/SHAPE/BUILD/PROVE/SHIP/FINISH, per-agent
adapters, and the `plan` phase's `produces:` contract. It then parks itself:

```yaml
# Phase 1 (this version): advisory + warn-only. No phase-mismatch hard-blocks.
# Phase 2 gate: 30+ sessions of empirical use → decide which phases warrant … warnings
out_of_scope:
  - "Hard-block on phase mismatch (Phase 2 gate; advisory-only in Phase 1)"
```

Ten weeks and far more than 30 sessions later, the ceremony is fully *declared* and nowhere *bound*.
Three specific unbound joints:

- **No entry binding.** `~/.claude/settings.json` sets `permissions.defaultMode: "auto"`. Every
  session opens in the BUILD stage; the `plan` phase is reachable only by the operator remembering
  to reach for it. The registry's own `enforcement: warn` is honest about this.
- **No chain binding.** The `plan` phase `produces:` a dated plan file and stops. Nothing carries
  that file to a GitHub issue or a PR. Evidence: 19 plans in `docs/plans/`, no `INDEX.md`, no issue
  linkage in any of them, and no way to answer "which plans were actually implemented?"
- **No predicate.** Compliance lives in prose and memory — precisely the form this repo's charter
  rejects (§ Definition of Done: *"deliver an executable predicate … never hand-maintained prose"*).

Limen already binds the *other* half of the same doctrine: `mode:plan-only` derives Opus and
`mode:build-from-plan` is capped cheap (#1840, `model_selection.tier_for_classes`), and
`plan_handoff.py` emits a model-neutral receipt between them. **That split is bound for dispatched
fleet tasks and unbound for the interactive sessions where the operator actually works.** This plan
closes the asymmetry.

## Resolved design decisions

- **D1 — the entry binding is `permissions.defaultMode: "plan"` in the project's committed
  `.claude/settings.json`**, not a hook. A SessionStart hook cannot change the permission mode (its
  only lever is context injection), and no prose reliably out-competes a settings default. Project
  scope beats the user-global `auto` by Claude Code's precedence order, and travels with the repo.

- **D2 — the fleet is structurally immune; verified, not assumed.** `dispatch.py` launches every
  Claude lane with an explicit `--permission-mode dontAsk` **and validates it at launch**
  (`_assert_claude_launch_contract` → `ClaudeLaunchContractError`, dispatch.py:2788: *"Claude fleet
  launch must use exactly one dontAsk permission mode"*). A CLI flag outranks settings, so no
  headless lane, beat rung, or scheduled agent can be stalled by this default. This was the one real
  risk in the change and it is closed by a contract that already exists.

- **D3 — "unless this is illogical" is realized as a cheap, recorded escape, not as a carve-out
  list.** Enumerating exempt session shapes would be hand-maintained prose that decays. Instead:
  plan mode costs a read-only session *nothing* (it never needs to leave), and a trivial fix leaves
  it in one action. The transcript records every `permissionMode` transition, and
  `scripts/harness-root-probe.py` already reads that field — so the escape is observable rather than
  invisible. **The default binds; the exit is one keystroke; the exit is recorded.**

- **D4 — the chain gets one command, because the side door is always the cheaper door.** The
  `ship-docs.sh` lesson is explicit in this repo's history: the `docs:` class bypassed PRs on 35 of
  40 commits *until a single command made the front door cheaper than the side door*. A plan → issue
  → PR chain that costs three manual steps will be skipped the same way. Hence
  `scripts/session-plan.py open <slug> --issue N`: writes the plan, ships the branch and PR.

- **D4a — but the organ never writes to GitHub in-process** (revised mid-implementation, when
  `check-effectors.py` failed the first cut). Class C of the OUTBOUND-EFFECTORS gate is an AST walk
  that catches outward `gh` argv built inside Python: a `PreToolUse(Bash)` hook sees a command
  *string*, so it can never see `subprocess.run(["gh", "issue", "create", …])`. Three new findings
  fired. The registry's baseline is explicitly **shrink-only**, so adding this organ to the blind
  list — even though `sync-censor-issues.py` and `sync-hishand-issues.py` are already on it for the
  identical action — would grow exactly what the gate exists to shrink. So `open` without `--issue`
  **prints** the precise `gh issue create` and exits 2; `close` prints the `gh issue close`. One
  extra step buys every outward write staying on the guarded rail. Note the rejected shortcut:
  the scanner walks *Python only*, so moving the same call into a bash helper would silence it
  while the blindness stayed identical — gate evasion, which the charter forbids outright.

- **D5 — the predicate reads the plan file, not GitHub, by default.** Plans carry `Issue:` / `PR:`
  lines stamped by the organ. A gate that needs network is a gate that fails offline and gets
  disabled; `--live` opts into `gh` cross-checking. Same fail-open discipline as `session-orient.sh`.

- **D6 — the 19 legacy plans are baselined, not retro-fitted.** `institutio/governance/`
  already carries six `*-baseline.txt` files for exactly this ratchet pattern (orphan-params,
  test-hygiene, ungated-effectors…). New plans are held; history is recorded, not rewritten.

- **D7 — the plan home is `docs/plans/`, not `.claude/plans/`.** The canonical registry names
  `<repo>/.claude/plans/`; limen diverged to `docs/plans/` and the divergence is load-bearing
  (`check-session-streams.py` reads `docs/{plans,continuations}/`, and `docs/` is what publishes).
  Repo-local convention wins; the divergence is declared here rather than silently tolerated.

- **D8 — the registry is amended additively (Universal Rule #3).** `session-phases.yaml` gains an
  `entry:` block and `phase: 2` for the entry binding *only*. Every other phase stays
  `enforcement: warn`. Advancing one joint is not a licence to hard-block the whole lifecycle.

## Steps

1. **Entry binding** — `.claude/settings.json`: `permissions.defaultMode: "plan"`.
2. **The chain organ** — `scripts/session-plan.py`: `open` (plan file + `plan`-labelled issue +
   branch/PR via `ship-docs.sh`), `close` (stamp implementing PR), `audit` (chain state per plan).
3. **The predicate** — `scripts/check-session-phase.py` + `institutio/governance/session-plan-baseline.txt`;
   registered as gate `session-phase` in `institutio/governance/gates.yaml` so `verify-scoped.sh`
   picks it up on any `docs/plans/**` change and `check-gates.py` holds it in parity.
4. **Orientation** — `session-orient.py` gains `section_phase()`: names the entry phase, the one
   command, and any plans whose chain is open.
5. **Doctrine** — a `Session Phase Entry` section in `CLAUDE.md` pointing at the canonical registry;
   `docs/agent-instruction-standard.md` untouched (no new instruction surface).
6. **Canonical amendment** — the chezmoi source of `session-phases.yaml` gains the `entry:` block
   (cross-repo; that repo's direct-master convention governs, per its own `rule_clarifications`).

## Premortem

- **It annoys more than it helps on trivial sessions.** Mitigated by D3 (one-keystroke exit) and by
  the fact that read-only sessions pay nothing. If it still grates, `defaultMode` is one line to
  revert — the organ and predicate keep their value independently.
- **`ship-docs.sh` refuses the plan file.** It refuses deploy-trigger paths; `docs/plans/**` is not
  one. Verified against `gates.yaml:deploy_triggers` before wiring.
- **The predicate red-checks every PR that touches a plan.** Bounded by the baseline (D6) and by
  `paths:` scoping — a plan-less PR never runs it.
- **Two plan homes drift further apart.** D7 declares the divergence; the predicate scans only
  `docs/plans/`, so `.claude/plans/` (session logs/handoffs, last written 2026-06) stays legacy.

## Verification

- `python3 scripts/check-session-phase.py` → exit 0 (baseline clean).
- `python3 scripts/check-gates.py` → registry ↔ workflow parity holds with the new gate.
- `python3 scripts/session-plan.py audit` → this plan's own chain resolves.
- `python3 -m ruff check scripts/session-plan.py scripts/check-session-phase.py`
- `bash scripts/verify-scoped.sh` → green on the diff.
- **Self-referential proof:** this plan file, its issue, and its PR are themselves produced by the
  chain being built. If the chain does not close on its own plan, it does not work.
