# Inbound Magnet System — repos that get *asked*, never ask

**Thesis (his words, locked):** "We need the money to come to us. Asking for shit is shit; we want to be asked for shit — this way we are in the position of power." The 200+ repos are **lures**. They exist so the buyer who has the expensive problem *finds him*, lands in his inbox, and already understands they're going to pay — before a single dollar sign is spoken.

Two non-negotiables that shape everything below:

1. **High-ticket only.** No Fiverr, no $5 hand jobs, no negotiation. The ask is high-ticket off the bat. The whore move — "yeah great idea" then never doing it — is dead.
2. **No dollar signs on the wall.** The buyer must *know they're going to pay* from the production-grade weight of the work, not from a price tag. Value signals price. The number stays off the page until they're in the door.

And the surface serves **two buyers at once**, same proof:

- **Clients** — MCA funders, ops leads, founders who need the thing built/run. High-ticket engagements.
- **Recruiters / employers** — $100–200k remote roles. He should already have people knocking. Same repos that prove "this solves your problem" prove "this is the builder you want to hire."

---

## Part 1 — Case study: `public-record-data-scrapper` (the proving ground, NOT a lead to operate)

> This repo already attracted a real warm inbound lead unprompted. We do **not** chase that lead, draft its emails, or book its calls. We use it to *derive the pricing model and positioning* — then generalize. (See memory `repos-are-inbound-signal-surface`.)

**What it is:** a production 50-state UCC public-records aggregation platform — collects UCC-1 filings from Secretary-of-State portals, enriches with SEC/OSHA/USPTO/Census + key-gated premium sources, scores each prospect 0–100 on financing likelihood with an A–F health grade, delivers via dashboard / REST API / CLI. 3,399 passing tests, Terraform AWS (multi-AZ RDS, Redis, S3), 60+ collection agents, live Vercel deploy.

**Who pays, and why it's high-ticket:** MCA funders / ISOs / brokers buy leads *constantly*. Commodity aged UCC lists are cheap and worthless; **exclusive, fresh, enriched, scored** UCC leads are the difference between a dialer full of dead numbers and a funded deal — and one funded deal is a 8–15% commission on a $50k–$500k advance. Good data here is worth thousands per conversion. That's the whole reason this is high-ticket: the buyer's *cost of not having it* is enormous.

### The RPG dialogue tree — engagement paths (deepest = highest ticket)

Each path is a "level" of implementation. The buyer self-selects by depth. Prices here are **internal proposal anchors** — defensible bands to negotiate *up* from, never published on the page. (He said "I don't even know what to charge" — these are the starting model, to validate against real MCA-data market rates.)

| Path | What they get | Internal anchor | Cadence |
|------|---------------|-----------------|---------|
| **1 · "Feed me leads"** (Data-as-a-Service) | They never touch the platform. We deliver scored, enriched, **exclusive** UCC leads on a recurring feed — their states, their filters. Beats every commodity list they buy today. | **$3k–$15k / mo** by volume · states · exclusivity | Recurring — *this is the engine* |
| **2 · "Run it in my shop"** (White-label deploy) | The platform under their brand, their infra (or our managed). They own the pipeline; stop renting lists forever. | **$25k–$75k** setup + **$2k–$8k / mo** managed | Setup + recurring |
| **3 · "Build it for my exact world"** (Custom) | Their states, scoring tuned to *their* underwriting, integration into their CRM/dialer (Salesforce, GHL…), their compliance vertical. | **$40k–$150k** project | Project + optional retainer |
| **4 · "Build my whole data org"** (Fractional / retainer) | He *becomes* their data-infrastructure engine — this system, the next one, the next. | **$10k–$25k / mo** retainer | Ongoing — **bleeds into the comp conversation** |

**Path 4 is the bridge to the recruiter door.** "Be our data org on retainer" and "come run our data org for $180k" are the same conversation from two sides. The surface that opens Path 4 for a client opens the senior-hire offer for an employer. Build once, both doors open.

### How the buyer *knows they'll pay* without a price tag

The production-grade weight **is** the price signal. `3,399 tests · Terraform multi-AZ · 50-state · live deploy` reads, to anyone who builds, as *"this is not a free toy and the person who made it does not work for free."* The README's job is to make the expensive problem and the serious solution obvious, then offer one door:

> **Deploy this for your shop →** / **Work with the team that built this →**  (routes to inbox; no price)

That CTA is high-ticket by *omission* — a price tag invites haggling; its absence says "if you have to ask, this conversation starts at serious." That's the position of power, encoded in the page.

---

## Part 2 — The en-masse system (what I build)

The case study above is a **hand-built instance**. The system makes it the **structural default** across every value-repo — warm inbound by existing, at scale, for both buyer types. It rides the existing fleet/organ pattern and operates over `value-repos.json` (revenue/conductor repos first).

```
                    ┌─────────────────────────────────────────┐
                    │  INBOUND MAGNET ORGAN  (daemon lane)      │
                    │  runs continuously over value-repos.json  │
                    └─────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
  A. POSITIONING            B. DISCOVERABILITY            C. CAPTURE
  (per repo)                (make the buyer find it)      (they come to us)
```

**A · Positioning layer** — for each value-repo, derive and inject a consistent positioning block (no prices): `{ buyer persona · the expensive problem · cost-of-not-having-it · engagement ladder (the RPG tree) · implied-premium CTA }`. This is literally the Part-1 artifact, *generated* per repo instead of hand-written.

**B · Discoverability layer** — make the buyer land:
- GitHub **topics** tuned to how the buyer searches ("ucc-leads", "mca-data", "lead-enrichment"…), not how an engineer tags.
- README headers/structure SEO'd for the buyer's vocabulary.
- A **front-door**: profile README + a single site that frames the 200 repos as a *portfolio of solved expensive problems* = proof of power.
- **Two doors on the front-door:** **"Deploy a solution →"** (clients) and **"Hire the builder →"** (recruiters / $100–200k roles). Same proof, two audiences.

**C · Capture layer** — every CTA routes to one inbound funnel that lands in his inbox, tagged by repo + door. **No outbound, ever** — capture is not chasing. Email stays draft-only + his hand. They knock; we open.

**The organ (E):** a daemon lane in the existing fleet that runs A+B over the value-repos continuously — regenerate positioning, keep topics/SEO fresh, keep the front-door current — so inbound stops being a lucky accident (the way the scraper lead happened) and becomes the system's steady-state output.

### Build order (each step shippable, none requires operating any lead)

1. **Positioning generator** — the per-repo artifact generator (Part-1 shape, parameterized). Prove it by regenerating the scraper repo's positioning block.
2. **Front-door** — profile README + portfolio site, two doors (client / recruiter).
3. **Discoverability pass** — topics + SEO across `value-repos.json` repos.
4. **Capture funnel** — one tagged inbound form → inbox.
5. **Organ lane** — wire 1–4 into the daemon so it self-runs and stays fresh.

### What stays his hand / a lever (unchanged)
Anything that **sends** (replies to inbound, outbound). Capture lands it in his inbox; he opens the conversation. The system's job ends at "they're knocking and they already know they'll pay."

---

*Origin: session 9388ade2. Companion memory: `repos-are-inbound-signal-surface`. Price bands are internal proposal anchors to validate against real market rates — never published.*
