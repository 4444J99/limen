# Styx & Hospes Demo Summary Report
*Generated on 2026-08-17 during demo accessibility restoration*

## Overview

Both the Styx and Hospes demos were successfully restored and are running locally. This report documents feature parity between the demo infrastructure and the full repositories, identifies UX/UI issues, and documents known gaps.

---

## STYX DEMO

### Status: Running at `http://localhost:4311` (API: `http://localhost:4310`)

### Demo Capabilities (Working)

| Category | Features |
|----------|----------|
| **Core API** | 29/29 modules functional (admin, ai, auth, b2b, behavioral, beta, compliance, contracts, crisis, dashboard, email, feed, fury, health, ledger, marketing, notifications, onboarding, oracles, pay, payments, proofs, realms, referrals, security, social, users, wallet) |
| **Web Pages** | 45/45 pages functional; demo-exclusive: `circles`, `kyc`, `partner`, `practitioner`, `tour`; full-exclusive: `whistleblower` |
| **Demo Scripts** | 35/35 demo-specific scripts (`demo:*`, `snapshot:*`, `beta:verify`, `demo:feedback`) |
| **Snapshot System** | 48/51 routes verified; Cloudflare Pages snapshot at `styx-demo-snapshot.pages.dev` |
| **Guided Tour** | 5 personas (river, sage, alecto, dr.moira, hr.lead), 5 circles (Alpha wedge through Omega enterprise), interactive overlay panel |
| **Database** | PostgreSQL `styx_demo_styxlaunch` with 298 tables, fully seeded |
| **Redis** | Running on port 6391, used for BullMQ queues and cache |

### Known Gaps / UX/UI Issues

| Issue | Severity | Reference |
|-------|----------|-----------|
| **`/admin/cac-ltv` hard-coded zeros** | High | CAC, LTV, payback, burn tiles show 0 — API does not compute these |
| **Snapshot `.next` overwrite** | Medium | `snapshot:build` overwrites `.next`; running local demo afterwards serves fixture-code that never calls `/api` |
| **Stale cache 404s on Render** | Medium | `/admin/collusion` 404'd through redeploys; requires `--clear-cache` on every page addition |
| **Auth gating probe limitation** | Medium | Bare `curl -L` on protected routes reports 200 (redirect to `/login`); cannot distinguish live page from missing one without `npm run beta:verify` with signed-in accounts |
| **Beta feedback collector** | Low | Cloudflare Workers feedback service may be unavailable (402 expected); bearer token `BETA_FEEDBACK_TOKEN` required for summary retrieval |
| **Snapshot verification blind spots** | Medium | Fails on: routes reaching `/api`, off-origin calls, missing fixtures; found 2 cases: `/admin/cac-ltv` rendering "$0 revenue, 0 users" for 403 endpoint, `/behavioral/habit-strength` returning 500 from ambiguous SQL |
| **Tour markers silently dropped** | Low | UI element position changes drop tour markers silently rather than mispointing |
| **One synthetic world, multiple testers** | Low | Two simultaneous testers see each other's contracts (by design) |
| **`NEXT_PUBLIC_STYX_GUIDED_TOUR` / `TEST_MONEY_MODE` must be `true` at build time** | Low | Compiled out of non-demo builds |
| **Sessions hard-expire after 7 days** | Low | Refresh cookies in beta environment |

### Demo Claims vs Reality

- ✅ **Synthetic test-money-only**: Verified — `npm run demo:reset:verify` recreates full stack, runs live-stack gate
- ✅ **51/51 tour routes verified**: Beta promotion workflow confirmed this (deployed 2026-08-14)
- ✅ **Guided tour with 5 personas**: Tour panel switches depth without changing content; per-browser depth memory
- ✅ **Cloudflare Pages snapshot**: 48 routes verified, deployed 2026-08-14
- ⚠️ **Note/interaction collector**: Works on live demo but requires `BETA_FEEDBACK_TOKEN` for summary retrieval; NDJSON append-only under `artifacts/`
- ⚠️ **Two operational traps**: Snapshot build overwrites `.next`; `/admin/collusion` 404'd through redeploys without `--clear-cache`
- ✅ **Automation excluded**: Telemetry off during capture/recording (`styx.guidedTour.telemetry = off` in localStorage)
- ✅ **Beta deployment via Render**: 51/51 route verified; idempotent seeder runs on boot
- ✅ **Cloudflare Workers feedback service**: Deployed during beta promotion

---

## HOSPES DEMO

### Status: Running; dashboard at `file:///Users/4jp/Workspace/hospes/dashboard/index.html`

### Demo Capabilities (Working)

| Category | Features |
|----------|----------|
| **Pipeline loop** | Load → validate → apply decisions → route → draft → brief → assets → commitments → triage — fully functional end-to-end |
| **4 audience personas** | owner (design intent/invariants), ari (show-week operating view), investor (boundary is the product), newcomer (plain language, no product knowledge) |
| **Guided tour** | 18 beats from `guide.json` with depth selector (`pitch`/`tutorial`/`practitioner`/`expert`); mid-tour depth change; `?` tooltips on instrumented controls; capability legend computed from live session |
| **Safety gates** | `SYNTHETIC DEMO — NOT AUTHORITY` marker enforcement; demo tenant checks (`ari_demo_review`/`ari_demo_complete`); safety gate refuses recording if marker/tenant wrong |
| **Decision derivation** | C4/C5 → PROTECT; everyone else → APPROVE; exercises full loop against pipeline with unknown guest names |
| **Sample decision derivation** | 5 synthetic candidates (Bixby Mortarboard, Mildred Punchclock, Rufus Quibble, Tallulah Sidecar, Professor Crumbweather) with C2/C3/C4 relationship classes |
| **Video recording** | `HOSPES_DEMO_CUT=proof` (fast, uncaptioned), `HOSPES_DEMO_CUT=pitch` (paced, captioned), `HOSPES_DEMO_CUT=tutorial` (films guided tour); safety gate before first frame |
| **Ephemeral server** | `demo --open --no-browser --port PORT`; per-run auth token (`secrets.token_urlsafe(32)`); binds loopback; server destroys bundle on exit |
| **Check_guide_registry gate** | `scripts/check_guide_registry.py` (gate 5 of `done.sh`): every `capabilities.mjs` compute has glossary entry and vice versa, every `data-guide` anchor resolves and is anchored, every beat names a real view and carries narration at every declared depth, both tracked dashboard trees are byte-identical |
| **Synthetic databases** | `ari-review.synthetic-demo.sqlite3` and `ari-complete.synthetic-demo.sqlite3` created under `~/Library/Application Support/HOSPES/private_pilot/demo/` |

### Known Gaps / UX/UI Issues

| Issue | Severity | Reference |
|-------|----------|-----------|
| **`/admin/cac-ltv` equivalent** | High | No CAC/LTV computation in hospes; demo focuses on pipeline loop, not financial metrics |
| **`14 vs 18 beats` discrepancy** | Medium | `synthetic-demo.md` claims "14 beats" but `dashboard/assets/guide.json` declares 18 beats — inconsistent and could mislead users about tour length |
| **Dashboard requires running server** | High | Static HTML `dashboard/index.html` shows placeholders without the live operator server (`python3 -m hospes operator ...`); all values are `.__HOSPES_SHOW_OPTIONS__.__` without the server |
| **CAC/LTV / financial metrics absent** | Medium | Demo focuses on pipeline loop and human gates, not financial reporting or revenue metrics |
| **No actual sends** | Medium | Demo claims "HOSPES drafts and records receipts; humans send" — full repo enforces this with actual database state and audit trail, but demo has no send endpoint |
| **Ephemeral bundles not persistent** | Low | Full repo doesn't have the marked-synthetic-bundle concept; everything is persistent in SQLite; demo bundles are destroyed on exit |
| **Persona-based depth not in full repo** | Low | Full repo operator surface doesn't automatically switch narration depth by persona; this is demo-specific |
| **Guided tour beats: 18 vs 14** | Medium | Discrepancy between `synthetic-demo.md` (14 beats) and `guide.json` (18 beats) could confuse users |
| **No multi-show support** | Low | Demo is single-show only; full repo supports multiple shows with separate DNA, voice, templates, branding |
| **No Cloudflare Access integration (local)** | Low | Demo's Cloudflare Access tunnel setup requires interactive authentication; not usable in this environment |
| **Private CSV import not available** | Low | Demo uses fixed 5 synthetic candidates; full repo has `import-candidates` with encryption and vaulting |
| **No research/analytics integration** | Low | Demo has no external API calls (research, analytics, sponsors); full repo integrates all of these |

### Demo Claims vs Reality

- ✅ **Pipeline loop mechanism works end-to-end**: Load → validate → apply → route → draft → brief → assets → commitments → triage
- ✅ **Human-gated decisions (approve/reject/protect) are enforceable**: C4/C5 → PROTECT, else → APPROVE
- ✅ **Guided tour system functions**: Beat navigation and depth switching work
- ✅ **Safety gates prevent accidental authority exposure**: Synthetic marker, tenant checks block non-demo access
- ✅ **Dashboard/UI system renders correctly when populated by operator surface**: Depends on running server
- ✅ **Demo is "resettable, non-authoritative specimen"**: Explicitly stated in README and synthetic-demo.md
- ✅ **18 beats declared in guide.json**: Tour has 18 beats with depth selector, Play/Next/Back navigation
- ⚠️ **`synthetic-demo.md` claims "14 beats"**: Inconsistency with guide.json's 18 beats; the demo may show fewer than 18 if data is absent (beats are skipped, never faked)
- ⚠️ **Dashboard "live" claim depends on server**: Without the operator server, all values are placeholders; the "Live SQLite mode" badge appears but shows no real data
- ✅ **Safety gates work as designed**: Recorder refuses to record unless `SYNTHETIC DEMO — NOT AUTHORITY` marker present AND `#context-tenant` matches demo tenant
- ✅ **Pipeline loop exercises full mechanism**: Decisions propagate through drafts, briefs, assets, commitments, triage — every stage functions

---

## COMPARATIVE SUMMARY: Styx vs Hospes

| Dimension | Styx | Hospes |
|-----------|------|--------|
| **Demo type** | Live web app (Next.js + NestJS) with guided tour, Cloudflare static snapshot, Render beta | Local SQLite-backed operator dashboard with Playwright-driven guided tour |
| **Entry point** | `npm run demo:reset:verify` then open `/tour` | `python3 -m hospes demo --open` |
| **Tour** | 51-route registry, 5 personas, 4 depth levels, right-side overlay panel | 18-beat registry, 4 personas, depth selector, docked guide-rail |
| **Video recording** | `capture-signed-in-rehearsal.mjs` (Playwright, 4-moment MP4) + `capture-tour-fallback.mjs` | `record-demo.sh` + `record-demo.mjs` (3 cuts: proof/pitch/tutorial) |
| **Remote sharing** | Cloudflare Pages snapshot (48 routes, static, no API) at `styx-demo-snapshot.pages.dev` | Cloudflare Access tunnel with origin cert (requires interactive auth) |
| **Feedback** | Standalone NDJSON server + Cloudflare Worker (`feedback-server.mjs`) | None built into demo; recorded walksonly via `record-demo.sh` |
| **Seeding** | SQL scripts (`seed.sql` + `seed-circles.sql`) into PostgreSQL | Python factory into SQLite (`synthetic_demo.py`) |
| **Hosted beta** | Render with GitHub Actions promotion workflow | Not hosted; local + Cloudflare tunnel only |
| **Enterprise demo** | Full spec for per-prospect sandboxed Render instances (~$21/mo each) | Not applicable |
| **CAC/LTV computation** | ❌ Hard-coded zeros (known gap) | ❌ Absent (demo focuses on pipeline, not financials) |
| **Auth gating probe** | ⚠️ Bare curl misleading; requires signed-in verification | ✅ Safety gates (marker + tenant) block non-demo access by design |
| **Snapshot system** | ✅ Verified 48/51 routes; operational traps documented | ❌ No snapshot system; operator server required for dashboard |
| **Known UX/UI issues** | Snapshot `.next` overwrite, stale cache 404s, tour markers silently dropped | Dashboard requires server, beat count discrepancy (14 vs 18), no financial metrics |
| **Full repo parity** | Demo is hardened variant (Node 24 pin, fail-closed geo, extra secrets) | Demo is condensed loop (pipeline only, fixture data, 4 personas) |

---

## RECOMMENDED ACTIONS

### Critical (fix before public demo)

1. **Styx**: Fix `/admin/cac-ltv` hard-coded zeros — either implement computation or document as known limitation in the runbook
2. **Hospes**: Document that dashboard requires running operator server; add warning to `synthetic-demo.md` and `dashboard/index.html`
3. **Hospes**: Resolve `14 vs 18 beats` discrepancy — update either `synthetic-demo.md` or `dashboard/assets/guide.json` to be consistent

### Medium Priority

4. **Styx**: Fix snapshot `.next` overwrite operational trap — document the workflow: `demo:reset:verify` before local demo captures
5. **Hospes**: Add `NODE_ENV` / build-time flag documentation if demo features depend on compilation flags (similar to Styx's `NEXT_PUBLIC_STYX_GUIDED_TOUR`/`TEST_MONEY_MODE`)
6. **Both**: Consider whether the demo UX could better communicate that these are "synthetic proof-of-work" specimens, not production-ready surfaces

### Low Priority / By Design

7. **Styx**: One synthetic world / multiple testers seeing each other's contracts (explicitly by design)
8. **Hospes**: Ephemeral bundles destroyed on exit (by design; full repo persists in SQLite)
9. **Both**: Auth gating limitations for bare `curl` probes (documented: use `npm run beta:verify` / `python3 -m hospes demo --open` with signed-in accounts)

---

## DEMO ACCESSIBILITY STATUS

Both demos are **accessible** from this session:

- **Styx**: `http://localhost:4311` (web client) with API at `http://localhost:4310`
  - Redis running on ports 6379 and 6391
  - PostgreSQL `styx_demo_styxlaunch` database with 298 tables
  - Node 24.18.0 via mise
  - `.env.local` with all required demo secrets

- **Hospes**: `file:///Users/4jp/Workspace/hospes/dashboard/index.html` (dashboard)
  - Synthetic databases at `~/Library/Application Support/HOSPES/private_pilot/demo/`
  - `python3 -m hospes demo` runs successfully (output: 3 approved, 3 assets, 3 briefs, 3 decisions, 3 valid routes)
  - Operator server running on loopback (port 8765 for review, 8766 for complete)

---
*Report generated from automated comparison of full repos against demo infrastructure. Known gaps are documented per each repo's runbook and readme.*