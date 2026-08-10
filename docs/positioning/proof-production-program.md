# Proof-Production Program

The minimum costly-to-fake evidence required to support the chosen position ("production-systems
architect who builds and operates a governed multi-agent delivery system"). Ordered by
credibility-per-effort. Corrections and proof precede ornamentation.

Each object: claim supported → data required → visibility → effort → credibility → dependency →
acceptance criterion.

## P1 — Limen engineering report (flagship proof object)

- **Claim:** the governed multi-agent delivery system is real, operating, and measured.
- **Data:** the public dashboard's own status series (tasks by state over time), dispatch/receipt
  counts, agent-lane mix, budget-cap behavior, failure taxonomy (`failed` vs `failed_blocked` vs
  `needs_human`), verification-gate pass rates. All exists in repo + dashboard today.
- **Visibility:** public (numbers already on the public dashboard) — the report adds method.
- **Effort:** days, not weeks. **Credibility: highest** — operational receipts with failure modes
  are costly to fake precisely because they include failure.
- **Dependency:** none; data live now.
- **Acceptance:** a reader can reproduce every headline number from the public endpoint; failure
  modes given equal typographic weight to successes; cost/reliability method stated.

## P2 — Truth-reconciled public surfaces (correction before ornament)

- **Claim:** every published number is current, sourced, and dated.
- **Data:** the claims ledger; census; live URL tests.
- **Visibility:** public. **Effort:** small (this branch + the publish atoms). **Credibility:**
  foundational — one discovered stale/false claim poisons every true one.
- **Dependency:** owner publish approval (README regeneration, blog field, org README).
- **Acceptance:** `scripts/profile-link-integrity.py` exits 0; profile counts match census basis
  with date; never-publish list absent from all live surfaces.

## P3 — Cost-per-task and failure-mode analysis

- **Claim:** the system's economics are engineered, not vibes ("agentic delivery under budget
  caps").
- **Data:** budget debits per task, model-tier selection records, retry/failure costs — present
  in Limen's budget and dispatch logs.
- **Visibility:** method public; absolute spend may stay banded. **Effort:** medium.
  **Credibility:** high with buyers burned by ungoverned agent spend.
- **Dependency:** P1 framing. **Acceptance:** a named cost metric with method, date range, and
  distribution (not a single average).

## P4 — Test-reproduction receipts for flagship repos

- **Claim:** repo-asserted test counts (3,399 / ~170 / 1,107 / 400+) are real CI output.
- **Data:** fresh CI runs on each flagship, linked run URLs.
- **Visibility:** public. **Effort:** small per repo. **Credibility:** converts every
  "repository-asserted" ledger row to "verified."
- **Dependency:** none. **Acceptance:** each flagship README's test claim links a dated passing
  run; ledger rows flipped.

## P5 — Public-safe architecture demonstration

- **Claim:** the method transfers beyond its author's environment.
- **Data:** packet/lease/receipt lifecycle walk-through on a toy repo; recorded or scripted.
- **Visibility:** public. **Effort:** medium. **Credibility:** high for technical buyers;
  the demo *is* the product for governance-advisory work.
- **Dependency:** P1. **Acceptance:** a stranger can follow the demo to a verified merged change
  governed end-to-end.

## P6 — External validation objects (slower lane)

- Talks/essays derived from P1/P3 (the flagship publication of the inbound system); external
  technical review of Limen's contract surfaces; collaborator case studies where a partner
  drives the domain. Each converts internal receipts into third-party-witnessed proof.
- **Acceptance:** at least one artifact witnessed outside the estate (accepted talk, published
  review, named collaborator statement).

## Deliberately not in the program

- Public MRR disclosure — **not mandatory**; privately verified revenue or case-study-based proof
  outperforms it at this stage (compare again when revenue exists).
- Percentile/ranking claims — no independent reproducible source; excluded by ledger.
- Volume-led claims ("100 products") — excluded until classification could support a precise,
  dated, defined count — and even then volume stays context, not lead.
