# Portfolio Information Architecture — Progressive Disclosure

Three levels, no more. Each level answers its visitor's question and offers exactly one deeper
door. Pairs every ORGANVM Greek/Latin term with an immediately understandable label — the
cosmology is brand depth, never the front door.

Companion docs: `claims-ledger.md` (what may be said where), `estate-classification.md`
(flagship evidence), `authorship-disclosure-policy.md` (how authorship is described).

## Level 1 — The front door (10 seconds)

Surfaces: `4444J99` profile README, portfolio landing page, bios, org profile README header.

Must answer, in order:
1. **What does Anthony do?** — "I build production systems that solve expensive problems."
   Supporting line: "One person, directing a governed multi-agent production system — with the
   receipts public."
2. **For whom?** — the two doors, unchanged: clients who want a system deployed for their shop;
   employers/recruiters hiring a senior systems builder.
3. **What expensive problem?** — agentic delivery that survives contact with reality: most AI
   pilots fail on governance, verification, and cost control — this estate runs on a system built
   to prevent exactly that, live since May 2026.
4. **Strongest proof?** — one link to the live Limen dashboard (public receipts: tasks,
   completion, failure states) + one flagship case study.
5. **Do next?** — one contact action per door (existing mailto pattern).

Level-1 claim rules: only `verified` ledger rows; every number dated; no volume-as-lead; no
rankings; authorship sentence present.

## Level 2 — Flagships and method (5 minutes)

Surface: portfolio case-study layer (+ per-repo positioning pages).

**Flagship selection criteria** (explicit, per mandate): technical substance, operational
reality, buyer relevance, verifiability, distinctiveness, maturity, documentation quality, live
demonstration, external validation. Not personal affection, not raw size.

**Selected flagships (5):**

| Flagship | Plain label | Selection evidence |
|---|---|---|
| **Limen** | The governed multi-agent delivery system | Live dashboard receipts (3,111 tasks / 1,357 done since 2026-05-31, observed 2026-08-09); 10 agent lanes; the system thesis itself |
| **UCC Public-Records Intelligence Platform** | Data product with a real buyer category | 4 implemented state collectors on a 50-state architecture; 3,399 repo-asserted tests; strongest external fork signal (incl. a company) |
| **AI Chat Exporter** | Consumer-grade tool with install surface | Live install page; ~170 repo-asserted tests, 5 formats, 9 locales |
| **a-i--skills** | Agent-skills library | Highest external star signal in estate (15★/7F, verified external accounts) |
| **MONETA** | Self-hosted Bitcoin licence mint | Live at mint.4444j99.dev; sovereign-commerce demonstration |

The Level-1 generator consumes this exact set from `positioning-seeds.json` →
`frontdoor.flagships`; adding a value-repository seed does not silently promote it to the front
door, and inline verified surfaces do not alter `value-repos.json` funding priorities.

Each case study: problem → architecture → decisions/tradeoffs → verification story →
status/authorship disclosure (per policy) → what it proves about the method. universal-mail and
Styx sit in the second rank until their asserted test counts are reproduced (proof program P4).

**Method page:** how the governed system works — packet/lease/receipt lifecycle, verification
gates, budget caps — written for buyers, with the engineering report (P1) as its evidence.

Selected creative/theoretical context appears here as *one* page ("the library — one system,
eight shelves"), each shelf paired with its plain label.

## Level 3 — The full estate (for the diligent)

Surfaces: estate directory, org profile README body, per-org indexes, private data room.

- Full shelf taxonomy (all orgs, plain labels beside Greek/Latin names).
- The dated census numbers, with basis and date.
- The honest archive tier (71 archived repos stay archived and labeled).
- Detailed metrics with methodology (contribution totals live here or nowhere).
- Private diligence materials (revenue, analytics, professional history) — data room only,
  by request, never on public surfaces.
- The deeper ORGANVM cosmology for those who want it.

## Navigation contract

- L1 links to L2 flagships and one L3 directory entry point; L2 links back to L1 door actions.
- Every URL on any level must be in `link-surfaces.json` or covered by
  `scripts/profile-link-integrity.py` — the link-rot class (Pages URLs don't follow repo
  transfers) is now a guarded failure mode.
- The durable front-door URL is the custom domain (`4444j99.dev`, lever
  `L-URL-HIERARCHY-SIGNOFF`); github.io URLs are canonical-secondary fallbacks.
