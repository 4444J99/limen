# Canonical Claims Ledger

The single reconciliation surface for every quantitative and qualitative claim used in public
positioning. Before any claim appears on a public surface (README, portfolio, bio, org profile,
essay, application), it must have a row here with a status that permits that surface.

Maintained beside `positioning-seeds.json` (the judgment layer) and
`docs/github-estate-census.json` (the count authority). Reconciled 2026-08-10 against the stable
two-pass W01 receipt and live authenticated evidence.

## Evidence-authority ladder

When sources disagree, higher wins. Never average contradictory numbers into a cleaner fiction —
preserve the disagreement explicitly.

1. Current authenticated primary evidence (live API calls, live HTTP tests).
2. Dated exhaustive census data (`docs/github-estate-census.json`).
3. Current repository contents, tests, deployments, analytics.
4. Contemporaneous third-party primary research.
5. Repository or profile assertions.
6. Secondary market reports and practitioner commentary.
7. Interpretations and hypotheses.

## Status vocabulary

| Status | Meaning |
|---|---|
| `verified` | Supported by current, inspectable primary evidence |
| `repository-asserted` | Reported by a repo/profile/portfolio; not independently reproduced |
| `derived` | Calculated from multiple verified records; method recorded |
| `conflicted` | Current sources disagree; disagreement preserved below |
| `unverified` | Plausible but presently unsupported |
| `superseded` | Replaced by newer authenticated evidence |

## Placement tiers

- **L1 homepage** — front-door surfaces (profile README, portfolio landing, bios).
- **L2 case-study** — flagship pages, engineering reports, methodology docs.
- **L3 data-room** — private diligence materials shared under direct request.
- **nowhere** — must not be published in any form.

---

## 1. Estate counts

| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| 314 repositories total (235 public, 79 private) | `verified` (stable two-pass census 2026-08-10T21:20:04Z) | `docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json`; both authenticated passes share the same repository identity/visibility digest | "As of August 2026, the GitHub estate contains 314 repositories — 235 public and 79 private — across a personal account and ten organizations." | L1 (dated) |
| Live count 2026-08-09: 309 repos (235 public, 74 private) | `superseded` by the newer exhaustive two-pass census | Historical authenticated per-org `gh api` listing, deduped | never use as the current estate count; retain only as historical drift evidence | L3 historical |
| 1 personal account + 10 organizations | `verified` | Census + live org listing | as-is | L1 |
| "~280 repositories" (voice memo) | `superseded` | Census supersedes | never use | nowhere |
| 307/308 repository counts (older records) | `superseded` | Census supersedes | never use | nowhere |
| Profile repository counts | `derived` on a distinct live-profile basis | `scripts/profile-visuals.py` writes `public-repos.json` from the live GitHub API; `scripts/sync-readme.py` renders its dated manifest. This is not the exhaustive census basis. | Label as live profile/API counts with the generation date; never present them as the estate census or use them to revise the dated census row above | L1 when dated and basis-labeled |
| Org README shows "215 repositories" | `superseded` (stale generation 2026-07-30) | Org profile README vs census | regenerate from census | fix, then L1 |
| Repository count ≠ product count | `verified` (classification over the W01 denominator) | `docs/positioning/estate-classification.md`; W01 two-pass receipt | "A 314-repository software and creative-systems estate containing numerous product experiments and several substantial operating systems." | L1 |

## 2. Product claims

| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| "~100 products" / "100 functioning products" / "shipped ~100 products" | `unverified` | No classification supports it; estate contains products, prototypes, specs, infra, forks, archives | never substitute "shipped products" for "repositories" | nowhere |
| Limen operates live in owner's environment | `verified` | Public dashboard `limen-dashboard.pages.dev` (public-status.json: 3,111 tasks and 1,357 completed, observed 2026-08-10); current workflow and endpoint anchors are in `docs/positioning/evidence/flagship-evidence.yaml` | "Limen is a live orchestration and governance system, operating continuously in production in its owner's environment since May 2026." "Production" = operational internally; not customer deployment | L1/L2 |
| Public-record system: 50-state coverage | `conflicted` → `repository-asserted` | Repo docs support 4 implemented state collectors (CA/TX/FL/NY) + a 50-state architecture/roadmap | "Four implemented state collectors on a fifty-state architecture" | L2 |
| AI chat exporter: ~170 tests, 5 formats, 9 locales, working ChatGPT support | `repository-asserted` | Repo README; not reproduced in this pass | "repository-reported" phrasing until CI receipt exists | L2 with label |
| AI chat exporter: "thousands of people install and use daily" | `unverified` | README assertion; no analytics inspected | remove or replace with verifiable install metric | nowhere until proven |
| Styx: substantial implementation, 1,107 asserted tests | `repository-asserted` | Repo docs; no adoption/revenue evidence | describe as implementation scale, not adoption | L2 with label |
| universal-mail: 400+ asserted tests | `repository-asserted` | Repo docs | same treatment | L2 with label |
| Your Fit Tailored: completed product | `superseded` | Spec-first pilot package; no runtime app | "specification-first pilot package" | L2 with label |
| MONETA mint live | `verified` | `mint.4444j99.dev` HTTP 200 (2026-08-09) | "self-hosted Bitcoin licence mint, live" | L2 |

## 3. Public-surface claims

| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| "Zero stars and forks across the entire estate" | `superseded` (false) | Live sweep 2026-08-09: 69 stars / 23 forks estate-wide; top: a-i--skills 15★/7F (external stargazers verified), public-record-data-scrapper 7★/6 external forks incl. one company, agentic-titan 5★/2F | do not claim zero; do not inflate either — modest but real external signal | ledger only |
| "No organization profile README" | `superseded` (stale) | `organvm/.github/profile/README.md` exists (11,204 bytes) but carries stale counts + dead links | regenerate, then link | fix, then L1 |
| "Zero external human contributors" | `unverified` | No exhaustive authorship analysis performed; limen contributors include bots + 1 external-named account | do not claim zero externals; use authorship policy language | nowhere |
| Portfolio dead at `organvm.github.io/portfolio` | `verified` (404) — root cause: repo transferred to `organvm-vii-kerygma`; Pages URLs do not follow transfers | Live HTTP tests 2026-08-09: old URL 404; `organvm-vii-kerygma.github.io/portfolio/` + `/resume/` + `/directory/` all 200; Netlify mirror 200 | repoint all references (done repo-side); durable fix = custom domain | fixed |
| Essays dead at `organvm.github.io/public-process` | `verified` (404) — same class: repo now `organvm-vi-koinonia/public-process` | Live: `organvm-vi-koinonia.github.io/public-process/` 200 | repoint org README links (generator outside this repo) | packet |
| 3 project sites 404 (narratological-algorithmic-lenses, meta-source--ledger-output, showcase-portfolio) | `verified` (404 despite Pages API "built", repos public) | Live HTTP + Pages API 2026-08-09 | re-deploy Pages or unlink from portfolio | approval atom |
| Profile `blog` field → dead URL | `verified` | Account blog field carries old portfolio URL | PATCH to kerygma URL (staged: `scripts/profile-bio-sync.py`) | approval atom |

## 4. Contribution and ranking claims

| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| "Top 1% Python committer" | `unverified` — must not publish | committers.top does not substantiate; no language-specific reproducible ranking exists; `laurea` is self-built (not independent) | "No independent, reproducible source presently supports this claim." | nowhere |
| "Top 0.1% engineering throughput" (in always-working fixtures/marketing) | `unverified` | Self-computed | do not publish as ranking; volume may be stated as raw dated counts with method | nowhere as ranking |
| 32,815 contributions (profile README) | `derived`, method not attached | Self-calculated | publishable internally only with methodology, date range, machine-assist treatment, reproducible source | L3 |
| Commit counts (e.g., limen 3,678 by owner) | `verified` per-repo | GitHub contributors API | usable per-repo with date + machine-assist disclosure | L2 |

## 5. Authorship

| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| "Solo-built" (implying every line manually authored) | `unverified` and misleading | Estate is extensively machine-assisted by design | "Architected and directed by one person through a governed, multi-agent production system." | L1 (the corrected form) |
| Machine assistance is central, not concealed | `verified` (system thesis) | Limen itself is the governing system; receipts on dashboard | per `docs/positioning/authorship-disclosure-policy.md` | L1/L2 |

## 6. Commercial evidence

| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| Revenue, paying customers, external adoption | `unverified` (absence of public evidence ≠ evidence of absence) | Private analytics/payment records not inspected in this pass | make no public revenue/adoption claims; build proof program | nowhere until proven |
| COO-level standing | `unverified` by public evidence | Professional history not investigated by dossier | do not publish executive titles; express capability through operating receipts | nowhere as title |
| Fractional-CAIO pricing bands, MRR floors, Show HN channel, LLC profits-interest structure | `unverified` (hypotheses) | Dossier market research (authority tier 6) | treat as directional hypotheses requiring buyer evidence + professional review | L3 planning only |

## 7. Limen operating metrics (proof-object source)

| Metric | Status | Evidence |
|---|---|---|
| 3,111 tasks total, 1,357 done, 459 archived, 829 open, 356 failed_blocked, 109 needs_human (since 2026-05-31) | `superseded` as a composite snapshot | The current packet refreshes only total and completed. Withhold the other status counts until they are regenerated together from a dated public snapshot. |
| Multi-agent lanes (agy, claude, codex, copilot, gemini, jules, opencode, oz, warp, github_actions) | `verified` | `AGENTS.md`, dispatch code, dashboard |
| Cost/reliability/verification metrics | not yet published | Requires the Limen engineering report (proof program object P1) |

## 8. PSP-P02 selected-flagship packet claims

The rows in this section are the public-safe, machine-reproducible subset prepared by the
PSP-P02-W04/W05 evidence cohort. W03 and W04 are accepted, and W05 is formally admitted for
sanctioned integration. This ledger is not the W05 completion receipt, does not close its issue,
and does not authorize a new public surface by itself. The verifier is
`python3 scripts/flagship-evidence.py --verify-live --json`; its exact snapshot comparisons require
a dated packet refresh when a live source changes.

The first four rows below are a managed projection of every indexed packet metric. The verifier
requires the metric identifier, status, observed value, and public-safe wording to match exactly,
so a packet refresh or removal cannot leave a stale section-8 claim behind.

| Packet metric | Status | Observed value | Public-safe wording | Tier |
|---|---|---|---|---|
| `limen/public_tasks_total` | `verified` | `3111` | The public dashboard reported 3,111 total tasks on 2026-08-10. | L2 (dated) |
| `limen/public_tasks_completed` | `verified` | `1357` | The public dashboard reported 1,357 completed tasks on 2026-08-10. | L2 (dated) |
| `public_records/implemented_collectors` | `repository_asserted_with_public_anchor` | `4` | Four implemented state collectors (CA, TX, FL, and NY) sit on a broader architecture. | L2 |
| `ai_chat_exporter/export_formats` | `verified` | `5` | The public product surface presents five export formats: Markdown, HTML, JSON, PNG, and text. | L2 |

Selected-flagship usage, installs, customers, adoption, revenue, rankings, and private
implementation remain `unverified` and deliberately withheld. No current public primary source in
the W04/W05 packet set supports them; do not publish them.

## 9. Research-criticism import

W05 imports the 13-claim W08 adjudication from immutable source head
`96d0ac9e8755c1b7ed9ecf49a82b54b501f7a4aa` ([PR #2314](https://github.com/organvm/limen/pull/2314)).
The complete per-layer citation sets remain normative in
`docs/positioning/program/research-adjudication.json` at that head. The machine-checked W05
projection in `docs/positioning/evidence/flagship-evidence.yaml` preserves every layer disposition,
publishable status, public wording, and required receipt. A verified measurement must never be
promoted into an unsupported inference or implication.

| Claim ID | Measurement | Inference | Implication | Prominence | Publishable status |
|---|---|---|---|---|---|
| `profile-production-systems-headline` | `verified` | `bounded` | `not_established` | `retain_l1` | `provisional_verified_wording` |
| `profile-portfolio-link` | `contradicted` | `supported` | `contradicted` | `correct_immediately` | `broken_link_with_live_successor` |
| `profile-has-no-proof` | `partially_verified` | `contradicted` | `bounded` | `narrow` | `partially_reproducible` |
| `profile-public-repository-counts` | `verified` | `bounded` | `not_established` | `supporting_only` | `verified_dated_profile_basis` |
| `profile-contributions-last-year` | `verified` | `bounded` | `not_established` | `supporting_only` | `verified_when_dated_and_context_labeled` |
| `profile-federation-coverage` | `partially_verified` | `bounded` | `not_established` | `retain_l2` | `verified_public_nonempty_org_coverage` |
| `profile-daily-regeneration` | `verified` | `supported` | `bounded` | `retain_l2` | `verified_observation_window` |
| `profile-universal-production-claim` | `partially_verified` | `unsupported` | `not_established` | `narrow` | `mixed_featured_system_evidence` |
| `profile-limen-operating-proof` | `verified` | `bounded` | `not_established` | `retain_l2` | `verified_owner_environment_operation` |
| `profile-zero-manual-upkeep` | `unverified` | `unsupported` | `contradicted` | `withhold` | `withheld` |
| `lavrea-top-01-throughput` | `partially_verified` | `unsupported` | `not_established` | `withhold` | `withheld_as_ranking` |
| `lavrea-top-1-python-full-stack` | `partially_verified` | `unsupported` | `not_established` | `withhold` | `withheld_as_ranking` |
| `profile-one-creator-authorship` | `verified` | `bounded` | `contradicted` | `narrow` | `publishable_with_disclosure` |

## Never-publish list

- "Top 1% Python committer" (or any unreproducible percentile).
- "~100 shipped/functioning products."
- "Solo-built" in the every-line-manual sense.
- Raw repository volume as the lead claim.
- "Zero stars/forks/contributors" (false) — and equally, inflated adoption claims.
- Unverified daily-install/usage claims.
- Revenue or customer claims without receipts.
- Executive titles (COO/CAIO) as established fact rather than capability-in-evidence.
- Private repository names or contents on any public surface.

## Update discipline

A claim changes status only with dated evidence at an equal or higher authority tier. New public
claims require a row here first. The link-rot class of failure (GitHub Pages URLs do not follow
repo transfers) is now guarded by `scripts/profile-link-integrity.py`; keep its SURFACES list
pointed at current canonical URLs, and prefer the custom-domain lever (`L-URL-HIERARCHY-SIGNOFF`)
as the durable fix.
