# Session Model Cadence — open cheap, escalate deliberately

Issue: #1948
PR: #1949

## Context

Fable's weekly allotment burned ~50% in two days (2026-08-05 → 2026-08-07). Root cause is the
same interactive bypass as the 2026-07-09 blowout: interactive sessions open on the **account
default model** and ride it for every turn — the shim governs only daemon/`claude -p` spawns,
and the staged countermeasure (`docs/keys/fable-guard-settings-snippet.json` + lever
`L-FABLE-GUARD-ARM`, issue #827) was never armed. Fable was doing routine execution work that
Sonnet/Haiku should carry; it only needs to plan (and even then, only for genuinely hard plans).

The operator's asked-for cadence: first message (a chaotic brainstorm) gets *structured into a
plan* on a cheap model; the ratification turn runs Fable/Opus; execution runs a Sonnet/Haiku
fleet with Opus only when needed. Also asked: whether plan-mode entry should become auto-mode
entry with plan-first *enforced*.

## Harness ground truth (verified against current docs, 2026-08-07)

- **No per-message model routing exists.** A session runs one model; `/model` is manual and
  session-only; hooks cannot change the model; the old `opusplan` plan/build pairing is gone.
- Therefore "msg1 Sonnet → msg2 Fable → fleet" cannot be automated per-message. The enforceable
  levers are: the session-*opening* model (`model` in settings.json), a SessionStart warning,
  and the SessionEnd/beat transcript audit.
- Plan-mode entry (`permissions.defaultMode: "plan"`) already *is* the "always start with a
  plan" enforcement. Auto-mode entry plus a hand-built deny-until-plan hook would rebuild plan
  mode, worse. Keep the entry binding; fix the economics under it.

## Decided shape

1. **Opening pin → Sonnet.** The staged snippet now pins `"model": "sonnet"` (was `"opus"`) and
   its README states the cadence. Arming stays human-gated ("do NOT let an agent arm
   settings.json") — lever `L-FABLE-GUARD-ARM` updated to carry the new meaning.
2. **Guard follows the cadence.** `scripts/fable-session-guard.py` `FABLE_SWITCH` becomes
   `/model sonnet` (the opening tier), so the over-cap warning recommends the cadence's floor,
   not Opus.
3. **Charter carries the doctrine.** `CLAUDE.md` → Session Phase Entry gains a "Session model
   cadence" paragraph: open on Sonnet; structure the brainstorm in plan mode; `/model opus` is
   the deliberate ratification escalation; Fable only under a live `docs/fable-allotment.md`
   acceptance receipt; execution drops back to Sonnet and fans out through the tiered fleet
   (`.claude/agents/` pins + `model_selection.py` ladder — authority unchanged, not restated).
4. **Audit already live — no new code.** The beat's `consume-session-end-breadcrumbs.py` runs
   `claude-workflow-guard.py audit-transcript`, which already bills main-loop Fable/Opus burn
   and flags unaccepted Fable (`claude-workflow-guard.py:559`). Nothing to extend.

## Files touched

- `docs/keys/fable-guard-settings-snippet.json` — opening pin `opus` → `sonnet`; README cadence.
- `scripts/fable-session-guard.py` — `FABLE_SWITCH` → `/model sonnet`.
- `CLAUDE.md` — Session Phase Entry: new "Session model cadence" paragraph.
- `his-hand-levers.json` — `L-FABLE-GUARD-ARM` label/unlocks updated (targeted edit).
- `docs/plans/2026-08-07-session-model-cadence.md` — this plan.

## The one human atom

Paste `docs/keys/fable-guard-settings-snippet.json` into `~/.claude/settings.json` (model pin +
SessionStart hook append), then run `scripts/verify-fable-gate.sh`. Owner: lever
`L-FABLE-GUARD-ARM` (issue #827). Everything else in this plan is agent-executable and shipped.

## Verification

- `scripts/verify-scoped.sh` green on the branch (runs `session-phase` for this plan file plus
  whatever the diff implicates).
- `python3 scripts/fable-session-guard.py --model claude-fable-5` exits 2 with the new
  `/model sonnet` switch string; `--model claude-sonnet-5` exits 0.
- `scripts/check-agent-docs.py` green (CLAUDE.md changed).
- Merge via `scripts/merge-policy.sh` → `scripts/await-pr.sh <PR#> --merge` (docs/config-class
  diff; non-deploy).
