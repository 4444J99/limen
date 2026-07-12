# OBSERVATORY — KERNEL (the legibility-and-traction organ)

> **Boundary (load-bearing, repeated everywhere in this organ):** OBSERVATORY is a **read-only**
> research organ. It studies public material, scores it, and *proposes* exactly one reversible
> experiment per day. It never mutates a public surface, never sends, never spends. The single
> irreducible human act it produces is the **approval** of a proposed experiment (a
> `his-hand-levers.json` lever) — never recited in chat, never auto-applied. Stars and counts are
> *signals*, never truth; the organ is built to resist the vanity metric it studies. Offline is
> fail-open: live rungs SKIP, never a faked PASS.

---

## Why this organ exists

An institution-sized body of work was built before one unmistakable public artifact existed through
which outsiders could understand, experience, use, and circulate it. The deficit is not production —
it is **activation, compression, concentration, and distribution**. The successful projects that trend
each day concentrate attention on one object, name one user, make one promise, and show that promise
becoming true immediately. Diagnosing *why they win and we don't* — honestly, controlling for
inherited advantage — is a system, not an opinion. This organ is that system.

This organ is an **institutional prosthesis** for legibility: it replaces the growth/DevRel desk and
competitive-intelligence team that a funded startup would have on payroll (~$1M/yr combined headcount).
A single operator cannot out-spend a team, but the outputs that matter are information flows, not human
hours — and those are replicable with code, bounded by API rate limits not salary lines. **Generic and
nameless underneath, his instance on top.**

The rival institution is a growth / DevRel desk fused with a competitive-intelligence team: a body that
watches the field, benchmarks its own surfaces against it, and runs one measured experiment at a time.

---

## The 5-primitive kernel, mapped to the legibility domain

| Primitive | Legibility meaning | Concretely |
|---|---|---|
| **Member** | a repo / public surface | a comparable winner, a matched control, or one of our own surfaces — the unit the whole system observes |
| **Mandate** | a legibility / traction gap | a transferable mechanism we lack, or a claim of ours that is untrue, incoherent, or drifting |
| **Standing** | drift / gap state | how far our surface sits from truth (internal) or from an adopted winner (external) — measured, never assumed |
| **Standard** | the priority formula + honesty rule | `explanatory_strength × controllability × similarity × EV ÷ activation_cost`; confounders discount strength; star count never enters a numerator |
| **Governance** | the experiment gate | the human approves the one proposed reversible experiment (dry by default; `--apply` arms it); the fleet may prepare it, the human publishes it |

This is the *same* kernel as the legal, governance, consulting, and other VLTIMA organs — only the
domain changes. The structure is fixed; the skin is legibility. That is the fractal: one kernel,
every pillar.

---

## The loop (OBSERVATORY is GITVS's twin)

GITVS runs `observe → diff → reconcile` on the estate's **configuration** (invariant: drift = ∅).
OBSERVATORY runs the *same loop* on the estate's **legibility & traction** — how the world understands,
trusts, uses, and circulates the estate.

| | MICRO — internal legibility | MACRO — external legibility |
|---|---|---|
| **question** | are our own public numbers true & coherent? | why do comparable winners get adopted and we don't? |
| **sensor** | VVLTVS + `face-ownership.json` (already exist) | trending + competitor collectors (`gh api`) |
| **diff** | claim drift / severed pipe (already computed) | matched-cohort mechanism scoring → activation gap |
| **reconcile** | revive the pipe / project from the register (the missing effector) | one reversible experiment for the hero repo |

Both faces write **one** append-only evidence store and feed **one** experiment selector: the day's
single highest-priority gap flows through the same priority formula and becomes one proposed lever.
The reconciler is not a separate system; it is internal-legibility gaps flowing through the same pipe.

---

## Fractal deployment

### MACRO — GITVS's legibility twin: the platform anyone can hold

A portable legibility-and-traction engine any operator or small team can adopt as their growth floor,
independent of ORGANVM's specifics. It runs the same `observe→diff→reconcile` loop that GITVS runs on
configuration, but pointed at whether the world can understand, trust, use, and circulate an estate:

1. **Study winners *and* controls.** For each trending/comparable winner it selects ~3 matched controls
   (same age, category, language, owner archetype, audience, release maturity) that did *not* win — so
   "why they succeeded" becomes a bounded hypothesis, not a survivorship story.
2. **Score mechanisms by transferability.** Every apparent advantage gets an explanatory strength
   (discounted by confounders it can't rule out) and a controllability score (can *you* reproduce it
   now). Never tells you to "become Apple" — it surfaces the cheap, transferable wins.
3. **Prove your own surfaces true.** It reconciles your public claims (repo counts, capabilities,
   status) against their canonical source, flagging drift and severed pipes before a surface lies.
4. **Propose one experiment.** One reversible change to your highest-leverage surface, with a
   measurement contract (baseline, target, window, failure criterion, reversal path) — and it measures
   whether attention actually converted to use, trust, or revenue.

Full platform description in [`MACRO-FACE.md`](MACRO-FACE.md).

### MICRO — Anthony's activation deficit: the estate's activation program

The ORGANVM estate's activation program. The diagnosis it was built to act on:

> **You do not have a production deficit. You have an activation, compression, concentration, and
> distribution deficit.**

Each morning it collects the day's GitHub winners (PageAgent, OfficeCLI, `mattpocock/skills`, etc.),
selects matched controls, extracts each README's communication surface, and scores which winning
mechanisms are *transferable and cheap* for the estate — a one-sentence promise, a one-line install, a
15-second visual proof — versus the inherited advantages we cannot copy.

Internal legibility reconciles the 105/116/171 claim-drift through the `face-ownership.json`/VVLTVS
loop: the sensor detects drift and severed pipes (the `build_vars → system-vars.json` step dropped
from `metrics-refresh.yml` on 2026-05-22, freezing the bio at 148); OBSERVATORY supplies the missing
effector to revive the pipe and project each face from its register — without becoming a fourth stamper.

The one experiment selects the hero repo (`value-repos.json` rank 1) and proposes one reversible
change — replace an abstract hero with an executable demo, cut install from eight steps to two,
reconcile a contradictory claim — with a measurement contract tracking visits → proof → trial → use →
return → inquiry.

Full deployment record in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## Convergence, not greenfield

This organ does **not** introduce a new metric registry, a new data store, or a new sensor.

| ChatGPT spec (overruled) | Actual (codebase idiom) |
|---|---|
| `organvm/observatory` repo | In-repo organ (`organs/observation/`) |
| DuckDB | JSONL (append-only evidence, same as `censor/precedents.jsonl`) |
| Astro dashboard | Next.js (existing `public-portal/`) |
| Playwright website capture | stdlib `urllib` (P3-CAPTURE, default OFF; Playwright is a recorded phase-3 residual) |

All ground truth is read from existing registries — never duplicated:
- `value-repos.json` — hero ordering (time-to-dollar)
- `revenue-ladder.json` — per-repo outcome class
- `docs/github-estate-ledger.json` — GITVS-owned estate inventory
- `face-ownership.json` — internal-legibility constitution (via VVLTVS)
- `institutio/observatory/mechanisms.yaml` — human-curated controllability/activation_cost knobs
- `institutio/governance/parameters.yaml` — `OBSERVATORY_*` parameter panel (shared with VIGILIA)

GITVS's proven `gh` idiom is reused (cascade token, fail-open subprocess wrappers). The reconcile
face delegates to VVLTVS (`scripts/vvltvs-organ.py`) — never re-derives drift (the "fourth stamper"
doctrine). Working handle **OBSERVATORY**; final name via nomenclator (`INDEX·NOMINVM`).

---

## The authority contract

| What the organ does | What the human does |
|---|---|
| Collects trending winners, selects matched controls, extracts README surfaces | Supplies competitor seeds and mechanisms.yaml controllability knobs — the strategic manual override |
| Scores mechanisms by the priority formula, discounts confounders | Reviews the scored proposals; the standard is the formula, not a human popularity contest |
| Reconciles internal legibility via VVLTVS sensor — detects drift, severed pipes | Decides which drifted face to fix and the priority order of internal repairs |
| Writes the daily brief: 3 mechanisms, 3 confounders, 1 hero, 1 experiment, 1 measurement contract | **Approves** the one proposed reversible experiment before any public-surface change |
| Homes the approved experiment as a `his-hand-levers.json` lever (dry by default; `--apply` arms it) | Publishes the experiment themselves — the fleet prepares, the human sends |

The pattern is: **study, score, reconcile, propose — the human gates every outward-facing act.**

---

## Hard guardrails (non-negotiable, every beat)

- **Read-only against public surfaces.** Default runs write only under `logs/observatory/`; the only
  public action is a filed proposal. `--apply` is the only path that homes a lever.
- **Stars are a signal, never truth.** No score uses star count in a numerator. Success is stored as
  an 8-component vector (reach, activation, retention, trust, maintenance, distribution, economic
  return, cultural impact), never collapsed to a scalar. Confounders (existing audience, corporate
  brand, launch event, suspected star manipulation) *discount* explanatory strength by construction.
- **Converge, do not add a stamper.** The internal-legibility face extends the existing
  `face-ownership.json` constitution and pairs with the VVLTVS sensor; it never introduces a rival
  metric registry (the "fourth stamper" disease the constitution was written to end).
- **Bounded & fail-open.** v1 caps the daily gh budget (`OBSERVATORY_WINNERS_LIMIT=3`);
  offline degrades to SKIP; every stage is `_safe`-wrapped so a faulting stage stops no other stage
  and never wedges the beat (exit 0 always).
- **Deterministic by default.** The done-predicate asserts byte-identical re-runs. The core pipeline
  is pure computation over snapshot files; network touches are isolated to `collect.py` and written
  to evidence before analysis begins. P2-LLM and P2-SYNTH are default-off extensions.
- **No invented proof.** Every mechanism seed in `mechanisms.yaml` corresponds to a real feature
  extracted by `surface.py`. Every gap type (`claim_drift`, `severed_pipe`) corresponds to a VVLTVS
  check. Every formula term is computed from actually-observed data or declared in the human-owned
  seeds file.

---

## The done-predicate

```bash
python -m limen.observatory doctor --offline
```

Exits 0 ⟺ the organ is wired, deterministic (a re-run reproduces byte-identical derived state — the
idempotent fixed point), shape-complete (each brief carries both faces + exactly 3 mechanisms, 3
confounders, 1 hero, 1 experiment, 1 measurement contract, no score using stars), and
**read-only against public surfaces** (default runs write only under `logs/observatory/`; the only
public action is a filed proposal). Offline is fail-open: live rungs SKIP, never a faked PASS.

---

## What gets built next

From the scaffold stage (10% → building 30%):

1. **Arm L-OBSERVATORY-ACTIVATE** — the lever is declared in `his-hand-levers.json`; needs human
   approval to set `LIMEN_OBSERVATORY=1`.
2. **Run one real beat** — produce the first `brief-latest.json` with real winners from the live
   `gh` search, a real hero gap, and the first experiment proposal.
3. **Beat wiring verification** — confirm the `observatory-run` sensor fires on its cadence, the
   loop completes within its timeout, and `doctor --offline` is green on the deployed checkout.
4. **P3-CAPTURE residual evaluation** — evaluate whether stdlib `urllib` captures sufficient signal
   or whether a Playwright upgrade would materially improve mechanism quality for JS-heavy winners.

---

*Companion documents: [`CHARTER.md`](CHARTER.md) (org-chart + virtual firm + workflow orchestration +
leverage math) · [`MACRO-FACE.md`](MACRO-FACE.md) (the legibility-and-traction engine any operator
can hold) · [`MICRO-FACE.md`](MICRO-FACE.md) (the estate's activation program: claim-drift
reconciliation + daily experiment proposal on the hero repo).*
