# {{MEMBER_NAME}} — {{NICHE_PARTNER}} Lane: The Operating Floor

## Get clients · talk to clients · move them through the funnel

> **Boundary (inherited from `../FUNNEL-ENGINE.md`, load-bearing):** every
> outbound act — post, DM, email, send, spend — is fired by the partner's own hand.
> The system stages drafts, sequences, and configs only. No scraping, no bulk
> prospecting, no automated sends. Affiliate-program and platform terms are
> honored as written.

This is a fitness-lane instance of the niche-funnel engine: a partner's own
{{EXPERIENCE_DURATION}} building an affiliate funnel, recovered from the 2026-04-25 strategy corpus
(private archive), rebuilt as a runnable floor. The machine config is
[`instances/rob-fitness.yaml`](instances/rob-fitness.yaml); the conversation
drafts are [`templates/talk-tracks-fitness.md`](templates/talk-tracks-fitness.md);
the opt-in capture spec is
[`templates/capture-form-fitness.md`](templates/capture-form-fitness.md).
`validate-funnel.py` is the predicate over all of it.

---

## 1. Get clients — hunting becomes farming

The partner's gap analysis identified the core bottleneck: {{OLD_HOURS_PER_WEEK}} manual outreach per week (the old L1), constraining growth. The partner's stated attractor law rejects "cold pressure models — grinding cold DMs without prior content-led warming." The acquisition floor is therefore **content-led, inbound-only**:

| Move | What the partner does | What the system stages |
|---|---|---|
| **L0 library** | Confirms the reel/short links already in circulation (owed atom — see engagement record) | The content inventory: every existing reel/short catalogued with a `Source_Content_ID`, so leads attribute to the piece that warmed them |
| **Content cadence** | Fires {{CONTENT_FREQUENCY}} fitness posts/week from staged drafts | Draft hooks, captions, and CTA lines per post; each CTA points at the free-plan capture form, never at a DM ask |
| **Signal response** | Replies personally to commenters/DMers who raise a hand | A daily *signal sheet*: who engaged meaningfully in the last 24h (from the partner's own notifications, which they read — the system never logs into accounts), with a suggested reply track per signal type |
| **Retired tactic** | — | Hashtag/follower scraping is **retired**, recorded as such in the instance config so no future session "helpfully" rebuilds it |

Target from the partner's KPI sheet: manual L1 hours **< 5/week** (from {{OLD_HOURS_PER_WEEK}}), and
a rising **L0 inbound ratio** (% of leads arriving from content vs. outreach).

## 2. Talk to clients — the six conversations

Every client conversation in this funnel is one of six tracks, drafted in
`templates/talk-tracks-fitness.md` and personalized per lead by Rob before he
hits send. The tracks are honest by construction: they name what's free, what
costs money, and that Rob earns an affiliate commission — the post-2025 BODi
model is 1-level affiliate distribution, so the language is *sharing a link*,
never *joining a downline*.

1. **Inbound reply** — a commenter/DMer showed intent; answer the actual
   question, offer the free plan only if they asked about training.
2. **Opt-in invite** — move an interested person to the capture form
   ("personalized free plan" — the real deliverable, gated by email).
3. **Plan delivery** — send the personalized plan; set the check-in
   expectation (weekly, opt-out anytime). The plan itself is now
   generated-then-personalized: the daily engine turns the form answers into
   a predicate-checked week-one packet in two commands (see `plan_generator`
   in the instance config), the Field Ops surface renders it for review (see
   `plan_surface`), and the cover sheet's "Coach notes / personalization"
   section is where Rob's voice goes. Red-flagged intakes never reach the
   generator — they refuse straight to the Track-1 personal conversation.
   Rob still fires the send.
4. **Check-in cadence** — the {{CRM_PLATFORM}}-driven warm loop: celebrate progress,
   surface obstacles, no pitch until the lead raises the buying question or
   completes 2+ check-ins.
5. **Offer conversation** — the paid ask, made personally: the offer ladder
   with the affiliate link disclosed as such. One ask, then respect the answer.
6. **Ambassador invite** — for VIPs who *already* share Rob's content
   organically: how to get their own affiliate link. Invitation only; no
   recruiting scripts, no income claims.

Each track carries a **disqualify-gracefully** branch — the person who isn't
a fit gets a useful pointer and a clean exit. That is both the ethics floor
and (per Rob's hero literature, *Beach Money*) the long-game play.

## 3. Move them through the funnel — stages, gates, cadence

The stage map lives in the instance config with an entry/exit criterion, a
named artifact, and a human gate per level. The operating rhythm that drives
movement:

- **Daily (≈30 min, "power half-hour"):** read the signal sheet → send
  5–10 personal replies/check-ins from staged drafts → mark outcomes in
  {{CRM_PLATFORM}}. Partner types every send.
- **Weekly:** fire the content batch ({{CONTENT_FREQUENCY}}); send one {{NEWSLETTER_NAME}}-pattern
  email to the list; review the {{CRM_PLATFORM}} warm column and pick who's ready for
  an offer conversation.
- **Monthly:** KPI review against the sheet below; prune dead leads with a
  graceful-exit note; ambassador check-in.

**KPIs (partner-owned, from the recovered production stack):** manual L1 hours,
L0 inbound ratio, owned conversion ({{SOCIAL_PLATFORM}} → email list), VIP retention months
(LTV), ambassador velocity. The monthly review asks one question per KPI:
what single staged artifact would move it most?

## 4. What's blocked on Rob (owed atoms — homed, not nagged)

These live in `organs/consulting/engagements/rob.yaml → channels.owed_by_rob`,
the durable owner. The floor runs degraded-but-running without them:

- personal BODi affiliate/referral link (until then, offer drafts carry an
  explicit `{{ROB_AFFILIATE_LINK}}` slot that the validator verifies is
  declared owed, never fabricated);
- canonical FB/IG handle confirmation (RB-8);
- current {{CRM_PLATFORM}} field schema (so the four attribution fields —
  `Source_Content_ID`, `Wearable_User`, `Owned_Media_Subscriber`,
  `Ambassador_Readiness` — land without collision);
- existing reel/short links (to seed the L0 inventory).

## 5. Reuse — what the other instances take from this floor

The six-conversation structure, the stage map shape, the capture-form spec,
and the validator are niche-agnostic. Jessica's HR instance and John F.'s
finance instance instantiate the same `instances/*.yaml` schema when they
reach EXECUTION; only the offers, idiom, and CRM differ. That is the engine
thesis working: **one floor, N niches.**

## Done predicate (this floor)

```bash
python organs/consulting/funnel/validate-funnel.py --quiet \
  && python organs/consulting/validate-consulting.py --fleet --quiet
```

Exit 0 ⟺ every instance config is structurally valid, every stage carries a
human gate, no autonomy or scraping tactic has crept into the config, and the
engagement fleet still validates.
