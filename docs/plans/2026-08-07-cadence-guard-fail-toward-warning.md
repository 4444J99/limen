# Session-model cadence — a guard that cannot see must warn, not pass

Issue: #1990
PR: (pending)

## Context

**The stack's own verification is green, and that is the finding.** `scripts/verify-fable-gate.sh`
passes all five blocks; `cli/tests/test_fable_session_guard.py` passes; the `fable-balance` beat
sensor runs every metabolize pass. Nothing in the shipped stack fails. The defects were found
*around* it — in the inputs it resolves, the population it covers, the copy of itself that actually
executes, and whether it is installed at all.

### The incident, root-caused

The operator burned ~50% of the weekly Fable allotment in two days with no downgrade and no warning.
The chain, every link verified read-only on 2026-08-07:

1. The live checkout sat at `6f401171` — **36 commits behind** `origin/main`. `scripts/sync-release.sh --check` says so itself: `FAIL — HEAD 6f40117 != origin/main 8d8a771`.
2. **`a575be0c` (#1930, "restore sight to the blind weekly meter") is among the missing commits.** `diff` against the live copy: it still carries `_FABLE_WEEKLY_BUDGET_TOKENS_DEFAULT = 1_000_000_000` (the 16× ceiling #1930 corrected to 64M) and `_transcripts_dir()` returning `Path.home() / ".claude" / "projects"` — the pre-relocation path holding **0** `.jsonl`.
3. `institutio/governance/sensors.yaml:610` declares `fable-balance` → `python3 scripts/fable-allotment.py balance`, run each beat **from that checkout**. So the meter is recomputed every beat by the *unhealed* script, scanning an empty directory.
4. It therefore writes `spent_pct: 0.0, over_cap: false` — while a healed recompute gives **75.47%, `over_cap: true`**.
5. Per #1930's own blast-radius note, `over_cap: true` is precisely what makes "accepted Fable selections downgrade to Opus unconditionally and `fable-session-guard.py` hard-warn at SessionStart." At `false`, both brakes are released.

**The meter was fresh and wrong.** `logs/fable-allotment.json` was rewritten at 09:17 that morning
and every beat before it. This is load-bearing for the design: **an age bound on the artifact passes
on this incident.** Freshness of an artifact is not truth of its value when the *writer's code* is
the stale party. F1 alone would not have caught it; F4 is the fix that does. Sequencing follows.

### Measured state, 2026-08-07 (read-only)

| Fact | Evidence |
|---|---|
| True weekly Fable spend | `fable-allotment.py balance --no-write` → `over_cap: true, spent_pct: 75.47` |
| Cached meter, live checkout | `logs/fable-allotment.json` written 09:17 → `spent_pct 0.0 / over_cap false` |
| Live checkout currency | 36 behind `origin/main`; `sync-release.sh --check` FAIL |
| Guard on empty payload | `printf '{}' \| fable-session-guard.py` → **exit 0, zero bytes on stderr** |
| Guard on Opus | `--model claude-opus-5` → **exit 0, zero bytes** — byte-identical to confirmed-cheap |
| Guard installed? | `~/.claude/settings.json`: 8 `SessionStart` entries, none the guard; no top-level `model` |
| Beat daemon currency | `check-beat-freshness.py` → STALE (daemon 11:58:49Z, loop body 13:38:58Z), **exit 0** |
| `verify-fable-gate.sh` registered as a gate | `grep fable institutio/governance/gates.yaml` → **zero matches** |
| Codex / Gemini opening pin | `~/.codex/config.toml` `gpt-5.6-sol` + `ultra`; `~/.gemini/settings.json` no `model` key |

### The unifying defect class, in one sentence

**A safety guard degrades silently toward "everything is fine" whenever its input is stale,
unresolvable, undeployed, or unarmed — because "I could not resolve this" and "this is fine" are
encoded as the same value.**

The same shape four times: `_load_balance()` → `None` → `over = False` → clean · `_resolve_model()`
→ `""` → `_is_fable("")` False → `return 0` printing nothing · an undeployed copy printing
superseded advice with no indication it is pre-merge · an unarmed guard indistinguishable from one
that ran and found nothing. Only the missing-meter path degrades correctly, and it does so by
accident of control flow (`not accept` already forces exit 2), not by design.

The Opus blind spot is a different failure — not silent degradation but a **covered surface one rung
wide**. It sits in EXPAND.

### Why the salve is not another sensor

This class is chronic and every episode has already been paid for: `IF-LIVE-TREE-COHERENCE` records
six days executing a tree where CORPORA/CONVERGENCE/ATOM-HOMING did not exist; `sensors.yaml:1617`
records seven flywheel PRs inert 18h and a 15-day starvation on the same unrun restart atom;
`sync-release.sh:36` records 60 behind for three days "of loud fail-open beats." Each produced a
**new sensor**. Every one is `severity: advisory`. `check-beat-freshness.py` is firing right now and
exits 0.

Detection is complete. It has no teeth. That is `PREC-2026-07-08-armed-valve-outcome` almost
verbatim — *"a beat-wired organ running in permanent dry-run … is an UNMET outcome, not a filed
one."* And the sharpest form: every ideal form in the ledger is measured against the tree in `main`;
**the fleet executes a different tree.** `IF-HARNESS-SENSED` reports green while the deployed
`fable-allotment.py` is still hardcoded to the pre-relocation path that IF claims to have closed.

### What this plan does not touch

- **`~/.claude/settings.json` is never written by any change here.** Arming stays human-gated; every change is on the read side.
- **The guard's exit code is not made blocking.** SessionStart hooks are fail-open by harness contract and the staged command ends `|| true`. The only live lever is what gets **printed**.
- **`sync-release.sh`'s fail-open preconditions are unchanged.** F4 closes detection and point-of-use, not enactment.

## Resolved design decisions

- **D0 — Freshness is not truth; deployment currency leads.** The incident was a *fresh* artifact written by *stale code*. F4 therefore lands in the first wave, not fourth, and F1's verdict carries a provenance dimension: an untrusted deployment makes every beat-written artifact untrusted, independent of its age.
- **D1 — Freshness is measured from the file's mtime, not a new body field.** `compute_balance()` declares "timestamps derive from data, never wall-clock in the body", and `verify-fable-gate.sh` block 5 asserts two consecutive runs are byte-identical. Adding `generated_at` turns a green predicate red and restamps fixtures across four test files. `logs/` is gitignored runtime state with one writer, so the file's mtime **is** the writer's heartbeat. **`scripts/fable-allotment.py` is not modified.** `scripts/state-freshness.py` gains a reserved `--field mtime` sentinel.
- **D2 — One meter reader, in `cli/src/limen/model_selection.py`** — already the pure-stdlib module both guard-side consumers importlib-load by file path. The three forked readers (`_fable_balance`, `_load_balance`, `_fable_over_cap`) are **deleted**, not mirrored. `parameters.yaml:3142` already named all three; the fork was declared and never closed.
- **D3 — UNRESOLVED is a verdict, never a value-shaped sentinel.** Readers return `{state, balance, age_s, trusted, detail}`, never `dict | None`. `dict | None` *was* the bug: no room for "unknown", so unknown collapsed into permissive.
- **D4 — An untrusted meter costs a TIER, never the work.** Dispatch downgrades an accepted Fable selection to **Opus**; the session guard hard-warns. Declared hatch: `LIMEN_FABLE_BALANCE_MAX_AGE_S <= 0`.
- **D5 — One ordinal primitive.** `_ladder_index(rung, ladder)` generic; `_tier_index` becomes its Claude binding (no caller moves). `_rung_of(pin, ladder)` classifies dearest-first, returning `""` for unclassifiable. `_opening_verdict(...)` returns `ok | above-floor | unresolved`. F3 lands the generic form so F6 adds no rewrite.
- **D6 — The cadence ceiling is registry-declared and hard-capped at the value.** `LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER` (default `sonnet`) routes through `_cap_tier(value, "opus")` — as does `--ceiling`, because the cap belongs to the value, not one accessor. The Fable arm evaluates **first and unconditionally**: defence in depth.
- **D7 — One gate, `fable-cadence`,** registering `bash scripts/verify-fable-gate.sh`, `tier: cheap`. Its `paths` accumulate as fixes land. (It is registered nowhere today.)
- **D8 — Exactly one reader of `~/.claude/settings.json` arming state:** `armed-valve-audit.probe_file_json` driven by `spec/armed-valves.json`. F6's `hook-armed` rows carry an `arming_valve` id and delegate; F7 adds no second probe kind.
- **D9 — One new ideal-form row for the invariant: `IF-GUARD-FAIL-TOWARD-WARNING`** (F7). `IF-ARM-STATE-PROBED` (F5) and `IF-SESSION-OPENING-FLOOR` (F6) are genuinely distinct and keep their own rows.
- **D10 — One censor precedent,** `PREC-2026-08-07-guard-degrades-toward-silence`, appended with the first landing, stating the full class including the siblings that landing does not close.
- **D11 — Exit codes are for the test harness only.** No change makes a SessionStart hook blocking.

## Steps

Each step is done when its predicate exits 0. Read each predicate's **own** exit code — never a pipeline's.

1. **FULL** — record the measured baseline above; no change. Predicate: the table reproduces. *(done, this document)*
2. **HEAL / F4** — deployment currency becomes a declared sensor with an **offline receipt**, so a guard running out of the deployed tree can cite evidence instead of rendering absence as silence. `check-live-checkout.py` answers only when run, needs a network `git ls-remote`, and leaves no artifact — no point-of-use consumer can afford it inline. Adds the receipt + sensor entry + `scripts/tests/live-checkout-currency.test.sh`. **M**
3. **HEAL / F1** — the weekly meter becomes falsifiable: one verdict-returning reader (D2/D3), mtime freshness (D1), provenance from F4's receipt (D0), every untrusted state routed to the warning; registers the existing predicate as the `fable-cadence` gate; lands the censor precedent. **M**
4. **HEAL / F5** — probe the arm, never write it: `settings.json` arming becomes a beat verdict through the existing armed-valve registry. Until the paste happens, `FABLE_GUARD_SESSIONSTART_WIRED` and `SESSION_MODEL_OPENING_PIN` report PARKED every beat instead of being invisible. Also corrects `L-FABLE-GUARD-ARM`'s stale `label` (it still says the snippet pins `opus`; the shipped snippet pins `sonnet`). **M**
5. **HEAL / F2** — an unresolvable session model becomes a THIRD state that speaks; the `bool(x.get("over_cap"))` twin fixed in the same pass. **M**
6. **EXPAND / F3** — guard the cadence CEILING, not the literal string `fable`; ordinal primitives land in generic form (D5). **M**
7. **EXPAND / F6** — the session-opening floor becomes a per-lane census fact: one declared row per vendor, one provider-neutral probe, one beat entry. Answers the operator's "all providers, not just Claude." **L**
8. **EVOLVE / F7** — the invariant as a generalized executable contract: one shared body (`cli/src/limen/guard_contract.verdict`) short-circuiting before any guard-specific condition, a declared-population ratchet (`parameters.yaml` rows with `guard_state: true`), degenerate-case proofs that are **executed** rather than inspected, and `IF-GUARD-FAIL-TOWARD-WARNING`. **L**

## Sequencing

```
F4 (M) ──┬─> F1 (M) ──> F2 (M) ──> F3 (M) ──> F6 (L) ──> F7 (L)    serial: one file
F5 (M) ──┘   (F5 parallel throughout; hard prerequisite for F6)
```

F4 leads (D0): it is the only fix that catches the incident that motivated the plan, and F1's
provenance dimension consumes its receipt. Four of seven edit `fable-session-guard.py`'s `main()` —
that is the whole sequencing problem. F5 is fully parallel (its only shared file, `spec/armed-valves.json`,
is read but not edited by F6/F7) and must precede F6 or `arming_valve` has no target.

One concern per branch: `feat/live-checkout-currency` · `fix/fable-meter-falsifiable` ·
`feat/armed-valve-file-probe` · `fix/guard-unresolved-model` · `feat/session-cadence-ceiling` ·
`feat/session-opening-floor` · `feat/guard-fail-toward-warning`. All seven are non-deploy. Merge each
via `scripts/merge-policy.sh <PR#>` exit 0 → `scripts/await-pr.sh <PR#> --merge`.

## Premortem

- **The advisory becomes the common path and gets pasted back out.** After F2+F3 a session opening on the operator's saved Opus default warns *every time*. If that reads as noise the failure mode is a human removing the hook — the same silence through a different door. The ceiling is a one-token registry change (`LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER=opus`), not a code narrowing. **Do not add a `LIMEN_FABLE_GUARD_QUIET` hatch later** — that re-creates the defect as a supported feature.
- **Dispatch behaviour reverses.** An untrusted meter downgrades accepted Fable to Opus, so on a host with no running beat Fable becomes unreachable for fleet dispatch. Work is never blocked, only the reserved tier withheld. **State this in the F1 PR body** — it is the one intentional behaviour change outside the guard.
- **F4's bootstrap paradox.** Both halves live inside the files being fixed, so F4 cannot retroactively have caught the incident that motivated it: until they reach the live checkout through the same fail-open `sync-release.sh` path that *is* the defect, no receipt exists. F4 closes future recurrences only — and if that tree stays parked, the fix sits undeployed exactly as before. **This is the strongest argument that the deployment atom is real work, not hygiene.**
- **The loader divergence gets "normalized".** F2/F3's `__file__` pin (against two `LIMEN_ROOT`-reading precedents) is load-bearing: a worktree-run verification must not resolve through the live checkout. The split is *code by `__file__`, runtime state by `LIMEN_ROOT`*; the reason goes in the docstring.
- **The baseline becomes where fixes hide.** `--update` refusing to pin HARD findings is the structural guard; a diff emptying a named vacuum without a `degrades` assertion is visible in review — but only if someone looks.
- **An offline host warns on every session.** F4's receipt is written only from a real measurement, so an unreachable origin ages it out and consumers degrade to the warning. Correct direction, genuinely noisy on a laptop that travels.

## Open questions

1. **Does the SessionStart payload carry `model` on this build?** *Partially established.* The hooks documentation states SessionStart is the only event receiving a `model` field and that it "is not guaranteed to be present". Unestablished: whether it arrives in practice, for which `source` values, and whether it names the session model. Resolving experiment is a temporary payload-dump SessionStart hook — **a settings.json write, so it is staged and handed over, never applied by an agent** (filed against `L-FABLE-GUARD-ARM`; same file, same boundary). **The plan is correct either way:** every branch degrades toward the warning, so if the field never arrives the guard is loud rather than silent. What is lost is precision, not safety.
2. **The transcript rung cannot help a fresh session** — on `source: "startup"` there is no assistant turn yet. A genuine rung for `resume`/`compact` only; stated in its docstring, not a defect to "fix".
3. **`$CLAUDE_EFFORT` is the only model-related env var the harness sets.** It is an *effort* level with no established mapping to tier. It must **not** be used as a model proxy.
4. **Does the harness render a hook's stderr identically on exit 0 vs exit 2?** Unresolved on disk. Do not assert that removing `|| true` changes what the user sees.
5. **Is `/model`'s saved default readable anywhere?** No — searched `~/.claude.json` (full traversal), both settings files; only per-project `lastModelUsage`. Treated as harness-internal. If a future build exposes it, F6's Claude row moves from `hook-armed` to `config-file`.
6. ~~**Is the live checkout currently drifted?**~~ **CLOSED 2026-08-07** — yes, 36 behind, and it is the incident's root cause (see Context). The ground pass could not check it from an isolated worktree; `sync-release.sh --check` answers without `git -C`.
7. **Where do agy / copilot / warp / oz keep their interactive opening pin?** Not located. F6 declares `config_path=""`, classifying them `unresolved` — the honest starting state, clearing when someone locates the file.

## Residuals

Human-gated atoms are **filed in their registry owner and cited by predicate — never recited as a
list.** Registry owner: `his-hand-levers.json`.

- **`L-FABLE-GUARD-ARM` (issue #827)** — the one staged paste. Nothing here adds to its cost, and every fix is correct whether or not it is pulled: the dispatch cap gate, all three beat sensors and both new gates gain their guarantees with no arming at all. Only the interactive warning waits on it. **F5 gives it a read-side predicate for the first time.**
- **The deployment atoms** — the live checkout reaching `origin/main`, and `launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat` (the exact remedy `check-beat-freshness.py` already prints). Until both, nothing merged today is running. These belong to `IF-LIVE-TREE-COHERENCE` and the beat-freshness sensor; F4 makes the first continuously audible rather than fail-open into a log nothing reads.
- **New atom, filed by F6:** `L-LANE-OPENING-FLOOR` — lowering operator-owned non-Claude pins (`~/.codex/config.toml` `ultra` → `high`; a flash-class `model` in `~/.gemini/settings.json`). Needs a real `issue` int before landing (`no-tasks-on-me.sh` §SS7).
- **Reporting predicates** (run these; do not re-audit by hand):
  ```
  bash scripts/no-tasks-on-me.sh
  python3 scripts/credential-wall.py --check
  python3 scripts/armed-valve-audit.py --check        # PARKED rows name the unpulled arms
  python3 scripts/session-opening-floor.py            # non-ok rows name the unlowered pins
  ```

## Verification

Exit 0 ⟺ the plan is implemented. Run each bare and read its **own** exit code.

```bash
bash scripts/verify-fable-gate.sh                    # F1, F2, F3
bash scripts/tests/live-checkout-currency.test.sh    # F4
python3 scripts/armed-valve-audit.py --check         # F5
python3 scripts/session-opening-floor.py --check     # F6
python3 scripts/check-guard-degradation.py           # F7 — the declared-population ratchet

python3 scripts/check-sensors.py                     # registry parity, one gate each
python3 scripts/check-params.py
python3 scripts/check-gates.py
python3 scripts/check-ideal-forms.py

PYTHONPATH=cli/src python3 -m pytest cli/tests/test_fable_session_guard.py \
  cli/tests/test_model_selection.py cli/tests/test_fable_allotment.py -q
python3 scripts/check-ruff-pin.py && python3 -m ruff check cli/src cli/tests web/api mcp ianva
bash scripts/verify-scoped.sh
```

The arc's own fixed point: with F4 landed and the tree current, `fable-allotment.py balance` and the
cached meter agree, and `printf '{}' | fable-session-guard.py` is no longer byte-identical to a
confirmed-safe session.
