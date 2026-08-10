# Cloudflare Durable Objects Standard-response mismatch

**Owner:** Anthony through human-gated lever `L-CLOUDFLARE-DO-QUOTA` and issue #2054. The registry
`his-hand-levers.json` remains the source of truth.

## Verified state

- At `2026-08-09T23:57Z`, the deployed `limen-runtime` service was reachable: GET `/health`
  returned 200.
- In the same audit window, authenticated `/api/conduct/capabilities` returned
  `500 {"detail":"Exceeded allowed rows written in Durable Objects free tier."}`.
- Cloudflare's read-only account settings report `default_usage_model: standard`.
- Cloudflare's read-only `limen-runtime` settings report `usage_model: standard` and the expected
  `CONDUCT_KEEPER` Durable Object binding.
- The current OAuth grant lacks Billing Read, so the subscriptions endpoint returns 403. That
  absence is not evidence about billing state.

[Cloudflare documents Standard as the Workers Paid usage model](https://developers.cloudflare.com/workers/platform/pricing/).
The measured facts support a Standard-versus-Free-tier-labelled response mismatch under
investigation. They do not prove that the operator exhausted a Free-plan quota, owes a plan
upgrade, or establish why Cloudflare produced the contradictory signals.

## Human gate and completion predicate

Open an authenticated Cloudflare support/account case with the worker name, exact response,
timestamp, and Standard settings. Ask Cloudflare to investigate and correct the contradictory
Free-tier-labelled response. Do not purchase, downgrade, redeploy, or replace the namespace merely
to test a theory.

After Cloudflare confirms the correction, load `LIMEN_CONDUCT_URL` and `LIMEN_CONDUCT_TOKEN` from
their credential-wall environment, then run:

```bash
/opt/homebrew/bin/limen conduct capabilities
```

Completion requires exit 0 with the capabilities schema. Then rerun the blocked continuation
launcher so its human-protected registration receives a durable session receipt.

This document and issue #2054 carry the additive correction. The keeper-owned
`GH-organvm-limen-2054` projection cannot be refreshed while the conduct endpoint returns the same
500. Once the predicate is green, reconcile that projection through the broker; never edit
`tasks.yaml` directly.

No billing change, production deployment, namespace replacement, or support message was performed
while recording this correction.

<!-- lever:L-CLOUDFLARE-DO-QUOTA -->
