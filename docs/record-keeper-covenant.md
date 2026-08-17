# Record-Keeper Covenant

A **testament file** is a durable record that accrues truth across sessions and has exactly
one legitimate author: **TABVLARIVS**, the record keeper. The memory dir (`MEMORY.md` plus its
per-topic atoms) and the board (`tasks.yaml`) are the two testament surfaces. When every
session may write a testament directly, the file races itself and the record drifts — the
memory dir already has as many writers as there are sessions, because the harness auto-writes
`MEMORY.md` and its atoms at the end of each one.

The covenant makes the keeper the **sole writer** and gives every other session a **lane**: a
ticket it submits, which the keeper's beat drain folds in. The single-writer law is only half
of it — the other half is **lane-not-wall**:

> A blocked write must have somewhere to go. Build the lane before the wall.

So the lane (the ticket path) lands and is proven green *before* the write-guard hook (the
wall) is armed — no truth a session needs to record is ever lost. And nothing arms by merge:
the write-guard is armed only by the operator's hand (`enforcement.armed: false` in the
registry until then). The checker, `scripts/check-covenant.py`, only **warns** while a lane is
unbuilt or a guard is unarmed, so every covenant PR merges as a green no-op.

The checked source of truth is [`institutio/governance/covenant.yaml`](../institutio/governance/covenant.yaml)
(schema, sole writer, lane, enforcement ids) and [`scripts/covenant.py`](../scripts/covenant.py)
(the shared loader + the out-of-repo memory-dir resolver, mirrored exactly from
`scripts/evocator.py`). `scripts/check-covenant.py` verifies the two do not drift, and
`scripts/verify-whole.sh` runs it so a future testament surface cannot silently escape the
covenant.

## Covenanted surfaces

### memory — the memory dir

- **path_env:** `LIMEN_MEMORY_DIR` (out-of-repo; index `MEMORY.md`, atoms `*.md`). The checker
  resolves it exactly as `evocator.py` does: the env override, else
  `~/.claude/projects/<workspace-slug>/memory`. It is out-of-repo, so CI never fails for its
  absence — the checker runs schema-only when the dir is not present.
- **sole writer:** `tabularius` (keeper env `LIMEN_MEMORIA`).
- **lane submit command:**
  `python3 scripts/memory-ticket.py --slug <s> --title <t> --desc <d> [--body-file f] [--star]`
  — pools a ticket under `<memdir>/.covenant-inbox`; the keeper folds it in with
  `scripts/tabularius-organ.py memory pass (LIMEN_MEMORIA=1)`.
- **enforcement:** hook `scripts/hooks/covenant-write-guard.sh` (gate `check-covenant`, sensor
  `covenant-attribution`) — **unarmed** until the operator arms it (PR 6). The engine
  (`cli/src/limen/memoria.py`) and the submit CLI (`scripts/memory-ticket.py`) are the lane and
  land first.
- **verify-only:** `scripts/evocator.py` reads the memory dir to keep it honest and never
  writes it — tolerated as read-only.

### board — `tasks.yaml`

- **path:** `tasks.yaml` (in-repo, the live task queue SSOT).
- **sole writer:** `tabularius`.
- **lane submit command:** `limen.tabularius.submit_task_upsert / submit_task_status` — pools a
  ticket under `logs/tickets/inbox`; the keeper folds it in with
  `scripts/tabularius-organ.py board pass`.
- **enforcement:** the board's teeth are the AST writer audit
  [`scripts/task-writer-audit.py`](../scripts/task-writer-audit.py) (gate `task-writer-audit`) —
  the covenant delegates to it and does **not** duplicate the board scan. Migration debt is
  tracked in [`docs/tabularius-writer-audit.md`](tabularius-writer-audit.md); the remaining
  legacy direct-writer packets are being burned down.

## Deliberate exclusions

Not every durable record is a testament under this covenant. The following are excluded on
purpose — each with one reason, and each a candidate for later enrolment (one surface per PR):

- **`docs/branch-hygiene.md`** — sole writer `scripts/reap-branches.py`. Already single-script;
  no competing sessions.
- **`organs/financial/*`** (`STATUS.md`, `cashflow.md`) — sole writer `scripts/financial-organ.py`.
  Generated ledger; no session writes it.
- **`studium/ledger/*`** — sole writer `scripts/studium.py`. Per-run study ledger.
- **`logs/overnight-watch.md`** — sole writer `scripts/overnight-watch.py`. Beat-log surface.
- **`docs/prompt-atom-ledger.md` + `docs/prompt-authority-seal.json`** — sole writer
  `scripts/prompt-atom-ledger.py`. Already single-script; candidate for later enrolment.
- **`face-ownership.json`** — a peer constitution, not a keeper testament.
- **`his-hand-levers.json`** — the to-human queue; sessions legitimately append their owed atoms.
- **`censor/precedents.jsonl`** — an append-only log written from multiple branches by design.
- **`organ-ladder.json`, `pillars.yaml`** — already guarded by their own registry gates.

The organ ledgers above are sole-script writers already, so they carry no cross-session race
today; enrolling them is a tidiness upgrade, not a leak fix, and each lands on its own PR.

## Arming sequence

For each covenanted surface the order is fixed and never inverted:

1. **Lane proven.** The submit CLI + the keeper drain land and the checker is green
   (`scripts/check-covenant.py` passes with the lane present).
2. **Wall armed by the operator** — the write-guard hook is wired into `.claude/settings.json`
   under a `PreToolUse` `Write|Edit` matcher, and `enforcement.armed` flips to `true`. This is a
   human-gated act (PR 6): **never by merge.** Once armed, the checker requires the hook and its
   settings wiring to exist, and a direct write to a testament surface is refused with the lane
   cited.
