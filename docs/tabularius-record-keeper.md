# TABVLARIVS — the one record-keeper over the board

> *The Roman* tabularius *kept the* tabulae publicae *— the single authoritative civic ledger. This
> organ keeps `tasks.yaml`: the one process allowed to edit the holy board, so the ~32 uncoordinated
> writers stop tearing it.* Sibling of MONETA (intakes cash), quaestor (finds money), CVSTOS (keeps
> the host), VVLTVS (keeps the face). **TABVLARIVS keeps the books.**

## The disease

`tasks.yaml` is the single SSOT board. Today **~32 code paths** across 5 tiers (CLI core, ~20
scripts, 7 FastAPI endpoints, 4 Cloudflare-Worker endpoints, 3 MCP handlers) each mutate it by
*read-whole-board → mutate-in-memory → rewrite-whole-board*. A `queue_lock` mutex exists but only
~13 of them honor it; the MCP server bypasses even the atomic write.

Two failure modes follow, and they are distinct:

- **Torn bytes** — a non-atomic writer (MCP's raw `open(w)+yaml.dump`) can leave a truncated/partial
  file. `io.atomic_write_text` (temp + `os.replace`) already prevents this *for writers that use it*.
- **Lost updates (clobber)** — two writers that both `load→mutate→save`, even under a save-only lock,
  race: the second's whole-board rewrite overwrites the first's just-committed change (last-writer-
  wins). Locking the `save` alone does **not** fix this — only serializing the whole
  read-modify-write does. Once collapsed 1449 tasks → 1 (the 2026-06-26 halt).

This is the "it's been messing up things a lot" the record-keeper dissolves.

## The cure: the single-writer principle

Workers stop mutating shared state. They **append one immutable ticket per unit of work** to a
lock-free inbox and hand it off. Exactly **one** keeper — TABVLARIVS — drains the inbox, folds the
tickets onto the board in order, validates, and seals. Because it is the *only* process doing
read-modify-write, there is no interleave to tear and no update to lose.

This is not new infrastructure. It is **Step 2+3 of `board-is-event-log-projection`** (memory;
PR #543): `materialize.fold` is the already-proven pure reducer (`board = fold(events)`); TABVLARIVS
gives it a live stream to consume. A ticket **is** a `materialize` Event with provenance, and the
archived ticket files are the append-only event log the board projects from.

```
   worker ──submit_ticket()──▶  logs/tickets/inbox/<id>.json   (atomic exclusive create; no lock, no board read)
                                          │
                     TABVLARIVS (each beat, sole queue-lock holder)
                                          │  drain → fold onto healed board → validate → collapse-guarded seal
                                          ▼
   logs/tickets/archive/  ◀── applied     tasks.yaml (the committed projection)
   logs/tickets/rejected/ ◀── quarantined (+ <id>.reason.txt)
```

### Components (shipped)

| Piece | Where | Role |
|-------|-------|------|
| Engine | `cli/src/limen/tabularius.py` | `Ticket`, `submit_ticket()`, `submit_task_upsert()`, `drain_once()`, the fold/validate/seal + quarantine |
| Producer API | `cli/src/limen/tabularius.py` → `submit_task_upsert()`, `submit_task_status()` | the one-line conversion target: a writer swaps `save_limen_file` for a keeper ticket per NEW task or status/result transition |
| Beat organ | `scripts/tabularius-organ.py` | thin per-beat wrapper (like `heal-board.py`); `--check`/`--dry-run`; writes the liveness stamp |
| Beat wiring | `scripts/heartbeat-loop.sh` | runs after `heal-board` (fold onto a *healthy* board), before the body's own mutation |
| Projection preservation | `limen.tabularius.preserve_board_projection()` | keeper-owned commit/push of the current `tasks.yaml` projection, under the queue lock, with a temporary git index so a push failure cannot strand the live checkout ahead |
| Writer audit | `scripts/task-writer-audit.py` | reports every remaining legacy direct board writer so the migration burns down explicitly instead of allowing another hidden writer |
| Proprioception | `scripts/organ-health.py` | a TABVLARIVS rung, green when `logs/tabularius-organ-state.json` is fresh |
| Keeper gate | `institutio/governance/parameters.yaml` → `LIMEN_TABVLARIVS` | master kill-switch for the keeper (default ON) |
| Cutover gate | `institutio/governance/parameters.yaml` → `LIMEN_TICKETS_PRODUCE` | flips converted writers from direct-write to producer (default **OFF** — a merge changes nothing live; the flip is the deliberate, revertible cutover) |
| Tests | `cli/tests/test_tabularius.py` | focused tests: end-to-end submit→drain, ordering, quarantine, lock-deferral, collapse-guard, projection preservation, status-ticket validation, **and the producer≡direct-write identity invariant** |

### Safety invariants (each inherited from a shipped precedent)

- **A worker never touches `tasks.yaml`** — `submit_ticket` is an exclusive atomic create (`os.link`).
  No read, no lock, no collapse risk. Preserves the one writer the fleet must never starve
  (`ingest-backlog.py`, which deliberately skipped the lock — tickets are exactly its mechanism).
- **One bad ticket never rejects the batch** — each ticket is applied + validated individually; a bad
  one is quarantined and the rest still land (the `_sanitize_dispatch_logs` tolerate-and-salvage law).
- **The seal is collapse-guarded** — the board is written through `save_limen_file`, so a batch that
  would shrink it is rejected whole and the good board is left intact.
- **Never dead-stop the beat** — if the queue lock is held (a legacy writer mid-migration), the keeper
  defers to the next beat rather than blocking (exactly `heal-board`'s stance).
- **Idempotent no-op while dark** — an empty inbox touches nothing (no lock, no board I/O), which is
  what makes it safe to run every beat before any producer exists.
- **Projection preservation is not a second writer** — the keeper may publish the already-sealed
  `tasks.yaml` projection, but it never edits the board. It commits only `tasks.yaml` from a temporary
  index, pushes before advancing local refs, and leaves other daemon/receipt drift untouched.

## Migration path

`tasks.yaml` is a deploy-trigger path, so every step is additive and reversible until a final flip.

- **Step 1 — SHIPPED (this PR).** The keeper exists and runs every beat. No writer behavior changes,
  so with no producers yet it is a proven no-op. The office is manned; no clerks hand it tickets yet.
- **Step 2 — convert writers to producers, one tier at a time (reversible per tier).**
  Each conversion is behind `LIMEN_TICKETS_PRODUCE` (default OFF), so it merges as a no-op and the
  cutover is a deliberate flip. The parity is *proven*, not assumed: `test_producer_path_matches_
  legacy_direct_write` shows a converted writer produces a board identical to the legacy direct write
  (same tasks, same fields, same order) save for the keeper's added `updated` provenance stamp — so
  every remaining conversion is a mechanical edit against a known-safe template, not surgery.
  1. **Scripts first** (lowest blast radius). **Reference pair converted** (`mine-backlog`,
     `ingest-backlog` — the latter a natural fit, it wanted lock-free): each now calls
     `submit_task_upsert` per new task when `LIMEN_TICKETS_PRODUCE=1`, keeping its read-only dedup so
     it only ever emits brand-new ids. The rest (`generate-backlog`, `generate-revenue-backlog`,
     `generate-organ-backlog`, `generate-positioning`, `discover-value`, `ingest-coverage`) are the
     same one-line swap against the proven template.
  2. **CLI harvest/dispatch result-apply** → emit a `submit_task_status()` ticket instead of mutating the blob.
  3. **MCP server** — replace the raw `yaml.dump` + git-push with a ticket append (removes the worst
     offender: no lock, no atomic write, no collapse-guard, and its own drifted duplicate models).
  4. **FastAPI + Worker endpoints** — enqueue a ticket and return; the keeper projects. This is the
     **website-sensitive** tier — requires green CI + a `web/app` build, and the decision below.
- **Step 3 — flip the source of truth.** Once every writer produces tickets and `materialize --verify`
  proves N consecutive beats of byte-identity, declare the archived event log the truth and
  `tasks.yaml` the derived cache. `heal-board`'s restore-from-HEAD stays as the outer safety net.

## The one genuine human decision (surfaces at Step 2.4, not before)

Routing the **live Cloudflare Worker / FastAPI** through the keeper makes their writes *eventually
consistent* — an API `POST` that used to write synchronously would return before the next beat folds
its ticket. **Decision:** is a bounded async delay acceptable for the live API contract, or must the
API keep a synchronous write path that *also* emits a ticket for reconciliation?
**Recommended default:** synchronous-write-plus-ticket for the live API tier (no contract change),
pure-ticket for the internal fleet. This is the only step gated by the website guardrail; everything
above it is autonomous.

## Recorded remaining work (this doc is the owner)

- [x] Step 2.1 (pattern proven) — `submit_task_upsert` producer API + `LIMEN_TICKETS_PRODUCE` gate +
      the producer≡direct-write identity test; reference pair `mine-backlog` + `ingest-backlog` converted.
- [x] Step 2.1 (creation tier converted + **CUTOVER LIVE**) — the whole task-CREATION tier now
      produces tickets: `generate-backlog`, `generate-revenue-backlog`, `generate-organ-backlog`,
      `discover-value` converted (behind the same gate). Reading the code corrected the remainder list:
      `generate-positioning` and `ingest-coverage` **never write `tasks.yaml`** (obligations / read-only) —
      not writers, so not converted. **`scripts/heartbeat-loop.sh` sets `LIMEN_TICKETS_PRODUCE=1`**, so the
      creation tier is live under the keeper (revertible via `~/.limen.env`). Smoke-proven: a real
      `generate-backlog` run submitted 5 tickets, left the board untouched, and the keeper folded them
      (2→7). The status-mutator tier still writes directly — that is Step 2.2.
- [x] Projection preservation returned to TABVLARIVS — the standalone live-state preserver was removed;
      `scripts/tabularius-organ.py` now calls `preserve_board_projection()` after every drain/no-op pass.
      The focused predicate proves the keeper pushes the board projection without stranding a local commit.
- [x] Creation-writer audit burn-down pass — `auto-scale`, `current-session-fanout`, `insight-route`,
      `append-tasks`, `batch-dispatch`, `corpus-converge`, and `converge-organ` now submit upsert
      tickets instead of directly rewriting the board. The auto-scale workflow runs `tabularius-organ`
      after producing tickets, so CI still commits the projection but the writer is the keeper.
      `scripts/task-writer-audit.py` now reports 22 legacy direct writer calls (down from 29).
- [x] Step 2.2 owner-recorded — the status/result writer tier is no longer an implicit side channel.
      `submit_task_status()` is the keeper API for status/result transitions, and
      `scripts/task-writer-audit.py` now writes the tracked receipt
      `docs/tabularius-writer-audit.md`, with every remaining direct writer mapped to a bounded owner
      packet and zero unclassified rows. This does **not** mean the direct writers are burned down; it
      means the work has named owners, predicates, and receipt targets instead of hiding in the beat.
- [ ] Burn down the legacy writer audit — `scripts/task-writer-audit.py` records the remaining direct
      `save_limen_file`/`atomic_write_text` board writers so each conversion becomes a bounded owner task
      instead of an implicit side channel.
- [ ] Step 2.2A — `TAB-STATUS-ASYNC-HEAL`: convert async reserve/reap/heal transitions to
      `task.status` tickets or keeper-drained status batches without introducing a double-dispatch
      window. Predicate: `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py
      cli/tests/test_async_dispatch.py -q`.
- [ ] Step 2.2B — `TAB-STATUS-DISPATCH-RESULTS`: convert CLI dispatch claim/result application to
      keeper-owned status batches. Predicate: `PYTHONPATH=cli/src python3 -m pytest
      cli/tests/test_tabularius.py -q`.
- [ ] Step 2.2C — `TAB-STATUS-HARVEST-RESULTS`: convert harvest/Jules landing result application to
      `task.status` tickets. Predicate: `PYTHONPATH=cli/src python3 -m pytest
      cli/tests/test_tabularius.py -q`.
- [ ] Step 2.2D — `TAB-ROUTE-RESIDUE-MUTATORS`: convert route, quicken, rewrite-owners, and
      self-improve board patches to keeper-owned tickets. Predicate: `PYTHONPATH=cli/src python3 -m
      pytest cli/tests/test_tabularius.py -q`.
- [ ] Step 2.2E — `TAB-CREATION-FALLBACKS` and `TAB-MAINTENANCE-BOARD-FALLBACKS`: remove/gate legacy
      fallback branches or explicitly move board-maintenance writers into the Tabularius/io allowlist.
      Predicate: `python3 scripts/task-writer-audit.py`.
- [ ] Step 2.2F — `TAB-HUMAN-ATOM-STATUS-WRITERS`: convert dispatch-continuity and routine-freshness
      `needs_human` atom refreshes to keeper-owned status/upsert tickets. Predicate:
      `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q`.
- [ ] Step 2.3 — MCP server → ticket producer (retire the raw write + duplicate models).
- [ ] Step 2.4 — live API/Worker tier (needs the consistency decision above; website-sensitive).
- [ ] Step 3 — flip SSOT to the event log; add an archive→`events.jsonl` compactor + a standing
      `fold(archive) == board` predicate.

See also: `board-is-event-log-projection` (memory), `cli/src/limen/materialize.py`,
`scripts/heal-board.py`, `io.py` (`queue_lock`, `save_limen_file`, the collapse-guard).
