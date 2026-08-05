# L2 Capture Form — fitness lane (the promised engine template)

> The opt-in gate for the personalized free plan. The plan is the *real*
> deliverable — the email capture is the fair trade, disclosed as such. This
> spec instantiates Rob's proven Google Form pattern; the field set is
> niche-agnostic (§ swap-table below) so Jessica's and John F.'s instances
> reuse the shape.

## Placement

The form link is the single CTA everywhere: post captions, pinned comments,
bio link, and Track 2 of the talk tracks. One destination, so
`Source_Content_ID` attribution stays clean.

## Fields (fitness instantiation)

| # | Field | Type | Why |
|---|---|---|---|
| 1 | Name | short text | address them like a person |
| 2 | Email | email, required | the owned-media capture — stated plainly: "this is how I send the plan + a weekly email you can drop anytime" |
| 3 | What brought you here? | short text | free-text attribution; maps to `Source_Content_ID` when it names a reel/post |
| 4 | Main goal, in your own words | paragraph | the personalization seed — the plan quotes this back |
| 5 | Days/week you can actually train | choice 1–6 | plans built on real capacity, not aspiration |
| 6 | Equipment access | checkboxes (none / dumbbells / full gym / bands) | determines plan family |
| 7 | Anything I should know? (injuries, schedule, life) | paragraph, optional | the "not a template" proof; also the disqualify signal (medical/rehab → Track 1 graceful pointer) |
| 8 | Wearable? (Whoop/Oura/watch/none) | choice, optional | feeds `Wearable_User`; future bio-synced plans per the production stack |
| 9 | Consent line | checkbox, required | "Send my plan + weekly check-in email. Unsubscribe anytime." — explicit, no pre-check |

## Routing (submission → funnel motion)

1. **Email** → the owned list (Kit/Beehiiv), tagged `fitness-free-plan`.
2. **Record** → {{CRM_PLATFORM}}: new row in the opt-in column; `Source_Content_ID`
   from field 3; `Wearable_User` from field 8; `Owned_Media_Subscriber = yes`.
3. **Rob** builds and sends the plan (Track 3) within ~48h — the SLA that
   makes the free tier feel paid.
4. Field 7 red flags (medical, rehab, disordered-eating signals) route to the
   disqualify-gracefully branch, *never* into the funnel.

## Swap table (instantiating another niche)

| Fitness field | HR-niche (Jessica) | Finance-niche (John F.) |
|---|---|---|
| Main goal | "What people problem is on fire?" | scoped at DISCOVERY — not invented here |
| Days/week capacity | team size / HR maturity | — |
| Equipment | current HR stack (payroll, ATS, handbook y/n) | — |
| Wearable | Styx interest (habit/accountability tooling) | — |

The lead magnet swaps with the niche (free plan → HR compliance-gap
checklist → TBD), but the shape — real deliverable, plain email trade,
explicit consent, attribution field, red-flag routing — is the engine's.
