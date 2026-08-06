# Enforce plan-on-Opus/Fable → build-on-Sonnet/Haiku

## Context

Limen already ships the *mechanism* for a plan/build phase split — `mode:plan-only` tasks emit a
model-neutral plan receipt (`cli/src/limen/plan_handoff.py`), and `mode:build-from-plan` tasks
consume it with tier re-derived fresh at claim time — and `docs/fable-allotment.md:3-13` already
**mandates** the policy ("Fable plans, cheaper tiers build … Building on Fable is prohibited";
role separation is "the root control", the weekly cap only "the backstop"). But neither half is
*bound* in the ladder:

- **Plan side**: `mode:plan-only` is a class the ladder sees (`dispatch._task_classes` = type ∪
  labels) yet appears in no tier set → a plan-only task derives **haiku** today.
- **Build side**: `builder_task_from_receipt` strips `mode:plan-only`/`tier:*`/`claude_tier`, but
  residual classes (`canon`, `synthesis`) on the builder task still resolve **opus** — no ceiling
  exists anywhere (`_cap_tier` is shipped but unconsumed for this).
- **Bonus leak found during design**: with `LIMEN_CLAUDE_BUILD_MAX_TIER=opus` semantics absent,
  `_bump_tier` + `LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE=1` + a valid receipt can bump a *build* task to
  Fable — directly against doctrine.

Goal: make the policy an executable, tested scaffold — plan-only derives Opus by default (Fable
stays the receipted exception), build-from-plan is capped at Sonnet (env-tunable, hard-capped at
Opus, Fable unreachable), and `scripts/claude-workflow-guard.py` gains phase-aware violations.
Verified: plan-only spawns already flow through `_claude_tier_for` (dispatch.py:3033 →
`_claude_model(task)`), so ladder changes take effect with no dispatch-lane change.

## Resolved design decisions

- **D1 — one label home**: `_PLAN_ONLY_CLASS`/`_BUILD_FROM_PLAN_CLASS` constants live in
  `model_selection.py` (pure-stdlib, imports nothing → cycle-free); `plan_handoff.py` imports them
  and keeps its public `PLAN_ONLY_LABEL`/`BUILD_FROM_PLAN_LABEL` names.
- **D2 — do NOT add the mode label to `_CLAUDE_OPUS_CLASSES_DEFAULT`**: `scripts/check-session-streams.py`
  gate G validates `job_class` against `_claude_opus_classes()` (domain vocabulary, not modes), and
  an operator `LIMEN_CLAUDE_OPUS_CLASSES` override would silently drop the guarantee. Check the
  mode classes explicitly inside `tier_for_classes` — signature unchanged, no caller can break.
- **D3 — build is cap-only**: haiku default preserved (cheapest-first doctrine); ceiling
  `_build_max_tier()` = `LIMEN_CLAUDE_BUILD_MAX_TIER` (default `sonnet`), itself hard-capped at
  `opus` — no env value can grant Fable for build.
- **D4 — cap wins** when both mode classes appear, and over an *accepted* fable class: build
  authorization means execution is imminent; the invariant must not depend on label-stripping.
- **D5 — un-accepted fable-class planning → opus** (the plan-phase rung), not the sonnet fallback
  (which exists to punish build-ish class overstatement).
- **D6 — `_bump_tier`**: earned escalation may exceed the build cap **to opus** (a detected failure
  is exactly where the "failure undetectable" cheap-tier rationale expires) but **never to fable**
  for build tasks — closes the retry-bump leak.
- **D7 — manual `claude_tier` pin stays sovereign** (builder tasks get `claude_tier=None`, so a pin
  is operator-deliberate); the guard's workflow lane surfaces expensive build runs anyway.
- **D8 — no `.claude/agents/build.md`**: parity tests (`test_claude_tier.py:299,314,403`) would
  force it to `model: haiku` (cap-only ⇒ empty-ledger derivation is haiku) — indistinguishable from
  scan/verify. Plan-handoff builders are fleet lanes, not in-harness subagent types.

## Steps

### 1. `cli/src/limen/model_selection.py` (the one ladder)

After `_CLAUDE_FABLE_CLASSES_DEFAULT` (~line 43) add the two constants + `_build_max_tier()`:

```python
_PLAN_ONLY_CLASS = "mode:plan-only"
_BUILD_FROM_PLAN_CLASS = "mode:build-from-plan"

def _build_max_tier() -> str:
    """The CEILING for mode:build-from-plan work. Env-tunable (LIMEN_CLAUDE_BUILD_MAX_TIER,
    default sonnet) but hard-capped at opus: building on Fable is prohibited by doctrine."""
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_BUILD_MAX_TIER", "sonnet"), "opus")
```

Rework `tier_for_classes` (line 181) body — **signature unchanged**:

```python
    wanted = set(classes)
    override = dict(overrides or {})
    plan_only = _PLAN_ONLY_CLASS in wanted
    if wanted & (_claude_fable_classes() | set(override.get("fable") or [])):
        if _claude_fable_acceptance_present():
            tier = _fable_or_downgrade()
        else:
            tier = "opus" if plan_only else _fable_fallback_tier()
    elif plan_only or wanted & (_claude_opus_classes() | set(override.get("opus") or [])):
        tier = "opus"
    elif wanted & (set(waste_classes) | set(override.get("sonnet") or [])):
        tier = "sonnet"
    else:
        tier = "haiku"
    if _BUILD_FROM_PLAN_CLASS in wanted:
        tier = _cap_tier(tier, _build_max_tier())  # cap-wins, unconditionally
    return tier
```

Extend the docstring with the two phase rules.

### 2. `cli/src/limen/plan_handoff.py`

Replace the label literals (lines 18-19) with imports keeping public names:

```python
from limen.model_selection import _BUILD_FROM_PLAN_CLASS, _PLAN_ONLY_CLASS
PLAN_ONLY_LABEL = _PLAN_ONLY_CLASS
BUILD_FROM_PLAN_LABEL = _BUILD_FROM_PLAN_CLASS
```

### 3. `cli/src/limen/dispatch.py` — `_bump_tier` (line 5974)

Add `_BUILD_FROM_PLAN_CLASS` to the existing `from limen.model_selection import (...)` block
(~line 102); change the fable-bump gate to also refuse fable for build tasks:

```python
    if bumped == "fable" and (
        _BUILD_FROM_PLAN_CLASS in _task_classes(task)
        or not (os.environ.get("LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE") == "1" and _claude_fable_acceptance_present())
    ):
        return "opus"
```

### 4. `cli/tests/test_claude_tier.py` (idiom: `_clear(monkeypatch)` + `LIMEN_ROOT=tmp_path`; add `LIMEN_CLAUDE_BUILD_MAX_TIER` to `_clear`, lines 64-83)

- `test_plan_only_class_derives_opus` — plan-only label alone lifts an otherwise-haiku task to opus.
- `test_plan_only_with_fable_class_needs_acceptance` — no receipt → opus; with `_write_fable_acceptance` → fable.
- `test_build_from_plan_caps_residual_opus_classes` — `["mode:build-from-plan", "canon"]` → sonnet (the receipt-leak fix).
- `test_build_from_plan_keeps_cheapest_first_default` — build label alone → haiku.
- `test_build_cap_env_is_hard_capped_at_opus` — env `fable` → opus; `opus` → opus; `haiku` → haiku.
- `test_build_from_plan_never_selects_fable_even_with_acceptance` — build + `long-horizon` + receipt → sonnet.
- `test_build_task_manual_pin_stays_sovereign` — `claude_tier="opus"` + build label → opus.
- `test_retry_bump_may_exceed_the_build_cap_but_never_to_fable` — build+canon+`tried:claude` → opus; with cap=opus + retry-bump-to-fable armed + receipt → still opus (the D6 leak).
- Extend `test_extracted_ladder_agrees_with_the_per_task_ladder` (line 430) with `("mode:plan-only","opus")` and the capped build row.

### 5. `cli/tests/test_plan_handoff.py`

- `test_mode_labels_have_one_source` — `PLAN_ONLY_LABEL is M._PLAN_ONLY_CLASS`, etc.
- `test_builder_task_from_canon_plan_resolves_within_build_cap` — end-to-end: plan task
  `[PLAN_ONLY_LABEL, "canon"]` derives opus → `build_plan_receipt` → `builder_task_from_receipt` →
  builder derives **sonnet**. (First env-touching test in this file: setenv `LIMEN_ROOT`, delenv
  `LIMEN_CLAUDE_MODEL`/`LIMEN_CLAUDE_BUILD_MAX_TIER`/`LIMEN_FABLE_ACCEPTANCE`.)

### 6. `scripts/claude-workflow-guard.py` (existing idioms: per-violation `LIMEN_ALLOW_*` escape, fail-open `_model_selection()` load, evidence capped at 10)

- **Transcript lane** (`audit_transcript`, 379-524): `_MUTATION_TOOLS = {"Edit","Write","MultiEdit","NotebookEdit"}` + conservative `_MUTATING_BASH_RE` (`git add|commit|push|apply|merge|rebase`, `gh pr create|merge|edit`). Any mutation tool_use on a turn whose resolved model contains fable → `building on Fable` violation unless `LIMEN_ALLOW_FABLE_BUILD=1`. Report keys `fableBuildToolCalls` / `fableBuildEvidence`.
- **Workflow lane** (`_workflow_violations`, after scan blob at 261): fail-open `_build_from_plan_label()` helper reading `_BUILD_FROM_PLAN_CLASS` from model_selection; label in scan + expensive/fable model → violation unless `LIMEN_ALLOW_EXPENSIVE_BUILD=1`.
- **Guard test**: `scripts/tests/claude-workflow-guard-phase.test.py` (hermetic, importlib-by-path, mirroring `correspondence-await-stale.test.py`): synthetic fable-turn+Edit jsonl → violation; `LIMEN_ALLOW_FABLE_BUILD=1` clears; haiku+Edit clean; workflow blob `mode:build-from-plan`+opus → violation, +sonnet clean. Wire one line into `scripts/verify-whole.sh` beside the other script tests (~lines 82-115).

### 7. Docs — `docs/fable-allotment.md`

Line 6: "hands off to a cheaper build tier (Sonnet/Haiku; `mode:build-from-plan` ceiling is
`LIMEN_CLAUDE_BUILD_MAX_TIER`, default Sonnet, hard-capped at Opus — Fable is unreachable for
build)". Add 3-4 lines under "Primary control" naming the scaffold: plan-only → Opus derivation
(Fable only with receipt); build cap; guard's two new violations + escape hatches; manual-pin
sovereignty stated as policy. (IDEAL-FORMS-LEDGER entry deferred — its own header requires a
paired `institutio/governance/ideal-forms.yaml` row + measuring command; file as follow-up.)

## Verification (in order)

```bash
python -m pytest cli/tests/test_claude_tier.py cli/tests/test_plan_handoff.py -q
python3 scripts/tests/claude-workflow-guard-phase.test.py
python -m ruff check cli/src cli/tests
scripts/verify-scoped.sh
```

Plus a live derivation smoke check:
`python3 -c "from limen.model_selection import tier_for_classes as t; print(t({'mode:plan-only'}), t({'mode:build-from-plan','canon'}))"` → `opus sonnet`.

Then branch `feat/phase-tier-enforcement` → push → PR → `scripts/merge-policy.sh` → merge per the
standing grant (non-deploy paths: cli/, scripts/, docs/).

## Risks (assessed)

- `tier_for_classes` has exactly one caller (`dispatch._claude_tier_for`, grep-verified); the shim
  has no class path; `check-session-streams.py` reads only the class *sets*, untouched → no ripple.
- Guard Bash heuristic under-detects by design (advisory backstop; mutation-tool names catch the
  harness's real write paths).
- Manual-pin bypass retained by design (D7) — documented as policy, surfaced by the guard.
