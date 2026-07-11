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

## Owned remaining work (each owner records its own residual)

The scaffold + reconcile + research + brief + beat steps are the organ's build-out. Beyond them, the
organ owns — and schedules — its own residual (not deferred-and-forgotten, not a menu):

- **P3-CAPTURE** — Playwright website capture (the one genuinely new dependency): screenshot a winner's
  homepage/above-the-fold for first-impression features a README can't show. Isolated behind
  `surface.capture_site()` + an `OBSERVATORY_PLAYWRIGHT` param.
- **P2-LLM** — an optional evidence-constrained interpretation step tagged `classes:[synthesis, analysis]`
  (→ Opus via `model_selection`), behind `OBSERVATORY_LLM` (default 0); enriches regex-extracted surface
  features. v1 is fully deterministic.
- **P2-SYNTH** — weekly/monthly KEEP/TEST/REJECT synthesis folding `mechanisms.jsonl` history into
  standing mechanism priors.
- **P3-DASH** — a Next.js `web/app/app/observatory/` report page: a *pure consumer* of `brief-latest.json`
  (no organ code change), the way the money dashboard reads `revenue-ladder.json`.

## Merge & safety

Branch per concern off `origin/main`, verify scoped (`scripts/verify-scoped.sh`), self-merge on
`merge-policy.sh` CLEARED. None of the organ's own paths are deploy-triggers, so its merges do not
auto-deploy. The one guardrail is unchanged: the organ never publishes public content itself.
