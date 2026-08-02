# 2026-08-02 — DIVRNAL: a declaration is worth what its consumer does with it

Third design record for the daily organ, same day as the second.
[`2026-07-31-diurnal-organ.md`](2026-07-31-diurnal-organ.md) records why the organ is shaped the
way it is. [`2026-08-02-diurnal-loop-closure.md`](2026-08-02-diurnal-loop-closure.md) records what
three days of running found: the loop the organ opened did not close, three times, all one species —
*a value that is computed or declared, and then consumed by nothing.*

Those three landed. This one records what was found when the same question was asked one level out,
and the answer was: **the species did not get fixed, it got promoted.**

## What was true after the loop closed

The organ emits, scores, ships, and lands its own pages. `done-diurnal.sh` stood at one `✗` — the
observation runway — and that one is time, not work. Every other check was green.

So the next question was not "what is broken" but "what does the organ still only *narrate*."

## Where the species went

Not inside `diurnal.py` any more. Into the relationship between what the registries **declare** and
what any consumer actually **does with the declaration**. Four instances, found in one morning.

### 1 · `cuttable: true` on 11 sections, reaching 3

`institutio/governance/diurnal.yaml` declares `cuttable: true` on eleven sections. On the live root,
`logs/diurnal/section-scores.json` held **three**. Three independent leaks in one function,
producing one symptom — invisible, because a subset looks exactly like a full set from outside:

| Leak | Mechanism |
|---|---|
| a display cap doing governance | `build_claims()` `break`ed at a claim cap written to keep the *briefing* short. The claim list is also the score list; the score list is what accrues noop streaks; noop streaks are the only thing that fires a cut. |
| staleness as a shield | a stale section is skipped, so a section reading a dead source never scored, never accrued, and could never be cut — over the six sections most worth examining, while the four that worked were the only candidates. |
| half a rule implemented | `check-diurnal.py`'s load-bearing rule (`cuttable ⟹ metric AND acted_when`) admits `metric_changed`; `budget.runs_remaining` and `revenue.received_count` use it precisely because a *fall* is bad news there. Both passed the rule and were structurally unclaimable. |

A fourth surfaced only from **driving** the fix, not from reading it: a fresh, cuttable section
pinned at its metric floor emits no claim (nothing falls below zero) and is not stale — so it
carried a record with two zero counters and read as *reachable* while remaining uncuttable forever.
The first version of the reach check would have reported that green.

**Landed in #1766.** Every cuttable section now advances exactly one counter per engaged evening:

| counter | condition | authority |
|---|---|---|
| `noop_streak` | claimed, did not move | the evening may **CUT** |
| `blind_streak` | source stale | **PROPOSE** — repair the producer or retire the section |
| `dormant_streak` | fresh, metric at its floor | **PROPOSE** — confirm the quiet is real or retire |

Only the first auto-cuts. A dead producer and a healthy zero (`mail.owed == 0` is good news) are
indistinguishable from inside the organ, and a cut section auto-restores only on an exception —
never on a value change — so cutting a healthy zero would hide the row the day it finally matters.

`done-diurnal.sh` check 7b holds the declaration to its consumer: **3/11 against the live root,
11/11 against a root driven through five engaged days.**

### 2 · The proposals were narration

`apply_cuts()` has always been able to say *"this producer is dead — retire or repair it."* Saying it
was all that ever happened: the list was built, put on `ctx`, printed into the page, never read back.
No file, no dedup, no age, no owner. The organ had printed the same three proposals on **every**
evening page since 2026-07-31 while their sources aged — `logs/omega.json` 10.6d,
`logs/routine-freshness.json` 22.1d, `state/aug1/revenue-received.json` 36.9d.

Six of sixteen rendered sections were reading dead sources. The organ reported it correctly, daily,
to nothing.

**Landed in #1768.** `logs/diurnal/proposals.json` — one record per `what`, carrying `first_seen`
(the clock, never reset by re-proposing), `last_seen`, `reason`, and a `disposition` a human sets by
hand. `done-diurnal.sh` check 7c goes red past `LIMEN_DIURNAL_PROPOSAL_MAX_AGE_DAYS`.

This grants the organ **no** authority it did not have. "Retire or repair" is a judgment it cannot
make, and the retire-PR remains the hand step `organs.yaml` declares and owns — that residual is
unchanged and correctly open. What changed is that the judgment is now owed on a date, and a red
check is what owes it. A proposal that stops recurring auto-resolves, so the gate can never stay red
on a problem already fixed; only engaged evenings write the book, so a week away can neither
manufacture a proposal nor resolve one by failing to observe it.

### 3 · The estate's most important number, off by 15×

`IF-AMALGAMATION` — the ideal form whose whole subject is open-PR debt — carried `probe: null`. Its
reason was exact, not lazy:

> *"The ideal is a monotonic TREND, not a level, and a level is the only thing measurable in one
> shot… A real probe needs a committed series, so the debt-trend recorder is this row's next form."*

**The series was already committed.** `gitvs.py` writes `open_pr_count` into
`docs/github-pr-debt-ledger.json`, every write is a commit, and five observations had been sitting
in `git log` for eleven days:

```
2026-07-22  1059
2026-07-23  1111   +52
2026-07-24  1115   +4
2026-07-24  1117   +2
2026-07-25  1164   +47
```

The ideal's word is *"monotonically **down**."* The measured trend is **+105 in three days**. The
ledger's hand-written Distance said *"75 open PRs (2026-06-25)"* and had said it for 38 days.

Nothing had to be built. Something had to be **read**.

**Landed in #1770** as `scripts/pr-debt-trend.py`. The half a naive trend predicate gets wrong is
encoded deliberately: **staleness is not at-ideal.** A debt series nobody records is not a debt trend
that improved — it is a debt trend nobody is measuring, and debt accretes fastest when nothing is
watching. Without that clause the probe would go green the moment the producer died.

`environment: host`, because a shallow CI checkout truncates git history and this must never read
"at ideal" because the evidence was clipped away.

### 4 · The registry said there was no field to lie in. There was.

`ideal-forms.yaml`'s header states the rule — *"NO ROW MAY CARRY A DISTANCE OR A STATUS. There is no
field to lie in."* Check A enforces it on the **registry**, which is the half nobody was writing
numbers in. Check A never reads the doc, and the doc is a prose ledger with a `- **Distance:**`
bullet per entry. Check D held `Status:` to a live measurement and never looked one bullet up.

**Check F, also in #1770.** A row *with* a probe may not write a Distance by hand; it must point at
`--measure`. Twelve rows carried one and are converted. Narrative is not the problem and keeps its
place on an `**Evidence:**` line; only the number has to be derived, and only where a command can
supply it — a `probe: null` row has no derivation, so its prose is all it has and check E already
counts those loudly. A probed row with *no* Distance line fails too: deleting the field is not the
fix, because a reader must still be told where the number comes from.

## What landed

| PR | Concern | State at writing |
|---|---|---|
| #1766 | the cut reaches every cuttable section — score all, render capped; blind + dormant streaks; check 7b | **merged** 14:57Z |
| #1770 | IF-AMALGAMATION's probe + check F | **merged** 15:05Z |
| #1768 | proposals get a durable home and a dated gate — `proposals.json`, check 7c | rebased onto #1766, queued |
| #1772 | the trend predicate named the wrong producer in its own escalation | opened |

#1772 is this record's own subject arriving one turn late, and it belongs here rather than in a
quiet patch. The escalation line in `pr-debt-trend.py` was written from the hypothesis below and
never revisited after the hypothesis was tested and **disproved**, so the file whose entire subject
is a number that went stale because nobody checked its producer shipped pointing at the wrong
producer. The test that should have caught it was written not to:

```python
assert "gitvs.py reconcile" in out or "gitvs.py" in out, "the failure must name its producer"
```

The `or` clause accepts any string containing `gitvs.py`. It was added to keep the assertion from
being brittle, and permissiveness is exactly how a wrong value survives review — a check declaring
an intent its predicate does not enforce, which is the species one more time, in a test.

#1766 and #1768 touch adjacent regions of `emit()` and insert at the same anchors in
`parameters.yaml` and `done-diurnal.sh`; they were scratch-merged and driven together before
either was proposed for merge, which is how the composed behaviour below was verified.

## The finding under the finding

The working hypothesis going in was that the debt ledger's producer times out on its beat bound
(`cadence: 8`, `timeout: 120`, `severity: silent` — a 154-page GitHub reconcile in 120 seconds
seemed doubtful).

**It does not.** `gitvs.py reconcile` returns in **0.1 seconds**, exit 0, and never touches the
ledger — it is a dry effector report. The actual writer is `gitvs.py pr-debt`, and it is wired to
**nothing**: no sensor, no gate, no beat rung, no workflow.

Its owner of record is `GITVS-UNCAPPED-PR-DEBT-0715` — the task the diurnal morning page prints as
the board's *critical next action*, asking for a predicate **that already exists**.

Not wired in this arc: 154 PR pages of GitHub API per beat is a real recurring cost and a separate
decision. It is now named in the ledger entry instead of being silent, and the probe fails loudly on
the staleness it causes.

## Composed behaviour, driven

A scratch merge of #1766 and #1768, run through five engaged days against copies of the live
sources with two producers aged past a month:

```
logs/omega.json                since=2026-08-02   (fleet-wide: source stale)
logs/routine-freshness.json    since=2026-08-02
tasks.yaml                     since=2026-08-02
section:board                  since=2026-08-02   (blind: its source never went fresh)
section:omega                  since=2026-08-02
section:routines               since=2026-08-02
section:ideal_forms            since=2026-08-02   (dormant: fresh, but at its floor)
section:opportunity            since=2026-08-02
  (8 tracked)

✓ every cuttable section is scored — the cut pool is the whole 11, not a subset
✓ every proposal is inside its 14-day window (8 open, 8 tracked)
```

The rehearsal earned its keep: a careless conflict resolution swallowed a heredoc terminator and
fused check 7b's Python block into check 7c's shell lines. It surfaced as `NameError: name
'python3' is not defined` — a defect that exists only in the merge, in neither branch, and that
running each branch's own tests could not have found.

## What did not change

- **The autonomy pause.** Filed and owned (`logs/autonomy-policy.json` + `scripts/autonomy-governor.py`).
- **The estate's PR debt.** Draining it is a mass merge — an explicitly human-gated lever.
- **`organs.yaml`'s residual.** The retire-PR is still a hand step. It is now dated rather than
  automated, which is the correct direction: the organ gained a clock, not a delete.

## Ω

`done-diurnal.sh` exits 0 when the runway reads 5. Engaged days so far: 2026-07-31, and today.
**Earliest Ω is the evening of 2026-08-05**, and only if commits actually happen on 08-03, 08-04 and
08-05. It cannot be accelerated and must not be faked — faking it is how you cut the wrong thing.

Two of the new checks go red the moment they land. That is correct: they measure conditions that
were true already and previously unmeasurable.

## Extensible — still gated, now sharper

The lift is unchanged in shape: the claim / re-probe / score / cut machinery comes out of
`diurnal.py` so GATES, SENSORS, PARAMETERS and IDEAL-FORMS can each be scored. What this arc
established is **which half is missing**. `ideal-forms.yaml` already has the *spatial* half — a probe
contract, a `--measure` runner, and now checks D and F holding both prose fields to it. What it
lacks is the *temporal* half: nothing claims a distance will decrease, re-probes it, scores it
held/missed/noop, or prunes an ideal that never moves. That is exactly `build_claims()` /
`score_claims()` / `apply_cuts()` over a different row shape.

**Do not start it until the runway reads 5.**

## The generalization

Every defect in both records is one sentence: **a declaration is worth exactly what its consumer
does with it, and nothing in a registry can tell you what that is.**

`cuttable: true` on eleven rows, consumed for three. `acted_when: metric_changed` on two rows,
consumed by none. `probe: null` with a reason that named data already in git. A `Distance:` field in
the one place its own prohibition wasn't looking. In every case the registry was correct, the
predicate that validated the registry was correct, and the number was wrong — because *declared* and
*consumed* are two different facts and only one of them was ever checked.

The three new checks (7b, 7c, F) are all the same shape: hold a declaration to its actual consumer,
so under-consumption is red rather than invisible.

And #1772 is the corollary, learned the hard way in the same afternoon: **an assertion written to
be permissive is a declaration with no consumer either.** `assert A or B` where `B` subsumes `A`
does not check `A`. The test read as coverage and enforced nothing, which is how the escalation
shipped naming a command that does not do the thing. Prefer an assertion that can fail.
