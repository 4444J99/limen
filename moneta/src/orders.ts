/**
 * In-memory order book. An order pins a buyer to a unique sat amount at the
 * receive address, so a single static address can disambiguate concurrent
 * payments by exact amount — no per-order address derivation (and so no xpub or
 * hot wallet) required for v1.
 *
 * `now`/`id` are injected so the lifecycle is deterministic under test. The store
 * is intentionally process-local; persistence can be layered later without
 * changing this contract.
 */

export type OrderStatus = 'reserved' | 'pending' | 'paid' | 'expired'

export interface Order {
    id: string
    email?: string
    /** Empty while `reserved` (no receive address yet); set when the order opens. */
    address: string
    /** Exact amount the buyer must send, unique among this address's open orders. `0` while reserved. */
    sats: number
    createdAt: number
    expiresAt: number
    status: OrderStatus
    /** Minted licence key, present once `status === 'paid'`. */
    license?: string
    /** Confirming transaction id, present once paid. */
    txid?: string
}

export interface CreateOrderInput {
    id: string
    email?: string
    address: string
    /** Desired amount; bumped upward to stay unique among open orders. */
    baseSats: number
    now: number
    ttlMs: number
}

export class OrderStore {
    private readonly orders = new Map<string, Order>()

    create(input: CreateOrderInput): Order {
        const sats = this.uniqueSats(input.address, input.baseSats, input.now)
        const order: Order = {
            id: input.id,
            email: input.email,
            address: input.address,
            sats,
            createdAt: input.now,
            expiresAt: input.now + input.ttlMs,
            status: 'pending',
        }
        this.orders.set(order.id, order)
        return order
    }

    /**
     * Pool a buyer's intent before there is any receive address to pay to. The
     * mint has no rail yet, so we hold the demand — not lose it — and open it
     * into a payable order the moment the valve (a receive address) is set.
     */
    reserve(input: { id: string, email?: string, now: number }): Order {
        const order: Order = {
            id: input.id,
            email: input.email,
            address: '',
            sats: 0,
            createdAt: input.now,
            expiresAt: 0,
            status: 'reserved',
        }
        this.orders.set(order.id, order)
        return order
    }

    /** Open a reserved order into a payable one once a receive address exists. */
    activate(input: { id: string, address: string, baseSats: number, now: number, ttlMs: number }): Order | undefined {
        const order = this.orders.get(input.id)
        if (!order || order.status !== 'reserved') return undefined
        order.address = input.address
        order.sats = this.uniqueSats(input.address, input.baseSats, input.now)
        order.createdAt = input.now
        order.expiresAt = input.now + input.ttlMs
        order.status = 'pending'
        return order
    }

    /** How many buyers are pooled behind an unopened valve (no address yet). */
    countReserved(): number {
        let n = 0
        for (const order of this.orders.values()) if (order.status === 'reserved') n++
        return n
    }

    get(id: string, now?: number): Order | undefined {
        const order = this.orders.get(id)
        if (!order) return undefined
        if (order.status === 'pending' && typeof now === 'number' && now >= order.expiresAt) {
            order.status = 'expired'
        }
        return order
    }

    markPaid(id: string, info: { license: string, txid: string | null }): Order | undefined {
        const order = this.orders.get(id)
        if (!order) return undefined
        order.status = 'paid'
        order.license = info.license
        if (info.txid) order.txid = info.txid
        return order
    }

    all(): Order[] {
        return [...this.orders.values()]
    }

    /** Smallest amount >= baseSats not already taken by an open order at the address. */
    private uniqueSats(address: string, baseSats: number, now: number): number {
        const taken = new Set<number>()
        for (const order of this.orders.values()) {
            if (order.address !== address) continue
            const stillOpen = order.status === 'pending' && now < order.expiresAt
            if (stillOpen) taken.add(order.sats)
        }
        let sats = Math.max(1, Math.ceil(baseSats))
        while (taken.has(sats)) sats++
        return sats
    }
}
