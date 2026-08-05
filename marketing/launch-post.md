# MONETA Mint-as-a-Service — launch post (ready to post, never auto-sent)

> REV-organvm-limen-revenue-launch-post-0708. Publishing under the owner's identity is
> the one atom the fleet cannot do (same boundary as the LAVREA launch kit,
> L-LAVREA-LAUNCH). Every claim below is grounded in `moneta/README.md` and the live
> instance; there are deliberately **no user counts and no revenue numbers** — the
> product is newly live and the post must not invent traction.
>
> Post targets: Show HN (Tue–Thu 8–10am ET), r/selfhosted or r/Bitcoin (check each
> sub's self-promo rules first), X/LinkedIn thread.

---

## Show HN

**Title:** Show HN: MONETA – sell software licences over Bitcoin with no payment processor

**Body:**

I got tired of every "sell your software" path running through a processor — Stripe,
Lemon Squeezy, Ko-fi — each one an account, a KYC gate, a cut, and a kill switch someone
else holds. So I built the missing half myself.

MONETA is a self-hosted Bitcoin licence mint in one container. The flow:

- A buyer pays sats straight to an address you control (MONETA never touches funds —
  it holds no spending keys and cannot sign transactions).
- The mint confirms the payment against a keyless public block explorer
  (mempool.space/Esplora, read-only, no API key — swappable for your own instance).
- On confirmation it signs your product's own ECDSA-P256 Pro licence — the same
  offline-verifiable token your licence check already validates. A purchased key works
  forever, with zero network calls and nothing a third party can revoke.

The detail I'm proudest of: **unconfigured, it never turns business away.** Before you
set a receive address, `/checkout` pools each buyer as a `reserved` order and `/health`
reports how many are waiting. Set `MINT_BTC_ADDRESS` and every pooled order opens and
mints on payment. The valve opens; no sale was lost while it was closed.

First consumer in production is my fork of the ChatGPT Exporter userscript — its Buy Pro
button opens a live mint today.

Source (MIT, part of a larger open agent-ops repo): https://github.com/organvm/limen/tree/main/moneta
Live mint: https://mint.4444j99.dev/
Landing: see `docs/moneta/index.html` in the repo

Happy to answer anything about the confirmation model (unique sat amounts per order),
key persistence across $0 hosts, or why I refuse to put a processor back in the path.

**Planned first comment (methodology, post immediately after submitting):**

The design constraint that shaped everything: receiving money to a self-custodied wallet
is the only rail a private party can run end-to-end with no account, no KYC, and no
middleman. Products with offline-signed licence cores already have half the system —
MONETA is just the other half: minting those licences on confirmed payment. The mint is
read-only against the chain; the only key it holds is a licence-signing key,
auto-generated on first boot, persistable as a deploy secret so issued licences never
invalidate across restarts.

---

## Reddit (r/selfhosted; adapt title for r/Bitcoin if posted there)

**Title:** I built a self-hosted Bitcoin licence mint so my software can sell Pro keys with no payment processor

**Body:**

**What it is:** MONETA — one Docker container that takes Bitcoin payments to an address
*you* control, confirms them against a keyless public explorer (mempool.space, read-only,
no API key), and signs an ECDSA-P256 licence your product verifies offline.

**What it never does:** touch your funds. No spending keys, no transaction signing. It
only asks the explorer "did N sats land at this address?" The one key it holds is a
licence-signing key — a code-signing key, not a wallet.

**Why self-hosted matters here:** the whole point is that no third party can freeze the
rail, take a cut, or revoke a customer's licence. Even the explorer dependency is
swappable for your own mempool/Electrs instance.

**Nice property:** with no address configured it still pools demand as reserved orders
and reports the waiting count — so you can ship the checkout before you've decided on
wallet custody, and open the valve later without losing a buyer.

**Run it:**

    docker build -t moneta . && docker run -p 8787:8787 --env-file .env -v "$PWD/.data:/app/.data" moneta

Source (MIT): https://github.com/organvm/limen/tree/main/moneta · Live instance: https://mint.4444j99.dev/

---

## X / LinkedIn thread

1/ Every indie "sell your software" path rents a processor: account, KYC, a cut, and a
kill switch someone else holds. I removed the processor instead.

2/ MONETA: a self-hosted Bitcoin licence mint. Buyer pays sats to YOUR address → mint
confirms via a keyless public explorer → signs the ECDSA-P256 Pro licence your product
already verifies offline. One container. MIT.

3/ It can't rug you or your buyers: read-only against the chain, holds no spending keys.
A purchased licence verifies offline forever — nothing phones home, nothing gets revoked.

4/ My favorite part: unconfigured, it POOLS demand as reserved orders instead of failing.
Set the receive address whenever — every waiting buyer's order opens and mints. The valve
opens; no sale was lost while it was closed.

5/ Live today powering Buy Pro on my ChatGPT Exporter fork:
https://chatgpt-exporter-e08.pages.dev/ · mint: https://mint.4444j99.dev/ · source:
https://github.com/organvm/limen/tree/main/moneta

---

## Post-publish verification (any agent can run)

```bash
# each posted link resolves and the mint still serves
curl -s -o /dev/null -w "%{http_code}\n" https://mint.4444j99.dev/        # expect 200
curl -s -o /dev/null -w "%{http_code}\n" https://chatgpt-exporter-e08.pages.dev/  # expect 200
# record the post URLs back onto the task (ship-gate accepts a posted link as the artifact)
```
