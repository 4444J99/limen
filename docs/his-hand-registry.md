# Known · owned · pervasive — the his-hand registry

> Surfaced once, owner + **cheapest path** each, then **not nagged** ([[known-owned-pervasive-then-idgaf]]).
> Everything reversible-and-mine is already done; only genuinely irreversible / identity / physical /
> his-login atoms are below. This is the persistent registry form — git-tracked, capture-pushed
> off-disk — that won't collide with the daemon-written `revenue-ladder.json` (whose `your_levers`
> already carries the revenue levers, quoted under item 1). Generated 2026-06-22 from a fresh 3-reader
> sweep of the live estate.

## Already autonomic — NOT your hand (closed, for the full picture)

- **Local storage creep** — DAEMON-OWNED (Tier 0 fixed + proven `b6950ff`): preserve sliver→Archive4T,
  reclaim caches + iCloud local-cache (copy→verify→`brctl evict`, reversible). 19.78 GB reclaimed in one
  pass; finishes the rest each C_BACKUP beat. [[storage-autonomic-solve]]
- **node_modules creep** — `clone-maintenance.sh`, every 8 beats; `.claude/worktrees/` hard-excluded.
- **Value measurement** — LIVE: every dispatched task carries a weight (`budget_cost`) and a graded
  return (`score-dispatch.py` → `ledger.py`). Current verdict: *"net WORTH IT — 514 shipped, 252 wasted;
  1110/1253 debits productive."* The "justify your value or die" loop is structural, not a slogan.
- **Corpus + media convergence** — `corpus-converge.py` (his words) + `media-atomize.py` (his docs → atoms,
  strand D slice 1) feed the same engine toward THE ONE, keyless.

## Your hand (irreducible — surfaced, parked)

### 1. Revenue → first dollar (Exporter) — *fastest path, ~10 min*
The Pro gate is **production-ready** (`a-organvm/a-i-chat--exporter`: 6-file license scaffold,
**125 tests green**, Lemon Squeezy + offline-ECDSA verification coded, fail-closed). Already seeded as
`REV-exporter-*` fleet tasks — **not hand-edited from this worktree**. Canonical `your_levers` holds:
- *"Ko-fi + GitHub Sponsors on the Exporter — donations flow TODAY (no LLC, no code; ~10 min each, I prep FUNDING.yml + README)"*
- *"Create the LemonSqueezy product + paste LEMONSQUEEZY_STORE_ID — unlocks the Exporter Pro tier (code already integrated)"*

**Owner:** you (account identity only). **Cheapest path:** create the Ko-fi/Sponsors/Lemon Squeezy
accounts (yours), paste `LEMONSQUEEZY_STORE_ID`; the fleet lands `FUNDING.yml` + README + checkout-URL
runbook. Nothing else blocks dollar #1.

### 2. ENC1101 → D2L build — *deadline 6/25*
Package staged **100%** at `edu-organism/classes/enc1101-summer-2026/prep/` (syllabus, schedule,
`d2l-checklist.md`, `announcements-summer2026-IMPORT.csv` = 21 rows, `intelligentagents_summer2026_d2l.xml`).
Shell is date-empty/unpublished. **Owner:** you (D2L login + cadence confirm). **Cheapest path:** ~30 min
Claude-in-Chrome drives Manage Dates + Announcements (CSV) + Intelligent Agents (XML) → publish → verify.
Say go and I co-drive while you're logged in. [[education-monolith-canon]]

### 3. Mail daemon credential — *revives the autonomous mail lane*
`universal-mail--automation/gmail_auth.py` reads, in priority order:
`GMAIL_TOKEN_JSON` → `GMAIL_TOKEN_OP_REF` → `OP_GMAIL_TOKEN_{ITEM,FIELD,VAULT}`; OAuth client via
`GMAIL_OAUTH_JSON` → `GMAIL_OAUTH_OP_REF` → `OP_GMAIL_OAUTH_{ITEM,FIELD,VAULT}`. None are set.
**Owner:** you. **Cheapest path:** set `GMAIL_OAUTH_OP_REF=op://Vault/Item/Field` in `~/.limen.env`; the
first daemon run triggers consent and auto-stores the token. (Gmail already works live via MCP; this only
revives the *autonomous* lane.) [[gmail-mutation-cascade-avenues]]

### 4. card-0186 Santander hold / Nelnet — *not required for dollar #1*
Already in `your_levers`: *"Stripe = DEFERRED — blocked by the card-0186 Santander hold; one call clears it
(also frees Anthropic + GitHub autopay)."* **Owner:** you. **Cheapest path:** one Santander call to clear
the fraud hold. Defers the subscription/Stripe path only — individual MoR rails (item 1) are unblocked.

### 5. Time Machine — *optional*
No completed backup. Data already has **3 copies** (iCloud + Archive4T + Backblaze), so TM is a
convenience, not a durability gap. **Owner:** you. **Cheapest path:** staging drive →
`tmutil setdestination`. Not blocking anything.
