# MONETA — go-live runbook

MONETA is a plain `node:20` container (listens on **`PORT=8787`**, health at `/health`). **Unconfigured it safely POOLS demand** — `POST /checkout` returns `202 {"status":"reserved"}`, collects nothing, drops no buyer. Going live is two reversible steps: **deploy the container**, then **paste one self-custodied Bitcoin address**. Verified deploy-ready: `npm test` = 42/42 (mirrors `.github/workflows/moneta.yml`); unconfigured probe confirmed `configured:false` + demand pooling.

The only irreducible human atom is step (c): a self-custody `MINT_BTC_ADDRESS` (lever **L-REVENUE-ACCT `#253`**). Everything else is automatable. MONETA only ever *reads* the chain against that address; it can never move funds.

## (0) Generate the production keypair (once, locally)
```bash
cd moneta
npm ci
npm run keygen            # prints the PUBLIC JWK (embed in the exporter, step d)
cat .data/mint.key.json   # the PRIVATE JWK → becomes the MINT_PRIVATE_JWK deploy secret. NEVER paste it in chat/repo.
```
> Free hosts recycle the filesystem, which would rotate the auto-generated key and break already-issued licences. So set a **stable `MINT_PRIVATE_JWK` as a deploy secret**. The order book may reset on restart; no *issued* licence is ever invalidated.

## (a) $0 host choice
| Host | $0? | Notes |
|------|-----|-------|
| **Koyeb** | ✅ 1 free nano web service | Best fit — deploys a Dockerfile from a repo subdir. **Recommended.** |
| **Render** | ✅ free web service | Works (Docker). Sleeps ~15 min idle, no persistent disk — fine with the `MINT_PRIVATE_JWK` secret above. |
| Fly.io | ⚠️ not truly free | Usage-based / card-gated now — treat as paid. |
| ~~CF Containers (alongside media-ark)~~ | ❌ ~$5/mo | Lever **L-MEDIA-ARK-HOST `#535`** — do NOT use to save cost; pick a genuine $0 host. |

## (b) Deploy — Koyeb (recommended)
Dashboard flow (version-proof): **Create Service → GitHub `organvm/limen` → Dockerfile, work dir `moneta`, port `8787`**, then set env/secrets:
```
PORT=8787
MINT_PRICE_USD=19                      # canonical price — $19, RESOLVED 2026-07-14: the exporter site's public Pro tier ($19 one-time, site/index.html) is the promise the buyer clicked; the live launchd deploy runs $19 (reserved orders quote at open time, so pooled buyers pay what the site showed them)
MINT_RETURN_URL_BASE=https://chatgpt.com/
MINT_PRIVATE_JWK=<production private JWK from step 0 — as a SECRET>
MINT_BTC_ADDRESS=<step (c) — the human lever>
```
Render alternative: New → Web Service → repo → Root Directory `moneta`, Runtime **Docker** → same env vars → health check path `/health`.

## (c) THE ONE HUMAN STEP — lever `L-REVENUE-ACCT #253`
Paste a **self-custodied `MINT_BTC_ADDRESS`** — a receive address from a wallet you personally control (any wallet, no account, no KYC). **Never a system-minted wallet** (that would defeat self-custody). This single value opens the valve.

## (d) Wire the public key into the exporter
`npm run keygen` prints the **public** JWK. In `a-i-chat--exporter`:
- Build env: **`VITE_EXPORTER_PUBLIC_JWK`** = the public JWK string (consumed in `src/utils/license.ts` for offline verify).
- Point the "Buy Pro" button at MONETA's hosted `/` (or `/buy`); checkout redirects the buyer back with `?ce_license_key=<licence>`, which the exporter captures automatically.

## (e) Verify go-live
```bash
BASE=https://<your-moneta-host>
curl -s $BASE/health   # EXPECT {"ok":true,"configured":true,"waiting":<N>}   ← configured flips true
curl -s $BASE/pubkey   # EXPECT the SAME public JWK embedded in the exporter
```
`configured:true` ⟺ address + signing key present. Any demand pooled while the valve was closed (`waiting:N`) **auto-opens**: each `reserved` order becomes `pending` (payable, BIP21 `payUri`) on its next `GET /order/:id`, and mints on confirmed payment — no queued buyer is dropped.

> **Never commit** the private JWK or the BTC address — both are deploy-time secrets/levers, not repo content.
