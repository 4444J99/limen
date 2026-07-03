<!-- the inbound-magnet system's own record of what's left — all of it is YOUR hand (outward-facing,
     a spend, or a judgment only you can make). The machine is built and self-verifying; these are
     the levers it deliberately does not pull for you. Cheapest path given for each. -->

# Inbound-magnet system — what's left (his hand)

The derivation layer (positioning generator + seeds + price guard), the form/operation split,
the capture funnel, the autonomic lane, and the portfolio-seeding pass (a-i-chat--exporter live;
three verified repos banked behind `awaiting_publish`) are all **built, tested, and merged** (PRs
#226 #228 #230 #237 #239 + this seeding pass). Everything below is a lever the system intentionally leaves to you — because it
publishes to your identity, spends, or is a judgment call that's yours to make. Nothing here
blocks the system; it sits inert and observable until you act.

> Canonical lever: this record is mirrored on your obligations face as **`L-POSITIONING-ACTIVATE`**
> in `his-hand-levers.json` — one pointer, surfaced beside the mail levers, never nagged. This doc
> stays the full per-trigger detail; the registry entry is the index.

| # | Trigger | Why it's yours | Cheapest path |
|---|---------|----------------|---------------|
| 1 | **Activate capture** | Publishes a contact address to the public surface | Set `frontdoor.contact` in `positioning-seeds.json` to a **dedicated inbound alias** (wiser than a personal inbox — it gets indexed). One line. Every CTA then becomes a repo+door-tagged `mailto:`. |
| 2 | **Validate the price anchors** | The bands are *my* proposals; the number is your call | Read `docs/positioning/*.internal.md` (gitignored, regenerated from seeds). Adjust the `internal_anchor` values in `positioning-seeds.json`. They never reach a public page either way. |
| 3 | **Arm the autonomic lane** | A standing token spend on the daemon | `LIMEN_POSITIONING=1` in `~/.limen.env`. Surfaces then self-refresh every 12 beats; `organ-health.py` already shows the rung (`POSITIONING:gated` until armed). |
| 4 | **Publish the front door** | Outward-facing to your public identity | Two staged pages, one paste each. `docs/positioning/_frontdoor.md` — the **products** (what someone can put to work today). `docs/positioning/_method.md` — the **builder + the method behind them**: the *Autonomic-Institution* lure that presents your data/information the way the scraper's page pulled its organic lead, one level up. It makes the products land and the person inevitable. Paste either onto a public profile README (`4444J99/4444J99` or `organvm/.github`), or drop `_method.md` into its own public repo with GitHub Pages for a dedicated front door. Both carry **no prices** by design. |
| 4b | **Fix the profile's dead links** | Outward to your identity, so the publish is your call — but it's pure demand-hygiene: dead links on your top identity surface repel the exact visitors the front door is built to pull | Your live `4444J99/4444J99` README links `4444j99.github.io/portfolio` + `/resume` — both **404**; the working Pages is `organvm.github.io/portfolio` (verified 200). The two hand-maintained links (README lines ~9, ~178) are a **one-paste fix, staged and ready** — say "fix it" and I publish it. A third dead `4444j99.github.io` link lives in the generated `SYSTEM-NAV` footer (regenerates from a generator not in this repo — locating it is the follow-up, low-value footer nav). |
| 5 | **Apply discoverability** | Mutates public repo topics/descriptions | Run the `gh` commands in `docs/positioning/_discoverability.md` (one block per repo — they're copy-paste ready). **Applied & live:** `a-i-chat--exporter` (12 topics), `public-record-data-scrapper` (10), `universal-mail--automation` (8), `limen`, `portfolio` — all with buyer-facing descriptions. |
| 6 | **Publish the 3 verified-but-private repos** | Each was proof-verified and fully seeded, but its repo is **private** — flipping it public exposes your source (an outward-facing identity change), and the doctrine is *publish the form* | `mirror-mirror`, `the-invisible-ledger`, `domus-genoma` are seeded with `"awaiting_publish": true` in `positioning-seeds.json`. They're banked and tested but kept **off** every public surface (a private repo's link 404s and pulls zero inbound). When you make a repo public, delete its `awaiting_publish` line — it renders on the next pass. Until then they're listed in the generator's `AWAITING PUBLISH` log, never silently dropped. |
| 6b | **Decide styx** | Two judgment calls only you can make | (a) The value-repos key `organvm/styx` **404s**; the real public product is `organvm/peer-audited--behavioral-blockchain`. (b) That product is **pre-revenue** (pitch deck live, API undeployed) — the front door promises "live platforms… put to work today," so it doesn't fit yet without either deploying it or reframing the door to admit built-but-not-live systems. Tell me which and I'll seed accordingly. |
| 6c | **Publish session-meta when ready** | It is seeded but held `awaiting_publish` until the repo goes public | `organvm/session-meta` is fully seeded with real proof signals, but its repo is still private — a private repo's link 404s and the front door won't render it. When you flip it public, delete its `awaiting_publish` line in `positioning-seeds.json` and it renders on the next pass. (Seeded & live: `limen`, `portfolio`, `public-record-data-scrapper`, `universal-mail--automation`, `a-i-chat--exporter`.) |
| 7 | **Deeper lead capture** | Edits the live mail organ in a **separate repo** | Optional. The 3-step `inbound-lead` protocol-class recipe is in `docs/positioning/_capture.md`. Today, tagged inbound already lands classified in your existing triage; this just gives leads their own first-class lane. |

**Invariant:** none of this sends, deletes, or spends without you. Capture drafts; it never reaches out.
