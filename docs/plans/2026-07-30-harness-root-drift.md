# The Harness Root Moved — Declare It, Resolve It Once, Sense It

*From "why can't I make plans in Fable" to the undeclared external dependency underneath it.*

## Context

Plan mode has been failing. Diagnosing it cost a disassembly of the Claude Code binary, two wrong
hypotheses from me, and a structural sweep of 258 transcripts. The measured fault:

| Metric | Value |
|---|---|
| `ExitPlanMode` calls, all time | 37 |
| Rejected (`is_error`) | **15 — 41% failure rate** |
| Fable / Opus failure rate | **58% (14/24) · 8% (1/13)** |
| Worst session (`c304e87f`) | 8 consecutive rejections over 2h07m |
| Retry after rejection clears it? | **No** — absorbing state, observed 4× in `cc44ac7a` (retry 14s later → same failure) |
| `EnterPlanMode` invocations, all time | **0** — it is `shouldDefer:true`, so the documented recovery path has never run |
| Non-plan mutations while `mode=plan` | **0** — the read-only guarantee held |
| Plan slugs written to *both* shared and worktree paths | 2 |

**Reproduced live while writing this plan.** The first write to the shared-checkout plan path was
admitted; every subsequent write and edit was denied by the harness worktree-isolation guard, in one
unbroken session. That is the absorbing-state signature, on demand.

### The root cause is not plan mode

**The Claude Code harness relocated its per-session runtime tree from `~/.claude/**` to
`<repo>/.agent-runtime/claude/**`. Every limen surface that consumes harness state still points at
the old location, which is now empty. Nothing detected the move.**

Verified: `~/.claude/projects/*/*.jsonl` → **0 files**.
`.agent-runtime/claude/projects/` → **258 files, 194 MB**.
Repo-wide grep for `agent-runtime` across `cli/`, `scripts/`, `institutio/` → **zero consumers**
(the single hit is an unrelated repo name in `institutio/github/estate.yaml:428`).

### Blast radius — all verified, all silent

| Surface | Hard-coded | Consequence |
|---|---|---|
| `cli/src/limen/action_admission.py:634-639` | `~/.claude/{plans,jobs,projects}` | `harness_session_write()` returns False for today's plan writes → they fall through to plan-only-mutation / shared-checkout denial. **The presenting bug.** |
| `cli/src/limen/vigilia/continuity.py:140` | `~/.claude/projects/*/*.jsonl` | Globs an empty dir; `logs/vigilia/status.json` still reports `"status": "ok"` against a transcript that no longer exists. **Organ blind, reporting healthy.** |
| `cli/src/limen/prompt_sources.py:1327-1330,1428` | `(".claude","projects"/"plans"/"tasks")` | Prompt-atom corpus starving — this feeds the live `prompt-corpus-control` sensor. |
| `scripts/claude-workflow-guard.py:324,335` | `~/.claude/projects` | The untiered-fan-out audit can't find sessions → the SessionEnd check silently no-ops. |
| `scripts/claude-usage.py:87` | same (**but** via `LIMEN_CLAUDE_TRANSCRIPTS_DIR` override) | Usage accounting wrong by default — yet this file already has the correct shape. |
| `scripts/{capture-session-claim,codex-claude-daily-review,corpus-feed,agent-session-full-stack-review}.py` | same | Session-claim capture, daily review, corpus feed, stack review — all reading an empty tree. |

**PR #1521 (`84e0d9ab`, 2026-07-24, "unbreak plan mode") did not regress — the ground moved under
it.** Same operator-reported symptom, six days later, wearing a different path. That is the signature
of an undeclared dependency: fixing the instance cannot prevent the recurrence.

### The generalization

This system declares everything it governs — GATES, SENSORS, PARAMETERS, ideal forms, levers. It
declares **nothing** about the external substrate it reads from. `~/.claude` is hard-coded in ten
places with no single resolver, no declared parameter, and no probe that fails when it goes empty.
Meanwhile 194 MB of high-fidelity telemetry — every tool call, model id, permission mode, error, and
compaction boundary this fleet has ever produced — sits unread, and `.gitignore:14` ignores it.

**Intended outcome:** one declared harness root, resolved in exactly one place, consumed everywhere,
sensed at beat cadence — so the next relocation is a red check instead of a furious operator.

## Scope boundary — what is not ours

Three defects are inside the Claude Code binary. They get worked around and cited inline at the
workaround site, per this repo's existing convention (`cli/src/limen/dispatch.py:3671`,
`ianva/src/ianva/creds.py:3`):

- `toolPermissionContext.mode` — read by both the write gate and `ExitPlanMode.validateInput` — can
  desync from the session `permissionMode` the UI drives, and re-entering plan mode does not resync it.
- `EnterPlanMode` is `shouldDefer:true`, so the error's own recovery advice can never execute.
- The worktree write-redirect is the harness's built-in worktree-isolation guard (named as such in
  the Claude Code changelog); confirmed **no** user hook implements it.

---

## Alpha → Omega

### α — One resolver, declared

Add `harness_root()` to a single module in `cli/src/limen/` (natural home beside
`session_sources.py`), resolving in order: `LIMEN_CLAUDE_HARNESS_ROOT` env → `<LIMEN_ROOT>/.agent-runtime/claude`
if it holds transcripts → `~/.claude`. Returns the root plus its `projects`/`plans`/`jobs` children.

Declare `CLAUDE_HARNESS_ROOT` in `institutio/governance/parameters.yaml` with
`env: LIMEN_CLAUDE_HARNESS_ROOT`, `owner: continuity`. **Required** — check C of `check-sensors.py`
rejects any sensor whose gate/env is undeclared, and this is the parameter panel's job regardless.

The shape already exists and is already correct in exactly one place — `scripts/claude-usage.py:87`'s
`os.environ.get("LIMEN_CLAUDE_TRANSCRIPTS_DIR", <default>)`. Generalize *that*; do not invent a new one.

### β — Repoint every consumer

Mechanical, one pattern across the ten sites in the blast-radius table: replace the literal
`Path.home() / ".claude" / …` with the resolver. Two need more than substitution:

- **`action_admission.py::_harness_session_dirs()`** — must return **both** roots, not one. A session
  may legitimately write to either; denying the live one is the presenting bug, and dropping the
  legacy one breaks any session still using it. Preserve the existing `path_within` symlink semantics
  exactly — the docstring's threat model (a symlink planted under a session dir resolving outside it)
  still holds and must keep holding.
- **`continuity.py:140`** — `CONTINUITY_TRANSCRIPT_GLOB`'s declared default becomes resolver-derived.
  `check-sensors.py` check E requires declared defaults to byte-match wherever they appear, so a
  resolver-derived default must not leave a stale literal behind.

### γ — Sense it

One entry in `institutio/governance/sensors.yaml`. The registry contract is strict and known:
`section`/`title`/`gate`/`default`/`source`/`owner`/`steps[{command,severity,escalation}]`; the gate
must be declared in `parameters.yaml` (check C); `source: [heartbeat]` **requires** `cadence` or check
F rejects it as unreachable; `severity: advisory` keeps the beat fail-open.

The sensor asserts two things:

1. **Root liveness** — the resolved harness root contains transcripts. Empty while a sibling candidate
   holds many *is* the relocation signature; escalate by name.
2. **Plan-mode fault signatures** — detector already prototyped and validated against the corpus,
   matching on JSON structure rather than error text (substring matching produced 3 false positives
   from sessions merely *discussing* the error):
   - **A** — `tool_result.is_error` whose `tool_use_id` resolves to `ExitPlanMode`. 15 true / 0 false.
   - **B** — file mutation while last recorded `permissionMode == "plan"`, excluding the session's own
     plan file (plan-file writes are legitimate). Currently 0 — the tripwire for the *dangerous* half.
   - **C** — one plan slug written to both a shared and a `.claude/worktrees/` path. 2 true positives.

   Bucket failures by `message.model`. The Fable/Opus split was the single most diagnostic number and
   surfaces only when failures are model-attributed.

Constraints from the prototype: incremental by byte-offset per file — re-parsing 194 MB every beat is
unacceptable on a 16 GB machine with logged jetsam kills. Read-only; never mutates transcripts.

**Extend, do not fork.** `vigilia/continuity.py` already parses these transcripts row-by-row with
`tool_use`/`tool_result` handling (`_row_text`) and is already beat-wired via `python3 -m limen.vigilia
beat`. Signature detection belongs there or beside it — `prompt_sources.py` is already the second
walker, and a third would be the parallel substrate the charter forbids. Nothing in the repo reads
`permissionMode` today; that extraction is the one genuinely new piece.

### δ — Mitigate the upstream half

- Make `EnterPlanMode` reachable: a standing instruction to load it via ToolSearch on entering plan
  mode, so the documented recovery path can actually execute.
- Route plan-heavy work to Opus while the desync is unfixed — 7.5× lower failure rate. A routing
  decision `cli/src/limen/model_selection.py` already owns, not a capability loss.

### ε — Home the findings

Three surfaces, each already canonical — no new substrate:

- **`censor/precedents.jsonl`** — a `doc_code_drift` precedent: *a fix pinned to an external product's
  internal layout is not durable; declare the dependency or it recurs.* Schema
  `id/ts/type/subject/outcome/reversible/action/authorised_by/review`, where `review` states the
  empirical-close condition. No plan-mode precedent exists today.
- **`docs/IDEAL-FORMS-LEDGER.md`** + machine twin `institutio/governance/ideal-forms.yaml` — an `IF-`
  entry for *external substrate is declared, resolved once, and sensed*. Sits beside the existing
  `IF-SESSION-NON-CONTENTION` (Status OPEN), same neighborhood.
- **The stranded note** — `plan-mode-worktree-shadow-bug.md`, currently untracked inside
  `.claude/worktrees/session-stream-cartridges/`: a Rule #2 violation produced by a system whose first
  rule is "nothing local-only." Fold its content into the precedent; delete the orphan.

Not a lever. Levers are irreducible human atoms; everything here is agent-fixable, so per the charter
it is done and reported, not surfaced.

### ω — Fixed point

`scripts/verify-scoped.sh` green on the diff, plus:

- Replay the full corpus → A reports exactly **15**, B **0**, C **2**.
- Synthetic fault injection per signature (fixtures, not live transcripts) → all three fire.
- Point the resolver at an empty root → the liveness check **fails**. This is the test that would have
  caught the original relocation, and the one that matters most.
- Re-run the beat → no state change.

---

## Verification

- `python3 -m pytest cli/tests -q` — `action_admission` has existing coverage
  (`cli/tests/test_codex_host_admission_hook.py:568-586`) that must stay green. The carve-out change
  is exactly the kind that silently widens an admission boundary, so assert both roots admitted **and**
  a symlink escape still denied.
- `python3 scripts/check-sensors.py` — checks A–F on the new registry entry.
- `python3 scripts/check-params.py` — new parameter declared, default-parity clean (check E).
- `python3 -m ruff check cli/src cli/tests web/api mcp ianva`.
- **End-to-end, the real proof:** run a plan-mode session in a worktree under Fable and confirm
  `ExitPlanMode` succeeds — the corpus supplies a 58% pre-fix failure rate to measure against.
- Two consecutive sensor runs over an unchanged corpus: work once, no work twice; bounded peak RSS.

## Sequencing

α and β are the fix and are independently shippable — they close the presenting bug on their own.
γ is what makes it stay closed. Landing β without γ reproduces exactly the PR #1521 situation: a
correct fix with nothing watching the assumption underneath it.

## Note on this plan's own file

Written to the worktree-prefixed path because the shared-checkout write was denied mid-session. A
stale first draft remains at `.agent-runtime/claude/plans/twinkly-wobbling-church.md` in the shared
checkout. If the approval dialog shows outdated content or reports no plan, that is signature C
reproducing on this very document.
