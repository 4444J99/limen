# The Niche-Funnel Engine

## Consulting organ — the client-growth playbook (one engine, N niche instances)

> **Boundary (load-bearing):** the engine stages drafts, sequences, and configs.
> Every outbound act — post, DM, email, send, spend — is fired by a human hand
> (the client's or Anthony's). Affiliate-program and platform terms are honored
> as written. Discovery happens through published content, never bulk
> prospecting or scraping.

## The thesis

Every friend in the orbit works a niche: Rob (fitness + chess), Jessica (human
resources), Maddie (wellness — Elevate Align), John F. (finance), Anthony
himself (the ORGANVM public face + Instagram). Helping each one earn is the
same build repeated with different parameters, because **the person is the
distribution channel, not the product**. The engine is the product; each person
is a profile plugged into it.

This fuses three ladder mandates that were already declared separately:

- **consulting** (rank 6): "turn the client-intake → delivery flow into a
  repeatable autonomic playbook" — this document is that playbook's growth side
- **media** (rank 4): the POSSE distribution rail (`organvm/social-automation`)
- **social** (rank 8): the audience/koinonia thesis and the relationship rails

## The pipeline (recovered, not invented)

The stage ladder below is Rob's own funnel — 3+ years of operating discipline
from his Beachbody/BODi era. BODi ended its multi-level coach network on
2025-01-01 and moved to a 1-level affiliate model, which makes the machinery
cleanly legitimate: content → affiliate link → commission, no downline. The
2026-04-25 strategy call already designed the cross-pollination in both
directions (BODi funnel discipline into Hokage Chess; content-first discovery
into the BODi funnel). The engine generalizes that design to every niche.

| Level | Stage | What runs | Executable form | Human gate |
|---|---|---|---|---|
| L0 | Discovery content | shorts/reels/videos in the niche's idiom | per-instance content pipeline + `organvm/social-automation` (POSSE: scheduling, Mastodon, Discord, RSS — extend with IG/YT export bundles) | client fires every publish |
| L1 | Audience capture | follows, community entry | platform profiles + a "Village"-pattern community (Discord role tiers) | client owns the community |
| L2 | Opt-in | lead magnet + capture form → email list | a "Scroll"-pattern newsletter (Kit/Beehiiv) + capture form | client sends every issue |
| L3 | Conversion | offer ladder + CRM cadence | per-instance offer config (Rob's: $0 → $300/mo cohort → $500 physical+app) + the client's CRM (Rob: {{CRM_PLATFORM}}) | client makes every offer and close |
| L4 | Expansion | referrals, ambassadors, community leadership | community roles + the client's own referral links | client invites personally; no recruiting automation |

## The instance register

| Instance | Niche | Product / offer | Record | Status |
|---|---|---|---|---|
| Rob | fitness + chess (+ bridge content) | BODi affiliate links + Hokage Chess offer ladder + `organvm/gamified-coach-interface` (Legion Command Center) | `engagements/rob.yaml` · floor: `funnel/ROB-BODI-OPERATING-FLOOR.md` + `funnel/instances/rob-fitness.yaml` | EXECUTION — the proven shape |
| Jessica | human resources (+ IG growth craft) | Styx (`organvm/peer-audited--behavioral-blockchain`) + the HR organ (`organs/hr/`) | `engagements/jessica.yaml` | DISCOVERY |
| Maddie | wellness (Elevate Align) | collaboratory constellation + quaestor grant engine | `engagements/maddie.yaml` | existing record |
| John F. | finance | unscoped — that is the DISCOVERY work | `engagements/john-f.yaml` | DISCOVERY |
| Anthony | ORGANVM public face + Instagram | the product estate | media organ micro (`organs/media/`) — the principal is not a consulting client | via media organ |

## Reuse map (nothing built twice)

- **Distribution rail:** `organvm/social-automation` — POSSE backend already built
- **Gamified client surface:** `organvm/gamified-coach-interface` — the Legion
  Command Center engine, already ported fitness → chess once, designed to port.
  Its Field Ops terminal now renders the daily-engine week-one packet (the L2
  deliverable) live; real client packets load in-browser only, never committed
- **Plan generator:** `organvm/daily-engine` (private) — capture-form answers →
  refusal-gated intake → predicate-checked week-one packet, two commands (see
  `funnel/instances/rob-fitness.yaml` `plan_generator` / `plan_surface`)
- **HR product:** the Styx three-repo constellation (product + theory + art)
- **Rob's content corpus:** `4444J99/hokage-chess` docs + the 30 open limen
  board atoms (MP / FWS / CWS / RB series)
- **Newsletter + community patterns:** The Scroll and The Village specs in the
  recovered 2026-04-25 business plan v2

## Provenance — the knowledge move

The engine's substance was recovered 2026-07-04 from the drive sweep, out of
sessions previously trapped in hokage-chess-scoped project directories:

- `Archive4T:/workspace-backup/organvm/_agent/hokage-chess/` — 144 strategy
  docs (business plans, funnel analysis, market research), incl.
  `research/2026-04-25-rob-funnel-analysis.md` and
  `docs/archive/2026-04/2026-04-25-rob-call-transcript-source.md`
- `T7Recovery:/CleanUnique-Lifeboat-2026-06-13/20_TEXT/agent-records-evidence-broad/claude-dotdir/`
  — the 2026-04-25 cross-pollination plans and the rob-prompts corpus

**This document and the engagement records are the durable home for that
knowledge.** The hokage-chess repo remains the chess-brand product lane; the
funnel machinery, the cross-niche design, and the instance register live here.

## Done predicate (v1)

```bash
for n in rob jessica maddie john-f; do
  test -f organs/consulting/engagements/$n.yaml || exit 1
done
python organs/consulting/validate-consulting.py --fleet --quiet
python organs/consulting/funnel/validate-funnel.py --fleet --quiet
```

Exit 0 ⟺ every registered instance has a valid engagement record and every
shipped funnel instance passes Engine Rules #1-7 (`funnel/validate-funnel.py`).
Landed increments: the Rob fitness-lane operating floor
(`funnel/ROB-BODI-OPERATING-FLOOR.md` + `funnel/instances/rob-fitness.yaml` +
talk tracks + the L2 capture-form template). Next increments (each lands as
its own PR): the per-instance offer/links config consumed by
`social-automation`; the Rob content pipeline fed from the hokage-chess corpus.
