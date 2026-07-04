/**
 * File-backed order persistence — the sovereign pool survives a restart.
 *
 * MONETA is built to run on a $0/ephemeral host, where the process is recycled
 * on every cold start and redeploy. Without durable storage the in-memory order
 * book — including every `reserved` buyer pooled behind an as-yet-unset receive
 * address — would evaporate on each restart, so "pool demand until the valve
 * opens" would be a promise the mint could not keep. This layers a single flat
 * JSON file under the {@link OrderStore} contract (no external DB — sovereignty
 * extends to storage), written atomically (temp file + rename) so a crash
 * mid-write can never leave a half-written, corrupt book behind.
 *
 * The file can carry buyer emails and minted licence keys, so it is written
 * owner-only (`0600`), the same posture as the signing keyfile in `keys.ts`.
 */

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import type { Order, OrderPersistence, OrderStatus } from './orders'

const ORDER_STATUSES = new Set<OrderStatus>(['reserved', 'pending', 'paid', 'expired'])

function isFiniteNumber(value: unknown): value is number {
    return typeof value === 'number' && Number.isFinite(value)
}

function optionalString(value: unknown): boolean {
    return value === undefined || typeof value === 'string'
}

function isOrder(value: unknown): value is Order {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false
    const order = value as Partial<Order>
    return typeof order.id === 'string' && order.id.length > 0
        && typeof order.address === 'string'
        && isFiniteNumber(order.sats) && order.sats >= 0
        && isFiniteNumber(order.createdAt)
        && isFiniteNumber(order.expiresAt)
        && ORDER_STATUSES.has(order.status as OrderStatus)
        && optionalString(order.email)
        && optionalString(order.license)
        && optionalString(order.txid)
}

export class FileOrderPersistence implements OrderPersistence {
    constructor(private readonly file: string) {}

    load(): Order[] {
        if (!existsSync(this.file)) return []
        try {
            const parsed = JSON.parse(readFileSync(this.file, 'utf8')) as unknown
            return Array.isArray(parsed) ? parsed.filter(isOrder) : []
        }
        catch {
            // A corrupt or partially written file must never crash the mint —
            // start empty rather than refuse to boot.
            return []
        }
    }

    save(orders: Order[]): void {
        mkdirSync(dirname(this.file), { recursive: true })
        const tmp = `${this.file}.tmp`
        writeFileSync(tmp, JSON.stringify(orders), { mode: 0o600 })
        renameSync(tmp, this.file)
    }
}
