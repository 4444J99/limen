# OBSERVATORY — CHARTER

The operating contract for the legibility-and-traction organ. Complements [`KERNEL.md`](KERNEL.md)
(the 5-primitive map) and the two FACE docs. Where prose and the executable predicate disagree, the
predicate (`observatory doctor` + `cli/tests/test_observatory.py`) wins.

## Provenance

Built from an imported design: the shared ChatGPT conversation `chatgpt.com/share/6a5234b0-…`, whose
one real request was *"study every day the repos and projects trending on GitHub … and figure out why
they're successful and I'm not."* ChatGPT's answer (the "OBSERVATORY" spec) scoped it as a read-only
module under LIMEN. This organ is that spec **converged onto codebase idiom**: the spec's greenfield
stack (`organvm/observatory` repo + DuckDB + Astro + Playwright) is overruled by what already exists —
an in-repo organ (GITVS's twin), JSONL evidence, a Next.js dashboard consumer, and existing registries
as ground truth. See `docs/…/review-and-implement-…observatory….md` in the plans archive for the
full derivation.

## Role & capabilities

This organ acts as the institutional equivalent of a **growth/DevRel + competitive-intelligence team** — a launch-analytics desk fused with a positioning studio. By automating the workflows of observation and reconciliation, it converts idle fleet capacity into the structural weight of a dedicated positioning team.

### Virtual Firm (Org-Chart of AI Roles)

To achieve this institutional weight without human headcount, OBSERVATORY is structured as a virtual firm of AI roles, executed sequentially by the `executive.py` convener:

- **The Scout (Data Collector):** (`collect.py` + `gh.py`) Finds top cohorts using `gh` queries. Bounded and fail-open.
- **The Analyst (Mechanism Extraction):** (`mechanism.py` + `interpret.py`) Distills unstructured signals into structured JSONL vectors. Backed by `OBSERVATORY_LLM` (Opus) when armed, otherwise uses deterministic heuristics.
- **The Auditor (Internal Face):** (`reconcile.py` + `VVLTVS`) Holds our public surfaces accountable to the internal `face-ownership.json` constitution.
- **The Strategist (Experiment Synthesis):** (`synthesis.py` + `lever.py`) Folds weekly histories into actionable priors and files human-gated proposals (PRs/levers) via `lever.propose`.
- **The Archivist (Ledger Discipline):** (`ledger.py`) Ensures all evidence is immutable (append-only JSONL) and derived state is safely regenerated.

### Workflows

1. **Observation (Macro Face):** Scans cohorts of successful external repositories and extracts the mechanisms driving their adoption (docs, fast starts, CI/CD signals).
2. **Reconciliation (Micro Face):** Holds the estate's own public surfaces against these mechanisms to ensure internal metrics are coherent.
3. **Experiment Generation:** Translates legibility gaps into actionable positioning levers and launch experiments without requiring a dedicated human staff.

### Inputs / Outputs

- **Inputs:** `gh` CLI search results, `value-repos/revenue-ladder/estate-ledger` as ground truth, internal metrics from `VVLTVS`.
- **Outputs:** Append-only JSONL evidence (`logs/observatory/*.jsonl`), daily briefs (`brief-latest.json`), and human-gated proposals (levers/PRs) to close legibility gaps.

## Home & shape

- **Charter / private data:** `organs/observation/` (this directory).
- **Engine:** `cli/src/limen/observatory/` — a subpackage mirroring `cli/src/limen/vigilia/`; one
  shell-out boundary (`gh.py`), one writer (`ledger.py`), a convener (`executive.py`) that `_safe`-wraps
  each stage, and a `__main__.py` that always exits 0 so an organ bug never wedges the beat.
- **Evidence + derived state:** `logs/observatory/` — append-only JSONL evidence
  (`snapshots/surfaces/cohorts/mechanisms.jsonl`) + regenerated `*-latest.json` derived docs.
- **Parameters:** `institutio/governance/parameters.yaml` (`OBSERVATORY_*`, master gate
  `OBSERVATORY_ENABLED=0` until armed by lever `L-OBSERVATORY-ACTIVATE`).

## Standing rules

1. **Read-only against public surfaces.** Default `run`/`reconcile apply` write only under
   `logs/observatory/` and LOCAL in-repo surfaces. A public-surface change is a *filed proposal*
   (a PR in the target repo, or a `his-hand-levers.json` lever) — never a silent push. `--apply` is the
   only path that writes a lever/task; `LIMEN_STAMP_PROPOSE` is the only path that opens a PUBLIC PR.
2. **Stars are a signal, never truth.** No score uses star count in a numerator; success is stored as
   the 8-component vector, never collapsed to a scalar; confounders (existing audience, corporate brand,
   launch event, suspected star manipulation) *discount* explanatory strength by construction.
3. **Converge, do not add a stamper.** The internal-legibility face extends the existing
   `face-ownership.json` constitution and pairs with the VVLTVS sensor; it never introduces a rival
   metric registry (that is the "four-stampers disease" the constitution was written to end).
4. **Bounded & fail-open.** v1 caps the daily gh budget (`OBSERVATORY_WINNERS_LIMIT=3`); offline degrades
   to SKIP; every stage is `_safe`-wrapped.

## Shipped — the organ is whole (zero residual)

The scaffold + reconcile + research + brief + beat build-out, then **every owned residual**, are shipped.
Each capability ships **DARK** behind its own default-off gate — nothing changes runtime behavior until armed:

- **P3-CAPTURE** ✅ — live-homepage capture (`surface.capture_site`, stdlib `urllib`; Playwright overruled to
  $0-capex, the DuckDB→JSONL / Astro→Next.js precedent). Merges `site_*` first-impression features when
  `OBSERVATORY_CAPTURE=1`; fail-open on unreachable/blocked/JS-only. Kept OUT of the pure `extract()`.
- **P2-LLM** ✅ — evidence-constrained interpretation (`interpret.py`) behind `OBSERVATORY_LLM` (default 0): a
  synthesis-class model (Opus via `model_selection`) explains the brief's mechanisms in the evidence's own
  terms, reached via a bounded `claude -p` subprocess, fail-open. The v1 core stays fully deterministic.
- **P2-SYNTH** ✅ — weekly KEEP/TEST/REJECT synthesis (`synthesis.py`, the 5th executive stage) behind
  `OBSERVATORY_SYNTH_ENABLED` (default 0): folds `mechanisms.jsonl` history into standing priors, at most once
  per ISO week (state-file gate). Writes recommendations only — never edits the human-curated `mechanisms.yaml`.
- **P-PROMOTE** ✅ — experiment→board via the tabularius single-writer (`lever.propose(apply=True)` →
  `submit_task_upsert` ticket inbox), behind `OBSERVATORY_APPLY`. Never a direct `tasks.yaml` write.
- **P3-DASH** ✅ — the owner `/observatory` Next.js page: a *pure consumer* of `brief-latest.json`, deployed
  live (`limen-dashboard.pages.dev/observatory`).

No residual remains. Future "study GitHub success" / "fix claim drift" work **EXTENDS** this organ (a new
mechanism seed, a new gap source, a new success-vector measurement) — it does not rebuild it.

## Merge & safety

Branch per concern off `origin/main`, verify scoped (`scripts/verify-scoped.sh`), self-merge on
`merge-policy.sh` CLEARED. None of the organ's own paths are deploy-triggers, so its merges do not
auto-deploy. The one guardrail is unchanged: the organ never publishes public content itself.
