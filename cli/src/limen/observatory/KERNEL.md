# OBSERVATORY — KERNEL (engine)

> The 5-primitive kernel, mapped onto the **legibility & traction** domain at the
> engine level. This file is the code-side twin of `organs/observation/KERNEL.md`:
> that one states the mapping in prose; this one pins every primitive to the module
> and function that implement it. Where the two disagree, the executable predicate
> (`observatory doctor` + `cli/tests/test_observatory.py`) wins.

## Boundary (load-bearing)

OBSERVATORY is a **read-only** research organ. It studies public material, scores
it, and *proposes* exactly one reversible experiment per day. It never mutates a
public surface, never sends, never spends. The single irreducible human act it
produces is the **approval** of a proposed experiment (a `his-hand-levers.json`
lever) — never recited in chat, never auto-applied. Stars and counts are
*signals*, never truth.

The default beat (`python -m limen.observatory run`) is **dry**: it writes only
under `logs/observatory/`. `--apply` is the one arm — it homes a lever idempotently
and promotes a reversible-prep task via tabularius. Nothing here opens a public PR
by itself.

## The loop (GITVS's legibility twin)

GITVS runs `observe → diff → reconcile` on the estate's **configuration**
(invariant: drift = ∅). OBSERVATORY runs the *same loop* on the estate's
**legibility & traction** — how the world understands, trusts, uses, and
circulates the estate. One loop, standard organ **two faces**, wired as one
pipeline in `executive.py:run_beat`:

| Face | question | sensor | diff | reconcile | code |
|---|---|---|---|---|---|
| **micro** (internal legibility) | are our own public numbers true & coherent? | VVLTVS + `face-ownership.json` | claim drift / severed pipe (`reconcile.gaps`) | revive the pipe / project from the register (a *proposal*) | `reconcile.py` |
| **macro** (external legibility) | why do comparable winners get adopted and we don't? | `gh` collectors | matched-cohort mechanism scoring → activation gap | one reversible experiment for the hero repo | `collect.py` → `mechanism.py` → `brief.py` |

Both faces write **one** append-only evidence store (`ledger.append_jsonl`) and
feed **one** experiment selector (`brief.select_experiment`): the day's single
highest-priority gap — "your bio lies" or "winners demo above the fold and you
don't" — flows through the same priority formula and becomes one proposed lever.
The reconciler is not a separate system; internal-legibility gaps flow through the
same pipe.

## The 5-primitive kernel, mapped to code

| Primitive | Legibility meaning | Implemented in |
|---|---|---|
| **Member** | a repo / public surface — ours, a comparable winner, or a matched control | `collect.snapshot` (normalizes each repo into `limen.observatory.snapshot.v1`); `estate.our_repos` reads the hero candidate set from `value-repos.json` |
| **Mandate** | a legibility / traction gap to close | `mechanism.activation_gap` (a transferable mechanism the hero *lacks*) and `reconcile.gaps` (a `claim_drift` / `severed_pipe` on our own surfaces) — both feed `brief.select_experiment` |
| **Standing** | drift / gap state | `reconcile.run` emits `gap_count` / `hard_gaps` / `coherent`; `mechanism.run` emits the hero's ranked `gaps` into `gap-latest.json`; `estate.outcome_class` derives each repo's stage |
| **Standard** | the priority formula + honesty rule | `mechanism.score` (the formula) + `cohort.confounders` / `cohort.confounder_discount` (the discount); the rule "stars never enter a numerator" is enforced by `cohort.control_query` excluding stars from match distance and `collect.snapshot` tagging `star_signal_only: true` |
| **Governance** | the experiment gate | `brief.build_brief` selects ONE experiment → `lever.propose` emits a human-gated `his-hand-levers.json` lever + a `tasks.yaml` task via tabularius; dry by default, `--apply` arms |

This is the *same* kernel as the legal, governance, and GITVS organs — only the
skin changes. The engine makes the mapping concrete and testable.

## The priority formula (Standard), in code

```
priority = explanatory_strength × controllability × similarity × expected_value
           ÷ activation_cost
```

Implemented in `mechanism.score`:

- `explanatory_strength` = `(1 − controls_have_frac) × confounder_discount` — the
  winner-vs-control contrast, *discounted* by confounders.
- `controllability`, `activation_cost` — the only human-curated inputs, from
  `institutio/observatory/mechanisms.yaml` (`mechanism.load_seeds`).
- `similarity` — 1.0 iff the mechanism targets the hero's primary success-vector
  component (`estate.outcome_class` → `_STAGE_COMPONENT`), else 0.6.
- `expected_value` — weighted by the hero's product stage (`_STAGE_EV`).

**Confounder-honesty rule (stars are a signal, never truth):** `cohort.confounders`
flags `existing_audience`, `corporate_brand`, and `star_manipulation_suspected`;
`confounder_discount` multiplies them into a factor in `(0, 1]`, so a repo that won
on inherited advantage yields low-priority mechanisms *by construction*. Star
count never appears in any numerator (`mechanism.score` never reads it);
success is stored as the 8-component vector (`collect._VECTOR_KEYS`) and never
collapsed to a scalar in a score.

## Fractal deployment

- **MACRO** — a portable legibility-and-traction engine any operator can hold:
  study the field, prove your own surfaces true, get one reversible experiment at a
  time. The engine is installer-agnostic; point it at any ranked value list +
  observed inventory (`config.value_repos` / `config.estate_ledger`) and seed
  competitors (`config.competitor_seeds`). See `organs/observation/MACRO-FACE.md`.
- **MICRO** — the ORGANVM estate's activation program: daily winners vs. matched
  controls, the estate's own claim-drift reconciled through the VVLTVS /
  `face-ownership.json` loop, one experiment/day on the hero repo
  (`value-repos.json` rank 1). See `organs/observation/MICRO-FACE.md`.

## Module map (the organ is whole)

```
observatory/
  config.py      params + ground-truth registries (value-repos / revenue-ladder / estate-ledger)
  gh.py          the ONLY shell-out boundary — GITVS's token cascade, fails OPEN
  ledger.py      the ONE writer — JSONL keeper discipline + derived *-latest.json
  collect.py     winners + competitor seeds + matched controls → snapshots/surfaces/cohorts
  cohort.py      matched-control selection (anti-survivorship) + confounder discount
  surface.py     deterministic README feature extraction (+ P3-CAPTURE site capture)
  mechanism.py   external-legibility analyze stage — score → hero activation gap
  estate.py      our own estate — outcome class, hero selection, activation gap
  reconcile.py   internal-legibility face — delegates to VVLTVS (never a 4th stamper)
  interpret.py   P2-LLM evidence-constrained interpretation (behind OBSERVATORY_LLM)
  synthesis.py   P2-SYNTH weekly KEEP/TEST/REJECT priors (behind OBSERVATORY_SYNTH_ENABLED)
  brief.py       both faces → one brief + one experiment selector
  lever.py       the Governance primitive — human-gated proposal (dry; --apply arms)
  executive.py   the convener — runs the 5-stage pipeline, _safe-wrapped, exit-clean
  doctor.py      the self-verifying predicate — `observatory doctor`
  __main__.py    heartbeat handle — always exits 0 (an organ bug never wedges the beat)
```

## Invariant (the done-predicate)

`observatory doctor` exits 0 ⟺ the engine is wired, deterministic (a re-run
reproduces byte-identical derived state — the idempotent fixed point asserted by
`ledger.write_latest`'s `sort_keys`), shape-complete (each brief carries both faces
+ exactly 3 mechanisms, 3 confounders, 1 hero, 1 experiment, 1 measurement
contract, no score using stars), and **read-only against public surfaces** (default
runs write only under `logs/observatory/`; the only public action is a filed
proposal). Offline is fail-open: live rungs SKIP, never a faked PASS.
