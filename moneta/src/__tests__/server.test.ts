import type { AddressInfo } from 'node:net'
import type { Server } from 'node:http'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { startServer } from '../server'
import { MintService } from '../service'
import { loadConfigFromEnv } from '../config'
import { generateMintKeypair, importSigningKey } from '../keys'

let server: Server
let base: string
let publicJwk: JsonWebKey

beforeAll(async () => {
    const keypair = await generateMintKeypair()
    publicJwk = keypair.publicJwk
    const config = loadConfigFromEnv({ MINT_PRIVATE_JWK: JSON.stringify(keypair.privateJwk) }) // no address -> unconfigured
    const service = new MintService({ config, signingKey: await importSigningKey(keypair.privateJwk) })
    server = startServer({ service, publicJwk: keypair.publicJwk }, 0)
    await new Promise<void>(resolve => server.once('listening', () => resolve()))
    base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
})

afterAll(() => {
    server.close()
})

describe('mint HTTP server', () => {
    it('GET /health reports liveness + configured flag + pooled demand', async () => {
        const res = await fetch(`${base}/health`)
        expect(res.status).toBe(200)
        expect(await res.json()).toEqual({ ok: true, configured: false, waiting: 0 })
    })

    it('GET /pubkey serves the verify key for the product build', async () => {
        const res = await fetch(`${base}/pubkey`)
        expect(res.status).toBe(200)
        const body = await res.json() as { jwk: JsonWebKey }
        expect(body.jwk.x).toBe(publicJwk.x)
        expect(body.jwk.d).toBeUndefined()
    })

    it('POST /checkout pools demand (reserves) while unconfigured', async () => {
        const res = await fetch(`${base}/checkout`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ email: 'a@b.com' }),
        })
        expect(res.status).toBe(202)
        expect((await res.json()).status).toBe('reserved')
    })

    it('GET / serves the self-contained checkout page (no third-party checkout)', async () => {
        const res = await fetch(`${base}/`)
        expect(res.status).toBe(200)
        expect(res.headers.get('content-type')).toMatch(/text\/html/)
        const html = await res.text()
        expect(html).toContain('<!DOCTYPE html>')
        expect(html).toContain('Unlock Pro')
        expect(html).toContain('/checkout')       // drives the flow against the same-origin API
        expect(html).toContain('MONETA')          // sovereign attribution
        // No rented processor leaks into the storefront.
        expect(html.toLowerCase()).not.toContain('lemonsqueezy')
        expect(html.toLowerCase()).not.toContain('stripe')
    })

    it('GET /buy is an alias for the checkout page', async () => {
        const res = await fetch(`${base}/buy`)
        expect(res.status).toBe(200)
        expect(res.headers.get('content-type')).toMatch(/text\/html/)
    })

    it('unknown routes 404', async () => {
        const res = await fetch(`${base}/nope`)
        expect(res.status).toBe(404)
    })
})
