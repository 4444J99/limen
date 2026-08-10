# Canonical Claims Ledger

The single reconciliation surface for every quantitative and qualitative claim used in public
positioning. Before any claim appears on a public surface (README, portfolio, bio, org profile,
essay, application), it must have a row here with a status that permits that surface.

Maintained beside `positioning-seeds.json` (the judgment layer) and
`docs/github-estate-census.json` (the count authority). Reconciled 2026-08-09 against live
authenticated evidence.

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
| 313 repositories total (235 public, 78 private) | `verified` (census 2026-08-08T19:14Z) | Exhaustive authenticated census, `docs/github-estate-census.json` | "As of August 2026, the GitHub estate contains 313 repositories — 235 public and 78 private — across a personal account and ten organizations." | L1 (dated) |
| Live count 2026-08-09: 309 repos (235 public, 74 private) | `verified` (live API sweep) | Authenticated per-org `gh api` listing, deduped | Use the dated census number with its date; note drift in L3 only | L3 |
| 1 personal account + 10 organizations | `verified` | Census + live org listing | as-is | L1 |
| "~280 repositories" (voice memo) | `superseded` | Census supersedes | never use | nowhere |
| 307/308 repository counts (older records) | `superseded` | Census supersedes | never use | nowhere |
| Profile repository counts | `derived` on a distinct live-profile basis | `scripts/profile-visuals.py` writes `public-repos.json` from the live GitHub API; `scripts/sync-readme.py` renders its dated manifest. This is not the exhaustive census basis. | Label as live profile/API counts with the generation date; never present them as the estate census or use them to revise the dated census row above | L1 when dated and basis-labeled |
| Org README shows "215 repositories" | `superseded` (stale generation 2026-07-30) | Org profile README vs census | regenerate from census | fix, then L1 |
| Repository count ≠ product count | `verified` (classification) | `docs/positioning/estate-classification.md` | "A 313-repository software and creative-systems estate containing numerous product experiments and several substantial operating systems." | L1 |

## 2. Product claims

| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| "~100 products" / "100 functioning products" / "shipped ~100 products" | `unverified` | No classification supports it; estate contains products, prototypes, specs, infra, forks, archives | never substitute "shipped products" for "repositories" | nowhere |
| Limen operates live in owner's environment | `verified` | Public dashboard `limen-dashboard.pages.dev` (public-status.json: 3,111 tasks, 1,357 done, since 2026-05-31, observed 2026-08-09); worker `/health` 200 | "Limen is a live orchestration and governance system, operating continuously in production in its owner's environment since May 2026." "Production" = operational internally; not customer deployment | L1/L2 |
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
| 3,111 tasks total, 1,357 done, 459 archived, 829 open, 356 failed_blocked, 109 needs_human (since 2026-05-31) | `verified` (observed 2026-08-09) | `limen-dashboard.pages.dev` public-status.json |
| Multi-agent lanes (agy, claude, codex, copilot, gemini, jules, opencode, oz, warp, github_actions) | `verified` | `AGENTS.md`, dispatch code, dashboard |
| Cost/reliability/verification metrics | not yet published | Requires the Limen engineering report (proof program object P1) |

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
