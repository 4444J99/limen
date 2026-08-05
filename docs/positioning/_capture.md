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

## The deeper wiring — BUILT (the inbound-lead lane is live, not a recipe anymore)

Inbound leads now have their **own first-class lane**, end to end. What used to be a
"deliberately left, opt-in" recipe here is now shipped across two repos:

1. `universal-mail--automation` — the **inbound-lead protocol family** (`inbound-lead-hire`,
   `inbound-lead-deploy`, `inbound-linkedin`) classifies a first-touch recruiter / client /
   LinkedIn reach-out and stamps `safe_intent: inbound-ack-hire | inbound-ack-deploy` on it, so
   the armed sender can auto-send a complete, professional-direct first-touch ack (see the SAFE
   intents in `institutio/governance/mail-tiers.yaml`). Recruiter mail no longer falls into the
   `decline` intent (re-scoped to vendor/sales pitches only), and `careerbits.com` was dropped
   from the `no_reply` suppressors so recruiting-CRM mail is lead-classified upstream, not muted.
2. `scripts/opportunity-review-delta.py` + the **`opportunity-pipeline` beat sensor**
   (`institutio/governance/sensors.yaml`, gate `LIMEN_OPPORTUNITY_PIPELINE`, cadence 12 beats) —
   a lead is a pipeline, not a one-shot reply, so this read-only, fail-open, PII-clean sensor
   surfaces the count-only review-due delta each cadence: any lead where the ball is on us > 24h
   (RED), a stalled interview/offer, a LinkedIn row with no reply path (needs contact discovery /
   a Chrome pass), or a counterparty demanding a portal/ATS form. Per-lead detail lands only in
   the sealed `_people-private/opportunities` estate; the face sees `logs/opportunity-status.json`.
3. `scripts/obligations-view.py` — a `🎯 warm lead · <door>` badge renders on every inbound-lead
   row in the obligations face.

When `~/Workspace/application-pipeline` is present, the sensor also folds pipeline-state truth in
via that repo's `opportunity_sync.py` (which upserts each lead into a submission package).

Everything above preserves the never-send guarantee: the first-touch ack is SAFE-tier and only
fires when the send valve is armed (`LIMEN_MAIL_SEND=1`); capture and draft, never cold outreach.
