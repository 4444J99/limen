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
| 4 | **Publish the front door** | Outward-facing to your public identity | Paste `docs/positioning/_frontdoor.md` onto a public profile README (`4444J99/4444J99` or `organvm/.github`). |
| 5 | **Apply discoverability** | Mutates public repo topics/descriptions | Run the `gh` commands in `docs/positioning/_discoverability.md` (one block per repo — they're copy-paste ready). |
| 6 | **Publish the 3 verified-but-private repos** | Each was proof-verified and fully seeded, but its repo is **private** — flipping it public exposes your source (an outward-facing identity change), and the doctrine is *publish the form* | `mirror-mirror`, `the-invisible-ledger`, `domus-genoma` are seeded with `"awaiting_publish": true` in `positioning-seeds.json`. They're banked and tested but kept **off** every public surface (a private repo's link 404s and pulls zero inbound). When you make a repo public, delete its `awaiting_publish` line — it renders on the next pass. Until then they're listed in the generator's `AWAITING PUBLISH` log, never silently dropped. |
| 6b | **Decide styx** | Two judgment calls only you can make | (a) The value-repos key `organvm/styx` **404s**; the real public product is `organvm/peer-audited--behavioral-blockchain`. (b) That product is **pre-revenue** (pitch deck live, API undeployed) — the front door promises "live platforms… put to work today," so it doesn't fit yet without either deploying it or reframing the door to admit built-but-not-live systems. Tell me which and I'll seed accordingly. |
| 6c | **Seed the remaining value-repos** | Each public page needs *real* proof, never fabricated weight | `session-meta`, `portfolio`, and the two `limen` mirrors aren't yet seeded. Point me at a repo's real proof signals (tests / deploy / scale) — or just name it — and I'll verify and draft its seed. **Seeded & live:** `public-record-data-scrapper`, `universal-mail--automation`, `a-i-chat--exporter`. |
| 7 | **Deeper lead capture** | Edits the live mail organ in a **separate repo** | Optional. The 3-step `inbound-lead` protocol-class recipe is in `docs/positioning/_capture.md`. Today, tagged inbound already lands classified in your existing triage; this just gives leads their own first-class lane. |

**Invariant:** none of this sends, deletes, or spends without you. Capture drafts; it never reaches out.
