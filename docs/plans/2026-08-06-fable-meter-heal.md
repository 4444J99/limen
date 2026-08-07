# Heal the blind Fable weekly meter: transcripts relocation + 16x budget miscalibration

Issue: #1929
PR: #1930

## Problem

The `/stats` + limits screens (2026-08-06) showed Fable weekly at **53%** with a $210 single-session Fable spend — past the **50% hard cap** in `docs/fable-allotment.md` — yet nothing warned or downgraded. Two blindnesses compounded:

1. **Dead transcripts path.** The harness relocated session transcripts from `~/.claude/projects/` (0 `.jsonl`) to `.agent-runtime/claude/projects/` (498 `.jsonl`). `scripts/fable-allotment.py:_transcripts_dir()` and `scripts/claude-workflow-guard.py:_find_session_dir/_find_session_jsonl` still read the legacy path — the same relocation sensors.yaml:509 records as having blinded ten surfaces. `logs/fable-allotment.json` sat stamped `week: 2026-07-06, over_cap: false`, and `model_selection.py` discards a stale-week balance, so `_fable_or_downgrade` never fired.
2. **16x miscalibrated divisor.** With sight restored, the meter read 3.39%: `LIMEN_FABLE_WEEKLY_TOKENS` defaulted to 1e9 billable tokens, while observed evidence (33.9M billable ↔ 53% on Anthropic's own meter; all Fable spend accrued Aug 5–6 inside the current window) implies a ~64M-billable weekly ceiling.

## Change

- `scripts/fable-allotment.py` — resolve the transcripts dir via `limen.harness_paths.harness_dir("projects", repo_root=ROOT)` (env pin `LIMEN_CLAUDE_TRANSCRIPTS_DIR` still wins); calibrate `_FABLE_WEEKLY_BUDGET_TOKENS_DEFAULT` to 64_000_000 with the dated evidence in a comment.
- `scripts/claude-workflow-guard.py` — `_harness_paths()` importlib-by-file-path loader (same fail-open pattern as `_model_selection()`), `_session_roots()` cascade, both session lookups search every live root.
- `institutio/governance/parameters.yaml` — `LIMEN_CLAUDE_TRANSCRIPTS_DIR` default `""` (= harness_paths resolution, documented); `LIMEN_FABLE_WEEKLY_TOKENS` default 64000000 with calibration provenance.
- Tests — relocated-tree resolution + env-pin precedence for both scripts (`test_fable_allotment.py`, `test_claude_workflow_guard.py`).

## Verification

- `python3 scripts/fable-allotment.py balance` → `week: 2026-08-03, spent_pct: 53.1, over_cap: true` — within 0.1 points of the operator's live Anthropic meter.
- `bash scripts/verify-fable-gate.sh` → PASS (over-cap downgrade, session hard-warn, idempotent balance).
- `python3 scripts/verify.py --changed` → exit 0 (one unrelated kill-race flake in `test_estate_audit_paired_custody` on the first run; passes in isolation and on re-run).

## Intended blast radius

Restamping at 53.1% flips the estate over-cap: accepted Fable selections downgrade to Opus unconditionally and `fable-session-guard.py` hard-warns Fable sessions at SessionStart — the fail-closed behavior `docs/fable-allotment.md` specifies, engaging for the first time since the relocation.

## Follow-ups (filed, not this change)

- `token-value-gauge.py:90`, `usage-telemetry.py:442`, `claude-usage.py:87` still hand-roll the legacy path — same one-line `harness_paths` route each.
- `harness_paths` is single-workspace: Fable burn in other workspaces' `.agent-runtime` trees is invisible to the meter (limen is where the burn is).
- The truest source stays the ratelimit-header capture (`logs/anthropic-ratelimit.json`) — when the fleet lands it, the calibrated divisor becomes the fallback only.
