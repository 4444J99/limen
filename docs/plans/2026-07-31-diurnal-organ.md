# 2026-07-31 — DIVRNAL: the day as a loop

Design record for the three-phase daily organ. Mechanics and operating instructions live in
[`docs/diurnal/README.md`](../diurnal/README.md); this file records *why it is shaped this way*
and what the exploration found. Shipped on `feat/diurnal-organ`.

## The ask

A morning briefing, an evening close, a midday check-in — "each of which should be reaching
forward and backwards towards each other for cuts and improvements."

That last clause is the specification. Three independent reports is a cron problem. A closed
loop in which each emission scores the previous one and prunes the next is an instrument that
improves itself from its own misses. Everything below follows from taking it literally.

## What exploration found (three parallel read-only sweeps)

**The repo did not lack briefings — it lacked a spine, and it lacked honesty about freshness.**

- **Six human-facing periodic emitters already existed**, fragmented across four unconnected
  channels: `scripts/opportunity-brief.py` (daily email), `scripts/conducting-report.py` (push),
  `scripts/insight-cadence.py` (markdown tiers), `scripts/health-organ.py` + `scripts/life-organ.py`
  (off-repo), `cli/src/limen/observatory/brief.py` (shipped dark), plus 13 cloud routines
  delivering into GitHub issues. No aggregator, no dated archive. A seventh parallel brief would
  have violated the charter's own "never fork parallel substrate."
- **~198 runtime artifacts had no freshness index.** `logs/organ-health.json` 10d stale,
  `logs/omega.json` 9d, `logs/ticks.jsonl` 4d, `logs/money-view.json` 10d,
  `logs/fleet-status.json` 27d — all presenting as current. The live proof, the same morning:
  `logs/session-orientation.md` reported "Autonomy — PAUSED" after the marker had been removed.
- **The mount point was constrained, not chosen.** `check-sensors.py` check F makes
  `source: [heartbeat]` without a `cadence:` a hard failure; and
  `unreachable-runners-baseline.txt` records that `metabolize.sh` is invoked by no tracked plist,
  workflow, or script — so a `metabolize`-only sensor is declared and never runs. Registry cadence
  is beat-modulo only, so wall-clock gating had to live inside the script
  (`scripts/insight-cadence.py` precedent).

## Decisions (operator, in session)

| Question | Chosen |
|---|---|
| Where a cut lands | Auto-apply its **own** template cuts with a receipt; fleet-wide cuts open a PR |
| Delivery | Morning + midday **push**; evening **persists** as dated markdown |
| Existing emitters | **Compose and cite** — never re-render, never absorb |
| Morning shape | **Full dashboard** |

"Full dashboard" was chosen against my minimalist recommendation, and it turned out to be the
correct starting state: a loop that prunes by measured noop needs something to measure. Start
minimal and there is no evidence about what is missing and nothing to cut. The dashboard is the
block of marble; the evening carves it.

## The two doctrines, both inherited rather than invented

Both come from `institutio/governance/ideal-forms.yaml` — *"NO ROW MAY CARRY A DISTANCE OR A
STATUS. There is no field to lie in."*

1. **Freshness is derived, never asserted.** A stale *cache* may hold a wrong value → withhold it
   and name the age. A stale *registry* holds a frozen but still-true value → report it and mark
   it `FROZEN`. (This distinction was missed in the first draft; withholding the board because
   `tasks.yaml` was a day old is over-correction, since the counts remain true.)
2. **You cannot prune what you cannot score.** `metric: null` ⟹ `cuttable: false`, enforced by
   check C of `scripts/check-diurnal.py`. A cuttable section with no metric would accrue an
   unfalsifiable noop streak and delete itself on no evidence at all — precisely the failure a
   self-pruning artifact must be structurally unable to commit.

The unifying move: **a claim and a section score are one measurement.** A claim is "section X's
metric will fall below N today." Evening re-reads it — decreased `held`, unchanged `noop`,
increased `missed` — and a noop claim *is* a noop section. That is what makes the cut
evidence-based rather than a matter of taste, and it removed the need for per-section
`acted_probe` shell commands that an earlier draft carried.

## Two defects the organ found in its own first run

- **A 6× over-count it caught itself.** The first dry-run printed `needs_human 702` on one line
  and `needs_human_count 109` on another, from the same page. Task status sits at indent 2 in
  `tasks.yaml`, but `dispatch_log` entries carry their **own** `status:` at indent 4, so a flat
  grep conflated task states with per-dispatch events. Fixed by anchoring, plus a permanent
  cross-check that prints `⚠ COUNT DISAGREEMENT` when the two independent derivations diverge —
  the page reports the conflict instead of silently picking a favourite. (This is the charter's
  Data Grounding rule working as intended: a count that disagrees with surrounding evidence is a
  bug in your own input until proven otherwise.)
- **Blocks landed in write order, not chronological order.** A phase run out of sequence left the
  day reading morning → evening → midday. The blocks are the record of a day; a record that
  reorders itself by write time is not a record.

## Deliberately left open

- **`calendar` is declared `ABSENT` with a written reason, not silently omitted.** No calendar
  state exists on disk anywhere in the estate — no `.ics`, no CalDAV client, no cached mirror —
  only session-scoped MCP tools that no script, beat, or artifact is wired to. Making it a real
  section is a lever, not a render fix.
- **Fleet-wide cuts are proposals only.** The evening names a stale producer; landing the retire
  takes a PR via `scripts/ship-docs.sh`.
- **The cut loop has a 5-engaged-day runway before it can fire at all**, which is the intended
  observation window — the first cuts should be reviewed rather than assumed correct.
