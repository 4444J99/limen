# EVOCATOR — the summoner (the portal)

> *"When I ask you to find everything, I'm asking you to build the portal that summons that
> context into every single place it needs to exist — not for a chat to search and then lose
> when the session ends."* — Anthony, 2026-06-25

EVOCATOR is the organ that turns a **found truth** into a **standing truth**: it takes one
canonical fact and keeps it present in every channel that fact must live in, on every beat,
self-healing drift. It is the missing connective tissue between channels the system already had.

## Why it exists

Before EVOCATOR, a truth I "found" reached only some channels, by hand:

- the **corpus** *converges* his words toward `00-THE-ONE.md` (pull-based — consumers read it),
- the **memory dir** reaches *interactive sessions* (MEMORY.md is injected natively per session),
- **capture** pushes repos off-disk for durability.

But nothing took a single found truth and **fanned it across every channel**, and nothing reached
the **autonomous beats** at all: a daemon beat (`claude -p`) is given only `FLAME.md` + its task —
never `MEMORY.md`, never a `CLAUDE.md`. So a fact written to memory was invisible to the thousands
of beats doing the actual work. "Every prompt and every session **and every beat**" was not true.

EVOCATOR closes that gap. Its key reach is **FLAME.md**, which *is* prepended to every beat: a
truth registered in the canon is held by every agent on every beat.

## The shape

One declarative source — [`canon.yaml`](./canon.yaml) — and an idempotent propagator
([`scripts/evocator.py`](../../scripts/evocator.py)) that, per beat, ensures each truth is present
in every declared channel:

| Channel | What the organ does | Reaches |
|---|---|---|
| **FLAME** | upsert a compact marked block into `FLAME.md` | **every autonomous beat** |
| **corpus** | write a collection shot the corpus-converge organ absorbs | **THE ONE** (deep self) |
| **memory** | **verify** (read-only) the memory file + `MEMORY.md` index line; report drift | **every interactive session** |
| *faces* | render `docs/CANON.md` + `evocator.html` + `logs/evocator.json` | humans + proprioception |

## How "find" works now

1. **Excavate** the answer (don't punt it back).
2. **Register one truth** in `canon.yaml` (id, claim, dense `line`, fuller `summons`,
   `source_of_record`, `confidence`, `reversible_via`, `channels`).
3. The organ **lands it everywhere**, every beat, and **self-heals** drift (writes only on change,
   so no git churn until a truth is added or edited).

The rich, hand-authored body of a truth lives in its **memory file** (domus-synced); the canon
holds the dense, machine-summonable form and the organ keeps the link honest.

## Invariants

- **Reversible by design.** Every truth names its `reversible_via` (its undo path). The canon is
  the system-of-record only for *where a truth lives*, never for overriding the truth's own owning
  repo (e.g. `quaestor` owns the MPO resolution; the canon points at it).
- **Derive, never pin.** The memory-dir scope is derived from the workspace path; every path takes
  an env override.
- **Fail-open, never gate the beat.** A missing dep / unreadable file is a logged skip, never a
  crash. No network, no tokens, can't time out.
- **Default-ON** (`LIMEN_EVOCATOR=1`; set `0` to roll back) — a portal that doesn't run isn't a
  portal. Cadence `C_EVOCATOR` (every 6 beats by default).

## Wiring

- **Heartbeat:** `C_EVOCATOR` voice in `scripts/heartbeat-loop.sh` (`evocator.py --apply` + `stamp evocator`).
- **Proprioception:** registered in `scripts/organ-health.py` (`_registry()`), and auto-discovered
  from the heartbeat regardless (membership is the loop's, never a hand-roster).
