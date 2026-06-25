# The Executive Life Office — Charter

*Working name: the Executive Life Office. Proposed canonical name (subject to the NOMENCLATOR): **OFFICIVM·VITAE**, the Office of Life (digital estate). Organ id: `life`.*

The digital-life sibling of the [Executive Health Office](../health-office/CHARTER.md): same instinct, same firewall, a different domain. Implemented by `scripts/life-organ.py`.

---

## 1. Mandate

This is an **institution**, not an errand.

The wealthy do not personally remember which of their accounts is the real one, track what gets deleted when a subscription lapses, keep a register of what they own and on which platform, or know whether a thing they bought can move from one device to another. They pay a small standing staff — a **records keeper**, an **estate / asset steward**, a **subscriptions manager**, a **chief of staff** — to run that apparatus around them.

This office is the AI prosthesis for that staff: the records keeper for a person's *digital* life — accounts, assets, subscriptions, recovery paths — made available to one person with none of the staff.

It does **not** enter credentials, create or delete accounts, change account settings, or perform recovery steps that require a password. Those are the principal's to do; the office keeps the chart, derives the deadlines, surfaces the one human action, and makes sure nothing drops.

## 2. Departments

**The inventory spine** (reactive — nothing silently lost):
- **LEDGER** — keeps the Life Chart's integrity: platforms, accounts, IDs, ownership.
- **ASSETS** — what's owned and where; the cross-platform transfer rules (what can move device-to-device and what is platform-locked).
- **DEDUP** — flags duplicate / conflicting accounts and which is canonical.

**The stewardship wing** (proactive — carry the load):
- **SUBSCRIPTIONS** — recurring memberships and the **derived purge clock**: when a membership lapses, what data gets deleted and *when*. The deadline is computed from the lapse date + a known purge rule (`PURGE_RULES` in the organ) — never pinned in the chart.
- **INBOX** — the open actions only the principal can do.
- **BRIEFING** — rolls every department into one Executive Life Briefing + an append-only chronicle.

## 3. Data separation (the firewall)

- **The Life Chart** lives OUTSIDE any git checkout, at `$LIMEN_LIFE_DIR` (default `~/Workspace/_life-private/digital-accounts.json`). It holds account IDs / handles / partial payment refs and is structurally uncommittable.
- The organ **reads** the chart and never mutates it.
- It writes human-readable products (`briefing.md`, `open-actions.md`, `chronicle.jsonl`) back into the private dir, and a **counts-only, PII-free** liveness stamp to `logs/life-organ-state.json` so `organ-health.py` can see it fired. No account ID ever reaches `logs/`, `web/`, or stdout.

## 4. Liveness

Fired by `heartbeat-loop.sh` on the `C_LIFE` cadence (`stamp life`); monitored by `organ-health.py` (rung `LIFE`, probing `logs/life-organ-state.json`). Read-only, lockless, fail-open: a missing chart yields a "no chart yet" stamp, never a crash, and never blocks the beat.
