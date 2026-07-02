# MONETA — the sovereign cash organ

*Juno **Moneta**: the Roman mint, the temple where coin was struck — the literal
root of "money" and "mint."*

Our own way to intake cash and process it — **no Stripe, no Lemon Squeezy, no
Ko-fi, no payment processor anywhere in the path.** MONETA accepts Bitcoin
(on-chain, Lightning-ready) straight to an address *you* control, confirms it
against a keyless public block explorer, and signs a product's own Pro licence —
the exact ECDSA-P256 token that product already verifies offline.

It is **fleet infrastructure, not a product feature.** One rail, many consumers:
every product embeds MONETA's public key and points its checkout here. It is the
sibling of [`quaestor`](https://github.com/organvm-iii-ergon/quaestor) — quaestor
*finds* money (grants); MONETA *intakes* it (sales) — both in `organvm-iii-ergon`,
both refusing to put a money task at a human's feet.

```
buyer ──pays sats──▶ your Bitcoin address
                          │  (you hold the keys; MONETA never touches funds)
buyer ──GET /order──▶ MONETA ──reads chain──▶ mempool.space  (read-only, no API key)
                          │
                          └─signs licence with MONETA's private key─▶ buyer
buyer pastes licence ─▶ the product verifies it offline against the public key
```

Why this shape: receiving money to a self-custodied wallet is the only rail a
private party can run end-to-end with **no account, no KYC, no middleman**. The
products' licence cores are already self-sovereign (offline signed keys); MONETA
supplies the missing half — minting them on confirmed payment instead of renting
a processor.

## What it never does

It is **read-only against the chain**. It holds no spending keys, signs no
transactions, and cannot move your funds — it only asks the explorer "did `N`
sats land at this address?". The only key it holds is the **licence**-signing key
(a code-signing key, like a release key), auto-generated on first boot.

## Consumers & migration targets

`a-i-chat--exporter` is the **first** consumer — its licence core already verifies
these tokens offline, so it only needs MONETA's public key + a checkout pointer
(see [Wire it to a product](#wire-it-to-a-product)). The rest are repos that an
org code-search shows still referencing a processor today — each a candidate to
migrate onto this rail (confirm the integration per-repo before cutting over):

| Repo | Rents today (code-search signal) |
|------|----------------------------------|
| `organvm/a-i-chat--exporter` | Lemon Squeezy — **migrate first** |
| `organvm/the-invisible-ledger` | Stripe (`src/`) |
| `organvm-iii-ergon/content-engine--asset-amplifier` | Stripe (`.env.example`, `apps/`) |
| `organvm/universal-mail--automation` | Stripe (`api/`) |

## Run

```bash
npm ci
cp .env.example .env      # fill in MINT_BTC_ADDRESS (and optionally a price)
npm start                 # http://localhost:8787
```

With nothing configured it still boots and serves `/health` + `/pubkey` — and it
**no longer turns business away**. Before a receive address is set, `/checkout`
pools each buyer as a `reserved` order (HTTP `202`) and `/health` reports the
`waiting` count. The instant `MINT_BTC_ADDRESS` is set, a reserved order opens
into a payable one on its next `/order/:id` poll and mints on confirmed payment —
no demand is lost while the valve is closed. The address is the one sovereign
value only the owner holds; it opens the valve, it is not a gate that drops sales.

Docker:

```bash
docker build -t moneta .
docker run -p 8787:8787 --env-file .env -v "$PWD/.data:/app/.data" moneta
```

## Endpoints

| Method | Path          | Purpose |
|--------|---------------|---------|
| GET    | `/health`     | Liveness + `configured` flag + `waiting` (buyers pooled behind an unset address). |
| GET    | `/pubkey`     | The ECDSA **public** JWK to embed in a product build. |
| POST   | `/checkout`   | `{ email? }` → `201` with a unique sat amount + BIP21 `payUri` when configured; `202` `reserved` (demand pooled) when no address is set yet. |
| GET    | `/order/:id`  | Poll; opens a `reserved` order once an address exists, then mints + returns the `license` once payment confirms. |

## Wire it to a product

1. `npm run keygen` — prints MONETA's **public** JWK (the private half stays in
   the gitignored keyfile / deploy secret).
2. Set it as the product's build env (for the Exporter: `VITE_EXPORTER_PUBLIC_JWK`,
   read in its `src/utils/license.ts`) so the product verifies licences MONETA signs.
3. Point the product's "Buy Pro" button at MONETA's hosted checkout; the page
   redirects the buyer back with `?ce_license_key=<licence>`, which the product
   captures automatically.

## Configuration

See [`.env.example`](./.env.example). The one self-custodied value is
`MINT_BTC_ADDRESS` — a Bitcoin address from any wallet you control. Swap
`MINT_EXPLORER_BASE` for your own self-hosted mempool/Electrs instance to drop
the last third-party read, too.
