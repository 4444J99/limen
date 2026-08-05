# BIFRONS — Charter (roles, workflow, boundary)

## Doctrine

Two faces, one relationship. A star is not a bookmark — it is the opening of an exchange. BIFRONS
absorbs the starred repo's wiring inward (dossiers, resonance, transmutation proposals) *and*
prepares value outward (contribution candidates, packets), threading both faces on one `exchange_id`.
It **sends nothing**: the single external write — an upstream PR — is the operator's hand.

## The loop (who does what)

| Stage | Owner | Verb |
|---|---|---|
| absorb — sync stars, build dossiers | alchemia | `alchemia stars sync\|dossier` |
| map — dossiers → resonance edges | organvm-engine | `organvm portal import-stars` |
| inbound — proposal → draft internal PR | organvm-engine | `organvm portal propose\|prepare` |
| outbound — candidate → packet (prepared) | organvm-engine | `organvm portal candidate\|package` |
| **gate** — open the upstream PR | **the operator** | `organvm portal submit --approve --execute` |
| backflow — seven-organ return | organvm-engine | `organvm portal backflow` |
| **beat** — one bounded cycle, unbidden | **this organ** | `scripts/bifrons-organ.py` → `organvm portal metabolize` |

## Boundary (the one valve)

Autonomy default **A2 = prepare, never submit**. The loop runs fully to `HUMAN_APPROVED`
autonomously; only the transition into `UPSTREAM_SUBMITTED` (the external write) requires the human,
and it rides the *existing* system-wide outbound-send valve — BIFRONS files no lever of its own.
Prepared contributions **pool** (`PATCH_PREPARED`/`HUMAN_APPROVED`) and self-surface as a count in
`PORTAL.md`; the gate is a valve the operator opens on his own cadence, not a wall the beat waits on.

## Aliveness (the beat)

`scripts/bifrons-organ.py` runs on the `bifrons-portal` heartbeat sensor (cadence
`LIMEN_BEAT_BIFRONS`, default 24). Each beat: metabolize its own past → one bounded effector cycle
(`organvm portal metabolize`, fail-open) → re-render `PORTAL.md` → write `logs/bifrons-portal.json`.
Idempotent, lockless, fail-open, `< 30s`. Verified by `avtopoiesis.py --strict` (bifrons ≥ 0.67 on
past/present/future) and `bifrons-organ.py --check` (omega det) / `--doctor` (omega live).
