/**
 * Mint entrypoint. Boots an HTTP server from environment config. The signing key
 * is always resolved (auto-generated + persisted on first run) so `/pubkey`
 * serves the verify key even before a receive address is set; checkouts made
 * before `MINT_BTC_ADDRESS` is provided pool as reserved orders and open into
 * payable ones automatically once it is — no demand is turned away.
 *
 * The order book is file-backed (`MINT_ORDERS_FILE`, default `.data/orders.json`)
 * so a restart on an ephemeral host never drops the pooled demand or an issued
 * licence. Mount `.data` as a volume (or set a stable `MINT_PRIVATE_JWK`) so the
 * signing key and the book both survive across redeploys.
 */

import { isConfigured, loadConfigFromEnv } from './config'
import { importSigningKey, loadOrCreateKeypair, publicJwkFromPrivate } from './keys'
import { OrderStore } from './orders'
import { FileOrderPersistence } from './orders-file'
import { MintService } from './service'
import { startServer } from './server'

async function main(): Promise<void> {
    const config = loadConfigFromEnv()

    const keypair = config.privateJwk
        ? { privateJwk: config.privateJwk, publicJwk: publicJwkFromPrivate(config.privateJwk) }
        : await loadOrCreateKeypair(config.keyFile ?? '.data/mint.key.json')

    const signingKey = await importSigningKey(keypair.privateJwk)
    const store = new OrderStore(new FileOrderPersistence(config.ordersFile))
    const service = new MintService({ config, signingKey, store })

    startServer({ service, publicJwk: keypair.publicJwk }, config.port)
    // eslint-disable-next-line no-console
    console.log(`[mint] listening on :${config.port} — configured=${isConfigured(config)} address=${config.address || '(unset)'} price=$${config.priceUsd}`)
}

main().catch((err) => {
    // eslint-disable-next-line no-console
    console.error('[mint] failed to start:', err)
    process.exitCode = 1
})
