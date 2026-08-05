# 2026-08-02 — DIVRNAL: closing the loop the organ opens

Second design record for the daily organ. The first —
[`2026-07-31-diurnal-organ.md`](2026-07-31-diurnal-organ.md) — records why the organ is shaped the
way it is. This one records what was found once it had actually run for three days, which is a
different kind of finding: not "does the design hold" but "does the loop close."

It did not. Three defects, all one species.

## What was true on 2026-08-02

The organ works end to end, unattended:

| Evidence | Value |
|---|---|
| Emissions on disk | `2026-07-31.md`, `2026-08-01.md`, `2026-08-02.md`, `INDEX.md` |
| Phases fired | 7 ledger rows — morning/midday/evening × 2 days, morning on day 3 |
| Scoring | 07-31 evening: held 1 · missed 1 · noop 2; streaks recorded |
| Cuts | 3 stale producers proposed |
| Shipping | armed by default, fired, 4 receipts in `shipped.json` |

It ran *while autonomy was paused* — sensors sit above the pause gate, so the window pause never
stopped DIVRNAL. The first plan's α premise ("the organ cannot reach the organism") was resolved by
that arc and is not the problem here.

**None of it had landed.** `git ls-files docs/diurnal/` returned exactly `2026-07-31.md` and
`README.md`. The 07-31 page was tracked but its evening block was uncommitted; 08-01, 08-02 and
`INDEX.md` were `??`.

## The species

> A value that is computed or declared, and then consumed by nothing.

That is the disease the first arc named one layer up — `resume_predicate` written as prose, which
`maintenance_blocker()` only ever *reported*. It recurred three times inside the organ built to
detect it. Worth stating plainly, because the recurrence is the finding: this is structural, not
incidental, and it is the argument for the extensible half.

### 1 · The receipt recorded the handoff, not the landing

`ship-docs.sh` self-merges only if `merge-policy.sh` clears within its own wait. Otherwise it
exits 2 and hands the PR to *"the beat's merge rung, per the charter"* — `drain.sh`, called at
`scripts/heartbeat-loop.sh:466`, **113 lines below the paused branch's `continue` at line 353.**
Autonomy had been window-paused since 2026-07-22, so the named owner had not run once.

The result was five OPEN, CLEARED, non-deploy, organ-authored PRs across three days
(#1750–#1754) while `shipped.json` reported every page published. `shipped.json` stored
`{rel: digest}` — *that* a page was handed off, never *where it went* — so nothing could ask
whether the handoff completed.

Three of the five were the same day. Every phase rewrites the page and regenerates `INDEX.md`, so
digest-keyed re-ship — correct behavior *when pages land* — opened three strictly nested PRs for
2026-08-01 (`morning` ⊂ `morning+midday` ⊂ `morning+midday+evening`).

**Fixed in #1758.** The receipt carries the PR number; `reap_shipped()` merges the organ's own
still-open PRs through `merge-policy.sh` + `await-pr.sh`. Today's page ships at evening only, when
it is complete; earlier days still ship from any phase so a crashed evening is caught next morning.

Deliberately *not* a general un-pausing — scope is PRs this organ opened, class is one
`ship-docs.sh` refuses to make deploy-triggering, authority is the pause **marker** exactly as the
shipping path already read it, and the work is bounded per run with the one sanctioned waiter.

### 2 · The runway was counted from a key no writer produced

`done-diurnal.sh` gated the cut loop on `rec.get("engaged_days", 0)`. `grep -rn engaged_days`
matched that line and nothing else. No writer existed anywhere in the estate.

The `.get` default is what made it invisible: it reported `only 0 engaged day(s) scored`, which is
indistinguishable from an honest early runway. A `KeyError` would have surfaced it on day one.

The judgment was being computed — `emit()` calls `engaged_today(root)`, hands it to `apply_cuts()`,
and drops it. The ledger row appended twelve lines later carried `ts`, `phase`, `sections`, `cuts`
and not `engaged`.

**Fixed in #1756.** `engaged` rides the evening ledger row, written conditionally so its absence on
a morning row still means "this phase does not score" rather than "this day earned nothing". The
runway counts distinct dates with an engaged evening; rows predating the field re-derive from git.

Counting evening *emissions* would have been wrong, and the live data proved it: 2026-08-01 ran a
full evening pass with zero commits, and the organ itself marked the day `UNSCORED (no commits) —
no streak moved, no cut fired`. Two evening rows, one engaged day. An away-week would otherwise
manufacture a runway and cut sections on no evidence.

### 3 · The predicate blocked on a claim the organ had disproved

`done-diurnal.sh` check 2 hard-failed with *"autonomy mode is paused — the beat cannot run the
diurnal sensor"*. Three days of unattended emissions disprove it.

It was also the wrong shape. The pause has a registry owner, and the charter's pattern for an owned
item is the `!` residual the script already emits for `organs.yaml` — an item with an owner is
homed, not dangling.

**Fixed in #1759.** Check 2 asserts what DIVRNAL's doneness requires: the sensor fired today, from
`state.json`'s `last_run`. Strictly sharper — the old check would have passed a green autonomy mode
while the organ sat silent for a week, which it could not detect at all.

## What landed

| PR | Concern | State at writing |
|---|---|---|
| #1750, #1757 | the backlog — three days of pages plus a regenerated INDEX | merged; all four files tracked |
| #1751–#1754 | strictly nested duplicates of the same day | closed as superseded |
| #1756 | the runway counter reads evidence | open, CI green-pending |
| #1758 | the organ lands its own pages; evening-only shipping | open, CI green-pending |
| #1759 | the predicate measures DIVRNAL, not the estate | open, CI green-pending |

#1756 and #1758 add files under `cli/tests/`, which the GATES registry classifies as a
deploy-trigger path — so both correctly demand the full rollup before merge, even though a test
file cannot deploy anything. Classification is by path prefix and errs toward caution; that is the
website guardrail working, not a snag.

## Ω

`scripts/done-diurnal.sh` once the three land — one `✗` remaining:

```
✓ registry coherent — 22 section(s), 10 protected
✓ the beat's diurnal sensor fired today
! autonomy mode is paused — owned by the governor's resume predicate, not by this organ
✓ live checkout is current with origin/main
✓ scripts/_root.py is the single root predicate, imported by both consumers
✓ a worktree is correctly refused as the organism
✓ today's emission exists
✓ and it is git-tracked
✗ only 1 engaged day(s) scored — a cut cannot yet fire on evidence (need 5)
! diurnal residual open — owner of record: organs.yaml
```

The runway is **time, not work.** It needs four more days on which commits actually happen. It
cannot be accelerated and must not be faked — faking it is how you cut the wrong thing.

## Extensible

Unchanged in shape from the first plan and now correctly gated. The machinery — *declare a metric
in a registry, emit a falsifiable claim, re-probe it mid-flight, score it held/missed/noop, prune
what never moves* — lifts out of `diurnal.py` so GATES, SENSORS, PARAMETERS and IDEAL-FORMS can
each be scored. `IDEAL-FORMS-LEDGER.md`'s hand-maintained **Distance** field is its first customer.

**Do not start it until the runway reads 5.** #1756 makes that number honest for the first time —
before it, the count read 0 and always would have, so "wait for five days" was itself
unfalsifiable.

## The generalization worth naming

The α finding is not confined to this organ. **The only automatic merge rung in the estate sits
below a pause gate that has held for eleven days.** Every merge since 2026-07-22 has required a
human or a session in the loop; ~100 PRs are open. #1758 fixes it for one class of one organ.

Whether the beat should drain provably-non-deploy PRs generally is a real question and a **separate
decision** — deliberately not folded in here, because it is an authority change and this was not.
