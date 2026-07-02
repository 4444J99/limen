import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { OrderStore } from '../orders'
import { FileOrderPersistence } from '../orders-file'

const ADDR = 'bc1qexample'
const TTL = 60_000

describe('FileOrderPersistence', () => {
    let dir: string
    let file: string

    beforeEach(() => {
        dir = mkdtempSync(join(tmpdir(), 'moneta-orders-'))
        file = join(dir, 'orders.json')
    })

    afterEach(() => {
        rmSync(dir, { recursive: true, force: true })
    })

    it('survives a restart: pooled demand and paid licences reload into a fresh store', () => {
        const sink = new FileOrderPersistence(file)

        const before = new OrderStore(sink)
        before.reserve({ id: 'r1', email: 'buyer@x.io', now: 1_000 }) // valve closed → pooled demand
        before.create({ id: 'p1', address: ADDR, baseSats: 15_000, now: 1_000, ttlMs: TTL })
        before.markPaid('p1', { license: 'LIC-123', txid: 'tx-abc' })

        // Simulate a cold start / redeploy: a brand-new process-local store that
        // reads the same file. Nothing survives in memory — only the sink does.
        const after = new OrderStore(sink)

        expect(after.countReserved()).toBe(1) // the pool did NOT leak on restart
        const pooled = after.get('r1')
        expect(pooled?.status).toBe('reserved')
        expect(pooled?.email).toBe('buyer@x.io')
        const paid = after.get('p1')
        expect(paid?.status).toBe('paid')
        expect(paid?.license).toBe('LIC-123')
        expect(paid?.txid).toBe('tx-abc')
    })

    it('reflects the latest mutation — activating a reserved order persists the opened state', () => {
        const sink = new FileOrderPersistence(file)
        const before = new OrderStore(sink)
        before.reserve({ id: 'r1', now: 1_000 })
        before.activate({ id: 'r1', address: ADDR, baseSats: 15_000, now: 2_000, ttlMs: TTL })

        const after = new OrderStore(sink)
        expect(after.countReserved()).toBe(0) // no longer pooled — the valve opened
        const opened = after.get('r1', 2_000)
        expect(opened?.status).toBe('pending')
        expect(opened?.address).toBe(ADDR)
    })

    it('starts empty and never crashes when the file is absent or corrupt', () => {
        const sink = new FileOrderPersistence(file)
        expect(new OrderStore(sink).all()).toEqual([]) // absent → empty

        writeFileSync(file, '{ not valid json', 'utf8')
        expect(new OrderStore(sink).all()).toEqual([]) // corrupt → empty, no throw
    })

    it('leaves the in-memory store (no sink) unchanged — no file is written', () => {
        const store = new OrderStore()
        store.create({ id: 'o1', address: ADDR, baseSats: 15_000, now: 1_000, ttlMs: TTL })
        expect(store.all()).toHaveLength(1)
        // A store with no persistence never touches disk; `file` stays absent.
        expect(new OrderStore(new FileOrderPersistence(file)).all()).toEqual([])
    })
})
