# IDEAL-FORMS LEDGER — limen fleet

Claude's own ideal-form ideas for the organism, tracked as **named params** — the same
weight as one of Anthony's asks (doctrine: *track my ideas like asks*; *distillation, not
reduction*). Precedent: `sovereign-systems--elevate-align/docs/IDEAL-FORMS-LEDGER.md` tracked
the Maddie project only; the limen fleet had **no** such registry — the "portals each
attempting their own ideal" were tracked nowhere. This is that registry.

Each entry is liquid, not a checkbox (per the AVTOPOIESIS gate): it names the **ideal form**,
measures the **distance from ideal** at a moment in time, and carries a **status** and an
**owner**. The ledger includes *itself* (self-reference is required, not optional).

| Field | Meaning |
|-------|---------|
| **Ideal form** | the condition when this is fully alive |
| **Distance** | how far from it we are *right now*, with evidence |
| **Status** | OPEN · PARTIAL · BLOCKED(human) · SEEDED · CLOSED |
| **Owner** | who closes the remaining distance |

---

### IF-FIRST-DOLLAR — the revenue close
- **Ideal form:** an executable first-dollar predicate that is green only when a *real payment
  has cleared*; the Exporter faucet open.
- **Distance:** every revenue product is code-complete; **tx-hash = 0**. The Exporter
  (`a-i-chat--exporter/`) still carries a literal `TODO_KO_FI_SLUG` and a build-time placeholder
  store ID.
- **Status:** BLOCKED(human) — `L-REVENUE-ACCT` requires account creation/KYC Claude cannot do.
- **Owner:** Anthony (create Ko-fi + Lemon Squeezy, paste `LEMONSQUEEZY_STORE_ID`) → Claude (wire).

### IF-AMALGAMATION — the future tense closes
- **Ideal form:** the fleet amalgamates portals faster than it spawns them; a predicate measures
  open-PR + unmerged-branch debt and the merge daemon drives it *monotonically* down.
- **Distance:** 75 open PRs, 157 unmerged branches (2026-06-25); the daemon rebases stale-base
  PRs but `gen-*`/`FORCE-route` duplicates accrete faster than they merge. No debt-trend predicate.
- **Status:** PARTIAL — merge daemon live (`merge-policy.sh`); no monotonic-debt predicate yet.
- **Owner:** Claude (predicate) + merge daemon.

### IF-LIVE-TREE-COHERENCE — the live checkout never drifts
- **Ideal form:** the live daemon checkout is always `≡ origin/main`; capture/sync keeps it
  fast-forwarded; no ahead/behind divergence, no stranded local commits.
- **Distance:** live `main` is **ahead 6 / behind 24** with uncommitted daemon state
  (`tasks.yaml`, `state/`, `obligations-ledger.json`); 6 local commits novel by patch-id
  (one is `health-office` — needs a PHI scan before any push). Residue of the
  capture↔sync deadly-embrace.
- **Status:** OPEN.
- **Owner:** Claude + the sync organ.

### IF-SESSION-NON-CONTENTION — sessions don't sit in contended worktrees
- **Ideal form:** an interactive session's cwd is an isolated, non-recycled worktree; the fleet
  never rebases or `clean`s the tree a live session is working in.
- **Distance:** this session's cwd (`.claude/worktrees/stateful-dazzling-rainbow`) was checked
  out to a fleet PR branch (`fix/creds-hydrate-noninteractive-guard`, #276), rebased, and amended
  **by the daemon mid-session.**
- **Status:** OPEN.
- **Owner:** Claude (worktree allocation / harness convention).

### IF-SENSOR-REGISTRY — the beat sensors are declared data, all consumers derive
- **Ideal form:** the beat's continuous-runtime sensors live in one registry
  (`institutio/governance/sensors.yaml`, VIGILIA's third axis beside GATES + PARAMETERS); the beat
  loop, `omega.sh`, and `armed-valve-audit.py` all **derive** from it; `check-sensors.py` holds it in
  parity. Adding a sensor is one registry entry, never a hand-wired shell block in three places.
- **Distance:** Phase 1 shipped 2026-07-10 (#884) — the registry (19 sensors), `beat-sensors.py`
  (`--list`/`--run`; dry-run reproduces the shell sequence), and `check-sensors.py` (wired into pr-gate)
  are live and drift-checked. But the live beat still **duplicates** the sensors: `metabolize.sh` runs
  the 18 hand-wired `── 0x ──` blocks, `omega.sh` hardcodes its rungs, `armed-valve-audit.py` greps the
  shell.
- **Status:** PARTIAL — declared + drift-checked (Phase 1). Phase 2 flips `metabolize.sh`/`omega.sh`/
  `armed-valve-audit.py` to derive from the registry — the high-blast-radius change on the live daemon,
  landed after equivalence is proven.
- **Owner:** Claude + tabularius.

### IF-LEDGER-OF-IDEALS — this ledger (self)
- **Ideal form:** every Claude-originated ideal is a tracked named param here; the ledger is
  linked from memory and the autopoiesis heartbeat references it (closing the self-loop).
- **Distance:** created 2026-06-25; not yet wired into a verification/heartbeat lane.
- **Status:** SEEDED (this commit).
- **Owner:** Claude.
