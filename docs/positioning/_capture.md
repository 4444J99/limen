<!-- maintained by hand — the spec for the inbound capture funnel (step 4 of the inbound-magnet system) -->

# Capture funnel — how a warm inbound lands

The positioning surfaces are the lure. This is what happens the moment they bite — the
cheapest mechanism that actually works today, with **zero new infrastructure and nothing ever
auto-sent**.

## The mechanism (live, in this repo)

Set `frontdoor.contact` in `positioning-seeds.json` to the inbound address you want public.
Then every CTA the generator renders becomes a `mailto:` whose subject is **pre-tagged with the
repo and the door**:

```
[<repo-slug> · deploy] — inbound      ← client door  (cta_client)
[<repo-slug> · hire] — inbound        ← recruiter door (cta_recruiter)
[front door · deploy] — inbound       ← the aggregate landing page
```

A click opens the prospect's mail client with that subject prefilled and your address in the
`To:`. The message lands in your inbox **already classified** — by which system drew them and
which audience they are — so the existing mail triage routes it without guessing.

No contact set → CTAs render as plain text and **no address is published**. Setting `contact`
is the single switch that turns capture live, and the address is your call (a dedicated alias
is wiser than a personal inbox — it gets indexed).

## Where a captured lead lives (existing machinery)

Inbound mail flows through the **obligations ledger** (built by `universal-mail--automation`,
rendered into `obligations-ledger.json` here). A reply-owed thread becomes an obligation with a
voice-matched **draft** — `draft-only by design: there is no send` (`draft_writer.py:14`). You
press send. The lead surfaces in the same ledger face you already review.

## His-hand follow-up — the deeper wiring (separate repo, live mail organ)

To give inbound leads their own first-class lane (a badge, a level-picker draft hint), add an
`inbound-lead` protocol class. This edits the **live mail organ** in a different repo, so it is
deliberately left as a scoped, opt-in change — not made automatically here:

1. `universal-mail--automation/core/protocols.py` — add an `"inbound-lead"` class: `rung
   "protocol"`, high `priority`, `requires_reply=True`, `draft_hint` = "acknowledge; confirm
   which engagement level (1–4) fits; propose a next step."
2. `universal-mail--automation/obligations_build.py` — recognize the `[… · deploy|hire] —
   inbound` subject tag (or ingest an `audit/inbound-leads.json`) and route it through that class.
3. (optional) `scripts/obligations-view.py` — a "🎯 warm lead — `<repo>`" badge in the face.

Everything above preserves the never-send guarantee: capture and draft, never outreach.
