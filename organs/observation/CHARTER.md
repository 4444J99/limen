# OBSERVATORY — CHARTER

> Working handle: **OBSERVATORY**. Final name via `INDEX·NOMINVM` (nomenclator beat).
> Rival: a **growth/DevRel + competitive-intelligence team** — a launch-analytics desk
> fused with a positioning studio.
>
> This is the operating contract for the legibility-and-traction organ. Complements
> [`KERNEL.md`](KERNEL.md) (the 5-primitive map) and the two FACE docs. Where prose and the
> executable predicate disagree, the predicate (`observatory doctor` + `cli/tests/test_observatory.py`)
> wins.

## Provenance

Built from an imported ChatGPT design (`chatgpt.com/share/6a5234b0-…`), whose one real request
was *"study every day the repos and projects trending on GitHub … and figure out why they're
successful and I'm not."* ChatGPT's answer scoped it as a greenfield repo (`organvm/observatory`
+ DuckDB + Astro + Playwright). That stack is **overruled by codebase idiom**: in-repo organ,
JSONL evidence store, Next.js dashboard consumer, existing registries as ground truth.

See `docs/…/review-and-implement-…observatory….md` for the full derivation.

## Institutional weight: the leverage math

One person with a single laptop cannot out-spend a growth/DevRel team (headcount ~$600K/yr)
or a competitive-intelligence desk (headcount ~$400K/yr). But the **outputs that matter** are
information flows, not human hours — and those are replicable with code, bounded by API rate
limits not salary lines.

| Team function | What it produces | OBSERVATORY's equivalent | Leverage ratio |
|---|---|---|---|
| DevRel: daily field scan | Know what's trending, who won, and why | `collect.py` + `cohort.py` — bounded gh search, snapshots, matched controls | 8 hrs human → ~2 min automated |
| CI: competitor brief | Ranked mechanisms + confounders per winner | `mechanism.py` — deterministic scorer with confounder discount | 16 hrs analyst → ~30 sec compute |
| DevRel: surface audit | Are our public numbers true and coherent? | `reconcile.py` via VVLTVS — drift detection on face-ownership.json | 4 hrs manual audit → ~5 sec check |
| CI: strategy memo | "What should we do?" with measurement contract | `brief.py` + `lever.py` — one experiment proposal, gated by `his-hand-levers.json` | 8 hrs strategist → ~30 sec generation |
| Growth: weekly synthesis | KEEP / TEST / REJECT of what's working | `synthesis.py` — folds mechanism history into standing priors, at most once/week | 4 hrs retro → ~10 sec fold |

**Daily output of the virtual firm**: one brief with 3 mechanisms, 3 confounders, 1 hero, 1
reversible experiment, 1 measurement contract. Written to `logs/observatory/` — the organ's
whole footprint under 50 KB/day. A real team would consume ~40 person-hours to produce the
same first-draft; this organ does it on one heartbeat tick for ~2 API calls (gh search + gh
snapshot per winner) and ~0.5s CPU.

The binding constraint is not generation capacity (the fleet has ~15K idle workunits/month).
It is the human approval gate (`his-hand-levers.json`) for the day's one experiment.

## Virtual firm: org-chart of AI roles

The organ is a **virtual firm** of 5 AI roles, executed in sequence by `executive.py`. Each
role maps to a concrete module (or pair of modules) in `cli/src/limen/observatory/`:

### 1. The Scout — Data Collection (`collect.py` + `gh.py`)
Finds today's GitHub winners and competitor seeds, snapshots each into a normalized record,
extracts README surfaces, and selects matched controls. Bounded by `OBSERVATORY_WINNERS_LIMIT`
(default 3). Fail-open on offline/unreachable.

**Code boundary:** `gh.py` is the ONLY shell-out boundary (a cascade token + thin subprocess
wrappers that fail open). `collect.py` owns the searches and snapshots; pure matching lives
in `cohort.py`. Reuses GITVS's proven `gh` idiom.

### 2. The Analyst — Mechanism Extraction (`mechanism.py` + `interpret.py`)
Distills unstructured README signals into structured mechanism claims — winner features its
matched controls mostly LACK. Each mechanism is scored by the priority formula:

    priority = explanatory_strength × controllability × similarity × expected_value
               ÷ activation_cost

with a hard rule: **star count never enters a numerator**. Controllability and activation_cost
are human-curated in `institutio/observatory/mechanisms.yaml`; everything else is computed from
evidence. `interpret.py` (P2-LLM, default OFF) optionally attaches an evidence-constrained model
interpretation via a bounded `claude -p` subprocess — fail-open, never mutates the deterministic
core.

### 3. The Auditor — Internal Legibility (`reconcile.py` + `estate.py`)
Holds the estate's own public surfaces accountable to the `face-ownership.json` constitution.
Delegates to the existing VVLTVS sensor (`scripts/vvltvs-organ.py`) — never re-derives drift
(the "fourth stamper" doctrine). Converts drifted faces + severed pipes into internal-legibility
gaps. `estate.py` reads the existing ground-truth registries (`value-repos.json`, `revenue-ladder.json`)
to derive outcome classes and the hero repo — it never invents a new success SSOT.

**Convergence constraint:** This role does NOT add a new metric registry. It reads VVLTVS's output
and `face-ownership.json` — the same sensor the GITVS organ uses. The estate ledger
(`docs/github-estate-ledger.json`) is the GITVS-owned inventory.

### 4. The Strategist — Experiment Synthesis (`brief.py` + `lever.py` + `synthesis.py`)
Folds external and internal gaps into one unified daily brief. Selects the single highest-priority
gap across both faces as the day's one reversible experiment. Writes the experiment as a
human-gated proposal (a `his-hand-levers.json` lever + a `tasks.yaml`-style task via the
tabularius single-writer). `synthesis.py` (P2-SYNTH, default OFF) folds `mechanisms.jsonl` history
into KEEP/TEST/REJECT priors at most once per ISO week.

**Design invariant:** `lever.py` never writes a public surface. `--apply` (gated by
`OBSERVATORY_APPLY`) is the only path that homes a lever. `LIMEN_STAMP_PROPOSE` would be the only
path that opens a public PR — that path is not wired in v1.

### 5. The Archivist — Ledger Discipline (`ledger.py` + `config.py`)
Ensures all evidence is append-only JSONL under `logs/observatory/` (immutable, byte-stable rows)
and derived state is regenerated each run (`*-latest.json`) with atomic writes. Snapshot lines
preserve history. Shared parameter panel `OBSERVATORY_*` in `institutio/governance/parameters.yaml`.
All readers fail-open: missing/corrupt registry → empty structure, never a crash.

## Workflows (the 5-stage pipeline)

The executive `run_beat()` orchestrates 5 stages in sequence (`executive._PIPELINE` — the doctor's
`pipeline` rung counts them). Each is `_safe`-wrapped: a faulting stage stops no other stage and
never wedges the beat (exit 0 always). The propose step is nested inside the brief stage
(`brief.run()` convenes `lever.propose()`), not a separate `_PIPELINE` entry.

| # | Stage | Module | What it does | Writes |
|---|-------|--------|-------------|--------|
| 1 | **collect** | `collect.py` | Search trending + competitors; snapshot each; select ~k matched controls per winner; extract README surfaces | `snapshots.jsonl`, `surfaces.jsonl`, `cohorts.jsonl` |
| 2 | **analyze** | `mechanism.py` | Score winner-vs-control contrasts by priority formula; compute activation gap against our hero's surface | `mechanisms.jsonl`, `gap-latest.json` |
| 3 | **reconcile** | `reconcile.py` | Run VVLTVS sensor → convert drifted faces + severed pipes into internal-legibility gaps | `reconcile.jsonl`, `reconcile-latest.json` |
| 4 | **brief** | `brief.py` + `interpret.py` (P2-LLM) | Merge both faces; pick highest-priority gap → one experiment; optionally attach LLM interpretation | `brief-latest.json`, `brief-latest.md`, `briefs.jsonl` |
| ↳ 4b | **propose** (within brief) | `lever.py` | Shape experiment as lever + task; home to `his-hand-levers.json` when armed | `proposals.jsonl`; lever (armed only) |
| 5 | **synthesize** | `synthesis.py` (P2-SYNTH) | Fold mechanism history → KEEP/TEST/REJECT priors (at most once/ISO week) | `synthesis-weekly-latest.json`, `synthesis.jsonl` |

All stages write under `logs/observatory/` — never to a public surface.

## Inputs / Outputs

### Read-only ground truth (never duplicated)

| Registry | Source | Role |
|----------|--------|------|
| `value-repos.json` | `config.value_repos()` | Hero ordering (time-to-dollar) |
| `revenue-ladder.json` | `config.revenue_ladder()` | Per-repo outcome class (stage, whose_hand) |
| `docs/github-estate-ledger.json` | `config.estate_ledger()` | GITVS's observed estate inventory |
| `face-ownership.json` | (via VVLTVS) | Internal-legibility constitution |
| `institutio/observatory/mechanisms.yaml` | `mechanism.load_seeds()` | Human-curated controllability/activation_cost knobs |
| `institutio/governance/parameters.yaml` | `config.get(...)` | `OBSERVATORY_*` parameter panel (shared with VIGILIA) |

### Output evidence store (`logs/observatory/`)

| Artifact | Kind | Schema |
|----------|------|--------|
| `snapshots.jsonl` | Append-only evidence | `limen.observatory.snapshot.v1` |
| `surfaces.jsonl` | Append-only evidence | `{"owner_repo": str, "features": dict}` |
| `cohorts.jsonl` | Append-only evidence | `{"winner", "match_key", "controls", "confounders"}` |
| `mechanisms.jsonl` | Append-only evidence | `{"mechanism", "winner", "priority", …}` |
| `reconcile.jsonl` | Append-only evidence | `{"gap_count", "hard_gaps", "gaps"}` |
| `proposals.jsonl` | Append-only evidence | `{"proposed", "armed", "lever", "task"}` |
| `briefs.jsonl` | Append-only snapshot | `limen.observatory.brief.v1` |
| `gap.jsonl` | Append-only snapshot | `limen.observatory.gap.v1` |
| `synthesis.jsonl` | Append-only snapshot | `limen.observatory.synthesis.v1` |
| `*-latest.json` | Regenerated derived state | Deterministic, byte-identical on re-run |
| `status.json` | Regenerated run status | `{"stages": […], "apply": bool}` |

## Home & shape

- **Charter / private data:** `organs/observation/` (this directory + KERNEL.md + MACRO/MICRO FACE).
- **Engine:** `cli/src/limen/observatory/` — 17 modules: a shell-out boundary (`gh.py`), a writer
  (`ledger.py`), a convener (`executive.py`) that `_safe`-wraps each stage, a predicate (`doctor.py`),
  and the full research + reconcile + synthesis loop. `__main__.py` always exits 0 so an organ bug
  never wedges the beat.
- **Beat wiring:** `scripts/observatory-beat.py` — the heartbeat's handle, declared as
  `observatory-run` sensor in `institutio/governance/sensors.yaml`. Ships dark behind
  `LIMEN_OBSERVATORY` (default OFF), armed by lever `L-OBSERVATORY-ACTIVATE` in `his-hand-levers.json`.
- **Evidence:** `logs/observatory/` — appended JSONL evidence + regenerated derived docs.
- **Parameters:** `institutio/governance/parameters.yaml` — `OBSERVATORY_*` (master gate, winners
  limit, LLM arm, capture arm, synth arm, apply arm, trending window, controls-per-winner,
  competitor seeds, trending query).

## Standing rules (invariants)

1. **Read-only against public surfaces.** Default `run`/`reconcile apply` write only under
   `logs/observatory/` and LOCAL in-repo surfaces. A public-surface change is a *filed proposal*
   (a `his-hand-levers.json` lever) — never a silent push. `--apply` is the only path that homes a
   lever; `LIMEN_STAMP_PROPOSE` is the only path that would open a PUBLIC PR (not wired in v1).
2. **Stars are a signal, never truth.** No score uses star count in a numerator; success is stored as
   an 8-component vector, never collapsed to a scalar; confounders (existing audience, corporate
   brand, launch event, suspected star manipulation) *discount* explanatory strength by construction.
3. **Converge, do not add a stamper.** The internal-legibility face extends the existing
   `face-ownership.json` constitution and pairs with the VVLTVS sensor; it never introduces a rival
   metric registry (that is the "four-stampers disease" the constitution was written to end). It
   reads `value-repos.json`, `revenue-ladder.json`, and `estate-ledger` — it never duplicates them.
4. **Bounded & fail-open.** v1 caps the daily gh budget (`OBSERVATORY_WINNERS_LIMIT=3`);
   offline degrades to SKIP; every stage is `_safe`-wrapped.
5. **Deterministic by default.** `doctor` asserts byte-identical re-runs. The core pipeline (stages
   1-5) is pure computation over snapshot files; network touches are isolated to `collect.py` and
   written to evidence before analysis begins. P2-LLM and P2-SYNTH are default-off extensions.
6. **Reuse GITVS, don't reimplement it.** `gh.py` copies GITVS's proven `gh` idiom (cascade token,
   fail-open subprocess wrappers). `config.py` shares the VIGILIA parameter panel. `reconcile.py`
   delegates to VVLTVS. The estate ledger is the GITVS-owned inventory.

## Convergence record — what was overruled

| ChatGPT spec | Actual (codebase idiom) | Reason |
|---|---|---|
| `organvm/observatory` repo | In-repo organ (`organs/observation/`) | One clone, zero cross-repo drift |
| DuckDB | JSONL (append-only evidence) | Already the codebase's evidence discipline (`censor/precedents.jsonl`) |
| Astro dashboard | Next.js (existing `public-portal/`) | One stack, one deploy target |
| Playwright website capture | stdlib `urllib` (P3-CAPTURE, default OFF) | $0-capex; JS-only sites read as "not demoed" which is itself an honest signal |

Playwright website capture is the one recorded phase-3 residual: `surface.capture_site()` uses
stdlib `urllib` (fail-open, no headless browser). A future upgrade to Playwright/headless would
improve signal quality on JS-heavy sites but gains nothing for the v1 deterministic loop.

## Naming note

Working handle: **OBSERVATORY** — the legibility-and-traction organ. The final name is deferred to
the nomenclator beat (`INDEX·NOMINVM`) which resolves names through the naming canon in `NAMING.md`
(Classical / Augustan register, `U→V` swap). Until then, every code path, doc, and parameter uses
the working handle `OBSERVATORY`.

## Maturity & residual

**Maturity: scaffold → building** (organ-ladder rank 15, currently 10%). The scaffold is complete:
all 17 engine modules are built, the beat script exists, parameters are declared, the doctor
predicate passes. The organ ships DARK behind `LIMEN_OBSERVATORY=0` — it is registered but idle
until armed by `L-OBSERVATORY-ACTIVATE`.

Residual work to reach 30% (building stage):
1. **Arm L-OBSERVATORY-ACTIVATE** — the lever is declared in `his-hand-levers.json`; needs human
   approval to set `LIMEN_OBSERVATORY=1`. This is the sole remaining residual: it turns the
   proven loop (see 2–3, done) into the standing daily brief on the beat's own cadence.
2. ~~Run one real beat~~ **DONE 2026-07-13 (first light).** One-shot dry run against live GitHub:
   all stages green in 106s. Real winner (`langchain-ai/openwiki`), real hero
   (`organvm/a-i-chat--exporter`), 3 scored mechanisms (top: `copy_paste_command`, priority 9.0),
   7 internal + 4 external gaps, one reversible experiment with a full measurement contract.
   Dry discipline held: `armed/lever_homed/task_promoted` all false. The run surfaced and fixed
   two brief-shape defects at root (`date: null` → stamped; external experiment `kind: null` →
   `mechanism_transfer`).
3. ~~Beat wiring verification~~ **DONE 2026-07-13 (machine-verifiable half).** The beat's det-tier
   wiring rung fires on its own (`doctor-latest.json` written by the heartbeat, `ok: true`), and
   the full loop completes in 106s — well inside the sensor's 240s timeout. The remaining
   *on-cadence gated-loop* observation is exactly what residual 1 unlocks — it is the lever's
   receipt, not separate work.

**No capability is invented.** Every mechanism seed in `mechanisms.yaml` corresponds to a real
feature extracted by `surface.py`. Every gap type (`claim_drift`, `severed_pipe`) corresponds to
a VVLTVS check. Every formula term is computed from actually-observed data or declared in the
human-owned seeds file. The organ observes, scores, proposes — it never fabricates.

## Merge & safety

Branch per concern off `origin/main`, verify scoped (`python -m limen.observatory doctor --offline`),
self-merge on `merge-policy.sh` CLEARED. None of the organ's own paths are deploy-triggers, so its
merges do not auto-deploy. The one guardrail is unchanged: the organ never publishes public content
itself.
