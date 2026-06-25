<!-- the inbound-magnet system's own record of what's left — all of it is YOUR hand (outward-facing,
     a spend, or a judgment only you can make). The machine is built and self-verifying; these are
     the levers it deliberately does not pull for you. Cheapest path given for each. -->

# Inbound-magnet system — what's left (his hand)

The derivation layer (positioning generator + seeds + price guard), the form/operation split,
the capture funnel, and the autonomic lane are all **built, tested, and merged** (PRs #226 #228
#230 #237 #239). Everything below is a lever the system intentionally leaves to you — because it
publishes to your identity, spends, or is a judgment call that's yours to make. Nothing here
blocks the system; it sits inert and observable until you act.

| # | Trigger | Why it's yours | Cheapest path |
|---|---------|----------------|---------------|
| 1 | **Activate capture** | Publishes a contact address to the public surface | Set `frontdoor.contact` in `positioning-seeds.json` to a **dedicated inbound alias** (wiser than a personal inbox — it gets indexed). One line. Every CTA then becomes a repo+door-tagged `mailto:`. |
| 2 | **Validate the price anchors** | The bands are *my* proposals; the number is your call | Read `docs/positioning/*.internal.md` (gitignored, regenerated from seeds). Adjust the `internal_anchor` values in `positioning-seeds.json`. They never reach a public page either way. |
| 3 | **Arm the autonomic lane** | A standing token spend on the daemon | `LIMEN_POSITIONING=1` in `~/.limen.env`. Surfaces then self-refresh every 12 beats; `organ-health.py` already shows the rung (`POSITIONING:gated` until armed). |
| 4 | **Publish the front door** | Outward-facing to your public identity | Paste `docs/positioning/_frontdoor.md` onto a public profile README (`4444J99/4444J99` or `organvm/.github`). |
| 5 | **Apply discoverability** | Mutates public repo topics/descriptions | Run the `gh` commands in `docs/positioning/_discoverability.md` (one block per repo — they're copy-paste ready). |
| 6 | **Seed the rest of the portfolio** | Each public page needs *real* proof, never fabricated weight | Confirm a repo's actual proof signals (tests / deploy / scale) — or point me at them — and I'll draft its seed. Currently seeded: `public-record-data-scrapper`, `universal-mail--automation`. Queue (in `value-repos.json`): `a-i-chat--exporter`, `mirror-mirror`, `the-invisible-ledger`, `styx`, `domus-genoma`. |
| 7 | **Deeper lead capture** | Edits the live mail organ in a **separate repo** | Optional. The 3-step `inbound-lead` protocol-class recipe is in `docs/positioning/_capture.md`. Today, tagged inbound already lands classified in your existing triage; this just gives leads their own first-class lane. |

**Invariant:** none of this sends, deletes, or spends without you. Capture drafts; it never reaches out.
