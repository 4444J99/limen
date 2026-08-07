# Corpus drain pilot: point the atomizer at the real stores, refresh the cursor, run one bounded disposition batch

Issue: #1957
PR: (pending)

## Context

Successor objective 3 of the prima-materia reconciliation (issue #1934), now opened as
its own chain per that plan's own ruling. The prompt-atom pipeline is built and
populated — 741,827 ask atoms across 164,048 lineages, an 862 MB private event journal,
a redacted public projection — and it is failing on exactly two axes:

- **Coverage.** `prompt-lifecycle-ledger.py`'s `LOCAL_SOURCES` read `$HOME` provider
  dirs, and `$HOME` has been evacuated: `~/.claude/projects` holds 0 jsonl while
  `.agent-runtime/claude/projects` holds 520 files / 529 MB; `~/.codex/sessions` holds
  only 2026-07-17→07-27 while `.agent-runtime/codex/sessions` carries 433 files
  through 2026-08; `~/.gemini` holds 422 chat jsonl + 388 antigravity conversation DBs
  (~570 MB) against a `corpora.yaml` vacuum that says "No Gemini corpus has ever been
  imported" — and the shipped glob only matches `*agy*`-named projects. Newest source
  event in the ledger: 2026-07-08.
- **Drain.** 0 of 741,827 atoms assessed; `Validation: FAIL`; 21,652 pending files;
  `EVERY-ASK-LEDGER.md` reports a month-stale horizon.

`SOURCE_HOME_OVERRIDE` exists (prompt-atom-ledger.py `load_lifecycle_module`) but
rebases paths **relative-verbatim** (`override/.claude/...`), while the runtime tree
drops the dot prefixes (`claude/`, `codex/`) — so the override cannot point at
`.agent-runtime` directly.

## Resolved design decisions

- **D1 — Coverage bridge = a shim home of symlinks, then a durable source-root
  widening.** The pilot creates a gitignored shim dir (under
  `.limen-private/session-corpus/lifecycle/source-home-shim/`) with
  `.claude → <live>/.agent-runtime/claude`, `.codex → <live>/.agent-runtime/codex`,
  `.gemini → ~/.gemini`, and runs the atomizer with `SOURCE_HOME_OVERRIDE=<shim>`.
  The shim is regenerable machinery, documented here (the tracked artifact is this
  plan + the eventual code change); the durable fix — runtime roots and the widened
  gemini glob (`*/chats/*.jsonl`, not just `*agy*`) declared in `LOCAL_SOURCES`
  itself — is this chain's implementing PR. A default no-override scan still covers
  the real `~/.codex`, so nothing regresses.
- **D2 — Bounded, always.** Every scan runs with the shipped ceilings (`--max-files`,
  byte/event/protocol ceilings; `--unbounded` is never used on the 16 GB host). The
  disposition batch obeys `docs/prompt-corpus-policy.json`
  (`reclassification.max_occurrences_per_run: 5`; batch cadence). Idempotence per the
  2026-07-25 iceberg plan: re-running over an unchanged corpus is byte-identical.
- **D3 — Declarations land with their first real import, not before.**
  `corpora.yaml`'s `gemini-history-memory` / `copilot-history-memory` move from
  `unpopulated` to declared corpora rows in the same PR whose scan actually ingests
  them — a registry that says "populated" ahead of the import is the false-green the
  corpus resolver's own history warns about (three relocations, two fail-opens).
- **D4 — Privacy constraints are inherited, not re-derived.** `check-atom-homing.py`
  check D (no atom statement in the public tree); `redacted: false` ⇒ never leaves
  its store; FERPA-flagged `composition-1-2` excluded from any shared corpus;
  homing is distillation — counts, generalizations, IDs cross into public, never
  statements. Nothing in `.agent-runtime`, the atom ledger, or any provider store is
  deleted or moved by this pilot (intake copies, never transfers).
- **D5 — The cursor refresh is part of the pilot, not an afterthought** — the
  month-stale horizon in `EVERY-ASK-LEDGER.md` is the visible symptom; `--check-cursor`
  before and after brackets the run.

## Steps

1. Shim home + `SOURCE_HOME_OVERRIDE` bounded probe:
   `python3 scripts/prompt-atom-ledger.py --scan --write --max-files <default ceiling>`
   with the shim; `--check-cursor` before/after; capture counts (pending files,
   newest event) as the receipt.
2. Implementing PR: widen `LOCAL_SOURCES` (runtime claude/codex roots, full gemini
   chats glob, antigravity conversation DBs via the existing `agy-conversation-v1`
   adapter) so the shim becomes unnecessary; `corpora.yaml` rows per D3;
   `check-corpora.py` + `check-atom-homing.py` green.
3. One bounded disposition batch through the policy axis; `docs/prompt-atom-ledger.md`
   regenerated (redacted projection) showing assessed > 0 and a current horizon.
4. Stamp this plan's `PR:` via `scripts/session-plan.py close corpus-drain-pilot --pr <N>`.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** (a) An unbounded scan
  thrashing the 16 GB host — D2 forbids `--unbounded`; runs are backgrounded and
  serialized. (b) Transcript text leaking into a tracked file — D4's check D is the
  executable guard; only redacted projections ship. (c) The scan contending with the
  beat's corpus organs — the atomizer is the single writer of its own journal;
  `corpus-feed.py` only counts; no shared write path. (d) Declaring gemini populated
  before it is — D3 ties the registry row to the importing PR. (e) A partial scan
  read as a full one — the ledger's own `Source scope: partial:all` field plus
  `--check-cursor` receipts state the denominator every time (Data Grounding).

## Verification

- `python3 scripts/prompt-atom-ledger.py --check` (journal/projection convergence)
- `python3 scripts/prompt-atom-ledger.py --check-cursor` (cursor coherence)
- `python3 scripts/check-corpora.py` and `python3 scripts/check-atom-homing.py`
- `docs/prompt-atom-ledger.md` shows: newest source event ≥ 2026-08, assessed > 0
- `bash scripts/verify-scoped.sh` on the implementing PR
